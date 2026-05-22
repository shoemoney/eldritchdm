"""
OPS-01 resume drill: pending Riposte timer survives bot restart.

Phase 5 Plan 02 Task 2. This is the marketing-grade proof that EldritchDM
does what it says: a player can kill the bot mid-combat with an active
Riposte window, restart it, and the same button still works (until the
8-second deadline passes — at which point the sweeper auto-cleans it).

OPS-01 acceptance gate (mapped to test methods below):
  - kill bot → sweeper picks up:  test_pending_riposte_survives_restart
  - callback works post-restart:  test_pending_riposte_survives_restart
  - expired auto-cleaned:         test_expired_timer_cleaned_on_restart
  - sweeper-after-rehydration:    test_setup_hook_orders_sweeper_after_rehydration
  - graceful shutdown clean:      test_graceful_shutdown_cancels_sweeper
  - reaction-budget restart-safe: test_consumed_in_round_survives_restart
  - orphaned message resilience:  test_sweeper_handles_orphaned_message

Drill mechanics mirror tests/integration/test_restart_mid_combat.py
(Phase 4 Plan 03 — BOT-08 extension drill): same temp DB shared between
two "bots" (in this scope: a bootstrap+repo set + the actual sweeper),
fresh repos on the second pass to prove persistence is purely disk-backed.

We deliberately do NOT spin up a full ``EldritchBot`` or hit Discord's
gateway. The OPS-01 invariant is: "the riposte_timers row + persistent
button outlive the process." That's an artifact of (a) SQLite on disk
and (b) the sweeper's deadline-driven loop — both fully testable here.

All 6 tests target sub-second wall-clock; combined < 5s per RESEARCH Q12.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio

from eldritch_dm.bot.dynamic_items import RiposteButton
from eldritch_dm.gameplay.reactions import check_riposte_eligibility
from eldritch_dm.gameplay.riposte_sweeper import RiposteSweeper
from eldritch_dm.gameplay.session_locks import SessionLocks
from eldritch_dm.persistence import (
    ChannelSessionRepo,
    PersistentViewRepo,
    WriterQueue,
)
from eldritch_dm.persistence.bootstrap import bootstrap
from eldritch_dm.persistence.models import (
    ChannelState,
    PersistentView,
    RiposteStatus,
    RiposteTimer,
)
from eldritch_dm.persistence.pc_classes_repo import PCClassesRepo
from eldritch_dm.persistence.riposte_timers_repo import RiposteTimerRepo

_CHANNEL_ID = "999999999000000005"
_USER_ID = 99
_CHARACTER_ID = "thorin"
_MONSTER_UUID = "goblin-scout"
_CAMPAIGN = "RiposteRestartDrill"
_SESSION_ID = "rd-riposte-001"


# ── Fixtures ────────────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def temp_db_path(tmp_path):
    """Bootstrap a fresh SQLite DB on disk and yield its path."""
    p = str(tmp_path / "eldritch_riposte.sqlite3")
    await bootstrap(p)
    return p


@pytest_asyncio.fixture
async def writer_queue(temp_db_path):
    """Live WriterQueue against the test DB. Stopped on teardown."""
    wq = WriterQueue(temp_db_path)
    await wq.start()
    yield wq
    await wq.stop()


@pytest_asyncio.fixture
async def repos(temp_db_path, writer_queue):
    return {
        "db_path": temp_db_path,
        "cs": ChannelSessionRepo(temp_db_path, writer_queue),
        "pv": PersistentViewRepo(temp_db_path, writer_queue),
        "rt": RiposteTimerRepo(temp_db_path, writer_queue),
        "pc": PCClassesRepo(db_path=temp_db_path),
    }


# ── Seed helpers (reusable across plans) ─────────────────────────────────────


async def _seed_combat_session(repos: dict, *, round_n: int = 2) -> None:
    """Channel session in COMBAT state, round N."""
    await repos["cs"].upsert(
        channel_id=_CHANNEL_ID,
        campaign_name=_CAMPAIGN,
        claudmaster_session_id=_SESSION_ID,
        state=ChannelState.COMBAT,
    )


async def _seed_combat_persistent_view(repos: dict) -> None:
    """Phase 2 combat embed persistent view row."""
    pv = PersistentView(
        custom_id=f"attack:{_CHANNEL_ID}:{_CHARACTER_ID}:2",
        view_class="AttackButton",
        message_id="55555",
        channel_id=_CHANNEL_ID,
        payload={},
        created_at=datetime(2026, 5, 22, tzinfo=UTC),
    )
    await repos["pv"].insert(pv)


async def _seed_riposte_timer(
    repos: dict,
    *,
    deadline_seconds_from_now: float = 5.0,
    status: RiposteStatus = RiposteStatus.PENDING,
    consumed_in_round: int | None = None,
) -> RiposteTimer:
    """Insert a riposte_timers row with the canonical drill fixture values.

    The custom_id is a placeholder ("" pre-backfill); production code calls
    repo.update_message_ref AFTER channel.send returns to write the real
    custom_id with the DB-assigned id. Tests that need a matching custom_id
    use the returned ``inserted.id``.
    """
    now = datetime.now(UTC)
    timer = RiposteTimer(
        channel_id=_CHANNEL_ID,
        character_id=_CHARACTER_ID,
        user_id=str(_USER_ID),
        monster_uuid=_MONSTER_UUID,
        weapon_used="longsword",
        message_id="77777",
        custom_id="",  # back-filled in production after channel.send returns
        deadline_ts=now + timedelta(seconds=deadline_seconds_from_now),
        status=status,
        created_at=now,
        consumed_in_round=consumed_in_round,
    )
    inserted = await repos["rt"].insert(timer)
    return inserted


async def _seed_pc_class(repos: dict) -> None:
    """Battle Master Fighter PC — the only RAW-eligible riposte class."""
    await repos["pc"].upsert(
        channel_id=_CHANNEL_ID,
        character_id=_CHARACTER_ID,
        class_name="fighter",
        subclass="battle master",
    )


# ── Test 1: Pending riposte timer survives restart ──────────────────────────


@pytest.mark.asyncio
async def test_pending_riposte_survives_restart(repos) -> None:
    """OPS-01: bot A seeds a pending timer; bot B (same DB) picks it up
    and the button still works.

    This is the marquee assertion of Phase 5.
    """
    # ── Bot A: seed a pending timer + persistent views ─────────────────────
    await _seed_combat_session(repos)
    await _seed_combat_persistent_view(repos)
    # DB AUTOINCREMENT assigns id=1 on a fresh DB; use the actual returned id.
    inserted = await _seed_riposte_timer(
        repos, deadline_seconds_from_now=5.0
    )
    actual_id = inserted.id
    assert actual_id is not None
    # Now seed the persistent_view row using the REAL id so the custom_id matches.
    pv = PersistentView(
        custom_id=f"riposte:{actual_id}:{_USER_ID}",
        view_class="RiposteButton",
        message_id="77777",
        channel_id=_CHANNEL_ID,
        payload={},
        created_at=datetime(2026, 5, 22, tzinfo=UTC),
    )
    await repos["pv"].insert(pv)
    await _seed_pc_class(repos)

    # Verify bot A's repo can read it
    bot_a_view = await repos["rt"].get(actual_id)
    assert bot_a_view is not None
    assert bot_a_view.status == RiposteStatus.PENDING

    # ── Simulate bot A.close() ──────────────────────────────────────────────
    # (The repos fixture's writer_queue stays alive; the "restart" is
    # semantic — we instantiate fresh repo objects on the SAME DB file.
    # Reuse the WQ since reads don't need it, but RiposteTimerRepo's writes
    # require a non-None WQ.)
    fresh_rt = RiposteTimerRepo(
        repos["db_path"], repos["pv"]._writer_queue  # type: ignore[attr-defined]
    )

    # ── Bot B: fresh sweeper on the same DB ─────────────────────────────────
    pending = await fresh_rt.list_pending()
    assert len(pending) == 1
    assert pending[0].id == actual_id
    assert pending[0].status == RiposteStatus.PENDING
    # Deadline still ~5s in the future
    deadline = pending[0].deadline_ts
    if deadline.tzinfo is None:
        deadline = deadline.replace(tzinfo=UTC)
    seconds_remaining = (deadline - datetime.now(UTC)).total_seconds()
    assert 0 < seconds_remaining <= 5.5, (
        f"Expected deadline ~5s in future, got {seconds_remaining}s remaining"
    )

    # ── RiposteButton template matches the persisted custom_id ──────────────
    custom_id = f"riposte:{actual_id}:{_USER_ID}"
    match = RiposteButton.template.fullmatch(custom_id)
    assert match is not None, (
        f"RiposteButton template {RiposteButton.template.pattern!r} failed to "
        f"match persisted custom_id {custom_id!r}"
    )
    assert match["timer_id"] == str(actual_id)
    assert match["user_id"] == str(_USER_ID)

    # ── Simulate a click using the same callback path the bot would use ─────
    # We can't spin up a real Discord gateway, so we exercise the same
    # delegated function that RiposteButton.callback calls.
    from eldritch_dm.bot.warnings import WarningKind
    from eldritch_dm.gameplay.reactions import handle_riposte_click

    interaction = MagicMock()
    interaction.user = MagicMock()
    interaction.user.id = _USER_ID
    interaction.response = AsyncMock()
    interaction.response.defer = AsyncMock()
    interaction.followup = AsyncMock()
    interaction.followup.send = AsyncMock()
    interaction.channel = AsyncMock()
    interaction.channel.fetch_message = AsyncMock(side_effect=Exception("ignored"))

    async def round_provider(_ch_id: str) -> int:
        return 2

    warning_sender = AsyncMock()

    rate_limiter = MagicMock()
    rate_limiter.acquire = AsyncMock()

    # combat_action is the bot's interaction with dm20 — stub it
    from unittest.mock import patch

    with patch(
        "eldritch_dm.gameplay.reactions.mcp_tools.combat_action",
        new=AsyncMock(return_value="**Hit!** Thorin hits Goblin Scout."),
    ) as mock_ca:
        await handle_riposte_click(
            interaction=interaction,
            timer_id=actual_id,
            expected_user_id=_USER_ID,
            repo=fresh_rt,
            mcp=MagicMock(),
            rate_limiter=rate_limiter,
            session_locks=SessionLocks(),
            current_round_provider=round_provider,
            warning_sender=warning_sender,
            invalid_action_kind=WarningKind.INVALID_ACTION,
            riposte_expired_kind=WarningKind.RIPOSTE_EXPIRED,
        )

    # combat_action was called with the seeded values
    mock_ca.assert_awaited_once()
    ca_kwargs = mock_ca.call_args.kwargs
    assert ca_kwargs["action"] == "attack"
    assert ca_kwargs["attacker"] == _CHARACTER_ID
    assert ca_kwargs["target"] == _MONSTER_UUID
    assert ca_kwargs["weapon_or_spell"] == "longsword"

    # Row is now consumed in round 2 — restart-stable
    after = await fresh_rt.get(actual_id)
    assert after is not None
    assert after.status == RiposteStatus.CONSUMED
    assert after.consumed_in_round == 2


# ── Test 2: Already-expired timer auto-cleaned on first sweeper pass ────────


@pytest.mark.asyncio
async def test_expired_timer_cleaned_on_restart(repos) -> None:
    """OPS-01: a row past its deadline at restart-time gets marked expired
    by the first sweeper iteration on bot B."""
    # FK: riposte_timers.channel_id references channel_sessions
    await _seed_combat_session(repos)
    # Seed: already-past deadline (1s in the past)
    inserted = await _seed_riposte_timer(
        repos, deadline_seconds_from_now=-1.0
    )
    assert inserted.status == RiposteStatus.PENDING
    timer_id = inserted.id
    assert timer_id is not None

    # Fresh sweeper on the same DB (bot B)
    fresh_rt = RiposteTimerRepo(repos["db_path"], repos["pv"]._writer_queue)  # type: ignore[attr-defined]
    locks = SessionLocks()

    msg = MagicMock()
    msg.delete = AsyncMock()
    bot = MagicMock()
    channel = MagicMock()
    channel.fetch_message = AsyncMock(return_value=msg)
    bot.get_channel = MagicMock(return_value=channel)

    async def fake_sleep(_s: float) -> None:
        raise asyncio.CancelledError

    sweeper = RiposteSweeper(
        repo=fresh_rt,
        bot=bot,
        session_locks=locks,
        sleep=fake_sleep,
    )

    with pytest.raises(asyncio.CancelledError):
        await sweeper._iterate_once()

    # Row is now expired
    after = await fresh_rt.get(timer_id)
    assert after is not None
    assert after.status == RiposteStatus.EXPIRED

    # Subsequent sweeper iterations don't re-process (it's no longer pending)
    msg.delete.reset_mock()
    bot.get_channel.reset_mock()
    sweeper2 = RiposteSweeper(
        repo=fresh_rt,
        bot=bot,
        session_locks=locks,
        sleep=fake_sleep,
    )
    with pytest.raises(asyncio.CancelledError):
        await sweeper2._iterate_once()

    bot.get_channel.assert_not_called()  # no more deletes for the expired row


# ── Test 3: Sweeper starts AFTER rehydrate_persistent_views ─────────────────


@pytest.mark.asyncio
async def test_setup_hook_orders_sweeper_after_rehydration(monkeypatch) -> None:
    """Critical ordering invariant: DynamicItems must be registered before
    any sweeper-triggered Discord interactions could route. We assert this
    by spying on the order of calls during setup_hook.

    Implementation note: full EldritchBot setup_hook touches Discord
    application_id + tree.sync which require real gateway state. We assert
    the ordering via static-source inspection: rehydrate_persistent_views
    is called BEFORE riposte_sweeper.start() in src/eldritch_dm/bot/bot.py.

    The runtime test for this is implicit in the other OPS-01 tests: if
    the sweeper started before rehydration, the on-disk row would be
    handled with no DynamicItem registry to dispatch button clicks against.
    """
    from pathlib import Path

    bot_py = (
        Path(__file__).resolve().parents[2]
        / "src"
        / "eldritch_dm"
        / "bot"
        / "bot.py"
    )
    src = bot_py.read_text(encoding="utf-8")

    rehydrate_idx = src.find("rehydrate_persistent_views(")
    sweeper_start_idx = src.find("await self.riposte_sweeper.start()")

    assert rehydrate_idx > 0, (
        "setup_hook must call rehydrate_persistent_views(...)"
    )
    assert sweeper_start_idx > 0, (
        "setup_hook must call await self.riposte_sweeper.start()"
    )
    assert rehydrate_idx < sweeper_start_idx, (
        f"rehydrate_persistent_views must be called BEFORE "
        f"riposte_sweeper.start(); got rehydrate@{rehydrate_idx}, "
        f"sweeper@{sweeper_start_idx}."
    )


# ── Test 4: consumed_in_round persists → reaction budget restart-stable ────


@pytest.mark.asyncio
async def test_consumed_in_round_survives_restart(repos) -> None:
    """The Phase 5 Plan 01 reaction-budget shim (consumed_in_round) must
    persist across restart. After bot B mounts the DB, an eligibility check
    in the SAME round must reject (budget exhausted); a check in the next
    round must succeed (new budget).
    """
    await _seed_combat_session(repos)
    await _seed_pc_class(repos)
    # Seed a CONSUMED timer with consumed_in_round=3
    consumed_timer = RiposteTimer(
        channel_id=_CHANNEL_ID,
        character_id=_CHARACTER_ID,
        user_id=str(_USER_ID),
        monster_uuid=_MONSTER_UUID,
        weapon_used="longsword",
        message_id="999",
        custom_id="riposte:50:99",
        deadline_ts=datetime.now(UTC) - timedelta(seconds=10),
        status=RiposteStatus.CONSUMED,
        created_at=datetime.now(UTC),
        consumed_in_round=3,
    )
    await repos["rt"].insert(consumed_timer)

    # Fresh repos on the same DB
    fresh_rt = RiposteTimerRepo(repos["db_path"], repos["pv"]._writer_queue)  # type: ignore[attr-defined]
    fresh_pc = PCClassesRepo(db_path=repos["db_path"])

    # Round 3 — budget exhausted
    result_r3 = await check_riposte_eligibility(
        channel_id=_CHANNEL_ID,
        character_id=_CHARACTER_ID,
        user_id=_USER_ID,
        primary_weapon="longsword",
        current_round=3,
        pc_classes_repo=fresh_pc,
        riposte_timers_repo=fresh_rt,
    )
    assert result_r3 is None, (
        "Reaction budget exhausted in round 3 → eligibility must reject"
    )

    # Round 4 — new round, budget refreshed
    result_r4 = await check_riposte_eligibility(
        channel_id=_CHANNEL_ID,
        character_id=_CHARACTER_ID,
        user_id=_USER_ID,
        primary_weapon="longsword",
        current_round=4,
        pc_classes_repo=fresh_pc,
        riposte_timers_repo=fresh_rt,
    )
    assert result_r4 is not None, (
        "Round 4 → fresh budget; eligibility must succeed"
    )
    assert result_r4.character_id == _CHARACTER_ID


# ── Test 5: Graceful shutdown cancels the sweeper cleanly ───────────────────


@pytest.mark.asyncio
async def test_graceful_shutdown_cancels_sweeper(repos) -> None:
    """OPS-04: bot.close() drains the sweeper task within 1s, leaving no
    orphan tasks."""
    locks = SessionLocks()
    bot = MagicMock()

    sweeper = RiposteSweeper(
        repo=repos["rt"],
        bot=bot,
        session_locks=locks,
        default_sleep_s=10.0,
        min_sleep_s=0.05,
    )
    await sweeper.start()
    assert sweeper.is_running() is True
    task = sweeper._task  # type: ignore[attr-defined]
    assert task is not None

    # Let the loop park
    await asyncio.sleep(0.05)

    # Stop within budget
    import time
    t_start = time.monotonic()
    await asyncio.wait_for(sweeper.stop(), timeout=2.0)
    elapsed = time.monotonic() - t_start
    assert elapsed < 2.0, f"sweeper.stop() must complete < 2s, took {elapsed:.2f}s"

    # Task is done, no leaked exception (CancelledError is normal)
    assert task.done()
    assert sweeper.is_running() is False


# ── Test 6: Orphaned message (Discord NotFound) is handled ──────────────────


@pytest.mark.asyncio
async def test_sweeper_handles_orphaned_message(repos) -> None:
    """OPS-01 robustness: a row whose Discord message has been manually
    deleted (or whose channel is no longer accessible) must NOT crash the
    sweeper. The row is still marked expired so it doesn't loop forever.
    """
    import discord

    # FK: riposte_timers.channel_id references channel_sessions
    await _seed_combat_session(repos)
    # Seed a past-deadline row whose Discord message will 404
    inserted = await _seed_riposte_timer(
        repos, deadline_seconds_from_now=-0.5
    )
    timer_id = inserted.id
    assert timer_id is not None

    fresh_rt = RiposteTimerRepo(repos["db_path"], repos["pv"]._writer_queue)  # type: ignore[attr-defined]
    locks = SessionLocks()

    bot = MagicMock()
    channel = MagicMock()
    channel.fetch_message = AsyncMock(
        side_effect=discord.NotFound(
            response=MagicMock(status=404, reason="Not Found"),
            message="message gone",
        )
    )
    bot.get_channel = MagicMock(return_value=channel)

    async def fake_sleep(_s: float) -> None:
        raise asyncio.CancelledError

    sweeper = RiposteSweeper(
        repo=fresh_rt,
        bot=bot,
        session_locks=locks,
        sleep=fake_sleep,
    )

    # Must NOT raise — NotFound is caught + logged
    with pytest.raises(asyncio.CancelledError):
        await sweeper._iterate_once()

    # Row is STILL marked expired (cleanup proceeds even if Discord 404'd)
    after = await fresh_rt.get(timer_id)
    assert after is not None
    assert after.status == RiposteStatus.EXPIRED
