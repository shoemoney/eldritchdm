"""
EldritchDM persistent button DynamicItem subclasses.

Each class subclasses ``discord.ui.DynamicItem[discord.ui.Button]`` with a
class-level ``template`` regex. Discord routes any incoming button click whose
``custom_id`` fullmatches the template to the appropriate class's
``from_custom_id`` classmethod, then invokes ``callback``.

IMPORTANT — rehydration note (from 02-RESEARCH.md):
    ``add_dynamic_items(Cls)`` registers a regex listener globally. Any
    ``custom_id`` matching the template is routed to the correct handler
    regardless of which message/channel the button lives on. This means
    ``bot.add_view(view, message_id=...)`` is NOT needed for DynamicItem-based
    buttons. The ``persistent_views`` table is bookkeeping / audit metadata —
    not a rehydration source. (Old tutorials that say ``add_view`` is required
    pre-date discord.py 2.4's DynamicItem API.)

``DYNAMIC_ITEM_CLASSES`` is the canonical tuple for Plan 03's ``setup_hook``::

    bot.add_dynamic_items(*DYNAMIC_ITEM_CLASSES)

Phase 2 callbacks are STUBS (D-23): they defer first (D-09), bind structlog
context (D-38), log the dispatch, and reply with an ephemeral "Phase N stub"
message. Real handlers land in:
    - Phase 3: ReadyButton
    - Phase 4: DeclareActionButton, EndTurnButton
    - Phase 5: RiposteButton

custom_id 100-char limit (D-22, T-02-10): encodings are compact digit-only
strings. For 19-digit Discord snowflakes (the realistic worst case):
    - ``endturn:9999999999999999999:9999999999999999999`` = 48 chars  ✓
    - ``riposte:9999999999999999999:9999999999999999999`` = 48 chars  ✓
"""

from __future__ import annotations

import re

import discord
import structlog

from eldritch_dm.logging import get_logger

log = get_logger(__name__)


# ── ReadyButton ────────────────────────────────────────────────────────────────


class ReadyButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"^ready:(?P<channel_id>\d+)$",
):
    """Lobby ready-up button.

    Encodes: ``channel_id`` (Discord channel snowflake).
    Phase 3 handler: marks the player as ready in channel session; triggers
    transition to exploration when all players are ready.
    """

    template = re.compile(r"^ready:(?P<channel_id>\d+)$")

    def __init__(self, channel_id: int) -> None:
        super().__init__(
            discord.ui.Button(
                style=discord.ButtonStyle.success,
                label="✅ Ready",
                custom_id=f"ready:{channel_id}",
            )
        )
        self.channel_id = channel_id

    @classmethod
    async def from_custom_id(
        cls,
        interaction: discord.Interaction,
        item: discord.ui.Button,
        match: re.Match[str],
        /,
    ) -> "ReadyButton":
        return cls(channel_id=int(match["channel_id"]))

    def _custom_id_str(self) -> str:
        return f"ready:{self.channel_id}"

    async def callback(self, interaction: discord.Interaction) -> None:
        # D-09: defer first — always
        await interaction.response.defer(thinking=True, ephemeral=True)

        # D-38: bind structlog context
        bound_log = log.bind(
            channel_id=self.channel_id,
            custom_id=self._custom_id_str(),
            view_class=type(self).__name__,
            user_id=getattr(interaction.user, "id", None),
        )
        bound_log.info("phase2_stub_callback_invoked")

        await interaction.followup.send(
            content=f"⏳ Phase 2 stub — {type(self).__name__} will be wired up in a later phase.",
            ephemeral=True,
        )


# ── DeclareActionButton ────────────────────────────────────────────────────────


class DeclareActionButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"^declare:(?P<channel_id>\d+)$",
):
    """Exploration intent-collection button.

    Encodes: ``channel_id``.
    Phase 4 handler: opens a modal for the player to declare their action
    intent before the DM narrates the scene.
    """

    template = re.compile(r"^declare:(?P<channel_id>\d+)$")

    def __init__(self, channel_id: int) -> None:
        super().__init__(
            discord.ui.Button(
                style=discord.ButtonStyle.primary,
                label="💬 Declare Action",
                custom_id=f"declare:{channel_id}",
            )
        )
        self.channel_id = channel_id

    @classmethod
    async def from_custom_id(
        cls,
        interaction: discord.Interaction,
        item: discord.ui.Button,
        match: re.Match[str],
        /,
    ) -> "DeclareActionButton":
        return cls(channel_id=int(match["channel_id"]))

    def _custom_id_str(self) -> str:
        return f"declare:{self.channel_id}"

    async def callback(self, interaction: discord.Interaction) -> None:
        # D-09: defer first — always
        await interaction.response.defer(thinking=True, ephemeral=True)

        bound_log = log.bind(
            channel_id=self.channel_id,
            custom_id=self._custom_id_str(),
            view_class=type(self).__name__,
            user_id=getattr(interaction.user, "id", None),
        )
        bound_log.info("phase2_stub_callback_invoked")

        await interaction.followup.send(
            content=f"⏳ Phase 2 stub — {type(self).__name__} will be wired up in a later phase.",
            ephemeral=True,
        )


# ── EndTurnButton ──────────────────────────────────────────────────────────────


class EndTurnButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"^endturn:(?P<channel_id>\d+):(?P<actor_id>\d+)$",
):
    """Combat turn-yield button.

    Encodes: ``channel_id``, ``actor_id`` (Discord user snowflake).
    Phase 4 handler: validates that ``interaction.user.id == actor_id``
    (T-02-09 elevation-of-privilege mitigation), then advances turn order.
    """

    template = re.compile(r"^endturn:(?P<channel_id>\d+):(?P<actor_id>\d+)$")

    def __init__(self, channel_id: int, actor_id: int) -> None:
        super().__init__(
            discord.ui.Button(
                style=discord.ButtonStyle.secondary,
                label="⏭️ End Turn",
                custom_id=f"endturn:{channel_id}:{actor_id}",
            )
        )
        self.channel_id = channel_id
        self.actor_id = actor_id

    @classmethod
    async def from_custom_id(
        cls,
        interaction: discord.Interaction,
        item: discord.ui.Button,
        match: re.Match[str],
        /,
    ) -> "EndTurnButton":
        return cls(
            channel_id=int(match["channel_id"]),
            actor_id=int(match["actor_id"]),
        )

    def _custom_id_str(self) -> str:
        return f"endturn:{self.channel_id}:{self.actor_id}"

    async def callback(self, interaction: discord.Interaction) -> None:
        # D-09: defer first — always
        await interaction.response.defer(thinking=True, ephemeral=True)

        bound_log = log.bind(
            channel_id=self.channel_id,
            actor_id=self.actor_id,
            custom_id=self._custom_id_str(),
            view_class=type(self).__name__,
            user_id=getattr(interaction.user, "id", None),
        )
        bound_log.info("phase2_stub_callback_invoked")

        await interaction.followup.send(
            content=f"⏳ Phase 2 stub — {type(self).__name__} will be wired up in a later phase.",
            ephemeral=True,
        )


# ── RiposteButton ──────────────────────────────────────────────────────────────


class RiposteButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"^riposte:(?P<timer_id>\d+):(?P<user_id>\d+)$",
):
    """Timed riposte reaction button.

    Encodes: ``timer_id`` (keys into ``riposte_timers`` table), ``user_id``.
    Phase 5 handler: validates the timer has not expired, then processes the
    riposte counter-attack.
    """

    template = re.compile(r"^riposte:(?P<timer_id>\d+):(?P<user_id>\d+)$")

    def __init__(self, timer_id: int, user_id: int) -> None:
        super().__init__(
            discord.ui.Button(
                style=discord.ButtonStyle.danger,
                label="⚔️ Riposte!",
                custom_id=f"riposte:{timer_id}:{user_id}",
            )
        )
        self.timer_id = timer_id
        self.user_id = user_id

    @classmethod
    async def from_custom_id(
        cls,
        interaction: discord.Interaction,
        item: discord.ui.Button,
        match: re.Match[str],
        /,
    ) -> "RiposteButton":
        return cls(
            timer_id=int(match["timer_id"]),
            user_id=int(match["user_id"]),
        )

    def _custom_id_str(self) -> str:
        return f"riposte:{self.timer_id}:{self.user_id}"

    async def callback(self, interaction: discord.Interaction) -> None:
        # D-09: defer first — always
        await interaction.response.defer(thinking=True, ephemeral=True)

        bound_log = log.bind(
            timer_id=self.timer_id,
            user_id=self.user_id,
            custom_id=self._custom_id_str(),
            view_class=type(self).__name__,
        )
        bound_log.info("phase2_stub_callback_invoked")

        await interaction.followup.send(
            content=f"⏳ Phase 2 stub — {type(self).__name__} will be wired up in a later phase.",
            ephemeral=True,
        )


# ── Registration tuple ─────────────────────────────────────────────────────────

DYNAMIC_ITEM_CLASSES: tuple[type[discord.ui.DynamicItem], ...] = (
    ReadyButton,
    DeclareActionButton,
    EndTurnButton,
    RiposteButton,
)
"""Canonical tuple for ``setup_hook`` registration.

Usage in Plan 03's setup_hook::

    bot.add_dynamic_items(*DYNAMIC_ITEM_CLASSES)

Note: ``add_dynamic_items`` alone is sufficient for persistent buttons.
Do NOT also call ``bot.add_view(view, message_id=...)`` for these classes
(see module docstring and 02-RESEARCH.md Pitfall 1).
"""
