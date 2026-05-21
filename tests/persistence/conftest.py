"""
Shared fixtures for persistence tests.

bootstrapped_db(tmp_path) → (db_path: str, writer_queue: WriterQueue)
    Bootstrap a fresh SQLite DB and start a WriterQueue.
    Teardown stops the queue.

bootstrapped_db_with_repos(tmp_path) → (db_path, wq, channel_repo, view_repo,
                                        riposte_repo, audit_repo, locks)
    Full setup: bootstrap + writer queue + all four repos + SessionLocks.
"""

from __future__ import annotations

import pytest
import pytest_asyncio

from eldritch_dm.persistence.bootstrap import bootstrap
from eldritch_dm.persistence.channel_sessions_repo import ChannelSessionRepo
from eldritch_dm.persistence.connection import WriterQueue
from eldritch_dm.persistence.locks import SessionLocks
from eldritch_dm.persistence.persistent_views_repo import PersistentViewRepo
from eldritch_dm.persistence.riposte_timers_repo import RiposteTimerRepo
from eldritch_dm.persistence.sanitizer_audit_repo import SanitizerAuditRepo


@pytest_asyncio.fixture
async def bootstrapped_db(tmp_path):
    """Bootstrap a fresh DB and start a WriterQueue. Yields (db_path, writer_queue)."""
    db_path = str(tmp_path / "test.sqlite3")
    await bootstrap(db_path)
    wq = WriterQueue(db_path)
    await wq.start()
    yield db_path, wq
    await wq.stop()


@pytest_asyncio.fixture
async def bootstrapped_db_with_repos(tmp_path):
    """Full setup: bootstrap + WriterQueue + all four repos + SessionLocks."""
    db_path = str(tmp_path / "test_full.sqlite3")
    await bootstrap(db_path)
    wq = WriterQueue(db_path)
    await wq.start()

    channel_repo = ChannelSessionRepo(db_path, wq)
    view_repo = PersistentViewRepo(db_path, wq)
    riposte_repo = RiposteTimerRepo(db_path, wq)
    audit_repo = SanitizerAuditRepo(db_path, wq)
    locks = SessionLocks()

    yield db_path, wq, channel_repo, view_repo, riposte_repo, audit_repo, locks

    await wq.stop()
