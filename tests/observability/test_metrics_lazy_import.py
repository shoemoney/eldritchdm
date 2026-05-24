"""Lazy-import canary for prometheus_client (Phase 13 / MON-01 / R-13-01-d).

Mirror of ``test_lazy_import.py`` (Phase 11): asserts that importing the bot's
observability surface with ``OBSERVABILITY_METRICS_ENDPOINT`` unset does NOT
pull ``prometheus_client`` into ``sys.modules``.

The Prometheus endpoint is opt-in via env. The cost of having `prometheus_client`
in the optional ``observability`` extras must be zero when the operator hasn't
turned the endpoint on. Plan 01 enforces this by inverting the
``span_buffer`` → ``metrics_endpoint`` dependency via
``SpanBuffer.add_post_write_observer(...)`` so ``span_buffer`` itself never
references ``prometheus_client``.

Uses ``subprocess`` so a prior test that DID start the endpoint cannot
pollute the current process's ``sys.modules`` and cause a false pass.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap


def test_no_prometheus_client_in_sys_modules_when_endpoint_disabled() -> None:
    """Full observability surface import does not leak prometheus_client when off."""
    script = textwrap.dedent(
        """
        import os
        # Both env gates explicitly off — neither tracer nor metrics endpoint
        # should pull their respective third-party libs.
        os.environ.pop("OBSERVABILITY_ENABLED", None)
        os.environ.pop("OBSERVABILITY_METRICS_ENDPOINT", None)

        # Import the full observability tree + the hot-path call sites.
        import eldritch_dm.observability  # noqa: F401
        import eldritch_dm.gameplay.smart_monster_driver  # noqa: F401
        import eldritch_dm.ingest.translate  # noqa: F401

        # Exercise the no-op context managers so the buffer-write path runs.
        from eldritch_dm.observability import traced_decision, traced_translate
        with traced_decision(
            monster_id="m", channel_id="c", combat_round=1, driver_path="smart"
        ) as s:
            s.set_attribute("eldritch.latency_ms", 1)
        with traced_translate(channel_id="c", model="ShoeGPT") as s:
            s.set_attribute("eldritch.latency_ms", 1)

        import sys as _sys
        leaks = sorted(k for k in _sys.modules if "prometheus_client" in k)
        assert not leaks, (
            f"prometheus_client leaked when OBSERVABILITY_METRICS_ENDPOINT is off: {leaks}"
        )
        print("METRICS_LAZY_IMPORT_OK")
        """
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert (
        result.returncode == 0
    ), f"subprocess failed:\nSTDOUT: {result.stdout}\nSTDERR: {result.stderr}"
    assert "METRICS_LAZY_IMPORT_OK" in result.stdout
