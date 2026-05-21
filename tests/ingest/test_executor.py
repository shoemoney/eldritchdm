"""Unit tests for eldritch_dm.ingest.executor."""

from __future__ import annotations

import asyncio

import pytest

from eldritch_dm.ingest.executor import IngestExecutor, get_executor


class TestIngestExecutor:
    async def test_run_sync_returns_value(self):
        """run_sync should execute a blocking callable and return its result."""
        executor = IngestExecutor(max_workers=1)
        result = await executor.run_sync(lambda: 42)
        assert result == 42
        executor.shutdown(wait=False)

    async def test_run_sync_with_args(self):
        """run_sync should forward positional arguments to the callable."""
        executor = IngestExecutor(max_workers=1)
        result = await executor.run_sync(lambda x, y: x + y, 3, 7)
        assert result == 10
        executor.shutdown(wait=False)

    async def test_run_sync_runs_in_thread(self):
        """run_sync should not run the callable on the event-loop thread."""
        import threading

        main_thread_id = threading.current_thread().ident
        seen_thread_id: list[int | None] = []

        def check_thread():
            seen_thread_id.append(threading.current_thread().ident)
            return True

        executor = IngestExecutor(max_workers=1)
        await executor.run_sync(check_thread)
        assert seen_thread_id[0] != main_thread_id
        executor.shutdown(wait=False)

    async def test_concurrent_calls(self):
        """Multiple concurrent run_sync calls should all complete."""
        import time

        executor = IngestExecutor(max_workers=2)

        def slow(n):
            time.sleep(0.01)
            return n * 2

        results = await asyncio.gather(
            executor.run_sync(slow, 1),
            executor.run_sync(slow, 2),
            executor.run_sync(slow, 3),
        )
        assert sorted(results) == [2, 4, 6]
        executor.shutdown(wait=False)

    async def test_run_sync_propagates_exception(self):
        """run_sync should propagate exceptions raised by the blocking callable."""
        executor = IngestExecutor(max_workers=1)

        def bad():
            raise ValueError("boom")

        with pytest.raises(ValueError, match="boom"):
            await executor.run_sync(bad)
        executor.shutdown(wait=False)

    def test_shutdown_safe_to_call_multiple_times(self):
        """shutdown() must not raise on repeated calls."""
        executor = IngestExecutor(max_workers=1)
        executor.shutdown(wait=False)
        executor.shutdown(wait=False)  # second call must be safe


class TestGetExecutor:
    def test_singleton(self):
        """get_executor() must return the same object on repeated calls."""
        e1 = get_executor()
        e2 = get_executor()
        assert e1 is e2

    async def test_singleton_is_functional(self):
        """Singleton executor must be able to run a simple callable."""
        result = await get_executor().run_sync(lambda: "ok")
        assert result == "ok"
