"""
LobbyCog — /start_game, /load_adventure, and EXPLORATION transition.

Implements LOBBY-01 (start_game MCP orchestration + rollback), LOBBY-02
(/load_adventure + curated autocomplete + idempotency mitigation), LOBBY-03
(lobby embed with segno QR + Ready button), and LOBBY-04 (ReadyButton state
machine wired via ReadyButton.callback — see dynamic_items.py).

Threat mitigations (from Plan 01 threat model):
  T-03-01: campaign name passed to dm20 verbatim; never echoed to LLM here
  T-03-03: /load_adventure gated on can_act_on_character(interaction, None)
           → manage_channels check only
  T-03-04: module_bound tracker prevents duplicate Chapter 1 entities (Pitfall 7)
  T-03-06: already-running detection + get_party_status recovery (Pitfall 8)
  T-03-07: best-effort end_claudmaster_session rollback on start_party_mode failure

Design decisions:
  D-03: Constructor-injected deps (mcp via bot, channel_sessions, persistent_views)
  D-04: /start_game — defer first; create_campaign → start_claudmaster_session
        → start_party_mode; rollback ordering preserved
  D-05: /load_adventure — curated ADVENTURE_IDS autocomplete (static, instant)
  D-09: defer-first enforced by EDM001 lint rule
  D-14: module_bound JSON field tracks re-run idempotency
  D-37: structlog binding — channel_id, campaign_name, tool_name on each MCP call

QR note: inline segno rendering here. Plan 03 will extract this into bot/qr.py
and update the import. Note this in SUMMARY for Plan 03 author.

SCOPE WALL: no character ingest in this cog — that's Plans 02 and 03.
"""
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Final

import discord
import structlog
from discord import app_commands
from discord.ext import commands

from eldritch_dm.bot.embeds import EmbedColor, lobby_embed
from eldritch_dm.bot.party_mode_parser import parse_party_mode_response
from eldritch_dm.bot.permissions import can_act_on_character
from eldritch_dm.bot.qr import render_qr_for_embed
from eldritch_dm.logging import get_logger
from eldritch_dm.persistence.models import ChannelState, PersistentView

if TYPE_CHECKING:
    from eldritch_dm.bot.bot import EldritchBot

# ── Curated adventure catalog (D-15, RESEARCH "Code Examples") ────────────────

ADVENTURE_IDS: Final[dict[str, str]] = {
    "CoS": "Curse of Strahd",
    "LMoP": "Lost Mine of Phandelver",
    "HotDQ": "Hoard of the Dragon Queen",
    "PotA": "Princes of the Apocalypse",
    "OotA": "Out of the Abyss",
    "ToA": "Tomb of Annihilation",
    "WDH": "Waterdeep: Dragon Heist",
    "WDMM": "Waterdeep: Dungeon of the Mad Mage",
    "BGDIA": "Baldur's Gate: Descent into Avernus",
}

log = get_logger(__name__)


# ── LobbyCog ──────────────────────────────────────────────────────────────────


class LobbyCog(commands.Cog):
    """Lobby cog: /start_game + /load_adventure + EXPLORATION transition.

    Constructor follows D-03: all runtime deps are injected, making the cog
    testable in isolation without a running Discord gateway.

    Attributes:
        bot: The EldritchBot instance (provides mcp, channel_sessions, persistent_views).
        _logger: structlog bound logger (bound with cog='lobby').

    Campaigns are never deleted by this cog on failure — dm20 campaigns are cheap
    and serve as audit records. Only claudmaster sessions are rolled back on error.
    """

    def __init__(
        self,
        bot: EldritchBot,
        *,
        logger: structlog.BoundLogger | None = None,
    ) -> None:
        self.bot = bot
        self._logger = (logger or log).bind(cog="lobby")

    # ── /start_game ────────────────────────────────────────────────────────────

    @app_commands.command(
        name="start_game",
        description="Start a new D&D 5e campaign in this channel. (Players will be guided to add characters next)",
    )
    @app_commands.describe(
        name="Campaign name (short, memorable)",
        description="Optional tagline shown in the lobby embed",
    )
    async def start_game(
        self,
        interaction: discord.Interaction,
        name: str,
        description: str | None = None,
    ) -> None:
        """Orchestrate the three-MCP-call campaign startup with rollback.

        Sequence (D-04):
          1. defer(thinking=True)  — EDM001 gate
          2. create_campaign       — dm20 creates the campaign record
          3. start_claudmaster_session — acquires a claudmaster session_id
          4. start_party_mode      — starts the WebSocket party server; returns markdown
          5. parse markdown via parse_party_mode_response
          6. Upsert channel_sessions with all three tokens
          7. Render segno QR + lobby embed + ReadyButton; send via followup

        Rollback (T-03-07):
          - start_party_mode failure → end_claudmaster_session (best-effort)
          - start_claudmaster_session failure → no rollback (nothing to undo)
          - Campaigns are never deleted on failure — they're cheap audit records

        LOBBY-01 requirement.
        """
        # Step 1: D-09 defer FIRST (EDM001)
        await interaction.response.defer(thinking=True)

        bound_log = self._logger.bind(
            command="start_game",
            channel_id=interaction.channel_id,
            user_id=getattr(interaction.user, "id", None),
            campaign_name=name,
        )
        bound_log.info("start_game_invoked")

        mcp = self.bot.mcp
        channel_id_str = str(interaction.channel_id)

        # Pre-step: Single-campaign-per-process guard (v1 constraint).
        # If ANY other channel already has a non-LOBBY session, refuse.
        try:
            active_rows = await self.bot.channel_sessions.list_active()
            for row in active_rows:
                if row.channel_id != channel_id_str and row.state != ChannelState.LOBBY:
                    bound_log.warning(
                        "start_game_blocked_active_session",
                        existing_channel_id=row.channel_id,
                        existing_state=row.state,
                    )
                    await interaction.followup.send(
                        content=(
                            f"A campaign is already active in another channel "
                            f"(campaign: '{row.campaign_name}', state: {row.state}). "
                            f"Only one active campaign is supported per bot instance."
                        ),
                        ephemeral=True,
                    )
                    return
        except Exception:
            bound_log.exception("start_game_active_session_check_failed")
            # Non-fatal: let the game start; the guard is best-effort

        # Step 2: Create campaign
        try:
            await mcp.call(
                "dm20__create_campaign",
                name=name,
                description=description or "",
            )
        except Exception:
            bound_log.exception("start_game_create_campaign_failed")
            await interaction.followup.send(
                content=f"Failed to create campaign '{name}'. Please try again.",
                ephemeral=True,
            )
            return

        # Step 3: Start Claudmaster session
        cm_session_id: str | None = None
        try:
            cm_result = await mcp.call(
                "dm20__start_claudmaster_session",
                campaign_name=name,
            )
            cm_session_id = (cm_result or {}).get("session_id")
        except Exception:
            bound_log.exception("start_game_claudmaster_failed")
            await interaction.followup.send(
                content=f"Failed to start DM session for '{name}'. Please try again.",
                ephemeral=True,
            )
            return

        # Step 4: Start party mode (with rollback on failure)
        try:
            party_markdown = await mcp.call(
                "dm20__start_party_mode",
                campaign_name=name,
            )
        except Exception:
            bound_log.exception("start_game_party_mode_failed")
            # T-03-07: rollback claudmaster session
            if cm_session_id:
                try:
                    await mcp.call(
                        "dm20__end_claudmaster_session",
                        session_id=cm_session_id,
                    )
                    bound_log.info("start_game_rollback_ok", session_id=cm_session_id)
                except Exception:  # noqa: BLE001
                    bound_log.warning("start_game_rollback_failed", session_id=cm_session_id)
            await interaction.followup.send(
                content=(
                    f"Failed to start Party Mode for '{name}'. Claudmaster session was rolled back."
                ),
                ephemeral=True,
            )
            return

        # Step 5: Parse party mode markdown
        try:
            if not isinstance(party_markdown, str):
                party_markdown = str(party_markdown)
            result = parse_party_mode_response(party_markdown)
        except ValueError as exc:
            bound_log.warning("start_game_party_mode_parse_error", error=str(exc))
            result = None

        # Handle already-running (Pitfall 8 / T-03-06): recover via get_party_status
        server_url: str = ""
        members_json: list[dict[str, Any]] = []

        if result is not None and result.already_running:
            bound_log.info("start_game_party_already_running")
            try:
                status = await mcp.call(
                    "dm20__get_party_status",
                    campaign_name=name,
                )
                server_url = (status or {}).get("server_url", "")
                # members from get_party_status may be in a different shape; defensive
                raw_members = (status or {}).get("members", []) if isinstance(status, dict) else []
                members_json = [
                    {"name": m.get("name", ""), "url": m.get("url", ""), "qr_path": None}
                    for m in raw_members
                    if isinstance(m, dict)
                ]
            except Exception:  # noqa: BLE001
                bound_log.warning("start_game_get_party_status_failed")
        elif result is not None:
            server_url = result.server_url
            members_json = [
                {
                    "name": m.character_name,
                    "url": m.url,
                    # T-03-05: never store raw path — read bytes then discard
                    "qr_path": None,
                }
                for m in result.members
            ]

        # Step 6: Upsert channel_sessions with all three tokens
        party_token_dict: dict[str, Any] = {
            "server_url": server_url,
            "members": members_json,
            "module_bound": None,
        }
        await self.bot.channel_sessions.upsert(
            channel_id=channel_id_str,
            campaign_name=name,
            claudmaster_session_id=cm_session_id,
            dm20_party_token=json.dumps(party_token_dict),
            state=ChannelState.LOBBY,
        )

        # Step 7: Render embed + QR + ReadyButton, send via followup
        from eldritch_dm.bot.dynamic_items import ReadyButton  # noqa: PLC0415

        view = discord.ui.View(timeout=None)
        view.add_item(ReadyButton(int(interaction.channel_id)))

        embed = lobby_embed(
            campaign_name=name,
            players=[],
            server_url=server_url or None,
            party_invite=server_url or None,
        )

        files: list[discord.File] = []
        if server_url:
            try:
                qr_file = render_qr_for_embed(server_url, filename="party_qr.png")
                embed.set_thumbnail(url="attachment://party_qr.png")
                files.append(qr_file)
            except Exception:  # noqa: BLE001
                bound_log.warning("start_game_qr_render_failed")

        msg = await interaction.followup.send(
            embed=embed,
            view=view,
            files=files if files else discord.utils.MISSING,
        )

        # Persist the message_id so rehydration can find the lobby embed
        try:
            msg_id = str(msg.id) if hasattr(msg, "id") else ""
            lobby_pv = PersistentView(
                custom_id=f"lobby:{channel_id_str}",
                view_class="LobbyCog",
                message_id=msg_id,
                channel_id=channel_id_str,
                payload={"campaign_name": name},
                created_at=datetime.now(tz=UTC),
            )
            await self.bot.pv_repo.insert(lobby_pv)
        except Exception:  # noqa: BLE001
            bound_log.warning("start_game_persist_view_failed")

        bound_log.info("start_game_ok", server_url=server_url)

    # ── /guide ─────────────────────────────────────────────────────────────────

    @app_commands.command(
        name="guide",
        description="Show the EldritchDM Player Guide with tips, flows, and hints!",
    )
    async def guide(
        self,
        interaction: discord.Interaction,
    ) -> None:
        """Send the player guide embed to help onboard new players."""
        # EDM001: Defer first
        await interaction.response.defer(ephemeral=True)

        desc = (
            "Welcome to the table! **EldritchDM** is your automated DM.\n\n"
            "**1️⃣ Join Lobby:** Wait for `/start_game`.\n"
            "**2️⃣ Character:** Use `/upload_character_url` or `/upload_character_file`.\n"
            "**3️⃣ Ready Up:** Click the ✅ Ready button.\n"
            "**4️⃣ Exploration:** Click `[ 💬 Declare Action ]`.\n"
            "**5️⃣ Combat:** Weapons out! Only click actions on *your turn*. Target by ID.\n"
            "**⚡ Ripostes:** Watch for the 8s Riposte button if a monster misses you!\n\n"
            "Full guide: [PLAYER_GUIDE.md](https://github.com/shoemoney/eldritchdm/blob/main/docs/PLAYER_GUIDE.md)"
        )

        embed = discord.Embed(
            title="🎮 EldritchDM Player Guide",
            description=desc,
            color=int(EmbedColor.LOBBY),
        )

        await interaction.followup.send(embed=embed, ephemeral=True)

    # ── /load_adventure ────────────────────────────────────────────────────────

    @app_commands.command(
        name="load_adventure",
        description="Load an official 5e adventure module into the active campaign",
    )
    @app_commands.describe(adventure_id="Adventure module ID (CoS, LMoP, etc.) — use autocomplete")
    async def load_adventure(
        self,
        interaction: discord.Interaction,
        adventure_id: str,
    ) -> None:
        """Bind an official 5e adventure to the active campaign.

        Uses static ADVENTURE_IDS for autocomplete (D-15) — no MCP cost per keystroke.

        Idempotency mitigation (RESEARCH §3, Pitfall 7, T-03-04):
          - Before calling dm20, reads dm20_party_token JSON from channel_sessions.
          - If module_bound is already set, uses populate_chapter_1=False to avoid
            duplicating Chapter 1 entities (locations, NPCs, quests).
          - After success, upserts channel_sessions with module_bound=adventure_id.

        Permission gate (T-03-03, D-29):
          Only users with manage_channels can load adventures (DM-only action).

        LOBBY-02 requirement.
        """
        # D-09: defer FIRST (EDM001)
        await interaction.response.defer(thinking=True, ephemeral=True)

        bound_log = self._logger.bind(
            command="load_adventure",
            channel_id=interaction.channel_id,
            user_id=getattr(interaction.user, "id", None),
            adventure_id=adventure_id,
        )
        bound_log.info("load_adventure_invoked")

        # Permission gate (T-03-03): DM-only action
        if not can_act_on_character(interaction, character_player_id=None):
            bound_log.warning("load_adventure_permission_denied")
            await interaction.followup.send(
                content="Only the DM (user with Manage Channels permission) can load adventures.",
                ephemeral=True,
            )
            return

        # Check active session
        channel_id_str = str(interaction.channel_id)
        session = await self.bot.channel_sessions.get(channel_id_str)
        if session is None:
            await interaction.followup.send(
                content="No active campaign in this channel — run /start_game first.",
                ephemeral=True,
            )
            return

        bound_log = bound_log.bind(campaign_name=session.campaign_name)

        # Idempotency mitigation (RESEARCH §3, Pitfall 7)
        module_bound: str | None = None
        current_token: dict[str, Any] = {}
        if session.dm20_party_token:
            try:
                current_token = json.loads(session.dm20_party_token)
                module_bound = current_token.get("module_bound")
            except (json.JSONDecodeError, AttributeError):
                pass

        should_populate = not bool(module_bound)
        bound_log.info(
            "load_adventure_idempotency_check",
            module_bound=module_bound,
            populate_chapter_1=should_populate,
        )

        # Call dm20 load_adventure
        try:
            await self.bot.mcp.call(
                "dm20__load_adventure",
                module_id=adventure_id,
                populate_chapter_1=should_populate,
                campaign_name=session.campaign_name,
            )
        except Exception:
            bound_log.exception("load_adventure_mcp_failed")
            await interaction.followup.send(
                content=f"Failed to load adventure '{adventure_id}'. Please try again.",
                ephemeral=True,
            )
            return

        # Patch dm20_party_token with module_bound
        current_token["module_bound"] = adventure_id
        await self.bot.channel_sessions.upsert(
            channel_id=channel_id_str,
            campaign_name=session.campaign_name,
            claudmaster_session_id=session.claudmaster_session_id,
            dm20_party_token=json.dumps(current_token),
            state=session.state,
        )

        adventure_title = ADVENTURE_IDS.get(adventure_id, adventure_id)
        confirm_embed = discord.Embed(
            title=f"📖 Adventure Loaded: {adventure_title}",
            description=(
                f"**{adventure_title}** (`{adventure_id}`) has been bound to "
                f"**{session.campaign_name}**.\n\n"
                f"{'Re-bound without duplicating Chapter 1 entities.' if not should_populate else 'Chapter 1 entities populated.'}"  # noqa: E501
            ),
            color=0x57F287,
        )
        confirm_embed.set_footer(text="🎲 ShoeGPT · EldritchDM")

        await interaction.followup.send(embed=confirm_embed, ephemeral=True)
        bound_log.info("load_adventure_ok", adventure_id=adventure_id)

    # ── /end_game ──────────────────────────────────────────────────────────────

    @app_commands.command(
        name="end_game",
        description="End the active campaign in this channel and clear session memory",
    )
    async def end_game(
        self,
        interaction: discord.Interaction,
    ) -> None:
        """Close the active campaign: end dm20 session, purge monster memory,
        flip the channel to LOBBY.

        Sequence (Phase 23 / D-178):
          1. defer FIRST (EDM001 / D-09).
          2. Permission gate: DM-only (T-03-03 parity with /load_adventure).
          3. Fetch the active session row; bail out if none.
          4. Best-effort dm20__end_claudmaster_session — failure is NON-FATAL
             (D-179 fail-soft). We still want to purge local state.
          5. Best-effort MonsterMemoryRegistry.purge_session — already fail-soft
             by contract (monster_memory.py L-07).
          6. Upsert channel_sessions back to LOBBY with claudmaster_session_id
             cleared.
          7. Ephemeral confirmation embed.

        WIRE-02 requirement (Phase 23, v1.7 honest-gap closure).
        """
        # Step 1: D-09 defer FIRST (EDM001), ephemeral
        await interaction.response.defer(thinking=True, ephemeral=True)

        bound_log = self._logger.bind(
            command="end_game",
            channel_id=interaction.channel_id,
            user_id=getattr(interaction.user, "id", None),
        )
        bound_log.info("end_game_invoked")

        # Step 2: Permission gate (T-03-03): DM-only action
        if not can_act_on_character(interaction, character_player_id=None):
            bound_log.warning("end_game_permission_denied")
            await interaction.followup.send(
                content="Only the DM (user with Manage Channels permission) can end the game.",
                ephemeral=True,
            )
            return

        # Step 3: Fetch active session
        channel_id_str = str(interaction.channel_id)
        session = await self.bot.channel_sessions.get(channel_id_str)
        if session is None:
            await interaction.followup.send(
                content="No active campaign in this channel — nothing to end.",
                ephemeral=True,
            )
            return

        bound_log = bound_log.bind(campaign_name=session.campaign_name)

        # Step 4: Best-effort dm20 close (D-179 fail-soft)
        if session.claudmaster_session_id:
            try:
                await self.bot.mcp.call(
                    "dm20__end_claudmaster_session",
                    session_id=session.claudmaster_session_id,
                )
                bound_log.info("end_game_dm20_close_ok")
            except Exception:
                # NON-FATAL: log + continue. We still need to purge local state.
                bound_log.exception("end_game_dm20_close_failed")

        # Step 5: Best-effort monster-memory purge (registry is itself fail-soft;
        # the defensive try here catches any pathological case — e.g., the
        # attribute being missing on legacy bot instances).
        registry = getattr(self.bot, "monster_memory_registry", None)
        purged = 0
        if registry is not None and session.claudmaster_session_id:
            try:
                purged = registry.purge_session(
                    channel_id_str,
                    session.claudmaster_session_id,
                )
                bound_log.info("end_game_memory_purged", count=purged)
            except Exception:
                bound_log.exception("end_game_memory_purge_failed")

        # Step 6: Flip state back to LOBBY (preserve row as audit; clear cm_id)
        try:
            await self.bot.channel_sessions.upsert(
                channel_id=channel_id_str,
                campaign_name=session.campaign_name,
                claudmaster_session_id=None,
                dm20_party_token=session.dm20_party_token,
                state=ChannelState.LOBBY,
            )
        except Exception:
            bound_log.exception("end_game_state_flip_failed")

        # Step 7: Ephemeral confirmation
        embed = discord.Embed(
            title="🛑 Session Ended",
            description=(
                f"Campaign **{session.campaign_name}** has been closed.\n\n"
                f"Monster memory cleared ({purged} entries).\n"
                f"Channel returned to LOBBY."
            ),
            color=0xED4245,
        )
        embed.set_footer(text="🎲 ShoeGPT · EldritchDM")
        await interaction.followup.send(embed=embed, ephemeral=True)
        bound_log.info("end_game_ok", purged=purged)

    @load_adventure.autocomplete("adventure_id")
    async def adventure_id_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> list[app_commands.Choice[str]]:
        """Return up to 25 matching adventure IDs (static, instant — no MCP cost).

        Matches on substring of either the adventure ID or the full title
        (case-insensitive). Empty ``current`` returns all 9 adventures.

        RESEARCH ref: "Code Examples" — autocomplete pattern
        CONTEXT ref: D-15 (static dict for v1; dynamic discover for v2)
        """
        cur = current.lower()
        return [
            app_commands.Choice(name=f"{aid} — {title}", value=aid)
            for aid, title in ADVENTURE_IDS.items()
            if cur in aid.lower() or cur in title.lower()
        ][:25]


async def setup(bot: EldritchBot) -> None:
    """discord.py extension entry point — called by bot.load_extension(...)."""
    await bot.add_cog(LobbyCog(bot))
