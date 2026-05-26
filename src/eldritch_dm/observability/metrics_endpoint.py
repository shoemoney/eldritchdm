"""Prometheus /metrics endpoint (Phase 13 / MON-01 / D-84, R-13-01-c/d).

Opt-in scrape target at ``:9090/metrics`` exposing the 5 D-85 KPIs as
Prometheus gauges plus an ``eldritch_smart_driver_decisions_total`` counter
labelled by driver_path + fallback_reason.

Lazy-import discipline:
  - ``prometheus_client`` is imported only inside ``start_metrics_endpoint()``
    after the env gate check. The lazy-import canary in
    ``tests/observability/test_metrics_lazy_import.py`` asserts that no
    ``prometheus_client`` symbol enters ``sys.modules`` when the env gate is
    off.
  - The decision-counter increment is wired via
    ``SpanBuffer.add_post_write_observer()`` (the IoC hook from
    ``span_buffer.py``). The closure imports prometheus_client once when the
    endpoint starts; ``span_buffer.py`` itself never references the lib.

Registry isolation:
  - Each call to ``start_metrics_endpoint()`` creates its own
    ``CollectorRegistry`` so test fixtures can spin endpoints up and down
    without the process-global ``prometheus_client.REGISTRY`` accumulating
    "duplicated timeseries" errors.

Port:
  - Default ``9090``. Override via ``OBSERVABILITY_METRICS_PORT`` env or the
    ``port`` argument. ``port=0`` requests an ephemeral port (tests).
"""
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import os
import socket
import threading

from eldritch_dm.logging import get_logger
from eldritch_dm.observability.kpi import get_cached_kpis
from eldritch_dm.observability.span_buffer import BufferRow, init_buffer

log = get_logger(__name__)

#: Module-level state — the endpoint is a process-singleton.
_HANDLE: _MetricsEndpointHandle | None = None
_HANDLE_LOCK = threading.Lock()


# ── Env gate ────────────────────────────────────────────────────────────────


def is_metrics_endpoint_enabled() -> bool:
    """Return True iff ``OBSERVABILITY_METRICS_ENDPOINT`` is a truthy string."""
    return os.environ.get("OBSERVABILITY_METRICS_ENDPOINT", "false").lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


# ── Handle ──────────────────────────────────────────────────────────────────


class _MetricsEndpointHandle:
    """Bundle of (gauges, counter, registry, http server, refresh timer)."""

    def __init__(self, *, port: int, refresh_seconds: float = 5.0):
        # Lazy import — only paid when the endpoint is actually starting.
        from prometheus_client import CollectorRegistry, Counter, Gauge  # noqa: PLC0415

        self._registry = CollectorRegistry()
        self._refresh_seconds = refresh_seconds
        self._stop_event = threading.Event()

        # ── 5 KPI gauges (D-85) ──
        self._gauges = {
            "latency_p99_ms": Gauge(
                "eldritch_smart_driver_latency_p99_ms",
                "P99 latency over rolling 5-min decision window",
                registry=self._registry,
            ),
            "success_rate": Gauge(
                "eldritch_smart_driver_success_rate",
                "Smart-path-without-fallback / total decisions (rolling 5min)",
                registry=self._registry,
            ),
            "tactical_score": Gauge(
                "eldritch_smart_driver_tactical_score",
                "Avg TacticalJudge overall_score over rolling 5min eval spans",
                registry=self._registry,
            ),
            "refusal_rate": Gauge(
                "eldritch_smart_driver_refusal_rate",
                "Refusals / total decisions (rolling 5min)",
                registry=self._registry,
            ),
            "fallback_rate": Gauge(
                "eldritch_smart_driver_fallback_rate",
                "Decisions with any fallback_reason / total (rolling 5min)",
                registry=self._registry,
            ),
        }

        # ── decisions counter ──
        self._decisions_counter = Counter(
            "eldritch_smart_driver_decisions_total",
            "Total monster-decision spans observed, by driver_path + fallback_reason",
            labelnames=("driver_path", "fallback_reason"),
            registry=self._registry,
        )

        # ── HTTP server ──
        # Resolve ephemeral port if requested (port=0).
        resolved_port = port
        if resolved_port == 0:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(("127.0.0.1", 0))
                resolved_port = s.getsockname()[1]

        from prometheus_client import start_http_server  # noqa: PLC0415

        # Bind address — DEFAULT to 127.0.0.1 (loopback only). Operators who
        # want to expose metrics on the network must opt in via
        # OBSERVABILITY_METRICS_BIND (e.g. "0.0.0.0" for all interfaces).
        # prometheus_client's own default is 0.0.0.0 which would leak metrics
        # to the LAN by default on a self-hoster's laptop — Rule 2 fix.
        bind_addr = os.environ.get("OBSERVABILITY_METRICS_BIND", "127.0.0.1")
        # prometheus_client 0.25.0 signature:
        # start_http_server(port, addr='0.0.0.0', registry=REGISTRY) -> (server, thread)
        # Tolerate older signatures that return None.
        result = start_http_server(
            resolved_port, addr=bind_addr, registry=self._registry
        )
        if isinstance(result, tuple) and len(result) == 2:
            self._server, self._server_thread = result
        else:
            self._server = None
            self._server_thread = None
        self._port = resolved_port

        # ── KPI refresh timer ──
        self._refresh_thread = threading.Thread(
            target=self._refresh_loop,
            name="prometheus-kpi-refresh",
            daemon=True,
        )
        self._refresh_thread.start()

        # ── Register the buffer post-write observer for the counter ──
        init_buffer().add_post_write_observer(self._on_buffer_write)

    @property
    def port(self) -> int:
        return self._port

    def _refresh_loop(self) -> None:
        # Initial refresh so the first scrape after startup has data.
        self._refresh_gauges()
        while not self._stop_event.wait(self._refresh_seconds):
            self._refresh_gauges()

    def _refresh_gauges(self) -> None:
        try:
            snap = get_cached_kpis(ttl_seconds=self._refresh_seconds)
        except Exception as exc:  # noqa: BLE001 — never crash the refresher
            log.warning(
                "metrics_endpoint.kpi_refresh_failed",
                error_type=type(exc).__name__,
                error=str(exc)[:200],
            )
            return
        # Gauges accept floats; for None we publish 'nan' which Prometheus
        # treats as "absent" (compatible with `rate(...)` queries that skip NaN).
        nan = float("nan")
        self._gauges["latency_p99_ms"].set(
            snap.latency_p99_ms if snap.latency_p99_ms is not None else nan
        )
        self._gauges["success_rate"].set(
            snap.success_rate if snap.success_rate is not None else nan
        )
        self._gauges["tactical_score"].set(
            snap.tactical_score if snap.tactical_score is not None else nan
        )
        self._gauges["refusal_rate"].set(
            snap.refusal_rate if snap.refusal_rate is not None else nan
        )
        self._gauges["fallback_rate"].set(
            snap.fallback_rate if snap.fallback_rate is not None else nan
        )

    def _on_buffer_write(self, row: BufferRow) -> None:
        if row.span_name != "eldritch.monster.decision":
            return
        self._decisions_counter.labels(
            driver_path=row.driver_path or "unknown",
            fallback_reason=row.fallback_reason or "none",
        ).inc()

    def stop(self) -> None:
        """Stop the refresh timer + HTTP server. Tests only."""
        self._stop_event.set()
        if self._server is not None:
            try:
                self._server.shutdown()
            except Exception as exc:  # noqa: BLE001
                log.warning(
                    "metrics_endpoint.shutdown_error",
                    error_type=type(exc).__name__,
                )


# ── Public API ──────────────────────────────────────────────────────────────


def start_metrics_endpoint(port: int | None = None) -> bool:
    """Start the Prometheus /metrics endpoint. Idempotent.

    Returns:
        True if the endpoint is running after this call (newly started or
        already-running); False if ``OBSERVABILITY_METRICS_ENDPOINT`` is
        unset/false.
    """
    global _HANDLE
    if not is_metrics_endpoint_enabled():
        return False
    with _HANDLE_LOCK:
        if _HANDLE is not None:
            return True
        resolved_port = port if port is not None else int(
            os.environ.get("OBSERVABILITY_METRICS_PORT", "9090")
        )
        try:
            handle = _MetricsEndpointHandle(port=resolved_port)
        except Exception as exc:  # noqa: BLE001
            log.error(
                "metrics_endpoint.start_failed",
                error_type=type(exc).__name__,
                error=str(exc)[:200],
                port=resolved_port,
            )
            return False
        _HANDLE = handle
        log.info(
            "observability.metrics_endpoint_started",
            port=handle.port,
            pid=os.getpid(),
        )
        return True


def get_endpoint_port() -> int | None:
    """Return the active endpoint's port, or None if not running. Tests only."""
    with _HANDLE_LOCK:
        return _HANDLE.port if _HANDLE is not None else None


def stop_for_tests() -> None:
    """Tear down the endpoint singleton. Tests only."""
    global _HANDLE
    with _HANDLE_LOCK:
        if _HANDLE is not None:
            _HANDLE.stop()
            _HANDLE = None
