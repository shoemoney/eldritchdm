"""
MonsterMemory — cross-round in-memory tactical signals for SmartMonsterDriver (Phase 21).

Three signals tracked per `(channel_id, session_id, monster_id)`:

- `damage_dealt_by[pc_id] -> int` — cumulative damage THIS PC dealt to THIS monster
  this session. Powers the LLM-facing `recent_damage_dealt` categorical band.
- `concentrating_on[pc_id] -> str | None` — spell name the PC is currently
  concentrating on (e.g. "Hypnotic Pattern"). Observable on the battlefield, so
  the spell NAME is allowed through to the LLM. Caller must call
  `observe_concentration(pc_id, None)` when concentration breaks.
- `marked_dangerous: set[pc_id]` — PCs the monster has internally flagged as
  high-priority threats. INT-gated: only monsters with INT ≥ 10 ever set this.

Locked decisions (21-01-PLAN.md L-01..L-08):

- **L-01**: `damage_dealt_by` is cumulative-this-session; the LLM-facing alias
  `recent_damage_dealt` reflects that because session lifetime IS "recent."
- **L-02**: Damage bands have explicit boundaries:
    `low` < 5, `moderate` ∈ [5, 14], `high` ≥ 15.
- **L-03**: A bounded `deque(maxlen=200)` of raw events is kept for audit/replay.
  Signal dicts are unbounded (party-sized in practice). Deque eviction NEVER
  rolls back signal totals.
- **L-06**: INT-gated marking: `observer_int` is passed by the caller per
  observation. `marked_dangerous` is set IFF `observer_int >= 10`.
- **L-07**: Fail-soft at every public boundary — `observe_*` swallow exceptions,
  `damage_band` returns None on error, `MonsterMemoryRegistry.recall` never
  raises.

Meta-knowledge guard (v1.1 D-57, this Phase D-159):
  Numerical damage stays INSIDE this module for the band computation only. The
  LLM-facing surface (via `_augment_with_memory` in smart_monster_driver) only
  ever sees the categorical band, the spell NAME, and the boolean flag.
  HP/AC NEVER touch this module.

Persistence (Plan 21-02): `MonsterMemoryRegistry` accepts an optional `repo`
that snapshots state to aiosqlite when `MONSTER_MEMORY_PERSIST=true`. Without
a repo, the registry is pure in-memory and behaves identically.
"""

from __future__ import annotations

from collections import deque
from typing import Any, Literal, Protocol

import structlog

log = structlog.get_logger().bind(component="monster_memory")

# ── Band boundaries (L-02) ────────────────────────────────────────────────────
DAMAGE_BAND_MODERATE_MIN: int = 5
DAMAGE_BAND_HIGH_MIN: int = 15

# ── INT threshold for marked_dangerous (L-06) ─────────────────────────────────
MARK_DANGEROUS_INT_THRESHOLD: int = 10

# ── Bounded event log (L-03) ──────────────────────────────────────────────────
EVENT_LOG_MAX: int = 200

DamageBand = Literal["low", "moderate", "high"]


def _classify_band(total_damage: int) -> DamageBand:
    """Classify cumulative damage into a band per L-02 boundaries."""
    if total_damage < DAMAGE_BAND_MODERATE_MIN:
        return "low"
    if total_damage < DAMAGE_BAND_HIGH_MIN:
        return "moderate"
    return "high"


class MonsterMemory:
    """In-memory tactical signals for ONE monster across rounds in ONE session.

    Construction is cheap and never raises. Each monster gets its own instance,
    keyed by `(channel_id, session_id, monster_id)` in `MonsterMemoryRegistry`.

    Public state (intentionally exposed for tests + persistence):
      - `damage_dealt_by: dict[str, int]`
      - `concentrating_on: dict[str, str | None]`
      - `marked_dangerous: set[str]`

    Public methods (all fail-soft):
      - `observe_hit(pc_id, damage, *, round_number=0, observer_int=None)`
      - `observe_concentration(pc_id, spell, *, round_number=0)`
      - `damage_band(pc_id) -> DamageBand | None`
      - `snapshot_dict() -> dict` (for persistence)
      - `MonsterMemory.from_snapshot(d) -> MonsterMemory` (classmethod)
    """

    __slots__ = (
        "damage_dealt_by",
        "concentrating_on",
        "marked_dangerous",
        "_events",
    )

    def __init__(self) -> None:
        self.damage_dealt_by: dict[str, int] = {}
        self.concentrating_on: dict[str, str | None] = {}
        self.marked_dangerous: set[str] = set()
        self._events: deque[tuple[int, str, str, Any]] = deque(maxlen=EVENT_LOG_MAX)

    # ── Observation API (called by bot cog / rules engine; D-163) ─────────────

    def observe_hit(
        self,
        pc_id: str,
        damage: int,
        *,
        round_number: int = 0,
        observer_int: int | None = None,
    ) -> None:
        """Record that `pc_id` dealt `damage` to this monster.

        Fail-soft: ANY exception is swallowed and logged. Combat is never
        crashed by a memory write.

        `observer_int` is the OBSERVING MONSTER's INT score. Only when it is
        provided AND ≥ MARK_DANGEROUS_INT_THRESHOLD is `pc_id` added to
        `marked_dangerous` — mirrors v1.1 D-53 INT-gating.
        """
        try:
            # Coerce + validate inputs strictly.
            if not isinstance(pc_id, str) or not pc_id:
                raise ValueError("pc_id must be non-empty str")
            dmg_int = int(damage)
            if dmg_int < 0:
                raise ValueError("damage must be non-negative")
            self.damage_dealt_by[pc_id] = self.damage_dealt_by.get(pc_id, 0) + dmg_int
            self._events.append((int(round_number), "hit", pc_id, dmg_int))
            if observer_int is not None and int(observer_int) >= MARK_DANGEROUS_INT_THRESHOLD:
                self.marked_dangerous.add(pc_id)
        except Exception as exc:  # noqa: BLE001 — fail-soft per L-07
            log.warning(
                "monster_memory_observe_hit_failed",
                pc_id=pc_id,
                error_type=type(exc).__name__,
                error=str(exc)[:200],
            )

    def observe_concentration(
        self,
        pc_id: str,
        spell: str | None,
        *,
        round_number: int = 0,
    ) -> None:
        """Record that `pc_id` is concentrating on `spell` (None clears).

        Fail-soft.
        """
        try:
            if not isinstance(pc_id, str) or not pc_id:
                raise ValueError("pc_id must be non-empty str")
            if spell is not None and not isinstance(spell, str):
                raise ValueError("spell must be str or None")
            self.concentrating_on[pc_id] = spell
            self._events.append((int(round_number), "concentration", pc_id, spell))
        except Exception as exc:  # noqa: BLE001 — fail-soft per L-07
            log.warning(
                "monster_memory_observe_concentration_failed",
                pc_id=pc_id,
                error_type=type(exc).__name__,
                error=str(exc)[:200],
            )

    # ── Derived signals ──────────────────────────────────────────────────────

    def damage_band(self, pc_id: str) -> DamageBand | None:
        """Return the damage band for `pc_id`, or None if unseen.

        Bands per L-02: low (<5), moderate (5..14), high (≥15).
        """
        try:
            total = self.damage_dealt_by.get(pc_id)
            if total is None or total <= 0:
                return None
            return _classify_band(total)
        except Exception as exc:  # noqa: BLE001 — fail-soft per L-07
            log.warning(
                "monster_memory_damage_band_failed",
                pc_id=pc_id,
                error_type=type(exc).__name__,
                error=str(exc)[:200],
            )
            return None

    # ── Persistence boundary (Plan 21-02) ────────────────────────────────────

    def snapshot_dict(self) -> dict[str, Any]:
        """Serialize state to a JSON-safe dict.

        Event log is intentionally NOT persisted (audit-only, in-memory).
        """
        return {
            "damage_dealt_by": dict(self.damage_dealt_by),
            "concentrating_on": dict(self.concentrating_on),
            "marked_dangerous": sorted(self.marked_dangerous),
        }

    @classmethod
    def from_snapshot(cls, d: dict[str, Any]) -> MonsterMemory:
        """Reconstruct from `snapshot_dict()`. Fail-soft → empty memory on error."""
        mem = cls()
        try:
            dd = d.get("damage_dealt_by") or {}
            co = d.get("concentrating_on") or {}
            md = d.get("marked_dangerous") or []
            if isinstance(dd, dict):
                mem.damage_dealt_by = {str(k): int(v) for k, v in dd.items()}
            if isinstance(co, dict):
                mem.concentrating_on = {
                    str(k): (str(v) if v is not None else None) for k, v in co.items()
                }
            if isinstance(md, (list, tuple, set)):
                mem.marked_dangerous = {str(p) for p in md}
        except Exception as exc:  # noqa: BLE001 — fail-soft per L-07
            log.warning(
                "monster_memory_from_snapshot_failed",
                error_type=type(exc).__name__,
                error=str(exc)[:200],
            )
            return cls()
        return mem


# ── Repo Protocol (avoid hard import of persistence at type-check time) ───────


class _MonsterMemoryRepoProto(Protocol):
    """Structural protocol for an optional persistence repo (Plan 21-02).

    The actual repo lives in `eldritch_dm.persistence.monster_memory_repo`.
    Using a Protocol here keeps gameplay decoupled at type-check time while
    allowing runtime injection.
    """

    async def load(
        self, channel_id: str, session_id: str, monster_id: str
    ) -> dict[str, Any] | None: ...

    async def upsert(
        self,
        channel_id: str,
        session_id: str,
        monster_id: str,
        snapshot: dict[str, Any],
    ) -> None: ...

    async def purge_session(self, channel_id: str, session_id: str) -> int: ...


# ── Registry ──────────────────────────────────────────────────────────────────


class MonsterMemoryRegistry:
    """Per-process registry of MonsterMemory instances.

    Key: `(channel_id, session_id, monster_id)`.

    Plan 21-01 surface (sync, in-memory only):
      - `recall(channel_id, session_id, monster_id) -> MonsterMemory`
      - `purge_session(channel_id, session_id) -> int`
      - `clear()`

    Plan 21-02 surface (async, opt-in repo):
      - `recall_async(...)` — hydrates from repo on first miss
      - `flush(channel_id, session_id, monster_id)` — upserts snapshot
      - `flush_all()` — upserts every in-memory entry
      - `purge_session_async(channel_id, session_id)` — repo + memory

    Fail-soft at every boundary (D-165 / L-07).
    """

    def __init__(self, *, repo: _MonsterMemoryRepoProto | None = None) -> None:
        self._entries: dict[tuple[str, str, str], MonsterMemory] = {}
        self._hydrated: set[tuple[str, str, str]] = set()
        self._repo = repo

    @property
    def has_repo(self) -> bool:
        """True when an opt-in persistence repo is wired (Plan 21-02)."""
        return self._repo is not None

    # ── Sync API (Plan 21-01) ─────────────────────────────────────────────────

    def recall(
        self, channel_id: str, session_id: str, monster_id: str
    ) -> MonsterMemory:
        """Get-or-create the MonsterMemory for the given key. Never raises."""
        try:
            key = (str(channel_id), str(session_id), str(monster_id))
            mem = self._entries.get(key)
            if mem is None:
                mem = MonsterMemory()
                self._entries[key] = mem
            return mem
        except Exception as exc:  # noqa: BLE001 — fail-soft per L-07
            log.warning(
                "monster_memory_registry_recall_failed",
                error_type=type(exc).__name__,
                error=str(exc)[:200],
            )
            return MonsterMemory()

    def purge_session(self, channel_id: str, session_id: str) -> int:
        """Drop all in-memory entries matching `(channel_id, session_id, *)`.

        Returns the count purged. Never raises.
        """
        try:
            ch, se = str(channel_id), str(session_id)
            to_drop = [k for k in self._entries if k[0] == ch and k[1] == se]
            for k in to_drop:
                self._entries.pop(k, None)
                self._hydrated.discard(k)
            return len(to_drop)
        except Exception as exc:  # noqa: BLE001 — fail-soft per L-07
            log.warning(
                "monster_memory_registry_purge_failed",
                error_type=type(exc).__name__,
                error=str(exc)[:200],
            )
            return 0

    def clear(self) -> None:
        """Drop ALL in-memory entries (test helper)."""
        self._entries.clear()
        self._hydrated.clear()

    # ── Async API (Plan 21-02 — opt-in repo) ─────────────────────────────────

    async def recall_async(
        self, channel_id: str, session_id: str, monster_id: str
    ) -> MonsterMemory:
        """Async get-or-create. Hydrates from repo on first miss when repo is wired.

        Never raises. Falls back to empty MonsterMemory on any error.
        """
        key = (str(channel_id), str(session_id), str(monster_id))
        try:
            if self._repo is not None and key not in self._hydrated:
                self._hydrated.add(key)
                snap = await self._repo.load(*key)
                if snap is not None:
                    self._entries[key] = MonsterMemory.from_snapshot(snap)
            mem = self._entries.get(key)
            if mem is None:
                mem = MonsterMemory()
                self._entries[key] = mem
            return mem
        except Exception as exc:  # noqa: BLE001 — fail-soft per L-07
            log.warning(
                "monster_memory_registry_recall_async_failed",
                error_type=type(exc).__name__,
                error=str(exc)[:200],
            )
            return self._entries.setdefault(key, MonsterMemory())

    async def flush(
        self, channel_id: str, session_id: str, monster_id: str
    ) -> None:
        """Upsert the snapshot for one key to the repo. No-op if no repo or no entry."""
        if self._repo is None:
            return
        key = (str(channel_id), str(session_id), str(monster_id))
        try:
            mem = self._entries.get(key)
            if mem is None:
                return
            await self._repo.upsert(*key, mem.snapshot_dict())
        except Exception as exc:  # noqa: BLE001 — fail-soft per L-07
            log.warning(
                "monster_memory_registry_flush_failed",
                error_type=type(exc).__name__,
                error=str(exc)[:200],
            )

    async def flush_all(self) -> int:
        """Flush every in-memory entry. Returns count of successful flushes."""
        if self._repo is None:
            return 0
        ok = 0
        for key, mem in list(self._entries.items()):
            try:
                await self._repo.upsert(*key, mem.snapshot_dict())
                ok += 1
            except Exception as exc:  # noqa: BLE001 — fail-soft per L-07
                log.warning(
                    "monster_memory_registry_flush_all_one_failed",
                    error_type=type(exc).__name__,
                    error=str(exc)[:200],
                )
        return ok

    async def purge_session_async(
        self, channel_id: str, session_id: str
    ) -> int:
        """Purge in-memory + repo entries for `(channel_id, session_id, *)`."""
        repo_count = 0
        if self._repo is not None:
            try:
                repo_count = await self._repo.purge_session(
                    str(channel_id), str(session_id)
                )
            except Exception as exc:  # noqa: BLE001 — fail-soft per L-07
                log.warning(
                    "monster_memory_registry_purge_async_repo_failed",
                    error_type=type(exc).__name__,
                    error=str(exc)[:200],
                )
        mem_count = self.purge_session(channel_id, session_id)
        return max(repo_count, mem_count)
