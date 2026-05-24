---
phase: 13-production-monitoring
plan: 01
requirements_completed: [MON-01]
subsystem: observability
tags: [kpi, prometheus, span-buffer, sqlite, lazy-import]
requirements:
  completed: [MON-01]
dependency-graph:
  requires: [11-OBS-01]   # builds on Phase 11's traced_decision/traced_translate/traced_eval
  provides:
    - "span_buffer.SpanBuffer + init_buffer() — primary span sink for KPI/cost"
    - "kpi.compute_kpis() + get_cached_kpis() — 5-min rolling KPI snapshots"
    - "metrics_endpoint.start_metrics_endpoint() — opt-in Prometheus :9090/metrics"
    - "SpanBuffer.add_post_write_observer() IoC hook"
  affects:
    - "instrumentation.py — _NoopSpan replaced by _BufferingSpan proxy (dual sink)"
    - "bot/__main__.py — observability wired into startup (Phase 11 gap closed)"
tech-stack:
  added:
    - "prometheus_client>=0.20,<1.0 (in [project.optional-dependencies].observability)"
  patterns:
    - "Module-level singleton with double-checked locking for hot-path-cheap init"
    - "Inversion of control via observer registration (avoids dependency leak)"
    - "Lazy-import canaries enforce zero-cost-when-disabled invariant"
key-files:
  created:
    - src/eldritch_dm/observability/span_buffer.py
    - src/eldritch_dm/observability/kpi.py
    - src/eldritch_dm/observability/metrics_endpoint.py
    - tests/observability/test_span_buffer.py
    - tests/observability/test_buffer_dual_sink.py
    - tests/observability/test_kpi.py
    - tests/observability/test_metrics_endpoint.py
    - tests/observability/test_metrics_lazy_import.py
    - tests/bot/test_metrics_endpoint_boot.py
  modified:
    - src/eldritch_dm/observability/instrumentation.py
    - src/eldritch_dm/observability/__init__.py
    - src/eldritch_dm/bot/__main__.py
    - tests/observability/test_disabled_noop.py
    - pyproject.toml
    - .planning/REQUIREMENTS.md
decisions:
  - "R-13-01-a: span_buffer is PRIMARY sink, OTLP is secondary — KPIs work without Phoenix"
  - "R-13-01-b: write path is queue+drain (batch=100/500ms) so the event loop never blocks on SQLite"
  - "R-13-01-c: prometheus_client.start_http_server (stdlib http.server), NOT aiohttp"
  - "R-13-01-d: prometheus_client in optional-dependencies; lazy import only inside start_metrics_endpoint"
  - "R-13-01-e: 5s in-process KPI cache bounds SQLite load under Prometheus scrape"
  - "Rule-3: init_tracing() was orphaned in Phase 11 — wired into bot.__main__.main during Phase 13"
metrics:
  duration: ~3h (planning + execution)
  completed_date: 2026-05-24
---

# Phase 13 Plan 01: KPI Monitors + Span Buffer + Prometheus /metrics Summary

## One-liner

Local SQLite span buffer is the primary sink for every traced decision;
5-minute rolling KPI computer drives an opt-in Prometheus `/metrics` endpoint
at `:9090` exposing the 5 AI-SPEC §7 indicators as gauges + a labelled
decision counter.

## What Was Built

### `observability/span_buffer.py`

A WAL-mode SQLite buffer at `~/.eldritch/spans.sqlite` (overridable via
`ELDRITCH_SPAN_BUFFER_PATH`). Hot-path cost on each `record()` is one
`queue.Queue.put_nowait` + observer fan-out — no SQLite I/O on the bot's
event loop. A daemon `span-buffer-drainer` thread batch-commits up to 100
rows per 500ms.

Inversion-of-control via `add_post_write_observer(callable)`: external
modules (metrics endpoint, future webhooks) react to writes without forcing
`span_buffer` to import their libraries — preserves the lazy-import canary.

`init_buffer()` is hot-path-cheap: a module-level `_BUFFER` sentinel under
double-checked locking returns immediately on calls 2..N (no `mkdir`,
`sqlite3.connect`, or schema check).

### `observability/kpi.py`

`compute_kpis(now, window_minutes=5)` reads decision + eval spans from the
buffer and returns a frozen `KPISnapshot` with the 5 D-85 KPIs:
`latency_p99_ms`, `success_rate`, `tactical_score`, `refusal_rate`,
`fallback_rate`. `get_cached_kpis(ttl_seconds=5)` bounds SQLite load under
Prometheus scrape — a 15s scrape interval triggers ~3 recomputes/min
regardless of client count.

Nearest-rank percentile (no interpolation) — locked in by tests so
operators get predictable behavior on small samples.

### `observability/metrics_endpoint.py`

`start_metrics_endpoint(port=9090)` lazily imports `prometheus_client`,
creates an isolated `CollectorRegistry` (fixes "Duplicated timeseries"
under fixture cycling), registers 5 gauges + 1 counter, and starts the
prometheus_client stdlib `http.server` in a background thread.

- 5 KPI gauges refreshed every 5s from `get_cached_kpis()`.
- 1 counter `eldritch_smart_driver_decisions_total{driver_path, fallback_reason}`
  registered as a `SpanBuffer` post-write observer — increments in lockstep
  with the buffer write itself.
- `port=0` / `OBSERVABILITY_METRICS_PORT=0` → ephemeral port for tests.
- `None` KPI values published as `NaN` (Prometheus 'absent'-compatible).

### Dual-sink `instrumentation.py`

`_NoopSpan` replaced by `_BufferingSpan` — a proxy that captures
`set_attribute` calls and, on context-manager exit, writes a `BufferRow` to
the buffer **regardless of OTel state**. When OTel is on, the proxy ALSO
forwards calls to the real OTel `Span`. Result: KPIs + cost reports work
whether or not Phoenix is up.

Existing dotted-attr keys (`eldritch.latency_ms`,
`eldritch.fallback.reason`, etc.) map to `BufferRow` columns in
`_BufferingSpan._to_row`. The `refusal` flag is derived from
`fallback_reason == "refusal"` — `driver_path == "random"` alone is NOT
sufficient (random happens for many reasons).

### Bot-startup wiring

`bot.__main__.main` now calls `init_tracing()` then
`start_metrics_endpoint()` after `configure_logging` and before
`require_token_or_exit`, both wrapped in a single try/except that logs
`observability_init_failed` so observability errors NEVER block Discord
boot.

### Lazy-import canaries (still green)

- `test_lazy_import.py` (Phase 11): no `opentelemetry` in `sys.modules` when
  `OBSERVABILITY_ENABLED=false`.
- `test_metrics_lazy_import.py` (new): no `prometheus_client` in
  `sys.modules` when `OBSERVABILITY_METRICS_ENDPOINT=false`.

Both pass even though both libraries are installed in the venv — proves the
gates work mechanically, not just by absence of the package.

## Test Coverage

- `tests/observability/` — 44 unit tests across 6 files (span buffer,
  KPI, metrics endpoint, dual-sink, both lazy-import canaries, existing
  Phase 11 attribute tests + disabled-noop)
- `tests/bot/test_metrics_endpoint_boot.py` — 3 tests asserting startup
  wiring via `inspect.getsource` (no Discord mocking needed)
- `lint-imports` — all 8 contracts kept (observability stays sibling-safe)
- `ruff check src/eldritch_dm/observability tests/observability` — clean

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking Issue] CONTEXT D-84 named `aiohttp.web` for the metrics endpoint**

- **Found during:** Plan-writing review (advisor check)
- **Issue:** `aiohttp` is explicitly forbidden by `./CLAUDE.md` ("What NOT to Use"); not in deps
- **Fix:** Used `prometheus_client.start_http_server` (stdlib `http.server` under the hood)
- **Files modified:** `metrics_endpoint.py`
- **Documented as:** R-13-01-c in 13-01-PLAN.md

**2. [Rule 2 - Missing Critical Functionality] CONTEXT D-92 implied OTel as the primary sink**

- **Found during:** Architecture review against D-83
- **Issue:** "monitors must run even without Phoenix" (D-83) cannot be met if OTel is the only sink — KPIs go dark when `OBSERVABILITY_ENABLED=false`
- **Fix:** Made the local SQLite buffer the primary sink; OTel export is now secondary
- **Files modified:** `instrumentation.py`, `span_buffer.py`
- **Documented as:** R-13-01-a in 13-01-PLAN.md

**3. [Rule 3 - Blocking Issue] Plan v1 had prometheus_client leaking into span_buffer**

- **Found during:** advisor pre-execution review of plan
- **Issue:** Initial plan wired the Prometheus Counter increment "inside `span_buffer.record()`" — would force `prometheus_client` into `sys.modules` even when the env gate was off, breaking the canary
- **Fix:** Added `SpanBuffer.add_post_write_observer()` IoC hook; metrics endpoint registers the counter-increment closure only when it starts
- **Files modified:** `span_buffer.py`, `metrics_endpoint.py`
- **Documented:** Plan 13-01 patched in commit 0c9c2e8 before execution

**4. [Rule 3 - Blocking Issue] `init_tracing()` was orphaned in Phase 11**

- **Found during:** Task 06 — grep for the existing `init_tracing` call site
- **Issue:** Phase 11 defined the function but no production startup code called it. Both `init_tracing()` and `start_metrics_endpoint()` had to be added to the bot boot path.
- **Fix:** Added a single try/except block in `bot.__main__.main` calling both, after `configure_logging` and before `require_token_or_exit`
- **Files modified:** `src/eldritch_dm/bot/__main__.py`
- **Documented as:** Discovery noted in this Summary; the wiring closes a Phase 11 latent gap.

**5. [Rule 1 - Bug] `test_disabled_noop.py::test_noop_span_is_not_otel_span` assertion against class name**

- **Found during:** Task 03 — instrumentation refactor renamed `_NoopSpan` → `_BufferingSpan`
- **Issue:** The test asserted `type(span).__name__ == "_NoopSpan"`, which is too brittle — the invariant being protected is "no OTel coupling," not the class name
- **Fix:** Changed the assertion to `cls.__module__.startswith("eldritch_dm.observability")` + `"opentelemetry" not in cls.__module__` — same intent, doesn't break on class rename
- **Files modified:** `tests/observability/test_disabled_noop.py`

**6. [Rule 2 - Missing Security Functionality] `prometheus_client.start_http_server` defaults to `0.0.0.0`**

- **Found during:** SUMMARY-writing self-review (threat-surface scan)
- **Issue:** `prometheus_client.start_http_server` binds `0.0.0.0` by default, exposing the `/metrics` endpoint (with `monster.id` + `channel.id` cardinality on the decision counter) to the LAN on a self-hoster's laptop the moment they set `OBSERVABILITY_METRICS_ENDPOINT=true`
- **Fix:** `metrics_endpoint.py` explicitly passes `addr="127.0.0.1"` as the default; operators opt into network exposure via `OBSERVABILITY_METRICS_BIND` env
- **Files modified:** `src/eldritch_dm/observability/metrics_endpoint.py`

### Auth Gates Encountered

None — pure local development, no external auth required.

## Self-Check: PASSED

- `src/eldritch_dm/observability/span_buffer.py` — FOUND
- `src/eldritch_dm/observability/kpi.py` — FOUND
- `src/eldritch_dm/observability/metrics_endpoint.py` — FOUND
- All 9 created test files — FOUND
- Commits b84a38e, ec49da7, 6ff715b, 864dc6c, ec51e20, d64f4a7 — FOUND
- ruff clean, lint-imports clean (8/8 contracts kept)
- 44 observability tests + 3 boot tests all pass

## Known Stubs

None — every code path in this plan is wired through to working storage,
computation, and HTTP serving. The Phoenix dashboard JSON files referenced
by OBS-02 (Phase 11) are out of scope for MON-01 (which only required the
`/metrics` endpoint as the per-AI-SPEC §7 deliverable).

## Threat Flags

None. The metrics endpoint binds on `127.0.0.1` by default — operators
must opt into network-wide exposure via `OBSERVABILITY_METRICS_BIND=0.0.0.0`.
This is a deliberate **Rule-2 hardening over `prometheus_client`'s default
of `0.0.0.0`**, which would have leaked KPI cardinality (monster.id +
channel.id labels) to the LAN by default on a self-hoster's laptop.
