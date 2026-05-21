"""
EldritchDM WAL checkpoint background task.

Periodically runs PRAGMA wal_checkpoint(TRUNCATE) to keep the WAL file from
growing unboundedly.  Skips the checkpoint if the WriterQueue has pending
writes (D-21) to avoid interfering with active writes.

Lifecycle (D-22):
    1. CheckpointTask.start() → spawns background task
    2. Background task: sleep interval → check qsize → checkpoint → repeat
    3. CheckpointTask.stop(final=True) → cancel + one final checkpoint

An interval_seconds of 0 disables the task (no background task spawned).
"""

from __future__ import annotations

import asyncio

from eldritch_dm.logging import get_logger
from eldritch_dm.persistence.connection import WriterQueue, open_connection

log = get_logger(__name__)


class CheckpointTask:
    """Periodic WAL checkpoint background task.

    Args:
        db_path: Path to the SQLite database file.
        writer_queue: The WriterQueue; used to check pending write depth.
            Pass None to skip the qsize check (always checkpoint).
        interval_seconds: Seconds between checkpoint runs.
            0 = disabled (no background task started).
    """

    def __init__(
        self,
        db_path: str,
        writer_queue: WriterQueue | None,
        interval_seconds: int = 600,
    ) -> None:
        self._db_path = db_path
        self._writer_queue = writer_queue
        self._interval_seconds = interval_seconds
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        """Start the periodic checkpoint background task.

        No-op if interval_seconds == 0 (disabled).
        """
        if self._interval_seconds == 0:
            log.debug("checkpoint_task_disabled", interval_seconds=0)
            return
        self._task = asyncio.get_event_loop().create_task(
            self._run(), name="CheckpointTask._run"
        )
        log.debug("checkpoint_task_started", interval_seconds=self._interval_seconds)

    async def _run(self) -> None:
        """Main loop: sleep → optionally checkpoint → repeat."""
        while True:
            try:
                await asyncio.sleep(self._interval_seconds)
            except asyncio.CancelledError:
                break

            await self._do_checkpoint()

    async def _do_checkpoint(self) -> None:
        """Run PRAGMA wal_checkpoint(TRUNCATE) unless the writer queue is busy."""
        if self._writer_queue is not None and self._writer_queue.qsize() > 0:
            log.debug(
                "checkpoint_skipped_queue_busy",
                q_depth=self._writer_queue.qsize(),
            )
            return

        try:
            async with open_connection(self._db_path) as conn:
                cursor = await conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                row = await cursor.fetchone()
                # Returns (busy, log, checkpointed)
                log.info(
                    "wal_checkpoint",
                    mode="TRUNCATE",
                    busy=row[0] if row else None,
                    log_frames=row[1] if row else None,
                    checkpointed_frames=row[2] if row else None,
                )
        except Exception as exc:  # noqa: BLE001
            log.error("checkpoint_error", error=str(exc))

    async def stop(self, final: bool = True) -> None:
        """Stop the checkpoint task.

        Args:
            final: If True, run one final checkpoint after cancelling the task.
        """
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
            log.debug("checkpoint_task_stopped")

        if final:
            log.debug("checkpoint_final_run")
            await self._do_checkpoint()
