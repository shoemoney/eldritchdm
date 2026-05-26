"""Thread-pool executor singleton for blocking OCR/PDF work.

OCR and synchronous PDF parsing must NOT run on the Discord event loop.
IngestExecutor wraps a ThreadPoolExecutor (max_workers=2) and exposes
`run_sync(fn, *args)` for off-loading blocking callables.

Usage:
    result = await get_executor().run_sync(blocking_fn, arg1, arg2)
"""
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import asyncio
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any, TypeVar

from eldritch_dm.logging import get_logger

log = get_logger(__name__)

_T = TypeVar("_T")

# Module-level singleton — created once at first access.
_executor: IngestExecutor | None = None


class IngestExecutor:
    """Singleton wrapper around ThreadPoolExecutor for ingest workloads.

    Args:
        max_workers: Maximum threads (default 2 — OCR is heavy, caps concurrency).
    """

    def __init__(self, max_workers: int = 2) -> None:
        self._pool = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="ingest")
        self._logger = log.bind(component="IngestExecutor", max_workers=max_workers)
        self._logger.debug("ingest_executor_created")

    async def run_sync(self, fn: Callable[..., _T], *args: Any) -> _T:
        """Run a blocking callable in the thread pool.

        Args:
            fn:   Synchronous callable.
            *args: Positional arguments forwarded to fn.

        Returns:
            Whatever fn returns, awaited through the event-loop executor bridge.
        """
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self._pool, fn, *args)

    def shutdown(self, wait: bool = True) -> None:
        """Shut down the thread pool.

        Should be called during bot.close() if the bot uses IngestExecutor.
        Safe to call multiple times.
        """
        self._pool.shutdown(wait=wait)
        self._logger.debug("ingest_executor_shutdown")


def get_executor() -> IngestExecutor:
    """Return the module-level IngestExecutor singleton, creating it on first call."""
    global _executor
    if _executor is None:
        _executor = IngestExecutor()
    return _executor
