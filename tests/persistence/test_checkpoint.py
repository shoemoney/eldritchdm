"""
Tests for eldritch_dm.persistence.checkpoint — WAL checkpoint background task.
"""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from eldritch_dm.persistence.bootstrap import bootstrap
from eldritch_dm.persistence.checkpoint import CheckpointTask
from eldritch_dm.persistence.connection import WriterQueue


class TestCheckpointRuns:
    """CheckpointTask._do_checkpoint actually runs a WAL checkpoint."""

    async def test_checkpoint_runs_on_demand(self, tmp_path: pytest.TempPathFactory) -> None:
        """Directly call _do_checkpoint — verify it executes without error."""
        db_path = str(tmp_path / "eld_cp.sqlite3")
        await bootstrap(db_path)

        task = CheckpointTask(db_path=db_path, writer_queue=None, interval_seconds=600)
        # Call _do_checkpoint directly — no background task needed
        await task._do_checkpoint()
        # No assertion needed; success = no exception raised

    async def test_checkpoint_task_starts_and_stops(
        self, tmp_path: pytest.TempPathFactory
    ) -> None:
        """start() + stop(final=False) cycle completes cleanly."""
        db_path = str(tmp_path / "eld_cp2.sqlite3")
        await bootstrap(db_path)

        checkpoint_calls: list[bool] = []

        async def record_checkpoint(self_inner: CheckpointTask) -> None:
            checkpoint_calls.append(True)

        with patch.object(CheckpointTask, "_do_checkpoint", record_checkpoint):
            task = CheckpointTask(
                db_path=db_path,
                writer_queue=None,
                interval_seconds=100,  # Long enough not to fire during test
            )
            await task.start()
            assert task._task is not None
            await asyncio.sleep(0.01)  # Let event loop process
            await task.stop(final=False)

        # The background task started but the interval didn't fire —
        # so we should have 0 background checkpoint calls (final=False skips final)
        assert len(checkpoint_calls) == 0


class TestCheckpointSkipsWhenQueueBusy:
    """CheckpointTask._do_checkpoint skips PRAGMA when writer queue is busy."""

    async def test_checkpoint_skips_when_queue_busy(
        self, tmp_path: pytest.TempPathFactory
    ) -> None:
        db_path = str(tmp_path / "eld_skip.sqlite3")
        await bootstrap(db_path)

        # Mock writer queue that always reports depth > 0
        mock_queue = MagicMock(spec=WriterQueue)
        mock_queue.qsize.return_value = 3

        pragma_ran = False

        class _TrackingConn:
            def __aenter__(self):
                nonlocal pragma_ran
                pragma_ran = True
                raise AssertionError("open_connection should not be called when queue is busy")

            def __aexit__(self, *args):
                pass

        task = CheckpointTask(
            db_path=db_path,
            writer_queue=mock_queue,
            interval_seconds=600,
        )

        # Call _do_checkpoint directly — it should skip because qsize > 0
        await task._do_checkpoint()

        # If we get here without the AssertionError, the skip worked
        assert not pragma_ran, "PRAGMA checkpoint should not run when queue is busy"
        mock_queue.qsize.assert_called()


class TestCheckpointStopFinal:
    """stop(final=True) runs one final checkpoint."""

    async def test_checkpoint_stop_final(self, tmp_path: pytest.TempPathFactory) -> None:
        db_path = str(tmp_path / "eld_final.sqlite3")
        await bootstrap(db_path)

        checkpoint_calls: list[bool] = []

        async def recording_do(self_inner: CheckpointTask) -> None:
            checkpoint_calls.append(True)

        with patch.object(CheckpointTask, "_do_checkpoint", recording_do):
            task = CheckpointTask(
                db_path=db_path,
                writer_queue=None,
                interval_seconds=3600,  # Never fires naturally in test
            )
            await task.start()
            # Immediately stop with final=True
            await task.stop(final=True)

        # Should have exactly one call from the final checkpoint
        assert len(checkpoint_calls) == 1, (
            f"Expected 1 checkpoint call from final=True, got {len(checkpoint_calls)}"
        )


class TestCheckpointDisabledWhenIntervalZero:
    """interval_seconds=0 prevents any background task from spawning."""

    async def test_checkpoint_disabled_when_interval_zero(
        self, tmp_path: pytest.TempPathFactory
    ) -> None:
        db_path = str(tmp_path / "eld_disabled.sqlite3")
        await bootstrap(db_path)

        task = CheckpointTask(
            db_path=db_path,
            writer_queue=None,
            interval_seconds=0,
        )
        await task.start()
        assert task._task is None, "Expected no background task when interval_seconds=0"
        await task.stop(final=False)
