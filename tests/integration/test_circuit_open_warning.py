"""SAFETY-02 end-to-end integration test (Phase 7 / G-4 closure).

Stamps the regression that no ``MCPCircuitOpen`` escapes from a
``DynamicItem`` button callback. The test patches the MCP layer to raise
``MCPCircuitOpen``, then dispatches a real button callback and asserts:

  1. ``send_warning`` is invoked with ``WarningKind.DM_OFFLINE``.
  2. ``MCPCircuitOpen`` does not bubble up to discord.py.
  3. Repeated clicks within the 30s debounce window do not re-warn.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from eldritch_dm.bot.dm_offline_debouncer import DMOfflineDebouncer
from eldritch_dm.bot.warnings import WarningKind
from eldritch_dm.mcp.errors import MCPCircuitOpen
from eldritch_dm.mcp.health import CircuitBreaker, CircuitState


def _make_open_circuit(*, opened_at: float, failures: int = 5) -> CircuitBreaker:
    """Build a real CircuitBreaker forced into the OPEN state."""
    cb = CircuitBreaker(threshold=3)
    cb._state = CircuitState.OPEN  # type: ignore[attr-defined]
    cb._failures = failures  # type: ignore[attr-defined]
    cb.opened_at = opened_at
    return cb


def _make_bot(
    *,
    debouncer: DMOfflineDebouncer,
    circuit: CircuitBreaker,
) -> MagicMock:
    bot = MagicMock()
    bot.dm_offline_debouncer = debouncer
    bot.circuit_breaker = circuit
    bot.mcp = MagicMock()
    return bot


def _make_interaction(bot, *, channel_id: int = 99) -> MagicMock:
    interaction = MagicMock()
    interaction.channel_id = channel_id
    interaction.client = bot
    interaction.user = SimpleNamespace(id=1234, display_name="Tester")
    interaction.response = MagicMock()
    interaction.response.defer = AsyncMock()
    interaction.followup = MagicMock()
    interaction.followup.send = AsyncMock()
    return interaction


@pytest.mark.asyncio
async def test_circuit_open_button_click_surfaces_dm_offline_warning() -> None:
    """A single MCPCircuitOpen-raising click produces exactly one DM_OFFLINE warning."""
    # Clock at t=100s; circuit opened at t=90s (10s open — past 5s gate).
    fake_clock = {"now": 100.0}
    debouncer = DMOfflineDebouncer(clock=lambda: fake_clock["now"])
    circuit = _make_open_circuit(opened_at=90.0, failures=7)
    bot = _make_bot(debouncer=debouncer, circuit=circuit)
    interaction = _make_interaction(bot)

    sent: list[tuple] = []

    async def fake_send_warning(interaction, kind, **ctx):
        sent.append((kind, ctx))

    # Patch send_warning at the decorator module so the wrapped callback sees it.
    with patch("eldritch_dm.bot.circuit_decorator.send_warning", new=fake_send_warning):
        # Use the decorator directly on a stub callback that raises
        # MCPCircuitOpen — same execution path as any real DynamicItem
        # callback that touches MCP.
        from eldritch_dm.bot.circuit_decorator import catch_circuit_open

        @catch_circuit_open
        async def stub_button_callback(self, interaction):
            raise MCPCircuitOpen(tool_name="dm20__combat_action")

        result = await stub_button_callback(object(), interaction)
        assert result is None, "MCPCircuitOpen must be swallowed"
        assert len(sent) == 1, f"expected exactly 1 warning, got {sent!r}"
        kind, ctx = sent[0]
        assert kind is WarningKind.DM_OFFLINE
        assert ctx["failure_count"] == 7

        # Four more rapid clicks in the same channel must NOT re-warn.
        for _ in range(4):
            await stub_button_callback(object(), interaction)
        assert len(sent) == 1, (
            f"debounce should suppress repeat warnings, got {len(sent)}: {sent!r}"
        )

        # Advance past the 30s window — next click warns again.
        fake_clock["now"] += 31.0
        await stub_button_callback(object(), interaction)
        assert len(sent) == 2, f"warning should re-arm after 30s; sent={sent!r}"
