"""
MCPCache — multi-level cache wrapping MCPClient (Phase 16 / MCPCACHE-01/02).

Composition (not inheritance) over MCPClient: ``MCPCache.call(...)`` mirrors
``MCPClient.call(tool_name, **arguments) -> dict`` exactly, so it is a
drop-in replacement at every call site.

Two layers, both honoring a strict fail-CLOSED allow-list:

- **L1** in-process ``OrderedDict`` LRU guarded by ``asyncio.Lock``.
  Default ``maxsize=512``, ``ttl=300s``. Always enabled when
  ``MCPCACHE_ENABLED=true`` (the default).

- **L2** ``aiosqlite`` WAL store at ``MCPCACHE_L2_PATH``
  (default ``~/.eldritch/mcp_cache.sqlite``). Opt-in via
  ``MCPCACHE_L2_ENABLED=true``. Default TTL 24h.

Allow-list — D-117 / mechanical honesty:
- ONLY static-reference tools are cacheable. Mutable-state reads
  (``dm20__get_character``, ``dm20__get_game_state`` …) are intentionally
  EXCLUDED — caching them between a write and the next read would serve
  stale HP / turn / state, breaking the v1.0 mechanical-honesty contract.
- Mutations / dice rolls are NEVER cacheable.

The args_hash is SHA-256 of canonical JSON (sorted keys, compact
separators) so cache keys are stable across processes and across
``PYTHONHASHSEED`` values — Python's ``hash(frozenset(...))`` is
randomized per-process and would silently miss L2 entries after restart.

Plan 16-02 extends this module with: ``invalidate()`` API, schema-version
polling background task, and OTel KPI emission.
"""
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import time
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

import aiosqlite
from pydantic import BaseModel, ConfigDict

from eldritch_dm.logging import get_logger
from eldritch_dm.mcp.errors import MCPToolError
from eldritch_dm.observability.instrumentation import (
    traced_mcp_cache,
    traced_mcp_cache_invalidation,
)

if TYPE_CHECKING:
    from eldritch_dm.config import Settings
    from eldritch_dm.mcp.client import MCPClient

log = get_logger(__name__)


# ── Cacheable allow-list ─────────────────────────────────────────────────────
#
# Fail-CLOSED: any tool NOT in this frozenset bypasses the cache and goes
# straight to MCPClient.call(). Mutations and mutable-state reads are
# intentionally absent.
#
# Adding mutable-state reads here in the future REQUIRES per-mutation
# invalidation wiring at every dm20__update_* / dm20__apply_* / dm20__set_*
# call site. Do not relax without that wiring.

CACHEABLE_TOOLS: frozenset[str] = frozenset(
    {
        # Static D&D 5e reference data — does not change between bot restarts
        "dm20__get_class_info",
        "dm20__get_race_info",
        # Campaign metadata — semi-static; mutated only by explicit campaign
        # CRUD calls which we don't cache and which can drive future
        # invalidation hooks.
        "dm20__list_campaigns",
        "dm20__get_campaign_info",
        # SRD rulebook search — content is static for a given dnd MCP version
        "dnd__search_all_categories",
        "dnd__verify_with_api",
    }
)


# ── Helpers ──────────────────────────────────────────────────────────────────


def _args_hash(arguments: dict[str, Any]) -> str:
    """Stable cross-process hash of an arguments dict.

    Uses canonical JSON (sorted keys, compact separators) + SHA-256. Stable
    across Python processes regardless of ``PYTHONHASHSEED``. Falls back to
    ``str()`` for non-JSON-serializable values via ``default=str``.
    """
    canonical = json.dumps(arguments, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# ── Data classes ─────────────────────────────────────────────────────────────


@dataclass(slots=True)
class _L1Entry:
    """One in-process cache entry."""

    value: dict[str, Any]
    created_ts: float


@dataclass(slots=True)
class _Counters:
    """Mutable counter bag for tests + KPI emission (Plan 16-02)."""

    l1_hits: int = 0
    l1_misses: int = 0
    l2_hits: int = 0
    l2_misses: int = 0
    bypass_count: int = 0
    invalidations_total: int = 0
    last_invalidation_removed: int = 0
    # plumbing for Plan 16-02 — populated by traced_mcp_cache_invalidation
    extra: dict[str, int] = field(default_factory=dict)


class MCPCacheMetrics(BaseModel):
    """Read-only snapshot of cache counters + current sizes (Plan 16-02).

    Returned by ``MCPCache.metrics_snapshot()`` for tests and KPI exporters.
    ``size_l2`` is ``-1`` when L2 is disabled (sentinel — distinguishes
    "disabled" from "empty").
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    hits_l1: int
    misses_l1: int
    hits_l2: int
    misses_l2: int
    bypass_count: int
    size_l1: int
    size_l2: int
    invalidations_total: int


# ── MCPCache ─────────────────────────────────────────────────────────────────


class MCPCache:
    """Multi-level cache wrapping an ``MCPClient`` (composition).

    Mirrors ``MCPClient.call(tool_name, **arguments)`` so it is a drop-in
    replacement at every call site. Non-cacheable tools fall straight
    through to the inner client.

    Args:
        inner: The ``MCPClient`` this cache wraps. The cache does NOT take
            ownership of the inner client's lifetime — callers manage
            ``inner.aclose()``. Pass ``aclose_inner=True`` to ``aclose()``
            if you want a single composite close.
        settings: Optional ``Settings`` override. Defaults to
            ``get_settings()``.
    """

    def __init__(self, inner: MCPClient, *, settings: Settings | None = None) -> None:
        from eldritch_dm.config import get_settings  # local to keep import light

        self._inner = inner
        self._settings = settings if settings is not None else get_settings()
        self._l1: OrderedDict[tuple[str, str], _L1Entry] = OrderedDict()
        self._l1_lock = asyncio.Lock()
        self._l2_conn: aiosqlite.Connection | None = None
        self._l2_lock = asyncio.Lock()
        self._counters = _Counters()
        self._poller_task: asyncio.Task[None] | None = None
        self._poller_stop: asyncio.Event = asyncio.Event()
        self._logger = log.bind(component="mcp_cache")

    # ── Public API ───────────────────────────────────────────────────────────

    async def call(self, tool_name: str, **arguments: Any) -> dict[str, Any]:
        """Cached version of ``MCPClient.call``.

        Lookup order: allow-list check → L1 → L2 (if enabled) → inner. Stores
        the result in L1 (and L2 if enabled) on every MISS. Emits one
        ``eldritch.mcp.cache`` span per call (layer attribute reflects the
        path taken).
        """
        start = time.monotonic()
        with traced_mcp_cache(tool_name=tool_name) as span:
            # Allow-list / master switch — fail-CLOSED bypass.
            if not self._settings.mcpcache_enabled or tool_name not in CACHEABLE_TOOLS:
                self._counters.bypass_count += 1
                try:
                    result = await self._inner.call(tool_name, **arguments)
                finally:
                    self._stamp_cache_span(span, layer="bypass", start_ts=start)
                return result

            key_hash = _args_hash(arguments)
            key = (tool_name, key_hash)

            # L1 lookup
            l1_value = await self._l1_get(key)
            if l1_value is not None:
                self._counters.l1_hits += 1
                self._stamp_cache_span(span, layer="l1", start_ts=start)
                return l1_value
            self._counters.l1_misses += 1

            # L2 lookup (only if enabled)
            if self._settings.mcpcache_l2_enabled:
                l2_value = await self._l2_get(tool_name, key_hash)
                if l2_value is not None:
                    self._counters.l2_hits += 1
                    await self._l1_put(key, l2_value)
                    self._stamp_cache_span(span, layer="l2", start_ts=start)
                    return l2_value
                self._counters.l2_misses += 1

            # Total MISS — call inner, then populate caches.
            try:
                value = await self._inner.call(tool_name, **arguments)
            except Exception:
                # On error, still emit a span (layer=miss) but do not cache.
                self._stamp_cache_span(span, layer="miss", start_ts=start)
                raise
            await self._l1_put(key, value)
            if self._settings.mcpcache_l2_enabled:
                await self._l2_put(tool_name, key_hash, value)
            self._stamp_cache_span(span, layer="miss", start_ts=start)
            return value

    def _stamp_cache_span(
        self,
        span: Any,
        *,
        layer: str,
        start_ts: float,
    ) -> None:
        """Set the standard mcp.cache attributes on the span proxy.

        Latency uses ``time.monotonic()`` deltas. ``size_l2`` is reported as
        -1 here because the cache-call hot path cannot await a SELECT COUNT(*).
        Use ``await cache.metrics_snapshot()`` for the authoritative L2 size.
        """
        latency_ms = int((time.monotonic() - start_ts) * 1000)
        span.set_attribute("eldritch.mcp.cache.layer", layer)
        span.set_attribute("eldritch.mcp.cache.size_l1", len(self._l1))
        # Hot-path sentinel. Authoritative size lives in metrics_snapshot().
        span.set_attribute("eldritch.mcp.cache.size_l2", -1)
        span.set_attribute("eldritch.mcp.cache.latency_ms", latency_ms)

    # ── Invalidation ─────────────────────────────────────────────────────────

    async def invalidate(
        self,
        tool_name: str | None = None,
        args: dict[str, Any] | None = None,
    ) -> int:
        """Clear matching entries from BOTH layers and return the count removed.

        - ``tool_name=None, args=None`` → wipe everything (scope='all').
        - ``tool_name='X', args=None``  → wipe all entries for tool X (scope='tool').
        - ``tool_name='X', args={...}`` → wipe one entry (scope='entry').

        Always emits one ``eldritch.mcp.cache.invalidation`` span.
        """
        if tool_name is None and args is not None:
            raise ValueError("invalidate(args=...) requires tool_name to also be set")

        if tool_name is None:
            scope: str = "all"
        elif args is None:
            scope = "tool"
        else:
            scope = "entry"

        with traced_mcp_cache_invalidation(
            scope=scope,  # type: ignore[arg-type]
            tool_name=tool_name,
        ) as span:
            removed = 0
            async with self._l1_lock:
                if scope == "all":
                    removed += len(self._l1)
                    self._l1.clear()
                elif scope == "tool":
                    matched = [k for k in self._l1 if k[0] == tool_name]
                    for k in matched:
                        del self._l1[k]
                    removed += len(matched)
                else:  # entry
                    assert tool_name is not None and args is not None
                    key = (tool_name, _args_hash(args))
                    if key in self._l1:
                        del self._l1[key]
                        removed += 1

            # L2 — only touch the DB if we ever opened it.
            if self._settings.mcpcache_l2_enabled and self._l2_conn is not None:
                if scope == "all":
                    cur = await self._l2_conn.execute(
                        "DELETE FROM mcp_cache_entries"
                    )
                    removed += cur.rowcount if cur.rowcount > 0 else 0
                elif scope == "tool":
                    cur = await self._l2_conn.execute(
                        "DELETE FROM mcp_cache_entries WHERE tool_name = ?",
                        (tool_name,),
                    )
                    removed += cur.rowcount if cur.rowcount > 0 else 0
                else:  # entry
                    assert tool_name is not None and args is not None
                    cur = await self._l2_conn.execute(
                        "DELETE FROM mcp_cache_entries WHERE tool_name = ? AND args_hash = ?",
                        (tool_name, _args_hash(args)),
                    )
                    removed += cur.rowcount if cur.rowcount > 0 else 0
                await self._l2_conn.commit()

            self._counters.invalidations_total += 1
            self._counters.last_invalidation_removed = removed
            span.set_attribute(
                "eldritch.mcp.cache.invalidation.entries_removed", removed
            )
            self._logger.info(
                "mcp_cache_invalidate",
                scope=scope,
                tool_name=tool_name,
                entries_removed=removed,
            )
            return removed

    # ── Schema-version polling ───────────────────────────────────────────────

    def start_schema_version_poller(
        self,
        client: MCPClient,
        *,
        interval_s: float = 60.0,
        on_schema_change: Callable[[], Awaitable[None]] | None = None,
    ) -> asyncio.Task[None]:
        """Start a background task that polls ``dm20__schema_version``.

        On first call: stores the version. On subsequent calls: if the value
        changed, wipes the MCP cache, optionally invokes
        ``on_schema_change`` (Phase 22 / OPQOL-03), and logs
        ``mcp_cache_schema_version_changed``. If the very first call raises
        ``MCPToolError`` (404 — tool not available), the task logs
        ``mcp_cache_schema_poller_disabled`` and exits cleanly.

        Args:
            client: MCPClient to poll.
            interval_s: poll interval in seconds (default 60s).
            on_schema_change: optional async callback invoked AFTER the MCP
                wipe on each detected version change. Used by OPQOL-03 to
                wipe Phase 17's character_cache atomically. Failure in
                either side (MCP wipe OR callback) logs
                ``eldritch.cache.partial_wipe`` and continues — partial-wipe
                is acceptable (D-171/172) since the caches are independent.

        Returns the task so callers can ``await stop_schema_version_poller()``
        on shutdown.
        """
        if self._poller_task is not None and not self._poller_task.done():
            return self._poller_task
        self._poller_stop = asyncio.Event()
        self._poller_task = asyncio.create_task(
            self._poll_schema_version(client, interval_s, on_schema_change),
            name="MCPCache._poll_schema_version",
        )
        return self._poller_task

    async def stop_schema_version_poller(self) -> None:
        """Signal the poller to stop and await its exit."""
        if self._poller_task is None:
            return
        self._poller_stop.set()
        try:
            await self._poller_task
        except Exception:  # noqa: BLE001
            pass
        self._poller_task = None

    async def _poll_schema_version(
        self,
        client: MCPClient,
        interval_s: float,
        on_schema_change: Callable[[], Awaitable[None]] | None = None,
    ) -> None:
        """The poller body. Disables itself gracefully if the tool 4xxs."""
        # Initial fetch.
        try:
            last_resp = await client.call("dm20__schema_version")
        except MCPToolError:
            self._logger.info(
                "mcp_cache_schema_poller_disabled",
                reason="tool_not_available",
            )
            return
        except Exception as exc:  # noqa: BLE001
            self._logger.warning(
                "mcp_cache_schema_poll_initial_failed",
                error=str(exc)[:200],
            )
            return
        last_version = last_resp.get("version") if isinstance(last_resp, dict) else None

        while not self._poller_stop.is_set():
            try:
                await asyncio.wait_for(self._poller_stop.wait(), timeout=interval_s)
                return  # stop event set
            except TimeoutError:
                pass

            try:
                resp = await client.call("dm20__schema_version")
            except MCPToolError:
                # Tool removed mid-run — disable the loop.
                self._logger.info(
                    "mcp_cache_schema_poller_disabled",
                    reason="tool_not_available_mid_run",
                )
                return
            except Exception as exc:  # noqa: BLE001
                self._logger.warning(
                    "mcp_cache_schema_poll_failed",
                    error=str(exc)[:200],
                )
                continue

            current = resp.get("version") if isinstance(resp, dict) else None
            if current != last_version:
                # Use scope='schema_version' to distinguish from explicit wipes.
                with traced_mcp_cache_invalidation(
                    scope="schema_version",
                ) as span:
                    removed = 0
                    # MCP wipe (Phase 16 side) — Phase 22 / OPQOL-03 wraps in
                    # try/except so a Phase 17 callback still runs even if
                    # MCP fails (and vice versa). Partial wipes log
                    # `eldritch.cache.partial_wipe` and continue (D-171/172).
                    mcp_wipe_ok = True
                    try:
                        async with self._l1_lock:
                            removed += len(self._l1)
                            self._l1.clear()
                        if (
                            self._settings.mcpcache_l2_enabled
                            and self._l2_conn is not None
                        ):
                            cur = await self._l2_conn.execute(
                                "DELETE FROM mcp_cache_entries"
                            )
                            removed += cur.rowcount if cur.rowcount > 0 else 0
                            await self._l2_conn.commit()
                    except Exception as exc:  # noqa: BLE001
                        mcp_wipe_ok = False
                        self._logger.warning(
                            "eldritch.cache.partial_wipe",
                            old=last_version,
                            new=current,
                            mcp_cleared=False,
                            primary_error_type=type(exc).__name__,
                            primary_error=str(exc)[:200],
                        )

                    # Phase 22 / OPQOL-03 wire — fire Phase 17 invalidation.
                    if on_schema_change is not None:
                        try:
                            await on_schema_change()
                        except Exception as exc:  # noqa: BLE001
                            if mcp_wipe_ok:
                                self._logger.warning(
                                    "eldritch.cache.partial_wipe",
                                    old=last_version,
                                    new=current,
                                    mcp_cleared=True,
                                    secondary_error_type=type(exc).__name__,
                                    secondary_error=str(exc)[:200],
                                )
                            # If MCP also failed, the partial_wipe log above
                            # already captured the primary failure. The
                            # callback failure is recorded indirectly via
                            # secondary_error_type only when MCP succeeded.

                    self._counters.invalidations_total += 1
                    self._counters.last_invalidation_removed = removed
                    span.set_attribute(
                        "eldritch.mcp.cache.invalidation.entries_removed",
                        removed,
                    )
                    self._logger.info(
                        "mcp_cache_schema_version_changed",
                        old=last_version,
                        new=current,
                        entries_removed=removed,
                    )
                # Advance version tracking regardless of wipe outcome —
                # otherwise a transient failure would re-fire on every poll.
                last_version = current

    # ── Metrics ──────────────────────────────────────────────────────────────

    async def metrics_snapshot(self) -> MCPCacheMetrics:
        """Read-only snapshot of cache counters + current sizes."""
        size_l2 = (
            await self._l2_size()
            if self._settings.mcpcache_l2_enabled
            else -1
        )
        return MCPCacheMetrics(
            hits_l1=self._counters.l1_hits,
            misses_l1=self._counters.l1_misses,
            hits_l2=self._counters.l2_hits,
            misses_l2=self._counters.l2_misses,
            bypass_count=self._counters.bypass_count,
            size_l1=len(self._l1),
            size_l2=size_l2,
            invalidations_total=self._counters.invalidations_total,
        )

    @property
    def l1_size(self) -> int:
        return len(self._l1)

    @property
    def l1_hits(self) -> int:
        return self._counters.l1_hits

    @property
    def l1_misses(self) -> int:
        return self._counters.l1_misses

    @property
    def l2_hits(self) -> int:
        return self._counters.l2_hits

    @property
    def l2_misses(self) -> int:
        return self._counters.l2_misses

    @property
    def bypass_count(self) -> int:
        return self._counters.bypass_count

    def reset_counters(self) -> None:
        """Zero all hit/miss counters. L1/L2 storage untouched."""
        self._counters = _Counters()

    async def aclose(self, *, aclose_inner: bool = False) -> None:
        """Close the L2 connection (if open) and stop the schema poller.

        Optionally close the inner client. Composition default: caller owns
        ``inner`` lifetime.
        """
        await self.stop_schema_version_poller()
        if self._l2_conn is not None:
            try:
                await self._l2_conn.close()
            except Exception:  # noqa: BLE001
                pass
            self._l2_conn = None
        if aclose_inner:
            await self._inner.aclose()

    # ── L1 ───────────────────────────────────────────────────────────────────

    async def _l1_get(self, key: tuple[str, str]) -> dict[str, Any] | None:
        """Return value at ``key`` if present and within TTL, else None.

        Expired entries are removed on read.
        """
        ttl = self._settings.mcpcache_l1_ttl_s
        async with self._l1_lock:
            entry = self._l1.get(key)
            if entry is None:
                return None
            if (time.monotonic() - entry.created_ts) > ttl:
                # Expired — drop and report MISS.
                del self._l1[key]
                return None
            # Move to MRU end.
            self._l1.move_to_end(key)
            return entry.value

    async def _l1_put(self, key: tuple[str, str], value: dict[str, Any]) -> None:
        """Insert/refresh ``key`` and evict the LRU entry if over size."""
        maxsize = self._settings.mcpcache_l1_size
        entry = _L1Entry(value=value, created_ts=time.monotonic())
        async with self._l1_lock:
            self._l1[key] = entry
            self._l1.move_to_end(key)
            # Evict from the LRU end until we are at or below maxsize.
            while len(self._l1) > maxsize:
                evicted_key, _ = self._l1.popitem(last=False)
                self._logger.debug(
                    "mcp_cache_l1_evict",
                    tool_name=evicted_key[0],
                    args_hash=evicted_key[1][:12],
                )

    # ── L2 ───────────────────────────────────────────────────────────────────

    def _l2_path(self) -> Path:
        raw = os.path.expanduser(self._settings.mcpcache_l2_path)
        return Path(raw)

    async def _l2_ensure_conn(self) -> aiosqlite.Connection:
        """Lazily open the L2 connection + create table if missing.

        Mirrors Phase 1 ``apply_pragmas`` semantics: WAL, foreign_keys ON,
        busy_timeout, synchronous=NORMAL.
        """
        if self._l2_conn is not None:
            return self._l2_conn
        async with self._l2_lock:
            if self._l2_conn is not None:
                return self._l2_conn
            db_path = self._l2_path()
            db_path.parent.mkdir(parents=True, exist_ok=True)
            conn = await aiosqlite.connect(str(db_path))
            await conn.execute("PRAGMA foreign_keys = ON")
            await conn.execute("PRAGMA journal_mode = WAL")
            await conn.execute("PRAGMA busy_timeout = 5000")
            await conn.execute("PRAGMA synchronous = NORMAL")
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS mcp_cache_entries (
                    tool_name     TEXT    NOT NULL,
                    args_hash     TEXT    NOT NULL,
                    response_json TEXT    NOT NULL,
                    etag          TEXT,
                    created_ts    INTEGER NOT NULL,
                    PRIMARY KEY (tool_name, args_hash)
                )
                """
            )
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_mcp_cache_created "
                "ON mcp_cache_entries(created_ts)"
            )
            await conn.commit()
            self._l2_conn = conn
            self._logger.debug("mcp_cache_l2_opened", path=str(db_path))
            return conn

    async def _l2_get(self, tool_name: str, args_hash: str) -> dict[str, Any] | None:
        """Read a value from L2 if it exists and has not exceeded L2 TTL."""
        ttl = self._settings.mcpcache_l2_ttl_s
        conn = await self._l2_ensure_conn()
        cursor = await conn.execute(
            "SELECT response_json, created_ts FROM mcp_cache_entries "
            "WHERE tool_name = ? AND args_hash = ?",
            (tool_name, args_hash),
        )
        row = await cursor.fetchone()
        await cursor.close()
        if row is None:
            return None
        response_json, created_ts = row
        now = int(time.time())
        if (now - int(created_ts)) > ttl:
            # Expired — drop the row so reads don't keep returning it.
            await conn.execute(
                "DELETE FROM mcp_cache_entries WHERE tool_name = ? AND args_hash = ?",
                (tool_name, args_hash),
            )
            await conn.commit()
            return None
        try:
            return json.loads(response_json)
        except json.JSONDecodeError:
            # Corrupt row — best-effort drop, treat as MISS.
            await conn.execute(
                "DELETE FROM mcp_cache_entries WHERE tool_name = ? AND args_hash = ?",
                (tool_name, args_hash),
            )
            await conn.commit()
            self._logger.warning("mcp_cache_l2_corrupt_row", tool_name=tool_name)
            return None

    async def _l2_put(
        self,
        tool_name: str,
        args_hash: str,
        value: dict[str, Any],
    ) -> None:
        """Upsert ``(tool_name, args_hash)`` -> ``value`` into L2."""
        conn = await self._l2_ensure_conn()
        response_json = json.dumps(value, default=str)
        now = int(time.time())
        await conn.execute(
            "INSERT OR REPLACE INTO mcp_cache_entries "
            "(tool_name, args_hash, response_json, etag, created_ts) "
            "VALUES (?, ?, ?, NULL, ?)",
            (tool_name, args_hash, response_json, now),
        )
        await conn.commit()

    async def _l2_size(self) -> int:
        """Return the current row count in L2 (or 0 if disabled / unopened)."""
        if not self._settings.mcpcache_l2_enabled or self._l2_conn is None:
            return 0
        cursor = await self._l2_conn.execute(
            "SELECT COUNT(*) FROM mcp_cache_entries"
        )
        row = await cursor.fetchone()
        await cursor.close()
        return int(row[0]) if row else 0
