"""SAFETY-02 unit tests for DMOfflineDebouncer (Phase 7 / G-4 closure).

Locks the two gates from D-34:
  * 30-second per-channel debounce (OPS-02-1)
  * 5-second minimum open-duration (OPS-02-2)

Plus per-channel isolation and clock injectability.
"""

from __future__ import annotations

from types import SimpleNamespace

from eldritch_dm.bot.dm_offline_debouncer import DMOfflineDebouncer


class _FakeClock:
    """Manually-advanceable monotonic clock for deterministic tests."""

    def __init__(self, start: float = 0.0) -> None:
        self.t = start

    def __call__(self) -> float:
        return self.t

    def advance(self, dt: float) -> None:
        self.t += dt


def _circuit(opened_at: float | None, failures: int = 5) -> SimpleNamespace:
    """Build a circuit-breaker stand-in with the surface the debouncer reads."""
    return SimpleNamespace(opened_at=opened_at, failure_count=failures)


# ── Gate 1: min open duration ──────────────────────────────────────────────


def test_circuit_open_less_than_min_open_returns_false() -> None:
    """Circuit OPEN for <5s suppresses the warning (OPS-02-2)."""
    clock = _FakeClock(100.0)
    deb = DMOfflineDebouncer(clock=clock)
    # Circuit just opened 1 second ago.
    circuit = _circuit(opened_at=99.0)
    assert deb.maybe_warn("chan-1", circuit) is False


def test_circuit_open_with_none_opened_at_returns_false() -> None:
    """Defensive: missing/None opened_at suppresses the warning."""
    deb = DMOfflineDebouncer(clock=_FakeClock(50.0))
    assert deb.maybe_warn("chan-1", _circuit(opened_at=None)) is False


def test_circuit_open_just_past_min_open_returns_true() -> None:
    """Crossing the 5s gate produces exactly one warning."""
    clock = _FakeClock(100.0)
    deb = DMOfflineDebouncer(clock=clock)
    # Opened 6 seconds ago — past the 5s gate.
    circuit = _circuit(opened_at=94.0)
    assert deb.maybe_warn("chan-1", circuit) is True


# ── Gate 2: per-channel 30s debounce ───────────────────────────────────────


def test_second_call_within_debounce_returns_false() -> None:
    """Within 30s of a warning, the same channel is suppressed."""
    clock = _FakeClock(100.0)
    deb = DMOfflineDebouncer(clock=clock)
    circuit = _circuit(opened_at=80.0)  # 20s open — past 5s gate

    assert deb.maybe_warn("chan-1", circuit) is True
    clock.advance(10.0)
    assert deb.maybe_warn("chan-1", circuit) is False
    clock.advance(15.0)
    assert deb.maybe_warn("chan-1", circuit) is False  # still inside 30s


def test_call_after_debounce_window_returns_true_again() -> None:
    """After 30s elapse, the next call returns True (and re-arms the window)."""
    clock = _FakeClock(100.0)
    deb = DMOfflineDebouncer(clock=clock)
    circuit = _circuit(opened_at=80.0)

    assert deb.maybe_warn("chan-1", circuit) is True
    clock.advance(31.0)
    assert deb.maybe_warn("chan-1", circuit) is True


# ── Gate isolation ─────────────────────────────────────────────────────────


def test_per_channel_isolation() -> None:
    """Channel A's debounce does NOT suppress Channel B's first warning."""
    clock = _FakeClock(100.0)
    deb = DMOfflineDebouncer(clock=clock)
    circuit = _circuit(opened_at=80.0)

    assert deb.maybe_warn("chan-A", circuit) is True
    # Channel B has never been warned; it should fire even within A's window.
    assert deb.maybe_warn("chan-B", circuit) is True
    # But A is still suppressed.
    assert deb.maybe_warn("chan-A", circuit) is False


# ── Knob overrides ─────────────────────────────────────────────────────────


def test_custom_debounce_seconds_respected() -> None:
    """Constructor allows overriding the 30s default."""
    clock = _FakeClock(100.0)
    deb = DMOfflineDebouncer(debounce_seconds=5.0, clock=clock)
    circuit = _circuit(opened_at=80.0)
    assert deb.maybe_warn("c", circuit) is True
    clock.advance(3.0)
    assert deb.maybe_warn("c", circuit) is False
    clock.advance(3.0)  # total 6s
    assert deb.maybe_warn("c", circuit) is True


def test_custom_min_open_seconds_respected() -> None:
    """Constructor allows overriding the 5s default."""
    clock = _FakeClock(100.0)
    deb = DMOfflineDebouncer(min_open_seconds=10.0, clock=clock)
    # Open for 7s — would pass default 5s gate but not the 10s override.
    assert deb.maybe_warn("c", _circuit(opened_at=93.0)) is False
    # Open for 11s — passes the 10s override.
    assert deb.maybe_warn("c", _circuit(opened_at=89.0)) is True


# ── Test helper ────────────────────────────────────────────────────────────


def test_force_warn_records_timestamp() -> None:
    """force_warn(...) bypasses both gates and records the warning timestamp."""
    clock = _FakeClock(100.0)
    deb = DMOfflineDebouncer(clock=clock)
    deb.force_warn("c")
    # Subsequent maybe_warn within 30s must be suppressed by the recorded
    # timestamp even if the circuit just opened.
    circuit = _circuit(opened_at=10.0)  # opened 90s ago — past 5s gate
    assert deb.maybe_warn("c", circuit) is False
