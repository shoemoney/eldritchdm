"""Tests for MonsterMemory + MonsterMemoryRegistry (Phase 21)."""

from __future__ import annotations

from typing import Any

import pytest

from eldritch_dm.gameplay.monster_memory import (
    DAMAGE_BAND_HIGH_MIN,
    DAMAGE_BAND_MODERATE_MIN,
    EVENT_LOG_MAX,
    MARK_DANGEROUS_INT_THRESHOLD,
    MonsterMemory,
    MonsterMemoryRegistry,
)

# ── MonsterMemory: observe_hit ────────────────────────────────────────────────


def test_observe_hit_accumulates() -> None:
    mem = MonsterMemory()
    mem.observe_hit("pc1", 3, round_number=1)
    mem.observe_hit("pc1", 7, round_number=2)
    mem.observe_hit("pc2", 5, round_number=2)
    assert mem.damage_dealt_by == {"pc1": 10, "pc2": 5}


def test_observe_hit_swallows_exception() -> None:
    """Pass non-coercible damage → no raise, no state change."""
    mem = MonsterMemory()
    mem.observe_hit("pc1", "not-a-number")  # type: ignore[arg-type]
    mem.observe_hit("", 5)  # empty pc_id
    mem.observe_hit("pc1", -3)  # negative damage
    assert mem.damage_dealt_by == {}
    assert mem.marked_dangerous == set()


# ── damage_band: boundary verification (L-02) ─────────────────────────────────


def test_damage_band_low_boundary() -> None:
    mem = MonsterMemory()
    mem.observe_hit("pc1", 4)
    assert mem.damage_band("pc1") == "low"


def test_damage_band_moderate_low_edge() -> None:
    """5 is the first moderate value."""
    assert DAMAGE_BAND_MODERATE_MIN == 5
    mem = MonsterMemory()
    mem.observe_hit("pc1", 5)
    assert mem.damage_band("pc1") == "moderate"


def test_damage_band_moderate_high_edge() -> None:
    """14 is still moderate; 15 flips to high."""
    mem = MonsterMemory()
    mem.observe_hit("pc1", 14)
    assert mem.damage_band("pc1") == "moderate"
    mem2 = MonsterMemory()
    mem2.observe_hit("pc2", 15)
    assert mem2.damage_band("pc2") == "high"
    assert DAMAGE_BAND_HIGH_MIN == 15


def test_damage_band_high() -> None:
    mem = MonsterMemory()
    mem.observe_hit("pc1", 30)
    assert mem.damage_band("pc1") == "high"


def test_damage_band_returns_none_for_unseen_pc() -> None:
    mem = MonsterMemory()
    mem.observe_hit("pc1", 10)
    assert mem.damage_band("unknown_pc") is None


# ── marked_dangerous INT-gating (L-06 / D-53) ─────────────────────────────────


def test_marked_dangerous_int_below_threshold_never_marks() -> None:
    assert MARK_DANGEROUS_INT_THRESHOLD == 10
    mem = MonsterMemory()
    mem.observe_hit("pc1", 5, observer_int=9)
    assert mem.marked_dangerous == set()


def test_marked_dangerous_int_at_threshold_marks() -> None:
    mem = MonsterMemory()
    mem.observe_hit("pc1", 5, observer_int=10)
    assert "pc1" in mem.marked_dangerous


def test_marked_dangerous_int_none_never_marks() -> None:
    mem = MonsterMemory()
    mem.observe_hit("pc1", 5)  # no observer_int passed
    assert mem.marked_dangerous == set()


def test_marked_dangerous_high_int_marks() -> None:
    mem = MonsterMemory()
    mem.observe_hit("pc1", 5, observer_int=18)
    assert "pc1" in mem.marked_dangerous


# ── observe_concentration ─────────────────────────────────────────────────────


def test_observe_concentration_set_and_clear() -> None:
    mem = MonsterMemory()
    mem.observe_concentration("pc1", "Hypnotic Pattern")
    assert mem.concentrating_on == {"pc1": "Hypnotic Pattern"}
    mem.observe_concentration("pc1", None)
    assert mem.concentrating_on == {"pc1": None}


def test_observe_concentration_swallows_invalid() -> None:
    mem = MonsterMemory()
    mem.observe_concentration("", "Bless")  # empty pc_id
    mem.observe_concentration("pc1", 123)  # type: ignore[arg-type]
    assert mem.concentrating_on == {}


# ── Bounded event log (L-03) ──────────────────────────────────────────────────


def test_event_deque_bounded_at_200() -> None:
    assert EVENT_LOG_MAX == 200
    mem = MonsterMemory()
    for i in range(250):
        mem.observe_hit("pc1", 1, round_number=i)
    # Deque capped at 200; totals remain correct (deque eviction never rolls back signals).
    assert len(mem._events) == 200
    assert mem.damage_dealt_by["pc1"] == 250


# ── Snapshot round-trip ───────────────────────────────────────────────────────


def test_snapshot_round_trip() -> None:
    mem = MonsterMemory()
    mem.observe_hit("pc1", 12, observer_int=14)
    mem.observe_hit("pc2", 3, observer_int=14)
    mem.observe_concentration("pc1", "Hypnotic Pattern")

    snap = mem.snapshot_dict()
    assert snap["damage_dealt_by"] == {"pc1": 12, "pc2": 3}
    assert snap["concentrating_on"] == {"pc1": "Hypnotic Pattern"}
    assert "pc1" in snap["marked_dangerous"]

    rehydrated = MonsterMemory.from_snapshot(snap)
    assert rehydrated.damage_dealt_by == mem.damage_dealt_by
    assert rehydrated.concentrating_on == mem.concentrating_on
    assert rehydrated.marked_dangerous == mem.marked_dangerous


def test_from_snapshot_fail_soft_on_corrupt() -> None:
    """Corrupt snapshot → empty MonsterMemory, never raises."""
    corrupt: dict[str, Any] = {"damage_dealt_by": "not-a-dict", "concentrating_on": 42}
    mem = MonsterMemory.from_snapshot(corrupt)
    assert mem.damage_dealt_by == {}
    assert mem.concentrating_on == {}
    assert mem.marked_dangerous == set()


def test_snapshot_dict_has_no_hp_ac_keys() -> None:
    """Meta-knowledge guard: persisted shape must never contain HP/AC fields."""
    mem = MonsterMemory()
    mem.observe_hit("pc1", 10)
    snap = mem.snapshot_dict()
    forbidden = {"hp_current", "hp_max", "ac", "armor_class"}
    assert forbidden.isdisjoint(snap.keys())


# ── MonsterMemoryRegistry: sync API (Plan 21-01) ──────────────────────────────


def test_registry_recall_creates_empty_then_reuses() -> None:
    reg = MonsterMemoryRegistry()
    a = reg.recall("chan1", "sess1", "monsterA")
    b = reg.recall("chan1", "sess1", "monsterA")
    assert a is b
    assert a.damage_dealt_by == {}


def test_registry_distinct_keys_get_distinct_instances() -> None:
    reg = MonsterMemoryRegistry()
    a = reg.recall("chan1", "sess1", "monsterA")
    b = reg.recall("chan1", "sess1", "monsterB")
    assert a is not b


def test_registry_purge_session_drops_matching_only() -> None:
    reg = MonsterMemoryRegistry()
    reg.recall("chan1", "sess1", "mA")
    reg.recall("chan1", "sess1", "mB")
    reg.recall("chan1", "sess2", "mC")  # different session
    reg.recall("chan2", "sess1", "mD")  # different channel
    n = reg.purge_session("chan1", "sess1")
    assert n == 2
    # sess2 and chan2 entries survive.
    assert ("chan1", "sess2", "mC") in reg._entries
    assert ("chan2", "sess1", "mD") in reg._entries


def test_registry_recall_never_raises() -> None:
    """Even with weird key inputs, recall returns a MonsterMemory."""
    reg = MonsterMemoryRegistry()
    # Coerced to str internally; never raises.
    mem = reg.recall("", "", "")
    assert isinstance(mem, MonsterMemory)


def test_registry_has_repo_false_without_repo() -> None:
    reg = MonsterMemoryRegistry()
    assert reg.has_repo is False


# ── MonsterMemoryRegistry: async API (Plan 21-02) ─────────────────────────────


class _FakeRepo:
    """In-memory fake repo for testing the async registry path."""

    def __init__(self) -> None:
        self.store: dict[tuple[str, str, str], dict[str, Any]] = {}
        self.load_calls = 0
        self.upsert_calls = 0
        self.purge_calls = 0
        self.fail_on_load = False
        self.fail_on_upsert = False

    async def load(
        self, channel_id: str, session_id: str, monster_id: str
    ) -> dict[str, Any] | None:
        self.load_calls += 1
        if self.fail_on_load:
            raise RuntimeError("simulated load failure")
        return self.store.get((channel_id, session_id, monster_id))

    async def upsert(
        self,
        channel_id: str,
        session_id: str,
        monster_id: str,
        snapshot: dict[str, Any],
    ) -> None:
        self.upsert_calls += 1
        if self.fail_on_upsert:
            raise RuntimeError("simulated upsert failure")
        self.store[(channel_id, session_id, monster_id)] = snapshot

    async def purge_session(self, channel_id: str, session_id: str) -> int:
        self.purge_calls += 1
        keys = [k for k in self.store if k[0] == channel_id and k[1] == session_id]
        for k in keys:
            del self.store[k]
        return len(keys)


@pytest.mark.asyncio
async def test_registry_recall_async_hydrates_from_repo() -> None:
    repo = _FakeRepo()
    repo.store[("c", "s", "m")] = {
        "damage_dealt_by": {"pc1": 20},
        "concentrating_on": {},
        "marked_dangerous": ["pc1"],
    }
    reg = MonsterMemoryRegistry(repo=repo)
    mem = await reg.recall_async("c", "s", "m")
    assert mem.damage_dealt_by == {"pc1": 20}
    assert "pc1" in mem.marked_dangerous
    # Second call uses cached, does not re-load.
    await reg.recall_async("c", "s", "m")
    assert repo.load_calls == 1


@pytest.mark.asyncio
async def test_registry_flush_writes_snapshot() -> None:
    repo = _FakeRepo()
    reg = MonsterMemoryRegistry(repo=repo)
    mem = await reg.recall_async("c", "s", "m")
    mem.observe_hit("pc1", 8)
    await reg.flush("c", "s", "m")
    assert repo.upsert_calls == 1
    assert repo.store[("c", "s", "m")]["damage_dealt_by"] == {"pc1": 8}


@pytest.mark.asyncio
async def test_registry_flush_all_returns_count() -> None:
    repo = _FakeRepo()
    reg = MonsterMemoryRegistry(repo=repo)
    await reg.recall_async("c", "s", "m1")
    await reg.recall_async("c", "s", "m2")
    n = await reg.flush_all()
    assert n == 2


@pytest.mark.asyncio
async def test_registry_purge_session_async_clears_both() -> None:
    repo = _FakeRepo()
    reg = MonsterMemoryRegistry(repo=repo)
    await reg.recall_async("c", "s", "m1")
    await reg.recall_async("c", "s", "m2")
    await reg.flush_all()
    assert len(repo.store) == 2
    n = await reg.purge_session_async("c", "s")
    assert n == 2
    assert repo.store == {}
    assert reg._entries == {}


@pytest.mark.asyncio
async def test_registry_recall_async_fail_soft_on_repo_error() -> None:
    repo = _FakeRepo()
    repo.fail_on_load = True
    reg = MonsterMemoryRegistry(repo=repo)
    mem = await reg.recall_async("c", "s", "m")
    # Falls back to empty memory; does NOT raise.
    assert isinstance(mem, MonsterMemory)
    assert mem.damage_dealt_by == {}


@pytest.mark.asyncio
async def test_registry_flush_fail_soft_on_repo_error() -> None:
    repo = _FakeRepo()
    repo.fail_on_upsert = True
    reg = MonsterMemoryRegistry(repo=repo)
    mem = await reg.recall_async("c", "s", "m")
    mem.observe_hit("pc1", 5)
    # Must not raise.
    await reg.flush("c", "s", "m")


@pytest.mark.asyncio
async def test_registry_async_ops_noop_without_repo() -> None:
    reg = MonsterMemoryRegistry()  # no repo
    mem = await reg.recall_async("c", "s", "m")
    mem.observe_hit("pc1", 5)
    await reg.flush("c", "s", "m")  # no-op
    n = await reg.flush_all()
    assert n == 0
