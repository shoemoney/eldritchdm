"""
Tests for eldritch_dm.bot.dynamic_items — DynamicItem persistent button subclasses.

Covers:
  - custom_id construction + 100-char limit
  - regex round-trip parsing via from_custom_id
  - bad custom_id does NOT match template
  - stub callback: defers first, then followup.send with class name
  - DYNAMIC_ITEM_CLASSES tuple completeness
  - boundary: 19-digit snowflake inputs still fit in 100 chars
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from eldritch_dm.bot.dynamic_items import (
    DYNAMIC_ITEM_CLASSES,
    AttackButton,
    CastSpellButton,
    DeclareActionButton,
    DodgeButton,
    EndTurnButton,
    ReadyButton,
    RiposteButton,
)

# ── Helpers ────────────────────────────────────────────────────────────────────


def _make_interaction() -> discord.Interaction:
    """Build a minimal mock discord.Interaction for callback testing."""
    interaction = MagicMock(spec=discord.Interaction)
    interaction.user = MagicMock(spec=discord.Member)
    interaction.user.id = 100
    interaction.channel_id = 200
    interaction.guild_id = 300

    interaction.response = AsyncMock()
    interaction.response.defer = AsyncMock()
    interaction.response.is_done = MagicMock(return_value=False)

    interaction.followup = AsyncMock()
    interaction.followup.send = AsyncMock()

    return interaction


# ── Test 1: custom_id construction + 100-char limit ───────────────────────────


class TestCustomIdConstruction:
    @pytest.mark.parametrize(
        "cls, kwargs, expected_custom_id",
        [
            (ReadyButton, {"channel_id": 123456789}, "ready:123456789"),
            (DeclareActionButton, {"channel_id": 987654321}, "declare:987654321"),
            # Phase 4: EndTurnButton uses dm20 character UUID + round_n (BREAKING vs Phase 2 stub)
            (EndTurnButton, {"channel_id": 111, "actor_id": "hero-001", "round_n": 1}, "endturn:111:hero-001:1"),
            (RiposteButton, {"timer_id": 999, "user_id": 888}, "riposte:999:888"),
            # Phase 4: new combat buttons
            (AttackButton, {"channel_id": 222, "actor_id": "hero-001", "round_n": 2}, "attack:222:hero-001:2"),
            (DodgeButton, {"channel_id": 333, "actor_id": "hero-001", "round_n": 3}, "dodge:333:hero-001:3"),
            (CastSpellButton, {"channel_id": 444, "actor_id": "wizard-001", "round_n": 4}, "cast:444:wizard-001:4"),
        ],
    )
    def test_custom_id_value(self, cls, kwargs, expected_custom_id) -> None:
        instance = cls(**kwargs)
        # DynamicItem exposes the wrapped button via .item
        assert instance.item.custom_id == expected_custom_id

    @pytest.mark.parametrize(
        "cls, kwargs",
        [
            (ReadyButton, {"channel_id": 123456789}),
            (DeclareActionButton, {"channel_id": 987654321}),
            (EndTurnButton, {"channel_id": 111, "actor_id": "hero-001", "round_n": 1}),
            (RiposteButton, {"timer_id": 999, "user_id": 888}),
            (AttackButton, {"channel_id": 222, "actor_id": "hero-001", "round_n": 2}),
            (DodgeButton, {"channel_id": 333, "actor_id": "hero-001", "round_n": 3}),
            (CastSpellButton, {"channel_id": 444, "actor_id": "wizard-001", "round_n": 4}),
        ],
    )
    def test_custom_id_under_100_chars(self, cls, kwargs) -> None:
        instance = cls(**kwargs)
        cid = instance.item.custom_id
        assert cid is not None
        assert len(cid) <= 100, f"custom_id too long: {len(cid)} chars -- '{cid}'"


# ── Test 2: regex round-trip via from_custom_id ───────────────────────────────


class TestRegexRoundTrip:
    @pytest.mark.parametrize(
        "cls, kwargs",
        [
            (ReadyButton, {"channel_id": 42}),
            (DeclareActionButton, {"channel_id": 777}),
            (EndTurnButton, {"channel_id": 1001, "actor_id": "hero-001", "round_n": 1}),
            (RiposteButton, {"timer_id": 3003, "user_id": 4004}),
            (AttackButton, {"channel_id": 2001, "actor_id": "hero-002", "round_n": 2}),
            (DodgeButton, {"channel_id": 3001, "actor_id": "hero-003", "round_n": 3}),
            (CastSpellButton, {"channel_id": 4001, "actor_id": "wizard-001", "round_n": 4}),
        ],
    )
    @pytest.mark.asyncio
    async def test_from_custom_id_round_trips(self, cls, kwargs) -> None:
        # Build instance
        original = cls(**kwargs)
        custom_id = original.item.custom_id

        # Match custom_id against template
        match = cls.template.fullmatch(custom_id)
        assert match is not None, f"template did not match custom_id: {custom_id!r}"

        # Reconstruct via from_custom_id
        interaction = _make_interaction()
        item_mock = MagicMock(spec=discord.ui.Button)
        reconstructed = await cls.from_custom_id(interaction, item_mock, match)

        # Verify captured fields match source kwargs
        for field, value in kwargs.items():
            assert getattr(reconstructed, field) == value, (
                f"{cls.__name__}.{field}: expected {value}, got {getattr(reconstructed, field)}"
            )


# ── Test 3: bad custom_id does NOT match template ─────────────────────────────


class TestBadCustomId:
    @pytest.mark.parametrize(
        "cls, bad_id",
        [
            (ReadyButton, "ready:notanumber"),
            (ReadyButton, "ready:123:extra"),
            (DeclareActionButton, "declare:"),
            (DeclareActionButton, "ready:123"),  # wrong prefix
            # Phase 4: EndTurnButton requires 3-segment format: channel:actor:round
            (EndTurnButton, "endturn:123"),  # missing actor_id and round
            (EndTurnButton, "endturn:123:UPPER:1"),  # uppercase actor_id
            (RiposteButton, "riposte:123"),  # missing user_id
            (RiposteButton, "riposte:!@#:456"),  # non-digits
            (AttackButton, "attack:123:UPPER:1"),  # uppercase actor_id
            (AttackButton, "attack:123"),  # missing segments
            (DodgeButton, "dodge:123:UPPERCASE:1"),  # uppercase
        ],
    )
    def test_bad_custom_id_does_not_match(self, cls, bad_id) -> None:
        match = cls.template.fullmatch(bad_id)
        assert match is None, (
            f"{cls.__name__}.template unexpectedly matched bad custom_id: {bad_id!r}"
        )


# ── Test 4: stub callback — defer first, then followup.send ───────────────────
# Note: ReadyButton and DeclareActionButton are NOT included here — their callbacks
# were replaced by real implementations in Phase 3 (Task 3) and Phase 4 (Task 3).
# Tests for the real callbacks live in:
#   - test_dynamic_items_real.py (ReadyButton)
#   - test_dynamic_items_declare_real.py (DeclareActionButton)


# Phase 4: EndTurnButton is promoted to real callback (no longer a stub).
# AttackButton/DodgeButton/CastSpellButton also real callbacks.
# Only RiposteButton remains a Phase 5 stub.
_STUB_CLASSES = [
    (RiposteButton, {"timer_id": 50, "user_id": 60}),
]


class TestStubCallback:
    @pytest.mark.parametrize("cls, kwargs", _STUB_CLASSES)
    @pytest.mark.asyncio
    async def test_callback_defers_first(self, cls, kwargs) -> None:
        instance = cls(**kwargs)
        interaction = _make_interaction()

        await instance.callback(interaction)

        # defer must be called before followup.send
        interaction.response.defer.assert_awaited_once_with(thinking=True, ephemeral=True)

    @pytest.mark.parametrize("cls, kwargs", _STUB_CLASSES)
    @pytest.mark.asyncio
    async def test_callback_followup_contains_class_name(self, cls, kwargs) -> None:
        instance = cls(**kwargs)
        interaction = _make_interaction()

        await instance.callback(interaction)

        interaction.followup.send.assert_awaited_once()
        call_kwargs = interaction.followup.send.call_args
        content = call_kwargs.kwargs.get("content") or (
            call_kwargs.args[0] if call_kwargs.args else ""
        )
        assert cls.__name__ in content, (
            f"Expected class name {cls.__name__!r} in followup content: {content!r}"
        )
        # Must be ephemeral
        assert call_kwargs.kwargs.get("ephemeral") is True

    @pytest.mark.parametrize("cls, kwargs", _STUB_CLASSES)
    @pytest.mark.asyncio
    async def test_callback_defer_before_followup_ordering(self, cls, kwargs) -> None:
        """Verify defer is awaited before followup.send (call ordering)."""
        call_order: list[str] = []

        interaction = _make_interaction()

        # Need to make them actual coroutines
        async def defer_coro(**kw):
            call_order.append("defer")

        async def send_coro(**kw):
            call_order.append("followup")

        interaction.response.defer = defer_coro
        interaction.followup.send = send_coro

        instance = cls(**kwargs)
        await instance.callback(interaction)

        assert call_order == ["defer", "followup"], (
            f"Expected ['defer', 'followup'], got {call_order}"
        )


# ── Test 5: DYNAMIC_ITEM_CLASSES tuple completeness ───────────────────────────


class TestDynamicItemClassesTuple:
    def test_has_seven_classes(self) -> None:
        """Phase 4 Plan 02 adds AttackButton, DodgeButton, CastSpellButton."""
        assert len(DYNAMIC_ITEM_CLASSES) == 7

    def test_contains_expected_classes(self) -> None:
        expected = {
            ReadyButton,
            DeclareActionButton,
            EndTurnButton,
            AttackButton,
            DodgeButton,
            CastSpellButton,
            RiposteButton,
        }
        assert set(DYNAMIC_ITEM_CLASSES) == expected


# ── Test 6: 19-digit snowflake boundary ───────────────────────────────────────


class TestSnowflakeBoundary:
    """Verify 100-char limit holds for worst-case 19-digit Discord snowflakes (D-22)."""

    MAX_SNOWFLAKE = 10**19 - 1  # 19 digits: 9999999999999999999

    def test_endturn_19digit_snowflakes_fit_100_chars(self) -> None:
        # Phase 4: actor_id is now a dm20 UUID (lowercase+dash), not a snowflake int.
        # Test with a typical UUID to verify 100-char limit.
        uuid_actor = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
        instance = EndTurnButton(channel_id=self.MAX_SNOWFLAKE, actor_id=uuid_actor, round_n=999)
        cid = instance.item.custom_id
        assert cid is not None
        assert len(cid) <= 100, f"endturn custom_id too long: {len(cid)} chars"

    def test_riposte_19digit_snowflakes_fit_100_chars(self) -> None:
        instance = RiposteButton(timer_id=self.MAX_SNOWFLAKE, user_id=self.MAX_SNOWFLAKE)
        cid = instance.item.custom_id
        assert cid is not None
        assert len(cid) <= 100, f"riposte custom_id too long: {len(cid)} chars"
