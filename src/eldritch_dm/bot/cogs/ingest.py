"""
IngestCog — /upload_character_url, /upload_character_file, /upload_character_manual.

Implements INGEST-01, INGEST-02, INGEST-08, INGEST-09, INGEST-10, INGEST-11.

Design:
  - D-09 defer-first: every handler awaits interaction.response.defer(ephemeral=True)
    as its FIRST line (EDM001 lint rule; modals use noqa with reason).
  - D-30 ephemeral confirmations: all followup.send(...) use ephemeral=True.
    Non-ephemeral surface is ONLY the lobby embed update after commit.
  - D-27 confidence routing:
      ≥ 0.6 → CharacterReviewModal (player confirms extracted data)
      < 0.6 → CharacterEntryModal  (player types from scratch)
  - RESEARCH §5 defer + send_modal conflict: because we defer first, we CANNOT
    call send_modal on the same interaction. Solution: 2-step flow —
      defer → followup ephemeral with a Button → button click is a fresh
      interaction → button opens the modal via response.send_modal().
  - RESEARCH §6 attachment size: check attachment.size BEFORE attachment.read().
  - T-03-16 permission gate: can_act_on_character enforces ownership / DM rights.
  - T-03-17 sanitization: all modal-submitted text passes through
    sanitize_player_input before any LLM or MCP call.
  - D-37 structlog: binds attachment_filename, bytes_size, ocr_backend,
    ocr_confidence, dm20_character_id per CONTEXT contract.

Architecture note (lobby embed update):
  On character commit, we look up the lobby message ID from the dm20_party_token
  JSON stored in channel_sessions (key: "lobby_message_id"). The LobbyCog stores
  this in the persistent_views row AND in dm20_party_token during /start_game.
  If the key is absent (older sessions), the update is skipped gracefully.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, Literal

import discord
import structlog
from discord import app_commands
from discord.ext import commands
from openai import AsyncOpenAI

from eldritch_dm.bot.embeds import lobby_embed_with_joined_member
from eldritch_dm.bot.modals import (
    CharacterEntryModal,
    CharacterReviewModal,
    parse_abilities_field,
)
from eldritch_dm.bot.permissions import can_act_on_character
from eldritch_dm.ingest import ingest
from eldritch_dm.logging import get_logger

if TYPE_CHECKING:
    from eldritch_dm.bot.bot import EldritchBot

log = get_logger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────────

MAX_ATTACHMENT_BYTES: int = 10 * 1024 * 1024  # 10 MB (RESEARCH §6 / T-03-14)

_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
_JPEG_MAGIC = b"\xff\xd8\xff"
_PDF_MAGIC = b"%PDF-"


# ── Magic-byte sniff (cog-level — surface user-facing errors before pipeline) ──


def _sniff_kind_cog(data: bytes) -> Literal["image", "pdf"] | None:
    """Quick magic-byte check to surface a friendly error BEFORE hitting the pipeline.

    The pipeline (ingest/pipeline.py) has its own _sniff_kind for defense-in-depth;
    this one is solely for early user-facing error messages in the cog.

    Returns:
        "image", "pdf", or None (unknown / unsupported).
    """
    head = data[:8]
    if head.startswith(_PNG_MAGIC) or head.startswith(_JPEG_MAGIC):
        return "image"
    if head.startswith(_PDF_MAGIC):
        return "pdf"
    return None


# ── IngestCog ──────────────────────────────────────────────────────────────────


class IngestCog(commands.Cog):
    """Character ingest cog: three upload slash commands for character onboarding.

    All three commands defer first (EDM001), gate by permission (D-29),
    and reply ephemerally (D-30, INGEST-10).

    After a character is committed to dm20, the lobby embed is updated
    non-ephemerally to show '✅ {char_name} ({class}, lvl {N}) joined'.
    """

    def __init__(
        self,
        bot: EldritchBot,
        *,
        logger: structlog.BoundLogger | None = None,
    ) -> None:
        self.bot = bot
        self._logger = (logger or log).bind(cog="ingest")

    # ── Helper: construct openai client ────────────────────────────────────────

    def _get_openai_client(self) -> AsyncOpenAI:
        """Construct or return the backend-agnostic OpenAI-compatible client (D-27).

        Resolution order:
          1. ``bot.openai_client`` if pre-set (test injection point).
          2. ``Settings.resolve_ingest_config()`` for endpoint + api_key
             selected by ``INGEST_BACKEND`` (omlx, ollama, openrouter).

        Raises:
            ValueError: ``INGEST_BACKEND=openrouter`` but ``OPENROUTER_API_KEY``
                is unset (propagated from ``resolve_ingest_config``).
        """
        if hasattr(self.bot, "openai_client") and self.bot.openai_client is not None:
            return self.bot.openai_client
        cfg = self.bot.settings.resolve_ingest_config()
        return AsyncOpenAI(base_url=cfg.endpoint, api_key=cfg.api_key)

    def _get_ingest_model(self) -> str:
        """Return the model id to send to the ingest backend (D-27).

        Resolution order: ``ingest_model_override`` → ``omlx_ingest_model``
        → ``omlx_model``. Encapsulated in ``Settings.resolve_ingest_config``.

        Falls back to a sensible default if ``resolve_ingest_config`` raises
        (e.g. missing OPENROUTER_API_KEY) — defensive so we don't lose the
        ability to surface the underlying error from the real call site.
        """
        try:
            return self.bot.settings.resolve_ingest_config().model
        except ValueError:
            # Pre-empt downstream surfacing by returning omlx_model; the
            # real backend selection error will be raised by _get_openai_client.
            return getattr(self.bot.settings, "omlx_model", "ShoeGPT")

    # ── Helper: look up lobby message ──────────────────────────────────────────

    async def _get_lobby_message(
        self,
        channel_id_str: str,
        channel: discord.abc.Messageable | None,
    ) -> discord.Message | None:
        """Look up the lobby embed message via dm20_party_token JSON.

        Returns the discord.Message if found, or None (graceful degradation).
        """
        try:
            session = await self.bot.channel_sessions.get(channel_id_str)
            if session is None or not session.dm20_party_token:
                return None
            token = json.loads(session.dm20_party_token)
            lobby_msg_id = token.get("lobby_message_id")
            if not lobby_msg_id or channel is None:
                return None
            return await channel.fetch_message(int(lobby_msg_id))
        except Exception:  # noqa: BLE001
            self._logger.debug("ingest_lobby_msg_lookup_failed", channel_id=channel_id_str)
            return None

    # ── Shared submit callback ─────────────────────────────────────────────────

    async def _on_character_submit(
        self,
        interaction: discord.Interaction,
        raw_dict: dict[str, Any],
        *,
        campaign_name: str,
        player_name: str | None = None,
    ) -> None:
        """Process a modal submission: parse abilities, validate, create character.

        Called from both CharacterReviewModal and CharacterEntryModal via the
        closure passed at modal construction (D-03 callback pattern).

        Args:
            interaction:    Discord interaction from the modal submit.
            raw_dict:       Raw modal field values (abilities_str not yet parsed).
            campaign_name:  Active campaign name from channel_sessions.
            player_name:    Override player name (defaults to interaction.user.display_name).
        """
        bound_log = self._logger.bind(
            user_id=interaction.user.id,
            campaign=campaign_name,
        )
        channel_id_str = str(interaction.channel_id)
        effective_player_name = player_name or interaction.user.display_name

        # Parse and validate ability scores
        try:
            abilities = parse_abilities_field(raw_dict["abilities_str"])
        except (ValueError, Exception) as exc:
            bound_log.warning("ingest_modal_abilities_parse_error", error=str(exc))
            await interaction.followup.send(
                content=(
                    f"❌ Invalid ability scores: {exc}\n"
                    "Please try `/upload_character_manual` again and re-enter your scores."
                ),
                ephemeral=True,
            )
            return

        # Build character dict for dm20
        try:
            class_level_int = int(raw_dict.get("class_level", "1"))
        except (ValueError, TypeError):
            class_level_int = 1

        character_payload: dict[str, Any] = {
            "name": raw_dict.get("name", "Unknown"),
            "character_class": raw_dict.get("character_class", ""),
            "class_level": class_level_int,
            "race": raw_dict.get("race", ""),
            "player_id": str(interaction.user.id),
            "player_name": effective_player_name,
            "strength": abilities.strength,
            "dexterity": abilities.dexterity,
            "constitution": abilities.constitution,
            "intelligence": abilities.intelligence,
            "wisdom": abilities.wisdom,
            "charisma": abilities.charisma,
        }

        # Persist via dm20__create_character
        try:
            result = await self.bot.mcp.call(
                "dm20__create_character",
                campaign_name=campaign_name,
                **character_payload,
            )
            char_name = raw_dict.get("name", "Unknown")
            char_class = raw_dict.get("character_class", "")
            char_level = class_level_int
            char_id = (result or {}).get("character_id") or (result or {}).get("name", "")
            bound_log.info("ingest_create_character_ok", character_id=char_id)
        except Exception as exc:
            bound_log.exception("ingest_create_character_failed", error=str(exc))
            await interaction.followup.send(
                content=f"❌ Failed to save character: {exc}",
                ephemeral=True,
            )
            return

        # Phase 5 Plan 01: persist (class, subclass) for Riposte eligibility.
        # dm20's get_character text omits subclass (RESEARCH Q2), so we capture
        # it now at ingest time. Best-effort — non-fatal if it fails (we still
        # have the dm20-side character). subclass may be "" for level 1-2 PCs.
        pc_classes_repo = getattr(self.bot, "pc_classes", None)
        if pc_classes_repo is not None and char_id:
            try:
                subclass = raw_dict.get("subclass") or ""
                await pc_classes_repo.upsert(
                    channel_id=channel_id_str,
                    character_id=str(char_id),
                    class_name=char_class,
                    subclass=subclass,
                )
            except Exception:  # noqa: BLE001
                bound_log.warning("ingest_pc_classes_upsert_failed", character_id=char_id)

        # Update lobby embed (non-ephemeral — D-30)
        try:
            channel = interaction.channel
            lobby_msg = await self._get_lobby_message(channel_id_str, channel)
            if lobby_msg is not None:
                joined_text = f"✅ {char_name} ({char_class}, lvl {char_level}) joined"
                updated_embed = lobby_embed_with_joined_member(
                    campaign_name=campaign_name,
                    players=[],
                    recently_joined=[joined_text],
                )
                await lobby_msg.edit(embed=updated_embed)
        except Exception:  # noqa: BLE001
            bound_log.warning("ingest_lobby_embed_update_failed")

        await interaction.followup.send(
            content=f"✅ {char_name} joined {campaign_name}!",
            ephemeral=True,
        )

    # ── /upload_character_url ─────────────────────────────────────────────────

    @app_commands.command(
        name="upload_character_url",
        description="Import a character from a D&D Beyond URL",
    )
    @app_commands.describe(
        url="Full D&D Beyond character URL or character ID",
        player_name="Override player name (defaults to your display name)",
    )
    async def upload_character_url(
        self,
        interaction: discord.Interaction,
        url: str,
        player_name: str | None = None,
    ) -> None:
        """Import a D&D Beyond character via dm20__import_from_dndbeyond.

        D-06: dm20 handles the URL fetch — no SSRF risk in our code.
        D-13: player_id bound to character for Phase 4 turn gatekeeping.
        """
        await interaction.response.defer(thinking=True, ephemeral=True)

        bound_log = self._logger.bind(
            command="upload_character_url",
            user_id=interaction.user.id,
            url=url[:60],
            channel_id=interaction.channel_id,
        )
        bound_log.info("upload_url_invoked")

        channel_id_str = str(interaction.channel_id)
        session = await self.bot.channel_sessions.get(channel_id_str)
        if session is None:
            await interaction.followup.send(
                content="❌ No active campaign in this channel — run /start_game first.",
                ephemeral=True,
            )
            return

        effective_player_name = player_name or interaction.user.display_name

        # Step 1: Import from D&D Beyond
        try:
            import_result = await self.bot.mcp.call(
                "dm20__import_from_dndbeyond",
                url_or_id=url,
                player_name=effective_player_name,
            )
        except Exception as exc:
            bound_log.warning("upload_url_import_failed", error=str(exc))
            await interaction.followup.send(
                content=f"❌ Could not import from D&D Beyond: {exc}",
                ephemeral=True,
            )
            return

        # Step 2: Defensively attach player_id (D-13)
        char_id = (import_result or {}).get("character_id") or (import_result or {}).get("name", "")
        char_name = (import_result or {}).get("name", url.split("/")[-1])
        char_class = (import_result or {}).get("class", "")
        char_level = (import_result or {}).get("level", 0)
        char_subclass = (import_result or {}).get("subclass", "") or ""

        try:
            await self.bot.mcp.call(
                "dm20__update_character",
                name_or_id=char_id,
                player_id=str(interaction.user.id),
                player_name=effective_player_name,
            )
        except Exception:  # noqa: BLE001
            bound_log.warning("upload_url_update_player_id_failed", char_id=char_id)

        # Phase 5 Plan 01: pc_classes upsert (Riposte eligibility — RESEARCH Q2)
        pc_classes_repo = getattr(self.bot, "pc_classes", None)
        if pc_classes_repo is not None and char_id:
            try:
                await pc_classes_repo.upsert(
                    channel_id=channel_id_str,
                    character_id=str(char_id),
                    class_name=str(char_class),
                    subclass=str(char_subclass),
                )
            except Exception:  # noqa: BLE001
                bound_log.warning("upload_url_pc_classes_upsert_failed")

        # Step 3: Update lobby embed
        try:
            channel = interaction.channel
            lobby_msg = await self._get_lobby_message(channel_id_str, channel)
            if lobby_msg is not None:
                joined_text = f"✅ {char_name} ({char_class}, lvl {char_level}) joined"
                updated_embed = lobby_embed_with_joined_member(
                    campaign_name=session.campaign_name,
                    players=[],
                    recently_joined=[joined_text],
                )
                await lobby_msg.edit(embed=updated_embed)
        except Exception:  # noqa: BLE001
            bound_log.warning("upload_url_lobby_embed_update_failed")

        bound_log.info("upload_url_ok", char_id=char_id, char_name=char_name)
        await interaction.followup.send(
            content=f"✅ Imported {char_name} to {session.campaign_name}!",
            ephemeral=True,
        )

    # ── /upload_character_file ────────────────────────────────────────────────

    @app_commands.command(
        name="upload_character_file",
        description="Upload a character sheet image or PDF for OCR parsing",
    )
    @app_commands.describe(
        attachment="PNG, JPEG, or PDF character sheet (max 10 MB)",
        player_name="Override player name (defaults to your display name)",
    )
    async def upload_character_file(
        self,
        interaction: discord.Interaction,
        attachment: discord.Attachment,
        player_name: str | None = None,
    ) -> None:
        """OCR/PDF ingest pipeline → confidence-routed modal → dm20 character creation.

        T-03-14: Size check BEFORE attachment.read() (RESEARCH §6).
        T-03-15: Magic-byte sniff overrides Discord content_type.
        T-03-16: Permission gate via can_act_on_character.
        D-31: <8s end-to-end budget.
        """
        await interaction.response.defer(thinking=True, ephemeral=True)

        bound_log = self._logger.bind(
            command="upload_character_file",
            user_id=interaction.user.id,
            attachment_filename=attachment.filename,
            bytes_size=attachment.size,
            channel_id=interaction.channel_id,
        )
        bound_log.info("upload_file_invoked")

        channel_id_str = str(interaction.channel_id)

        # Permission gate (T-03-16, D-29)
        if not can_act_on_character(interaction, character_player_id=str(interaction.user.id)):
            bound_log.warning("upload_file_permission_denied")
            await interaction.followup.send(
                content=(
                    "❌ Only the uploading player or DM (manage channels) can upload characters."
                ),
                ephemeral=True,
            )
            return

        # Session check
        session = await self.bot.channel_sessions.get(channel_id_str)
        if session is None:
            await interaction.followup.send(
                content="❌ No active campaign in this channel — run /start_game first.",
                ephemeral=True,
            )
            return

        # T-03-14: Size check BEFORE .read()
        if attachment.size > MAX_ATTACHMENT_BYTES:
            bound_log.warning("upload_file_oversize", size=attachment.size)
            await interaction.followup.send(
                content=(
                    f"❌ File exceeds the 10 MB limit "
                    f"({attachment.size // 1024 // 1024} MB). Please compress and retry."
                ),
                ephemeral=True,
            )
            return

        # Read the bytes
        data = await attachment.read()

        # T-03-15: Magic-byte sniff — reject unknown formats before hitting pipeline
        kind = _sniff_kind_cog(data)
        if kind is None:
            bound_log.warning("upload_file_unsupported_format")
            await interaction.followup.send(
                content=(
                    "❌ Unsupported file format (PNG, JPEG, PDF only). "
                    "Please upload a character sheet image or PDF."
                ),
                ephemeral=True,
            )
            return

        effective_player_name = player_name or interaction.user.display_name

        # Run the ingest pipeline (D-27 — backend selected by INGEST_BACKEND)
        openai_client = self._get_openai_client()
        ingest_model = self._get_ingest_model()
        try:
            result = await ingest(
                data,
                content_type=attachment.content_type,
                filename=attachment.filename,
                player_name=effective_player_name,
                user_id=str(interaction.user.id),
                openai_client=openai_client,
                mcp_client=self.bot.mcp,
                model=ingest_model,
            )
        except Exception as exc:
            bound_log.exception("upload_file_ingest_failed", error=str(exc))
            await interaction.followup.send(
                content=f"❌ Character ingest failed: {exc}",
                ephemeral=True,
            )
            return

        bound_log.info(
            "upload_file_ingest_done",
            confidence=result.confidence_score,
            ocr_backend=result.ocr_backend,
        )

        # Build prefill dict from ingest result
        prefill: dict[str, Any] = {}
        if result.parsed_sheet is not None:
            sheet = result.parsed_sheet
            prefill = {
                "name": sheet.name,
                "character_class": sheet.character_class,
                "class_level": sheet.class_level,
                "race": sheet.race,
                "abilities": sheet.abilities,
            }

        campaign_name = session.campaign_name

        # Confidence routing → 2-step button flow (RISKS: defer + send_modal conflict)
        if result.confidence_score >= 0.6:
            # High confidence: Review & Confirm button → CharacterReviewModal
            async def on_review_submit(
                modal_interaction: discord.Interaction,
                raw_dict: dict[str, Any],
            ) -> None:
                await self._on_character_submit(
                    modal_interaction,
                    raw_dict,
                    campaign_name=campaign_name,
                    player_name=effective_player_name,
                )

            button_label = "Review & Confirm"
            modal_factory = lambda: CharacterReviewModal(prefill, on_submit_cb=on_review_submit)  # noqa: E731
            button_style = discord.ButtonStyle.primary
        else:
            # Low confidence: Enter Character Manually button → CharacterEntryModal
            async def on_entry_submit(
                modal_interaction: discord.Interaction,
                raw_dict: dict[str, Any],
            ) -> None:
                await self._on_character_submit(
                    modal_interaction,
                    raw_dict,
                    campaign_name=campaign_name,
                    player_name=effective_player_name,
                )

            button_label = "Enter Character Manually"
            modal_factory = lambda: CharacterEntryModal(  # noqa: E731
                prefill or None, on_submit_cb=on_entry_submit
            )
            button_style = discord.ButtonStyle.secondary

        # Build ephemeral view with one button that opens the modal
        view = _ModalLaunchView(
            button_label=button_label,
            button_style=button_style,
            modal_factory=modal_factory,
        )

        warnings_text = ""
        if result.validation_warnings:
            warnings_text = "\n⚠️ " + "; ".join(result.validation_warnings[:3])

        pct = f"{result.confidence_score:.0%}"
        content = (
            f"📋 Character sheet processed (confidence: {pct}){warnings_text}\n"
            "Click the button below to review and confirm."
        )

        await interaction.followup.send(content=content, view=view, ephemeral=True)

    # ── /upload_character_manual ──────────────────────────────────────────────

    @app_commands.command(
        name="upload_character_manual",
        description="Enter a character sheet manually without OCR",
    )
    async def upload_character_manual(
        self,
        interaction: discord.Interaction,
    ) -> None:
        """Open the manual character entry modal directly (no OCR).

        CONTEXT D-08: Useful when OCR will fail (handwritten, glare, etc.).
        """
        await interaction.response.defer(thinking=True, ephemeral=True)

        bound_log = self._logger.bind(
            command="upload_character_manual",
            user_id=interaction.user.id,
            channel_id=interaction.channel_id,
        )
        bound_log.info("upload_manual_invoked")

        channel_id_str = str(interaction.channel_id)
        session = await self.bot.channel_sessions.get(channel_id_str)
        campaign_name = session.campaign_name if session else "Unknown Campaign"

        async def on_manual_submit(
            modal_interaction: discord.Interaction,
            raw_dict: dict[str, Any],
        ) -> None:
            await self._on_character_submit(
                modal_interaction,
                raw_dict,
                campaign_name=campaign_name,
            )

        modal_factory = lambda: CharacterEntryModal(on_submit_cb=on_manual_submit)  # noqa: E731

        view = _ModalLaunchView(
            button_label="Enter Character",
            button_style=discord.ButtonStyle.primary,
            modal_factory=modal_factory,
        )

        await interaction.followup.send(
            content=(
                "📝 Click below to enter your character manually.\n"
                "Fill in all five fields and submit to create your character."
            ),
            view=view,
            ephemeral=True,
        )
        bound_log.info("upload_manual_view_sent")


# ── View: Button that opens a Modal ───────────────────────────────────────────


class _ModalLaunchView(discord.ui.View):
    """Short-lived ephemeral view with a single button that opens a modal.

    Used to work around the defer + send_modal conflict (RISKS §1):
    the ingest commands defer first (EDM001), so they cannot call
    ``send_modal`` directly. Instead, they send this ephemeral view.
    Clicking the button gives us a fresh interaction we can call
    ``send_modal`` on.

    The ``modal_factory`` callable is invoked on each button click to
    produce a fresh modal instance with the correct closures.
    """

    def __init__(
        self,
        *,
        button_label: str,
        button_style: discord.ButtonStyle,
        modal_factory: Any,
    ) -> None:
        super().__init__(timeout=300)  # 5-minute window for the player to click
        self._modal_factory = modal_factory

        self._launch_button = discord.ui.Button(
            label=button_label,
            style=button_style,
        )
        self._launch_button.callback = self._on_button_click
        self.add_item(self._launch_button)

    async def _on_button_click(self, interaction: discord.Interaction) -> None:  # noqa: EDM001 — button opens modal; first response is send_modal
        """Open the modal on button click (fresh interaction — can use send_modal)."""
        modal = self._modal_factory()
        await interaction.response.send_modal(modal)


# ── Extension entry point ──────────────────────────────────────────────────────


async def setup(bot: EldritchBot) -> None:
    """discord.py extension entry point — called by bot.load_extension(...)."""
    await bot.add_cog(IngestCog(bot))
