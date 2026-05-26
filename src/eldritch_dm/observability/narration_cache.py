"""NarrCache + NarrCacheGate — opt-in narration response cache (Phase 18).

Wraps an OpenAI-compatible ``AsyncOpenAI.chat.completions.create`` call with
a fail-CLOSED narration cache. Designed as a **standalone API** —
``NarrCache`` does NOT hook into any specific call site in v1.5 because no
in-repo free-form narration LLM call exists yet (``dm20`` owns gameplay
narration internally via the MCP ``resolve_action`` tool). The API is
ready to wrap a future narration generator the moment one is added.

Why the cache defaults OFF (``NARRCACHE_ENABLED=false``, D-129):
  The narration cache is the riskiest cache in EldritchDM. A wrongly-cached
  response could leak mechanical effects (HP changes, AC checks, damage,
  conditions) and break the v1.0 mechanical-honesty contract. The
  ``NarrCacheGate`` is fail-CLOSED — it rejects on FIRST regex match — but
  operators must still opt in explicitly.

Architecture (D-130, D-132, D-133):
  - ``NarrCacheGate.is_pure_narration(text)``: stateless classifier;
    iterates module-level compiled regexes; returns ``False`` on first
    match. Empty / whitespace-only text returns ``True`` (vacuously
    narrative).
  - ``NarrCache.acompletion(client, *, model, messages, max_tokens,
    temperature, **kwargs)``: mirror of ``client.chat.completions.create``.
    HIT path re-gates the cached content (double-gate); MISS path gates
    the upstream response before storing. Either rejection counts the
    rejection and serves uncached.
  - L1 = ``OrderedDict`` + ``asyncio.Lock`` + monotonic TTL +
    ``NARRCACHE_L1_SIZE`` LRU bound.

This module emits no spans on its own. Plan 18-02 wires
``traced_narrcache`` and ``NarrCacheRuntimeOverride`` integration.
"""
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import asyncio
import hashlib
import re
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict

from eldritch_dm.logging import get_logger

if TYPE_CHECKING:
    from eldritch_dm.config import Settings

log = get_logger(__name__)


# ── Gate regex set (D-130, advisor-reviewed) ────────────────────────────────
#
# Compiled once at module load. Each pattern is case-insensitive and
# ``\b``-bounded. Stem patterns (``paralyz\w*``) cover suffix variants;
# complete-word patterns (``\bprone\b``) refuse to swallow word boundary.
# Order matters only for short-circuit cost — most-likely-to-match patterns
# are first.

_GATE_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        # HP / hit points
        r"\b(HP|hit\s*points?)\b",
        r"\bhp\d+\b",
        # AC / armor class
        r"\b(AC|armou?r\s*class)\b",
        # Damage / explicit numeric effects
        r"\b(damage|dmg)\b",
        r"\btakes?\s+\d+\b",
        r"\bdeals?\s+\d+\b",
        r"\b(reduced|drops?|falls?)\s+to\s+\d+\b",
        # Crit / nat-N
        r"\b(critical\s+hit|crit)\b",
        r"\bnatural\s+\d+\b",
        # Saves / DC
        r"\bsaves?\s+against\b",
        r"\bsaving\s+throw\b",
        r"\bDC\s*\d+\b",
        # Condition stems (paralyzed/paralyzing, stunned/stunning, ...)
        r"\b(paralyz|stunn|charm|frighten|grappl|incapacit|petrif|poison|restrain|unconsc)\w*",
        # Condition complete words (\b on both sides; no trailing \w*)
        r"\b(prone|status|condition|invisible)\b",
        # Dice notation + HP assignment
        r"\b\d+d\d+\b",
        r"\b\d+\s*hit\s*dice?\b",
        r"\bhp\s*[=:]\s*\d+\b",
        # Sentinel tokens (defensive: response should never echo these)
        r"<\s*player_action\s*>",
        r"<\s*damage\s*>",
        r"<\s*effect\s*>",
    )
)


class NarrCacheGate:
    """Fail-CLOSED mechanical-honesty classifier (D-130 / NARRCACHE-02).

    ``is_pure_narration(text)`` returns ``True`` only if NONE of
    ``_GATE_PATTERNS`` matches. The gate is invoked at TWO points in the
    cache lifecycle (D-130):

    1. **Pre-store** (on MISS): gate the upstream response before insertion.
    2. **Pre-serve** (on HIT): re-gate the cached content. If the regex set
       was tightened in a release and an old entry now matches, the entry
       is invalidated rather than served.

    Empty / whitespace-only text returns ``True`` (vacuously narrative — but
    in practice empty narration is dropped at the call site before it
    reaches the gate).
    """

    PATTERNS = _GATE_PATTERNS

    @staticmethod
    def is_pure_narration(text: str) -> bool:
        """Return True iff no mechanical-honesty pattern matches.

        Short-circuits on first match. Stateless / hot-path-safe.
        """
        if not text or not text.strip():
            return True
        for pattern in _GATE_PATTERNS:
            if pattern.search(text):
                return False
        return True


# ── Cache key (D-132) ───────────────────────────────────────────────────────


def _cache_key(
    *,
    model: str,
    system: str,
    user: str,
    max_tokens: int,
    temperature: float,
) -> str:
    """SHA-256 over canonical input string. Stable across processes."""
    payload = f"{model}\n{system}\n{user}\n{max_tokens}\n{temperature:.6f}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _extract_system_user(
    messages: list[dict[str, str]],
) -> tuple[str, str]:
    """Strictly parse a 2-message [system, user] list.

    Anything else raises ``ValueError`` — the cache key surface is
    intentionally bounded so we don't have to hash the entire role/content
    matrix and so multi-turn conversations bypass the cache automatically.
    """
    if len(messages) != 2:
        raise ValueError(
            f"NarrCache requires exactly 2 messages (system+user); got {len(messages)}"
        )
    sys_msg, user_msg = messages[0], messages[1]
    if sys_msg.get("role") != "system":
        raise ValueError("NarrCache: messages[0] must have role='system'")
    if user_msg.get("role") != "user":
        raise ValueError("NarrCache: messages[1] must have role='user'")
    return sys_msg.get("content", ""), user_msg.get("content", "")


# ── L1 entry ────────────────────────────────────────────────────────────────


@dataclass(slots=True)
class _L1Entry:
    """One cached completion entry."""

    completion: Any  # original ChatCompletion (or a fake in tests)
    response_text: str
    tokens_input: int
    tokens_output: int
    model: str
    created_monotonic: float


# ── Metrics snapshot ────────────────────────────────────────────────────────


class NarrCacheMetrics(BaseModel):
    """Read-only counter snapshot returned by ``NarrCache.metrics_snapshot()``."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    hits: int
    misses: int
    rejected_by_gate_store: int
    rejected_by_gate_serve: int
    bypass_count: int
    size: int


# ── NarrCache ───────────────────────────────────────────────────────────────


class NarrCache:
    """Opt-in narration response cache wrapping ``AsyncOpenAI``.

    Default OFF (``NARRCACHE_ENABLED=false``). Even when enabled, every
    insert and every serve is gated through ``NarrCacheGate`` —
    mechanical-effect text is NEVER cached and is NEVER served from
    cache. See module docstring for the rationale.

    The cache is keyed on ``(model, system, user, max_tokens,
    temperature)``; multi-turn calls (anything other than exactly
    ``[system, user]``) bypass the cache.

    Implementation lives mostly in Plan 18-02 (runtime override, spans,
    savings KPI). This skeleton supplies the public surface so 18-01's
    gate + corpus tests can rely on a stable import.
    """

    def __init__(self, *, settings: Settings | None = None) -> None:
        # Lazy-import settings to avoid an import cycle at module load.
        if settings is None:
            from eldritch_dm.config import get_settings

            settings = get_settings()
        self._settings = settings
        # asyncio.Lock is constructed lazily inside the first acompletion()
        # call so the cache is safe to instantiate at import / module
        # scope (no running loop required).
        self._lock: asyncio.Lock | None = None
        self._l1: OrderedDict[str, _L1Entry] = OrderedDict()
        # Counters
        self._hits = 0
        self._misses = 0
        self._rejected_store = 0
        self._rejected_serve = 0
        self._bypass = 0
        # Runtime-disable flag set by Plan 18-02's NarrCacheRuntimeOverride.
        # Kept as a per-instance bool so tests can flip without touching a
        # global singleton.
        self._runtime_disabled = False

    def _ensure_lock(self) -> asyncio.Lock:
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    # ── Public surface (Plan 18-01 stubs / 18-02 fills in) ──────────────────

    @property
    def size(self) -> int:
        return len(self._l1)

    def metrics_snapshot(self) -> NarrCacheMetrics:
        return NarrCacheMetrics(
            hits=self._hits,
            misses=self._misses,
            rejected_by_gate_store=self._rejected_store,
            rejected_by_gate_serve=self._rejected_serve,
            bypass_count=self._bypass,
            size=self.size,
        )

    def reset_for_tests(self) -> None:
        self._l1.clear()
        self._hits = 0
        self._misses = 0
        self._rejected_store = 0
        self._rejected_serve = 0
        self._bypass = 0

    # ── Internals shared across the file (will be used by acompletion + tests) ──

    def _make_key(
        self,
        *,
        model: str,
        messages: list[dict[str, str]],
        max_tokens: int,
        temperature: float,
    ) -> str:
        system, user = _extract_system_user(messages)
        return _cache_key(
            model=model,
            system=system,
            user=user,
            max_tokens=max_tokens,
            temperature=temperature,
        )

    def _is_expired(self, entry: _L1Entry, *, now_monotonic: float) -> bool:
        ttl = self._settings.narrcache_l1_ttl_s
        return (now_monotonic - entry.created_monotonic) >= ttl

    def _evict_lru_if_needed(self) -> None:
        max_size = self._settings.narrcache_l1_size
        while len(self._l1) > max_size:
            self._l1.popitem(last=False)

    # ── Hot-path: acompletion ───────────────────────────────────────────────

    async def acompletion(
        self,
        client: Any,
        *,
        model: str,
        messages: list[dict[str, str]],
        max_tokens: int,
        temperature: float,
        **kwargs: Any,
    ) -> Any:
        """Cached wrapper around ``client.chat.completions.create``.

        Returns the upstream ``ChatCompletion`` object (or a previously
        cached one). The cache is bypassed when any of these is true:

        - ``NARRCACHE_ENABLED`` is false (D-129, the default)
        - ``_runtime_disabled`` is true (D-134; Plan 18-02 ties this to the
          process-wide runtime override singleton)
        - ``messages`` is not exactly ``[system, user]`` (multi-turn / wrong
          shape → bypass; we keep the cache-key surface bounded)

        On a HIT, the cached response text is re-gated (D-130, double-gate):
        if the response now matches the regex set (e.g. the gate was
        tightened in a release), the entry is invalidated and treated as a
        MISS.

        On a MISS, the upstream call is made, the response text is gated,
        and the entry is stored ONLY if the gate accepts the text. Either
        way, the upstream result is returned.
        """
        # Lazy imports — D-65d invariant: this module must not import OTel at
        # module level, and these helpers themselves obey that invariant.
        from eldritch_dm.observability.instrumentation import traced_narrcache
        from eldritch_dm.observability.narrcache_runtime import (
            get_narrcache_override,
        )

        runtime_disabled = self._runtime_disabled or get_narrcache_override().is_disabled()

        t0 = time.monotonic()
        with traced_narrcache(model=model) as span:

            def _stamp(layer: str, *, savings_usd: float | None = None) -> None:
                latency_ms = int((time.monotonic() - t0) * 1000)
                span.set_attribute("eldritch.narrcache.layer", layer)
                span.set_attribute("eldritch.narrcache.size", len(self._l1))
                span.set_attribute("eldritch.narrcache.latency_ms", latency_ms)
                if savings_usd is not None:
                    span.set_attribute("eldritch.narrcache.savings_usd", float(savings_usd))

            # ── Bypass paths ────────────────────────────────────────────────
            if not self._settings.narrcache_enabled or runtime_disabled:
                self._bypass += 1
                try:
                    return await client.chat.completions.create(
                        model=model,
                        messages=messages,
                        max_tokens=max_tokens,
                        temperature=temperature,
                        **kwargs,
                    )
                finally:
                    _stamp("bypass")

            # Bounded key surface: only exactly system+user calls are cacheable.
            try:
                key = self._make_key(
                    model=model,
                    messages=messages,
                    max_tokens=max_tokens,
                    temperature=temperature,
                )
            except ValueError:
                self._bypass += 1
                try:
                    return await client.chat.completions.create(
                        model=model,
                        messages=messages,
                        max_tokens=max_tokens,
                        temperature=temperature,
                        **kwargs,
                    )
                finally:
                    _stamp("bypass")

            lock = self._ensure_lock()
            now = time.monotonic()

            serve_rejected = False

            # ── HIT path (with double-gate re-verification) ─────────────────
            async with lock:
                entry = self._l1.get(key)
                if entry is not None:
                    if self._is_expired(entry, now_monotonic=now):
                        # Expired — drop and fall through to MISS.
                        self._l1.pop(key, None)
                    elif not NarrCacheGate.is_pure_narration(entry.response_text):
                        # Gate tightened since the entry was stored — fail-CLOSED.
                        self._l1.pop(key, None)
                        self._rejected_serve += 1
                        serve_rejected = True
                        log.warning(
                            "narrcache.serve_gate_reject",
                            key_prefix=key[:16],
                            model=entry.model,
                        )
                    else:
                        # Bump LRU recency, compute savings, and return.
                        self._l1.move_to_end(key, last=True)
                        self._hits += 1
                        savings = _compute_savings_usd(
                            model=entry.model,
                            tokens_input=entry.tokens_input,
                            tokens_output=entry.tokens_output,
                        )
                        span.set_attribute("eldritch.tokens.input", 0)
                        span.set_attribute("eldritch.tokens.output", 0)
                        _stamp("hit", savings_usd=savings)
                        return entry.completion

            # ── MISS path (call upstream OUTSIDE the lock; gate, then store) ─
            completion = await client.chat.completions.create(
                model=model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
                **kwargs,
            )
            self._misses += 1

            response_text, tokens_in, tokens_out = _extract_completion_text(completion)
            span.set_attribute("eldritch.tokens.input", tokens_in)
            span.set_attribute("eldritch.tokens.output", tokens_out)

            if not NarrCacheGate.is_pure_narration(response_text):
                self._rejected_store += 1
                log.info(
                    "narrcache.store_gate_reject",
                    key_prefix=key[:16],
                    model=model,
                    text_preview=response_text[:80],
                )
                _stamp("gate_reject_store")
                return completion

            # Gate accepted — store with LRU + TTL bookkeeping.
            async with lock:
                self._l1[key] = _L1Entry(
                    completion=completion,
                    response_text=response_text,
                    tokens_input=tokens_in,
                    tokens_output=tokens_out,
                    model=model,
                    created_monotonic=time.monotonic(),
                )
                self._l1.move_to_end(key, last=True)
                self._evict_lru_if_needed()

            _stamp("gate_reject_serve" if serve_rejected else "miss")
            return completion


def _compute_savings_usd(*, model: str, tokens_input: int, tokens_output: int) -> float:
    """Return the USD cost that a cache HIT avoided.

    Loads the Phase 13 pricing table lazily (so the narration_cache module
    has no module-level dependency on ``cost.py``'s YAML reads). Unknown
    models return 0.0 — the warning is logged by ``calculate_cost`` itself.
    """
    try:
        from eldritch_dm.observability.cost import calculate_cost, load_pricing

        table = load_pricing()
        usd = calculate_cost(model, tokens_input, tokens_output, table)
        return float(usd)
    except Exception as exc:  # noqa: BLE001 — savings is observability, never block hot path
        log.debug(
            "narrcache.savings_calc_failed",
            error_type=type(exc).__name__,
            model=model,
        )
        return 0.0


def _extract_completion_text(completion: Any) -> tuple[str, int, int]:
    """Pull ``(content, tokens_in, tokens_out)`` from a ChatCompletion-like obj.

    Defensive: handles real OpenAI ``ChatCompletion`` objects, dicts, and
    test fakes that may set ``usage`` to ``None``.
    """
    try:
        choice = completion.choices[0]
        content = choice.message.content or ""
    except (AttributeError, IndexError, TypeError):
        content = ""
    usage = getattr(completion, "usage", None)
    tokens_in = int(getattr(usage, "prompt_tokens", 0) or 0) if usage is not None else 0
    tokens_out = int(getattr(usage, "completion_tokens", 0) or 0) if usage is not None else 0
    return content, tokens_in, tokens_out


__all__ = [
    "NarrCache",
    "NarrCacheGate",
    "NarrCacheMetrics",
    "_GATE_PATTERNS",
    "_cache_key",
    "_extract_completion_text",
    "_extract_system_user",
]
