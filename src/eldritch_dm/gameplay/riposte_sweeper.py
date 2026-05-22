"""
RiposteSweeper — background asyncio.Task that expires past-deadline rows.

Phase 5 Plan 02. RESEARCH Pattern 4 (verbatim) + SessionLocks integration.

Why this exists
---------------
``riposte_timers`` rows are written with a ``deadline_ts`` ~8 seconds in the
future. Without a sweeper, an expired row would sit forever as ``pending``
with a stale Discord button surface still attached. The sweeper:

  1. Loops on ``repo.list_pending()`` (uses ``idx_riposte_pending_deadline``).
  2. For each row whose ``deadline_ts <= now()``:
     a. Acquires ``session_locks.lock_for("riposte", row.channel_id)``.
     b. Calls ``repo.mark_expired(id)`` — SQL is conditional on
        ``status='pending'`` (idempotent + correct under click-race).
     c. Best-effort deletes the public Discord message
        (``bot.get_channel → channel.fetch_message → message.delete``).
  3. Sleeps until ``min(next_deadline - now, default_sleep_s)``, floored to
     ``min_sleep_s``. With ~8s Riposte TTLs and a 30s default, the practical
     sleep is bounded above by 8s; an empty queue sleeps the full 30s.

Why the lock
------------
The click callback (``handle_riposte_click``) reads-then-mark_consumed under
the SAME ``riposte:{channel_id}`` lock. So a click at T=7.999s and a sweeper
sweep at T=8.000s are serialized: whichever wins the lock, the loser's UPDATE
hits a row already in ``consumed`` or ``expired`` state. ``mark_expired`` is
``WHERE id=? AND status='pending'`` → 0 rows affected on a race (correct).
``mark_consumed_with_round`` unconditionally writes both columns — but the
lock means it never runs concurrently with mark_expired.

Anti-patterns we explicitly REJECT
----------------------------------
- Polling oMLX / dm20 in the sweeper. oMLX downtime must not delay timer
  expiry (RESEARCH anti-pattern callout). The sweeper only touches SQLite
  and Discord HTTP.
- ``View(timeout=8.0)`` for deadline enforcement. The View is persistent
  (``timeout=None``); deadline is enforced exclusively here.
- Per-row asyncio.Tasks. One sweeper task serves all channels — minimal
  scheduler pressure, deterministic shutdown.

Import-linter discipline
------------------------
This module lives under ``gameplay/``. It MUST NOT import from ``bot/``.
The ``bot``-typed handle is duck-typed as ``Any`` so we can call
``.get_channel(int)``. Discord exceptions (``NotFound``, ``Forbidden``,
``HTTPException``) come from the ``discord`` package which is unrelated
to our internal ``bot/`` module.

Lifecycle
---------
``await sweeper.start()`` — create the asyncio.Task.
``await sweeper.stop()`` — cancel + drain. Suppresses CancelledError so
callers can just ``await``. Plan 02 decision: stop() cancels (does NOT
flush in-flight mark_expired calls). Rationale: clean shutdown semantics
and no risk of hanging on a slow Discord delete. Pending rows survive
across restart and get cleaned up on the next bot's first sweep.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import discord

from eldritch_dm.gameplay.session_locks import SessionLocks
from eldritch_dm.logging import get_logger

if TYPE_CHECKING:
    from eldritch_dm.persistence.riposte_timers_repo import RiposteTimerRepo


_log = get_logger(__name__)


def _utc_now() -> datetime:
    return datetime.now(UTC)


class RiposteSweeper:
    """Background task that expires past-deadline riposte_timers rows.

    Phase 5 Plan 02 (RESEARCH Pattern 4).

    Args:
        repo: RiposteTimerRepo for list_pending + mark_expired.
        bot: Anything with ``.get_channel(int) -> discord.TextChannel | None``.
            Duck-typed to keep gameplay layer free of bot imports.
        session_locks: The shared SessionLocks registry. Sweeper acquires
            ``"riposte:{channel_id}"`` before mark_expired.
        default_sleep_s: Sleep when no pending rows or next deadline > this.
            Default 30s (RESEARCH Pattern 4).
        min_sleep_s: Floor on sleep duration to avoid hot-loop. Default 0.1s.
        clock: Injectable now-function for deterministic tests.
        sleep: Injectable sleep coroutine for deterministic tests.
        log: structlog logger; default module logger.
    """

    def __init__(
        self,
        *,
        repo: RiposteTimerRepo,
        bot: Any,
        session_locks: SessionLocks,
        default_sleep_s: float = 30.0,
        min_sleep_s: float = 0.1,
        clock: Callable[[], datetime] = _utc_now,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        log: Any = None,
    ) -> None:
        self._repo = repo
        self._bot = bot
        self._session_locks = session_locks
        self._default_sleep_s = float(default_sleep_s)
        self._min_sleep_s = float(min_sleep_s)
        self._clock = clock
        self._sleep = sleep
        self._log = (log or _log).bind(component="riposte_sweeper")
        self._task: asyncio.Task[None] | None = None

    # ── Lifecycle ────────────────────────────────────────────────────────────

    async def start(self) -> None:
        """Create the background asyncio.Task.

        Idempotent: calling twice is a no-op.
        """
        if self._task is not None and not self._task.done():
            return
        self._task = asyncio.create_task(self._run(), name="riposte_sweeper")
        self._log.info("riposte_sweeper_started", default_sleep_s=self._default_sleep_s)

    async def stop(self) -> None:
        """Cancel the background task and await clean shutdown.

        Suppresses CancelledError so the caller can just ``await``.
        Plan 02 decision: cancel (not flush) — see module docstring.
        """
        task = self._task
        if task is None:
            return
        if not task.done():
            task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        except Exception:  # noqa: BLE001
            # Sweeper task already logged the exception inside _run().
            self._log.warning("riposte_sweeper_stop_caught_exception")
        finally:
            self._task = None
            self._log.info("riposte_sweeper_stopped")

    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    # ── Loop body ────────────────────────────────────────────────────────────

    async def _run(self) -> None:
        """Top-level loop. Catches and logs unexpected errors per iteration."""
        while True:
            try:
                await self._iterate_once()
            except asyncio.CancelledError:
                raise
            # If _iterate_once exits cleanly we just continue — its own sleep
            # already paced us.

    async def _iterate_once(self) -> None:
        """One sweep + one sleep.

        Steps:
          1. list_pending (read-only — no lock needed, no WriterQueue contention).
          2. For each past-deadline row: acquire session lock → mark_expired →
             best-effort message delete.
          3. Compute sleep:
             - No pending → default_sleep_s
             - Smallest future deadline → max(min_sleep, deadline - now)
             - default_sleep_s cap on the wait so we don't sleep forever.
          4. await sleep.

        Cancellation: re-raised cleanly (cooperative shutdown).
        Unexpected exceptions in the loop body: caught, logged at EXCEPTION,
        and replaced with a defensive 1.0s sleep before continuing.
        """
        try:
            pending = await self._repo.list_pending()
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            self._log.exception("riposte_sweeper_list_pending_error")
            await self._sleep(1.0)
            return

        now = self._clock()
        # Process past-deadline rows
        future_rows: list[Any] = []
        for row in pending:
            deadline = row.deadline_ts
            if deadline.tzinfo is None:
                deadline = deadline.replace(tzinfo=UTC)
            if deadline <= now:
                await self._expire_row(row)
            else:
                future_rows.append(row)

        # Compute next sleep
        sleep_s = self._compute_sleep_seconds(future_rows, now)
        await self._sleep(sleep_s)

    async def _expire_row(self, row: Any) -> None:
        """Mark one row expired under the session lock + delete its message.

        SessionLocks invariant: lock acquired BEFORE mark_expired so this is
        serialized against handle_riposte_click for the same channel.

        Discord HTTP errors are caught + logged; the row is still marked
        expired (T-05-13/T-05-15) so the sweeper doesn't loop on the same row.
        """
        channel_id = str(row.channel_id)
        bound = self._log.bind(
            timer_id=getattr(row, "id", None),
            channel_id=channel_id,
            message_id=getattr(row, "message_id", None),
        )
        try:
            async with self._session_locks.lock_for("riposte", channel_id):
                try:
                    await self._repo.mark_expired(row.id)
                except asyncio.CancelledError:
                    raise
                except Exception:  # noqa: BLE001
                    bound.exception("riposte_sweeper_mark_expired_error")
                    # Fall through to attempt the delete anyway? No: if the
                    # write failed, don't poke Discord — we'd loop next sweep.
                    return
                # Best-effort message delete
                await self._delete_message(row, bound)
        except asyncio.CancelledError:
            raise

    async def _delete_message(self, row: Any, bound_log: Any) -> None:
        """Best-effort fetch+delete of the public Riposte button message.

        All Discord HTTP errors are caught. Non-fatal — the row is already
        marked expired by the time this runs.
        """
        message_id_raw = getattr(row, "message_id", "") or ""
        if not message_id_raw:
            bound_log.debug("riposte_message_delete_skipped_no_id")
            return
        try:
            channel_id_int = int(row.channel_id)
            message_id_int = int(message_id_raw)
        except (TypeError, ValueError):
            bound_log.warning("riposte_message_delete_bad_ids")
            return
        try:
            channel = self._bot.get_channel(channel_id_int)
        except Exception:  # noqa: BLE001
            bound_log.warning("riposte_message_delete_get_channel_failed")
            return
        if channel is None:
            bound_log.debug("riposte_message_delete_skipped_no_channel")
            return
        try:
            msg = await channel.fetch_message(message_id_int)
            await msg.delete()
            bound_log.debug("riposte_message_deleted")
        except discord.NotFound:
            bound_log.debug("riposte_message_delete_skipped_not_found")
        except discord.Forbidden:
            bound_log.warning("riposte_message_delete_forbidden")
        except discord.HTTPException:
            bound_log.warning("riposte_message_delete_http_error")
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            bound_log.exception("riposte_message_delete_unexpected_error")

    def _compute_sleep_seconds(self, future_rows: list[Any], now: datetime) -> float:
        """Return sleep duration: capped at default_sleep_s, floored at min_sleep_s."""
        if not future_rows:
            return self._default_sleep_s
        # Find earliest deadline
        earliest: datetime | None = None
        for row in future_rows:
            d = row.deadline_ts
            if d.tzinfo is None:
                d = d.replace(tzinfo=UTC)
            if earliest is None or d < earliest:
                earliest = d
        if earliest is None:
            return self._default_sleep_s
        seconds_until = (earliest - now).total_seconds()
        # Clamp to [min_sleep_s, default_sleep_s]
        return max(self._min_sleep_s, min(self._default_sleep_s, seconds_until))
