"""
Riposte reaction eligibility + button surfacing + click handling.

This module is the single source of truth for the Phase 5 Riposte feature
mechanics. It is called from two places:
  - `gameplay/monster_driver.py` on a monster-attack miss/nat1: calls
    `check_riposte_eligibility` and (if eligible) `surface_riposte_button`.
  - `bot/dynamic_items.RiposteButton.callback`: delegates to
    `handle_riposte_click` for the gate→combat_action→consume sequence.

Design decisions (Phase 5 Plan 01):
  D-A — `AttackButton._maybe_surface_riposte` is DELETED (wrong RAW path).
  D-B — MonsterDriver picks uniformly-random eligible PC targets. Smart
        Claudmaster-driven targeting is deferred to v2 (REQUIREMENTS REACT-*).
  D-C — Strict RAW: only Battle Master Fighter (PHB Riposte). The seam below
        for v2 YAML config is documented but NOT plumbed in v1.

Public-message + permission-gate (RESEARCH Pattern 3, finding #8):
  We post the Riposte button as a NON-ephemeral channel message. Ephemeral
  followups die after 15 minutes and CANNOT be re-edited from a fresh bot
  process — which would break COMBAT-11 restart-survival. The permission gate
  is enforced inside `handle_riposte_click` (interaction.user.id == row.user_id).

Reaction budget (RESEARCH Q1):
  dm20 has no native reaction tracking. We shim it via the additive
  `riposte_timers.consumed_in_round` column added in Phase 5 Plan 01
  bootstrap migration. Eligibility rejects when ANY row with
  `consumed_in_round == current_round` exists for the PC.

Subclass drift (RESEARCH Pitfall 5):
  We trust the `pc_classes` table at eligibility-check time. If a PC levels
  up mid-session, the row may go stale. v2 may re-sync via
  `validate_character_rules` at eligibility-check time; not in v1 scope.

Plan 02 lock seam:
  `handle_riposte_click` performs a read-then-mark sequence that is racy
  against the sweeper at the deadline boundary. Plan 02 wraps it in a
  per-channel asyncio.Lock keyed `riposte:{channel_id}`. Grep for the
  `PLAN-02-LOCK-SEAM` marker to find the exact wrap point.

Import-linter discipline:
  This module lives under `gameplay/` so it CANNOT import from `bot/`. The
  `bot/warnings.send_warning` and `bot/dynamic_items.RiposteButton` are
  passed in as callables (`warning_sender`, `button_factory`) so the caller
  in `bot/dynamic_items.py` wires them up at call time.

Phase 5 Plan 01.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any, Awaitable, Callable

import discord

from eldritch_dm.logging import get_logger
from eldritch_dm.mcp import tools as mcp_tools
from eldritch_dm.persistence.models import RiposteStatus, RiposteTimer

if TYPE_CHECKING:
    from eldritch_dm.persistence.pc_classes_repo import PCClassesRepo
    from eldritch_dm.persistence.riposte_timers_repo import RiposteTimerRepo

log = get_logger(__name__)

# ── Eligibility set (D-C — strict RAW) ────────────────────────────────────────
#
# Only Battle Master Fighter has the RAW Riposte maneuver. CONTEXT.md D-04
# previously implied Swashbuckler was on this list; that is INCORRECT —
# Swashbuckler's "Fancy Footwork" is not Riposte (no reaction-based melee
# counter-attack). Plan 01 ships RAW only.
#
# TODO(v2): Make this set configurable via a YAML file so homebrew DMs can
# extend it (e.g. add Brute / a homebrew "Counter-Striker" archetype). The
# YAML loader should normalize entries via the same lowercase + whitespace
# collapse rules used by PCClassesRepo so comparisons remain stable.
# See REQUIREMENTS REACT-* family for v2 work items.
ELIGIBLE_CLASS_SUBCLASSES: frozenset[tuple[str, str]] = frozenset(
    {
        ("fighter", "battle master"),
    }
)


# ── Eligibility result ────────────────────────────────────────────────────────


@dataclass(frozen=True)
class RiposteEligibility:
    """Returned by `check_riposte_eligibility` when a PC may riposte.

    Attributes:
        character_id: dm20 character UUID for the PC.
        user_id: Discord user snowflake (int) of the PC's player.
        primary_weapon: Weapon name to pass back into combat_action as
            `weapon_or_spell` on a successful click. None when not provided.
    """

    character_id: str
    user_id: int
    primary_weapon: str | None


# ── Eligibility check ─────────────────────────────────────────────────────────


async def check_riposte_eligibility(
    *,
    channel_id: str,
    character_id: str,
    user_id: int,
    primary_weapon: str | None,
    current_round: int,
    pc_classes_repo: PCClassesRepo,
    riposte_timers_repo: RiposteTimerRepo,
) -> RiposteEligibility | None:
    """Return RiposteEligibility if the PC may riposte THIS round, else None.

    Rules (Phase 5 Plan 01):
      1. PC must have a row in pc_classes (was ingested with class+subclass).
      2. (class_name, subclass) must be in ELIGIBLE_CLASS_SUBCLASSES.
      3. No existing pending row for (channel_id, character_id) — would-be
         duplicate riposte while one is already open.
      4. No row with consumed_in_round == current_round — reaction-budget
         shim (dm20 has no native reaction tracking).

    Args:
        channel_id: Discord channel snowflake string.
        character_id: dm20 character UUID.
        user_id: Discord user snowflake (int) for the PC's player.
        primary_weapon: Weapon the PC will riposte with (echoed back on
            successful click). None when unknown.
        current_round: Current combat round number (for budget enforcement).
        pc_classes_repo: PCClassesRepo for the (class, subclass) lookup.
        riposte_timers_repo: RiposteTimerRepo for existing-timer queries.

    Returns:
        RiposteEligibility if eligible; None otherwise.
    """
    info = await pc_classes_repo.get(channel_id, character_id)
    if info is None:
        # PC was never ingested via Phase 5 path (pre-migration character) —
        # silent skip. Eligibility-check failure is NOT a bug.
        return None

    key = (info.class_name, info.subclass)
    if key not in ELIGIBLE_CLASS_SUBCLASSES:
        return None

    timers = await riposte_timers_repo.list_for_character(channel_id, character_id)
    for t in timers:
        if t.status == RiposteStatus.PENDING:
            return None  # already has an open riposte window
        if t.consumed_in_round is not None and t.consumed_in_round == current_round:
            return None  # reaction budget exhausted this round

    return RiposteEligibility(
        character_id=character_id,
        user_id=user_id,
        primary_weapon=primary_weapon,
    )


# ── Surface button ────────────────────────────────────────────────────────────


async def surface_riposte_button(
    *,
    channel: Any,  # discord.TextChannel — Any for AsyncMock support
    eligibility: RiposteEligibility,
    monster_uuid: str | None,
    round_number: int,
    channel_id: str,
    repo: RiposteTimerRepo,
    button_factory: Callable[[int, int], discord.ui.Item],
    ttl_seconds: int,
    log: Any = log,
) -> int:
    """Insert a pending riposte_timers row + post the public Riposte button.

    Flow (RESEARCH Pattern 3 + Pitfall 1):
      1. Insert a row with placeholder message_id="" and a temporary deadline
         (NOW + ttl_seconds). We need the row id to embed in the custom_id.
      2. Build a persistent View (`timeout=None`) wrapping a Riposte button
         constructed via the caller-supplied `button_factory(timer_id, user_id)`.
         The factory pattern keeps `gameplay/` free of `bot/` imports.
      3. Send a public channel message that pings <@user_id>.
      4. Recompute deadline_ts = datetime.now(UTC) + ttl_seconds AFTER
         channel.send returns (Pitfall 1: Discord API latency would otherwise
         consume part of the TTL).
      5. Atomically back-fill message_id, custom_id, deadline_ts via
         repo.update_message_ref.

    Returns:
        The new timer_id (int) — useful for tests and instrumentation.
    """
    now = datetime.now(UTC)
    temp_deadline = now + timedelta(seconds=ttl_seconds)

    # Step 1: insert with placeholder message_id; custom_id is also placeholder
    # because we don't have the row id yet. We'll back-fill all three below.
    placeholder = RiposteTimer(
        channel_id=channel_id,
        character_id=eligibility.character_id,
        user_id=str(eligibility.user_id),
        monster_uuid=monster_uuid,
        weapon_used=eligibility.primary_weapon,
        message_id="",  # back-filled after channel.send
        custom_id="",  # back-filled after row id known
        deadline_ts=temp_deadline,
        status=RiposteStatus.PENDING,
        created_at=now,
        consumed_in_round=None,
    )
    inserted = await repo.insert(placeholder)
    timer_id = inserted.id
    assert timer_id is not None, "RiposteTimerRepo.insert must assign id"

    # Step 2: construct persistent View around the caller-supplied button.
    button = button_factory(timer_id, eligibility.user_id)
    view = discord.ui.View(timeout=None)  # sweeper owns deadline, NOT the View
    view.add_item(button)

    # Step 3: post public message with mention (NOT ephemeral — restart-survival).
    content = (
        f"⚔️ <@{eligibility.user_id}> — RIPOSTE opportunity! "
        f"You have {ttl_seconds}s to counter-attack."
    )
    message = await channel.send(content=content, view=view)

    # Step 4 (Pitfall 1): recompute the deadline AFTER channel.send returns so
    # the TTL accounts for actual Discord API latency, not the pre-send guess.
    real_deadline = datetime.now(UTC) + timedelta(seconds=ttl_seconds)

    # Step 5: back-fill the row
    message_id = str(getattr(message, "id", ""))
    real_custom_id = f"riposte:{timer_id}:{eligibility.user_id}"
    await repo.update_message_ref(
        timer_id,
        message_id=message_id,
        custom_id=real_custom_id,
        deadline_ts=real_deadline,
    )

    log.info(
        "riposte_button_surfaced",
        timer_id=timer_id,
        channel_id=channel_id,
        character_id=eligibility.character_id,
        user_id=eligibility.user_id,
        monster_uuid=monster_uuid,
        round_number=round_number,
        deadline_ts=real_deadline.isoformat(),
    )
    return timer_id


# ── Click handler ─────────────────────────────────────────────────────────────


async def handle_riposte_click(
    *,
    interaction: discord.Interaction,
    timer_id: int,
    expected_user_id: int,
    repo: RiposteTimerRepo,
    mcp: Any,
    rate_limiter: Any,  # ChannelRateLimiter — Any to avoid hard dep
    current_round_provider: Callable[[str], Awaitable[int]],
    warning_sender: Callable[..., Awaitable[None]],
    invalid_action_kind: Any,
    riposte_expired_kind: Any,
    log: Any = log,
) -> None:
    """Run the gate-and-dispatch sequence for a RiposteButton click.

    PLAN-02-LOCK-SEAM: replace status check with `async with session_locks.acquire("riposte", channel_id):` wrapper
    Plan 02 will wrap the read-then-mark sequence below in a per-channel
    asyncio.Lock so concurrent clicks (or a race with the background sweeper)
    cannot double-consume the same row. Plan 01 ships the correctness path
    via a status-check; Plan 02 hardens it.

    Branching:
      - Wrong user → ephemeral INVALID_ACTION warning; row untouched.
      - Row missing / status != pending → RIPOSTE_EXPIRED warning.
      - deadline_ts < now → mark expired ourselves, RIPOSTE_EXPIRED warning,
        best-effort delete the public message.
      - Otherwise: rate_limiter.acquire → combat_action(attacker=PC,
        target=monster_uuid, weapon_or_spell=weapon_used) →
        mark_consumed_with_round(current_round) → delete public message →
        ephemeral "✅ Riposte!" followup.

    Dependency injection (import-linter discipline):
      `warning_sender` is `bot.warnings.send_warning`. `invalid_action_kind`
      and `riposte_expired_kind` are the corresponding `WarningKind` values
      passed in from `bot/dynamic_items.py` so `gameplay/` stays free of
      `bot/` imports.

    The handler assumes the caller has already deferred the interaction
    (RiposteButton.callback does `await interaction.response.defer(ephemeral=True)`
    as its first line, per EDM001).
    """
    bound_log = log.bind(
        timer_id=timer_id,
        expected_user_id=expected_user_id,
        user_id=getattr(interaction.user, "id", None),
    )

    # Permission gate — only the targeted player can riposte
    actual_user_id = getattr(interaction.user, "id", None)
    if actual_user_id is None or int(actual_user_id) != int(expected_user_id):
        bound_log.warning("riposte_wrong_user_rejected")
        await warning_sender(
            interaction,
            invalid_action_kind,
            reason="Only the targeted player can Riposte.",
        )
        return

    # Load the row
    row = await repo.get(timer_id)
    if row is None:
        bound_log.warning("riposte_row_missing")
        await warning_sender(interaction, riposte_expired_kind)
        return

    if row.status != RiposteStatus.PENDING:
        bound_log.info("riposte_already_resolved", status=str(row.status))
        await warning_sender(interaction, riposte_expired_kind)
        return

    # Late click — deadline passed but sweeper hasn't marked it yet
    now = datetime.now(UTC)
    deadline = row.deadline_ts
    if deadline.tzinfo is None:
        deadline = deadline.replace(tzinfo=UTC)
    if deadline < now:
        bound_log.info("riposte_late_click_self_expire")
        try:
            await repo.mark_expired(timer_id)
        except Exception:  # noqa: BLE001
            bound_log.warning("riposte_mark_expired_failed")
        # Best-effort delete the public message
        try:
            if row.message_id and interaction.channel is not None:
                msg = await interaction.channel.fetch_message(int(row.message_id))
                await msg.delete()
        except Exception:  # noqa: BLE001
            bound_log.debug("riposte_public_message_delete_failed")
        await warning_sender(interaction, riposte_expired_kind)
        return

    # Successful click path
    current_round = await current_round_provider(row.channel_id)

    if rate_limiter is not None:
        await rate_limiter.acquire(row.channel_id)

    try:
        await mcp_tools.combat_action(
            mcp,
            action="attack",
            attacker=row.character_id,
            target=row.monster_uuid or "",
            weapon_or_spell=row.weapon_used,
        )
    except Exception:  # noqa: BLE001
        bound_log.exception("riposte_combat_action_error")
        await warning_sender(interaction, riposte_expired_kind)
        return

    try:
        await repo.mark_consumed_with_round(timer_id, current_round)
    except Exception:  # noqa: BLE001
        bound_log.exception("riposte_mark_consumed_error")
        # The combat_action already fired; we still owe the user a UI response.
        await interaction.followup.send(content="⚔️ Riposte! (state save failed)", ephemeral=True)
        return

    # Best-effort delete the public message — riposte resolved
    try:
        if row.message_id and interaction.channel is not None:
            msg = await interaction.channel.fetch_message(int(row.message_id))
            await msg.delete()
    except Exception:  # noqa: BLE001
        bound_log.debug("riposte_public_message_delete_failed_post_success")

    bound_log.info(
        "riposte_consumed",
        channel_id=row.channel_id,
        character_id=row.character_id,
        monster_uuid=row.monster_uuid,
        consumed_in_round=current_round,
    )
    await interaction.followup.send(content="⚔️ Riposte!", ephemeral=True)
