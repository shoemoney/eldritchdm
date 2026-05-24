"""SAFETY-02 unit tests for @catch_circuit_open (Phase 7 / G-4 closure)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from eldritch_dm.bot.circuit_decorator import catch_circuit_open
from eldritch_dm.bot.dm_offline_debouncer import DMOfflineDebouncer
from eldritch_dm.bot.warnings import WarningKind
from eldritch_dm.mcp.errors import (
    MCPCircuitOpen,
    MCPNetworkError,
    MCPTimeoutError,
    MCPToolError,
)


def _make_interaction(*, debouncer, circuit) -> MagicMock:
    """Build an interaction whose .client carries the SAFETY-02 surface."""
    interaction = MagicMock()
    interaction.channel_id = 12345
    interaction.client = SimpleNamespace(
        dm_offline_debouncer=debouncer,
        circuit_breaker=circuit,
    )
    interaction.followup = MagicMock()
    interaction.followup.send = AsyncMock()
    return interaction


def _circuit(opened_at: float | None, failures: int = 4) -> SimpleNamespace:
    return SimpleNamespace(opened_at=opened_at, failure_count=failures)


# ── Happy path: success returns value unchanged ─────────────────────────────


@pytest.mark.asyncio
async def test_returns_inner_value_on_success() -> None:
    @catch_circuit_open
    async def cb(self, interaction):
        return "result-42"

    interaction = _make_interaction(debouncer=None, circuit=None)
    assert await cb(object(), interaction) == "result-42"


# ── Non-MCPCircuitOpen exceptions propagate ─────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "exc",
    [
        TypeError("bad type"),
        ValueError("bad value"),
        MCPTimeoutError("timeout"),
        MCPNetworkError("network"),
        MCPToolError(
            tool_name="dm20__x",
            arguments={},
            response_payload=None,
            message="oops",
        ),
    ],
    ids=["TypeError", "ValueError", "MCPTimeout", "MCPNetwork", "MCPTool"],
)
async def test_non_circuit_exceptions_reraise(exc: Exception) -> None:
    @catch_circuit_open
    async def cb(self, interaction):
        raise exc

    interaction = _make_interaction(debouncer=None, circuit=None)
    with pytest.raises(type(exc)):
        await cb(object(), interaction)


# ── MCPCircuitOpen path ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_circuit_open_with_passing_debouncer_sends_warning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """First open-state click past the 5s gate produces one DM_OFFLINE warning."""
    # Stub send_warning at the module level so we can assert it was called.
    sent: list[tuple] = []

    async def fake_send_warning(interaction, kind, **ctx):
        sent.append((kind, ctx))

    import eldritch_dm.bot.circuit_decorator as mod

    monkeypatch.setattr(mod, "send_warning", fake_send_warning)

    debouncer = DMOfflineDebouncer(clock=lambda: 100.0)
    circuit = _circuit(opened_at=90.0, failures=7)  # 10s open — past 5s gate
    interaction = _make_interaction(debouncer=debouncer, circuit=circuit)

    @catch_circuit_open
    async def cb(self, interaction):
        raise MCPCircuitOpen(tool_name="dm20__get_game_state")

    result = await cb(object(), interaction)
    assert result is None, "decorator must swallow MCPCircuitOpen (return None)"
    assert len(sent) == 1, f"expected 1 send_warning call, got {sent!r}"
    kind, ctx = sent[0]
    assert kind is WarningKind.DM_OFFLINE
    assert ctx["failure_count"] == 7


@pytest.mark.asyncio
async def test_circuit_open_within_debounce_suppresses_warning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A second MCPCircuitOpen within 30s does NOT re-dispatch a warning."""
    sent: list[tuple] = []

    async def fake_send_warning(interaction, kind, **ctx):
        sent.append((kind, ctx))

    import eldritch_dm.bot.circuit_decorator as mod

    monkeypatch.setattr(mod, "send_warning", fake_send_warning)

    debouncer = DMOfflineDebouncer(clock=lambda: 100.0)
    debouncer.force_warn("12345")  # already warned on this channel
    circuit = _circuit(opened_at=90.0)
    interaction = _make_interaction(debouncer=debouncer, circuit=circuit)

    @catch_circuit_open
    async def cb(self, interaction):
        raise MCPCircuitOpen(tool_name="dm20__x")

    result = await cb(object(), interaction)
    assert result is None
    assert sent == [], "warning should be suppressed within debounce window"


@pytest.mark.asyncio
async def test_circuit_open_during_min_open_window_suppresses_warning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Transient circuit blip (< 5s open) produces no warning."""
    sent: list[tuple] = []

    async def fake_send_warning(interaction, kind, **ctx):
        sent.append((kind, ctx))

    import eldritch_dm.bot.circuit_decorator as mod

    monkeypatch.setattr(mod, "send_warning", fake_send_warning)

    debouncer = DMOfflineDebouncer(clock=lambda: 100.0)
    # Circuit opened 2 seconds ago — under the 5s min-open gate.
    circuit = _circuit(opened_at=98.0)
    interaction = _make_interaction(debouncer=debouncer, circuit=circuit)

    @catch_circuit_open
    async def cb(self, interaction):
        raise MCPCircuitOpen(tool_name="dm20__x")

    result = await cb(object(), interaction)
    assert result is None
    assert sent == [], "transient blip should not surface a DM_OFFLINE warning"


# ── Missing-infra defensive path ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_missing_debouncer_reraises_for_visibility() -> None:
    """If the bot is missing dm_offline_debouncer, re-raise so the dev sees it."""
    interaction = MagicMock()
    interaction.channel_id = 1
    # client is missing the attribute we need
    interaction.client = SimpleNamespace(circuit_breaker=_circuit(opened_at=0.0))

    @catch_circuit_open
    async def cb(self, interaction):
        raise MCPCircuitOpen(tool_name="x")

    with pytest.raises(MCPCircuitOpen):
        await cb(object(), interaction)
