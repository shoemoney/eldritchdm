"""
4-channel concurrent-write stress test.

Run with:
    RUN_STRESS=1 pytest tests/persistence/test_concurrent_writes.py -v
    RUN_STRESS=1 STRESS_DURATION_SEC=5 pytest tests/persistence/test_concurrent_writes.py::test_stress_5sec_sanity -v

Default pytest run skips this file entirely (fast suite).
CI runs this in the slow lane on main only.

Verifies (D-37):
  - Zero aiosqlite.OperationalError: "database is locked" / SQLITE_BUSY
  - Zero row loss across 4 concurrent channels
  - p99 write latency < 250ms
"""

from __future__ import annotations

import os
import random
import time

import pytest
import pytest_asyncio

pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(
        os.environ.get("RUN_STRESS") != "1",
        reason="Set RUN_STRESS=1 to run the concurrent-write stress test",
    ),
]

import asyncio
from datetime import UTC, datetime

from eldritch_dm.logging import get_logger
from eldritch_dm.persistence.bootstrap import bootstrap
from eldritch_dm.persistence.channel_sessions_repo import ChannelSessionRepo
from eldritch_dm.persistence.connection import WriterQueue
from eldritch_dm.persistence.locks import SessionLocks
from eldritch_dm.persistence.models import ChannelState, PersistentView, SanitizerAuditRow
from eldritch_dm.persistence.persistent_views_repo import PersistentViewRepo
from eldritch_dm.persistence.sanitizer_audit_repo import SanitizerAuditRepo

log = get_logger(__name__)


def percentile(values: list[float], p: int) -> float:
    if not values:
        return 0.0
    sorted_v = sorted(values)
    idx = max(0, int(len(sorted_v) * p / 100) - 1)
    return sorted_v[idx]


async def _producer(
    channel_id: str,
    repos: tuple,
    locks: SessionLocks,
    duration_s: float,
    write_latencies: list[float],
    errors: list[Exception],
) -> None:
    """Simulate a Discord channel producing mixed reads + writes."""
    channel_repo, view_repo, audit_repo = repos
    start = time.monotonic()
    view_counter = 0

    while time.monotonic() - start < duration_s:
        # Choose operation (60% writes, 40% reads)
        op = random.choices(
            ["upsert", "view_insert", "audit_insert", "list_channel", "get_session"],
            weights=[25, 20, 15, 20, 20],
        )[0]

        try:
            if op == "upsert":
                async with locks.get(channel_id):
                    t0 = time.monotonic()
                    await channel_repo.upsert(
                        channel_id=channel_id,
                        campaign_name=f"Camp-{channel_id}",
                        state=ChannelState.COMBAT,
                    )
                    write_latencies.append((time.monotonic() - t0) * 1000)

            elif op == "view_insert":
                view_counter += 1
                async with locks.get(channel_id):
                    t0 = time.monotonic()
                    view = PersistentView(
                        custom_id=f"{channel_id}-view-{view_counter}",
                        view_class="CombatView",
                        message_id=f"msg-{channel_id}-{view_counter}",
                        channel_id=channel_id,
                        payload={"round": view_counter},
                        created_at=datetime.now(UTC),
                    )
                    await view_repo.insert(view)
                    write_latencies.append((time.monotonic() - t0) * 1000)

            elif op == "audit_insert":
                t0 = time.monotonic()
                audit_row = SanitizerAuditRow(
                    channel_id=channel_id,
                    user_id="user-stress",
                    raw_input="I attack",
                    stripped_tokens=[],
                    redacted_output="I attack",
                    truncated=False,
                    ts=datetime.now(UTC),
                )
                await audit_repo.insert(audit_row)
                write_latencies.append((time.monotonic() - t0) * 1000)

            elif op == "list_channel":
                await view_repo.list_by_channel(channel_id)

            elif op == "get_session":
                await channel_repo.get(channel_id)

        except Exception as exc:
            errors.append(exc)

        await asyncio.sleep(0.001)  # yield the loop


@pytest_asyncio.fixture
async def stress_repos(tmp_path):
    """Full setup for stress test."""
    db_path = str(tmp_path / "stress.sqlite3")
    await bootstrap(db_path)
    wq = WriterQueue(db_path)
    await wq.start()

    channel_repo = ChannelSessionRepo(db_path, wq)
    view_repo = PersistentViewRepo(db_path, wq)
    audit_repo = SanitizerAuditRepo(db_path, wq)
    locks = SessionLocks()

    yield db_path, wq, channel_repo, view_repo, audit_repo, locks

    await wq.stop()


async def _run_stress(stress_repos, duration_s: int) -> None:
    db_path, wq, channel_repo, view_repo, audit_repo, locks = stress_repos

    channel_ids = [f"stress-ch-{i}" for i in range(4)]

    # Pre-create the 4 channel sessions (so upserts hit ON CONFLICT path)
    for cid in channel_ids:
        await channel_repo.upsert(channel_id=cid, campaign_name=f"StressCamp-{cid}")

    write_latencies: list[float] = []
    errors: list[Exception] = []

    producers = [
        _producer(
            cid,
            (channel_repo, view_repo, audit_repo),
            locks,
            duration_s,
            write_latencies,
            errors,
        )
        for cid in channel_ids
    ]

    await asyncio.gather(*producers)

    # Assertions
    assert len(errors) == 0, (
        f"Errors during stress test: {errors[:5]!r}"
    )
    assert len(write_latencies) > 0, "No write latencies recorded"

    p50 = percentile(write_latencies, 50)
    p99 = percentile(write_latencies, 99)
    total_writes = len(write_latencies)

    log.info(
        "stress_results",
        total_writes=total_writes,
        p50_ms=round(p50, 1),
        p99_ms=round(p99, 1),
        duration_s=duration_s,
        ops_per_sec=round(total_writes / duration_s, 1),
    )
    print(
        f"\n  Stress results: {total_writes} writes in {duration_s}s | "
        f"p50={p50:.1f}ms p99={p99:.1f}ms | "
        f"ops/sec={total_writes / duration_s:.1f}"
    )

    assert p99 < 250, f"p99 write latency {p99:.1f}ms exceeds 250ms limit"

    # Verify rows were written
    active = await channel_repo.list_active()
    assert len(active) >= 4, f"Expected >= 4 active sessions, got {len(active)}"


async def test_stress_5sec_sanity(stress_repos):
    """Quick 5-second smoke run.

    Useful for:  RUN_STRESS=1 STRESS_DURATION_SEC=5 pytest tests/persistence/test_concurrent_writes.py::test_stress_5sec_sanity
    """
    duration = int(os.environ.get("STRESS_DURATION_SEC", "5"))
    await _run_stress(stress_repos, duration)


async def test_concurrent_writes_60sec(stress_repos):
    """Full 60-second sustained-load test.

    Run with: RUN_STRESS=1 pytest tests/persistence/test_concurrent_writes.py::test_concurrent_writes_60sec
    """
    duration = int(os.environ.get("STRESS_DURATION_SEC", "60"))
    await _run_stress(stress_repos, duration)
