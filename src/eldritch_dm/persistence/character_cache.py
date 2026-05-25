"""CharacterCacheRepo — persistent character snapshot cache (Phase 17 / CHARCACHE-01/02/03).

Cache character snapshots across bot restarts so the first turn of a re-launched
session doesn't wait for full dm20 character ingest. The cache stores ONLY
static character data — combat-mutable state (current HP, conditions, etc.)
NEVER reaches this cache; the v1.0 mechanical-honesty contract is preserved
fail-CLOSED via ``extra="forbid"`` on ``CharacterSnapshot``.

Architecture:

- Storage: standalone aiosqlite WAL at ``~/.eldritch/character_cache.sqlite``
  (D-119). Separate DB from Phase 16's ``mcp_cache.sqlite`` and Phase 1's
  ``eldritch.sqlite3``. Lazy connection — NOT routed through Phase 1's
  ``WriterQueue`` (that owns the main DB).
- Schema (D-120)::

      CREATE TABLE character_cache_entries (
          character_id   TEXT    PRIMARY KEY,
          snapshot_json  TEXT    NOT NULL,
          etag           TEXT    NOT NULL,
          last_seen_ts   INTEGER NOT NULL,
          refreshed_ts   INTEGER NOT NULL
      );
      CREATE INDEX idx_character_cache_refreshed
          ON character_cache_entries(refreshed_ts);

- Refresh signal: synthetic SHA-256 ETag over canonical JSON of the latest
  dm20 response (D-122). dm20's MCP surface has no HTTP ETag headers, so the
  synthetic hash is the **primary** path, not a fallback.
- TTL short-circuit (D-123, Plan 17-02): ``CHARCACHE_TTL_S`` (default 3600s).
  Inside TTL → return cached without calling the fetcher (zero-network hit).
  Outside TTL → fall through to the ETag-refresh path.

Mechanical honesty (D-125 — HARD CONSTRAINT):

  ``CharacterSnapshot`` has a hardcoded allow-list of 14 STATIC fields:

    id, name, race, character_class, subclass, level, proficiency_bonus,
    alignment, languages, max_hp, base_stats, base_ac, base_speed, equipment

  Field names ``base_ac`` and ``base_speed`` (not bare ``ac`` / ``speed``) are
  deliberate — the prefix makes the static-vs-current distinction visible at
  every call site.

  ``model_config = ConfigDict(extra="forbid", frozen=True)`` rejects any other
  field at write time. The projector ``_project_to_snapshot`` ALSO drops
  combat-mutable fields silently before they reach the model so a noisy dm20
  response cannot poison the cache.

Plan 17-02 extends this module with the TTL short-circuit, an ``invalidate()``
API, KPI emission via ``traced_character_cache`` spans, and a
``metrics_snapshot()`` accessor.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from collections.abc import Awaitable, Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

import aiosqlite
from pydantic import BaseModel, ConfigDict, Field

from eldritch_dm.logging import get_logger

if TYPE_CHECKING:
    from eldritch_dm.config import Settings

log = get_logger(__name__)


# ── CharacterSnapshot — static-fields-only allow-list ────────────────────────


# Stat name literal — pinned so a typo at the call site fails at construction.
StatName = Literal["STR", "DEX", "CON", "INT", "WIS", "CHA"]


class CharacterSnapshot(BaseModel):
    """Static character data ONLY — the mechanical-honesty contract (D-125).

    Combat-mutable fields (``current_hp``, ``current_conditions`` …) are
    rejected at write time by ``extra="forbid"``. The projector
    ``_project_to_snapshot`` ALSO drops combat-mutable fields silently before
    they reach the model so a noisy dm20 response cannot poison the cache.

    Field naming: ``base_ac`` / ``base_speed`` (not bare ``ac`` / ``speed``) so
    the static-vs-current distinction is visible at every call site.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    # Identity (static)
    id: str
    name: str
    race: str
    character_class: str  # `class` is a Python keyword
    subclass: str = ""  # empty string allowed for level 1–2 PCs
    level: int
    proficiency_bonus: int
    alignment: str = ""
    languages: list[str] = Field(default_factory=list)

    # Static numerical floor (NEVER changes from damage / buffs / conditions)
    max_hp: int
    base_stats: dict[StatName, int]
    base_ac: int  # armor + DEX + class features ONLY; no buffs / spells
    base_speed: int  # racial/class base ONLY; no grapple / prone / exhaustion
    equipment: list[str] = Field(default_factory=list)  # items owned, NOT effects


# Pinned at import time so changes to the model force an update to the
# membership snapshot test. Modifying this REQUIRES reviewing D-125.
ALLOWED_SNAPSHOT_FIELDS: frozenset[str] = frozenset(
    CharacterSnapshot.model_fields.keys()
)


# D-125 forbidden names — used by tests AND by the projector to silently drop
# combat-mutable fields before they hit ``extra="forbid"``.
FORBIDDEN_SNAPSHOT_FIELDS: frozenset[str] = frozenset(
    {
        "current_hp",
        "current_temp_hp",
        "current_conditions",
        "exhaustion_level",
        "active_buffs",
        "concentration_target",
        "death_save_successes",
        "death_save_failures",
        "hit_dice_remaining",
        "current_speed",
        "current_ac",
    }
)


# ── Helpers ──────────────────────────────────────────────────────────────────


def etag_of(payload: Any) -> str:
    """Stable SHA-256 over canonical JSON.

    Independent of dict key order, ``PYTHONHASHSEED``, and Python version.
    Used as the synthetic ETag for D-122.
    """
    canonical = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), default=str
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _project_to_snapshot(response: dict[str, Any]) -> CharacterSnapshot:
    """Project a raw dm20 response to a ``CharacterSnapshot`` (allow-list only).

    - Unknown static fields are silently dropped.
    - Combat-mutable fields (D-125 forbidden list) are explicitly stripped
      BEFORE construction so a noisy upstream payload cannot trigger
      ``extra="forbid"`` rejection (which would crash the cache write).
    - Missing REQUIRED fields raise ``ValueError`` with a clear message.
    """
    if not isinstance(response, dict):
        raise ValueError(
            f"_project_to_snapshot expected dict, got {type(response).__name__}"
        )

    # Strip forbidden fields BEFORE building the projection dict so we never
    # try to validate them. This is belt-and-suspenders: extra="forbid" would
    # also catch them, but we want a clean projection, not a crash.
    cleaned = {
        k: v for k, v in response.items() if k not in FORBIDDEN_SNAPSHOT_FIELDS
    }

    # Some upstream payloads use legacy names — map them through.
    if "class" in cleaned and "character_class" not in cleaned:
        cleaned["character_class"] = cleaned.pop("class")

    # Pick ONLY allow-list fields. Drop everything else silently.
    projected = {k: v for k, v in cleaned.items() if k in ALLOWED_SNAPSHOT_FIELDS}

    # Required-field check up front so the error message names the missing
    # field rather than a generic pydantic validation error.
    required = {
        "id",
        "name",
        "race",
        "character_class",
        "level",
        "proficiency_bonus",
        "max_hp",
        "base_stats",
        "base_ac",
        "base_speed",
    }
    missing = required - projected.keys()
    if missing:
        raise ValueError(
            f"projection missing required static fields: {sorted(missing)}"
        )

    # Normalize languages to a sorted list for deterministic ETag stability.
    if "languages" in projected and isinstance(projected["languages"], list):
        projected["languages"] = sorted(projected["languages"])

    return CharacterSnapshot.model_validate(projected)


# ── Counters / metrics ───────────────────────────────────────────────────────


@dataclass(slots=True)
class _Counters:
    """Mutable counter bag for tests + KPI emission (Plan 17-02)."""

    hits_ttl: int = 0
    hits_etag: int = 0
    misses: int = 0
    invalidations_total: int = 0


class CharacterCacheMetrics(BaseModel):
    """Read-only snapshot of cache counters + current size (Plan 17-02).

    ``etag_match_rate = hits_etag / (hits_etag + misses)``; ``0.0`` if denom = 0.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    hits_ttl: int
    hits_etag: int
    misses: int
    size: int
    invalidations_total: int
    etag_match_rate: float


# ── Repo ──────────────────────────────────────────────────────────────────────


class CharacterCacheRepo:
    """Per-character snapshot cache with synthetic-ETag refresh + TTL short-circuit.

    Construction is cheap — the SQLite connection opens lazily on first use
    (``_ensure_conn()``). Callers MUST ``await aclose()`` on shutdown.

    Args:
        settings: Optional ``Settings`` override. Defaults to ``get_settings()``.
        path: Optional path override — primarily used by tests and the CLI.
            When supplied, wins over ``settings.charcache_path``.
    """

    def __init__(
        self,
        *,
        settings: Settings | None = None,
        path: str | os.PathLike[str] | None = None,
    ) -> None:
        from eldritch_dm.config import get_settings  # local — keep import light

        self._settings = settings if settings is not None else get_settings()
        # Path override wins; otherwise expand ~ in the settings path.
        if path is not None:
            self._db_path = Path(os.fspath(path))
        else:
            self._db_path = Path(os.path.expanduser(self._settings.charcache_path))
        self._conn: aiosqlite.Connection | None = None
        self._counters = _Counters()
        self._logger = log.bind(component="character_cache")

    # ── Connection ───────────────────────────────────────────────────────────

    @property
    def db_path(self) -> Path:
        """The on-disk SQLite path this repo manages."""
        return self._db_path

    async def _ensure_conn(self) -> aiosqlite.Connection:
        """Lazily open the SQLite connection + create the schema."""
        if self._conn is not None:
            return self._conn
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = await aiosqlite.connect(str(self._db_path))
        conn.row_factory = aiosqlite.Row
        # Pragmas mirror Phase 1 / Phase 16 — WAL + busy_timeout + sync=NORMAL.
        await conn.execute("PRAGMA foreign_keys = ON")
        await conn.execute("PRAGMA journal_mode = WAL")
        await conn.execute("PRAGMA busy_timeout = 5000")
        await conn.execute("PRAGMA synchronous = NORMAL")
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS character_cache_entries (
                character_id   TEXT    PRIMARY KEY,
                snapshot_json  TEXT    NOT NULL,
                etag           TEXT    NOT NULL,
                last_seen_ts   INTEGER NOT NULL,
                refreshed_ts   INTEGER NOT NULL
            )
            """
        )
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_character_cache_refreshed "
            "ON character_cache_entries(refreshed_ts)"
        )
        await conn.commit()
        self._conn = conn
        self._logger.debug("character_cache_opened", path=str(self._db_path))
        return conn

    async def aclose(self) -> None:
        """Close the SQLite connection. Idempotent."""
        if self._conn is None:
            return
        try:
            await self._conn.close()
        except Exception:  # noqa: BLE001
            pass
        self._conn = None

    # ── Public API ───────────────────────────────────────────────────────────

    async def get_or_fetch(
        self,
        character_id: str,
        fetcher: Callable[[str], Awaitable[dict[str, Any]]],
    ) -> CharacterSnapshot:
        """Return the cached snapshot, refreshing via ``fetcher`` when needed.

        Three paths:

        1. **TTL hit** (Plan 17-02): row exists AND ``now - refreshed_ts <= TTL``.
           Return cached without calling the fetcher. Counts toward ``hits_ttl``.
        2. **ETag match**: TTL expired OR no row yet → call fetcher → if the
           synthetic ETag of the new response equals the cached one, bump
           ``last_seen_ts`` only, return cached. Counts toward ``hits_etag``.
        3. **Miss**: no row OR ETag mismatch → project new payload, upsert,
           return new snapshot. Counts toward ``misses``.

        On instrumentation: Plan 17-02 wraps this method in
        ``traced_character_cache``.
        """
        with _maybe_traced_lookup(character_id) as span:
            now = int(time.time())
            ttl = self._settings.charcache_ttl_s
            conn = await self._ensure_conn()

            # TTL short-circuit lookup.
            cursor = await conn.execute(
                "SELECT snapshot_json, etag, refreshed_ts "
                "FROM character_cache_entries WHERE character_id = ?",
                (character_id,),
            )
            row = await cursor.fetchone()
            await cursor.close()

            if row is not None and (now - int(row["refreshed_ts"])) <= ttl:
                # TTL hit — no fetcher invocation.
                await conn.execute(
                    "UPDATE character_cache_entries SET last_seen_ts = ? "
                    "WHERE character_id = ?",
                    (now, character_id),
                )
                await conn.commit()
                self._counters.hits_ttl += 1
                _stamp_lookup_span(
                    span,
                    character_id=character_id,
                    layer="ttl_hit",
                    size=await self._size(conn),
                    start_ns=time.monotonic_ns(),
                )
                return CharacterSnapshot.model_validate_json(row["snapshot_json"])

            # Fetch fresh payload (TTL expired or no row).
            start_ns = time.monotonic_ns()
            payload = await fetcher(character_id)
            new_etag = etag_of(payload)

            if row is not None and row["etag"] == new_etag:
                # ETag match — same payload after fetch. Bump last_seen_ts
                # AND refreshed_ts (TTL window restarts since we just confirmed
                # freshness against the source).
                await conn.execute(
                    "UPDATE character_cache_entries SET last_seen_ts = ?, "
                    "refreshed_ts = ? WHERE character_id = ?",
                    (now, now, character_id),
                )
                await conn.commit()
                self._counters.hits_etag += 1
                _stamp_lookup_span(
                    span,
                    character_id=character_id,
                    layer="etag_match",
                    size=await self._size(conn),
                    start_ns=start_ns,
                )
                return CharacterSnapshot.model_validate_json(row["snapshot_json"])

            # MISS or mismatch — project + upsert.
            snapshot = _project_to_snapshot(payload)
            snapshot_json = snapshot.model_dump_json()
            await conn.execute(
                "INSERT OR REPLACE INTO character_cache_entries "
                "(character_id, snapshot_json, etag, last_seen_ts, refreshed_ts) "
                "VALUES (?, ?, ?, ?, ?)",
                (character_id, snapshot_json, new_etag, now, now),
            )
            await conn.commit()
            self._counters.misses += 1
            _stamp_lookup_span(
                span,
                character_id=character_id,
                layer="miss",
                size=await self._size(conn),
                start_ns=start_ns,
            )
            self._logger.info(
                "character_cache_refreshed",
                character_id=character_id,
                etag=new_etag[:12],
            )
            return snapshot

    async def invalidate(self, character_id: str | None = None) -> int:
        """Remove entries.

        - ``character_id=None`` → wipe everything; returns count removed.
        - ``character_id="X"`` → wipe that one entry; returns 0 or 1.

        Always increments ``invalidations_total``. Plan 17-02 wraps this in
        ``traced_character_cache_invalidation``.
        """
        scope: Literal["all", "entry"] = "all" if character_id is None else "entry"
        with _maybe_traced_invalidation(scope=scope, character_id=character_id) as span:
            conn = await self._ensure_conn()
            if character_id is None:
                cur = await conn.execute("DELETE FROM character_cache_entries")
            else:
                cur = await conn.execute(
                    "DELETE FROM character_cache_entries WHERE character_id = ?",
                    (character_id,),
                )
            await conn.commit()
            removed = cur.rowcount if cur.rowcount > 0 else 0
            self._counters.invalidations_total += 1
            _stamp_invalidation_span(span, entries_removed=removed)
            self._logger.info(
                "character_cache_invalidate",
                scope=scope,
                character_id=character_id,
                entries_removed=removed,
            )
            return removed

    async def purge_all(self) -> int:
        """Wipe every entry. Returns count removed.

        Phase 22 / OPQOL-03 alias for ``invalidate(None)``. Exists so the
        schema-poller callback at the OPQOL-03 wire site can pass a method
        with a self-documenting name (``repo.purge_all`` reads more clearly
        than ``lambda: repo.invalidate(None)``).
        """
        return await self.invalidate(None)

    async def metrics_snapshot(self) -> CharacterCacheMetrics:
        """Read-only snapshot of cache counters + current size."""
        conn = await self._ensure_conn()
        size = await self._size(conn)
        denom = self._counters.hits_etag + self._counters.misses
        rate = (self._counters.hits_etag / denom) if denom else 0.0
        return CharacterCacheMetrics(
            hits_ttl=self._counters.hits_ttl,
            hits_etag=self._counters.hits_etag,
            misses=self._counters.misses,
            size=size,
            invalidations_total=self._counters.invalidations_total,
            etag_match_rate=rate,
        )

    # ── Properties (test convenience) ────────────────────────────────────────

    @property
    def hits_ttl(self) -> int:
        return self._counters.hits_ttl

    @property
    def hits_etag(self) -> int:
        return self._counters.hits_etag

    @property
    def misses(self) -> int:
        return self._counters.misses

    @property
    def invalidations_total(self) -> int:
        return self._counters.invalidations_total

    def reset_counters(self) -> None:
        """Zero all counters. SQLite contents untouched."""
        self._counters = _Counters()

    # ── Internal ─────────────────────────────────────────────────────────────

    async def _size(self, conn: aiosqlite.Connection) -> int:
        cursor = await conn.execute(
            "SELECT COUNT(*) FROM character_cache_entries"
        )
        row = await cursor.fetchone()
        await cursor.close()
        return int(row[0]) if row else 0


# ── Instrumentation shims (Plan 17-02) ───────────────────────────────────────
#
# The real implementations live in ``eldritch_dm.observability.instrumentation``;
# the wrappers below are import-defensive so a stripped-down test environment
# (no observability extra) still works.


@contextmanager
def _maybe_traced_lookup(character_id: str) -> Iterator[Any]:
    try:
        from eldritch_dm.observability.instrumentation import (
            traced_character_cache,
        )
    except ImportError:  # pragma: no cover
        yield _NullSpan()
        return
    with traced_character_cache(character_id=character_id) as span:
        yield span


@contextmanager
def _maybe_traced_invalidation(
    *,
    scope: Literal["all", "entry"],
    character_id: str | None,
) -> Iterator[Any]:
    try:
        from eldritch_dm.observability.instrumentation import (
            traced_character_cache_invalidation,
        )
    except ImportError:  # pragma: no cover
        yield _NullSpan()
        return
    with traced_character_cache_invalidation(
        scope=scope, character_id=character_id
    ) as span:
        yield span


class _NullSpan:
    """Fallback no-op span when observability isn't wired (defensive)."""

    def set_attribute(self, *_: Any, **__: Any) -> None:  # pragma: no cover
        pass


def _stamp_lookup_span(
    span: Any,
    *,
    character_id: str,
    layer: Literal["ttl_hit", "etag_match", "miss"],
    size: int,
    start_ns: int,
) -> None:
    latency_ms = int((time.monotonic_ns() - start_ns) / 1_000_000)
    span.set_attribute("eldritch.character_cache.character_id", character_id)
    span.set_attribute("eldritch.character_cache.layer", layer)
    span.set_attribute("eldritch.character_cache.size", size)
    span.set_attribute("eldritch.character_cache.latency_ms", latency_ms)


def _stamp_invalidation_span(span: Any, *, entries_removed: int) -> None:
    span.set_attribute(
        "eldritch.character_cache.invalidation.entries_removed", entries_removed
    )
