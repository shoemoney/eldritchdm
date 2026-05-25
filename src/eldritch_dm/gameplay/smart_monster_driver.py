"""
SmartMonsterDriver — INT-gated, LLM-routed monster target selection (Phase 10).

Sibling to v1.0's `MonsterDriver` (gameplay.monster_driver). The smart driver
replaces only the `_choose_target` step: it consults the local oMLX/ShoeGPT LLM
(via the existing AsyncOpenAI client pattern from gameplay.ingest.translate)
for monsters with `intelligence >= 8`, falls back to uniformly-random selection
for `intelligence <= 4`, and 50/50-samples for `intelligence` in [5,7] using a
deterministic seed `hash((channel_id, round_number, monster_id))`.

Locked decisions (CONTEXT D-50..D-61):

- D-50: LLM endpoint is local oMLX (`http://localhost:8765/v1`, model
  `ShoeGPT`). NOT hosted OpenAI. The AsyncOpenAI client is injected by the
  caller — this module does not know about endpoints.
- D-51: Schema enforcement via `response_format={"type": "json_object"}` +
  post-parse `MonsterTacticChoice.model_validate_json(...)`. We do NOT use
  `.beta.chat.completions.parse` strict mode — local oMLX/ShoeGPT may not
  honor it reliably. A last-chance regex extractor handles JSON wrapped in
  prose.
- D-53: INT thresholds — `<=4` → random, `>=8` → LLM, `5..7` → deterministic
  50/50.
- D-54: 1500ms hard deadline via `asyncio.wait_for`. On timeout: structured
  log + random fallback.
- D-55: `MonsterTacticChoice` model with `target_pc_id` (required) and
  `rationale` (optional). The candidate-ID membership check happens at the
  call site (Pydantic models do not hold runtime state per AI-SPEC §4b.1).
- D-56: Per-round cache keyed on `(channel_id, round_number, monster_id)`
  with FIFO eviction at 256 entries. (Implemented in Plan 02.)
- D-57: Candidate slimming — only `id`, `name`, `hp_current`, `hp_max`, `ac`,
  `active_conditions[]`. NEVER pass class/subclass to the LLM (meta-knowledge
  violation per AI-SPEC §1b Tactical Intent).
- D-58: Fail-soft — ANY exception (network, schema, validator, timeout) →
  random fallback. NEVER propagate to the combat orchestrator.

This module is import-linter-safe: lives under `gameplay/`, imports only from
`gameplay/`, `logging`, `openai`, and `pydantic`. No upward imports into `bot/`.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import random as _random
import re
import time
from collections import OrderedDict
from collections.abc import Awaitable, Callable, Sequence
from typing import TYPE_CHECKING, Any, Literal

import discord
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from eldritch_dm.gameplay.monster_driver import MonsterDriver
from eldritch_dm.logging import get_logger
from eldritch_dm.observability import traced_decision

if TYPE_CHECKING:
    from openai import AsyncOpenAI

    from eldritch_dm.persistence.pc_classes_repo import PCClassesRepo
    from eldritch_dm.persistence.riposte_timers_repo import RiposteTimerRepo

log = get_logger(__name__)

# Regex last-chance extractor (D-51 graceful degradation): if `model_validate_json`
# fails because the LLM emitted prose around the JSON, we try to pull the
# `target_pc_id` (legacy single-target) or `target_pc_ids` (Phase 20 AOE)
# substring directly.
_TARGET_RE = re.compile(r'"target_pc_id"\s*:\s*"([^"]+)"')
# Phase 20 / D-149: match an AOE list shape `"target_pc_ids": ["a", "b", ...]`.
# We extract the list body then split via the quoted-string regex below.
_TARGET_LIST_RE = re.compile(r'"target_pc_ids"\s*:\s*\[([^\]]*)\]')
_QUOTED_ID_RE = re.compile(r'"([^"]+)"')
# Phase 20 / D-150: extract `tactic_kind` from prose when the strict parser failed.
_TACTIC_KIND_RE = re.compile(
    r'"tactic_kind"\s*:\s*"(single|aoe|multi_attack|breath|cone)"'
)

# D-56: per-round cache size guard. FIFO eviction.
_DEFAULT_CACHE_MAX_SIZE = 256

# Route labels returned by `_route_path`. Public alias for tests.
Route = Literal["random", "llm", "mixed_random", "mixed_llm"]


class MonsterTacticChoice(BaseModel):
    """LLM-emitted tactical choice (D-55, D-149, D-150).

    Phase 20 (D-149/D-150) extended the original single-target shape to
    a multi-target list + tactic-kind discriminator. Backwards-compat with
    the legacy ``{"target_pc_id": "<id>"}`` shape is preserved via a
    ``model_validator(mode="before")`` legacy coercion and a read-only
    ``@property`` shim.

    Fields:
      - ``target_pc_ids``: ordered list of candidate PC ids the monster
        intends to affect. MUST be non-empty. ALL ids must be in the
        runtime candidate set; the membership check happens at the call
        site (the Pydantic model itself does not see the runtime
        candidate list, per AI-SPEC §4b.1).
      - ``tactic_kind``: discriminator for downstream resolution. Validator
        enforces:
          * ``"single"``      → ``len(target_pc_ids) == 1``
          * ``"aoe"|"breath"|"cone"`` → ``len(target_pc_ids) >= 2``
          * ``"multi_attack"`` → ``len(target_pc_ids) >= 1`` (a single
            monster can pile multi-attack swings on one PC OR cleave
            across two adjacent PCs)
      - ``rationale``: optional, for trace-log only — never surfaced to
        players (v1.1 D-57 meta-knowledge guard).

    Legacy coercion:
      ``{"target_pc_id": "x"}`` and ``MonsterTacticChoice(target_pc_id="x")``
      are rewritten to ``{"target_pc_ids": ["x"], "tactic_kind": "single"}``
      so every existing call site continues to work unchanged.

    ``model_config.extra="ignore"`` — local models sometimes emit extra
    keys (e.g. "confidence", "alt_target"); we tolerate them.
    """

    model_config = ConfigDict(extra="ignore")

    target_pc_ids: list[str] = Field(..., min_length=1)
    tactic_kind: Literal["single", "aoe", "multi_attack", "breath", "cone"] = "single"
    rationale: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _coerce_legacy_shape(cls, data: Any) -> Any:
        """Rewrite legacy ``{target_pc_id: "x"}`` → ``{target_pc_ids: ["x"]}``.

        Non-dict inputs pass through (pydantic raises its own error). A dict
        that already contains ``target_pc_ids`` is left untouched even if
        ``target_pc_id`` is also present (the new shape wins).
        """
        if not isinstance(data, dict):
            return data
        if "target_pc_ids" in data:
            # New shape wins; drop the legacy key if present so it doesn't
            # confuse downstream consumers.
            data.pop("target_pc_id", None)
            return data
        if "target_pc_id" in data:
            legacy = data.pop("target_pc_id")
            data["target_pc_ids"] = [legacy] if isinstance(legacy, str) else legacy
            data.setdefault("tactic_kind", "single")
        return data

    @model_validator(mode="after")
    def _validate_kind_arity(self) -> MonsterTacticChoice:
        """Enforce ``tactic_kind`` / ``len(target_pc_ids)`` invariants."""
        ids = self.target_pc_ids
        if len(set(ids)) != len(ids):
            raise ValueError("target_pc_ids must not contain duplicates")
        kind = self.tactic_kind
        n = len(ids)
        if kind == "single" and n != 1:
            raise ValueError(
                f"tactic_kind='single' requires exactly 1 target id; got {n}"
            )
        if kind in ("aoe", "breath", "cone") and n < 2:
            raise ValueError(
                f"tactic_kind='{kind}' requires >=2 target ids; got {n}"
            )
        # multi_attack accepts >=1 — lower bound already enforced by min_length.
        return self

    @property
    def target_pc_id(self) -> str:
        """Backwards-compat shim for D-149 / pre-Phase 20 single-target call sites.

        Returns ``target_pc_ids[0]``. Always safe — ``min_length=1`` guarantees
        the list is non-empty.
        """
        return self.target_pc_ids[0]


# ── Helpers (module-level for testability) ────────────────────────────────────


def _slim_candidate(pc: dict[str, Any]) -> dict[str, Any]:
    """Project a PC dict to the LLM-safe subset (D-57)."""
    return {
        "id": pc.get("character_id", ""),
        "name": pc.get("name", ""),
        "hp_current": pc.get("hp_current"),
        "hp_max": pc.get("hp_max"),
        "ac": pc.get("ac"),
        "active_conditions": pc.get("active_conditions", []),
    }


def _extract_monster_int(current_actor: dict[str, Any]) -> int | None:
    """Try the two known shapes for monster INT; return None if unavailable."""
    raw = current_actor.get("intelligence")
    if raw is None:
        stats = current_actor.get("stats", {})
        if isinstance(stats, dict):
            raw = stats.get("intelligence")
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


# ── Driver ────────────────────────────────────────────────────────────────────


class SmartMonsterDriver(MonsterDriver):
    """INT-gated LLM-routed target selection driver.

    Subclasses v1.0's `MonsterDriver` and overrides `_choose_target` only.
    The rest of the combat flow (state fetch, combat_action call, Riposte
    surfacing, next_turn) is identical to v1.0.
    """

    def __init__(
        self,
        *,
        mcp: Any,
        rate_limiter: Any,
        pc_classes_repo: PCClassesRepo,
        riposte_timers_repo: RiposteTimerRepo,
        button_factory: Callable[[int, int], discord.ui.Item],
        state_provider: Callable[[str, str], Awaitable[dict[str, Any]]],
        channel_resolver: Callable[[str], Any],
        openai_client: AsyncOpenAI,
        llm_model: str = "ShoeGPT",
        llm_timeout_seconds: float = 1.5,
        ttl_seconds: int = 8,
        random_choice: Callable[[Sequence[Any]], Any] = _random.choice,
        eligibility_set: frozenset[tuple[str, str]] | None = None,
        cache_max_size: int = _DEFAULT_CACHE_MAX_SIZE,
        embed_update_callback: Callable[[str, str], Awaitable[None]] | None = None,
    ) -> None:
        super().__init__(
            mcp=mcp,
            rate_limiter=rate_limiter,
            pc_classes_repo=pc_classes_repo,
            riposte_timers_repo=riposte_timers_repo,
            button_factory=button_factory,
            state_provider=state_provider,
            channel_resolver=channel_resolver,
            ttl_seconds=ttl_seconds,
            random_choice=random_choice,
            eligibility_set=eligibility_set,
        )
        self._openai_client = openai_client
        self._llm_model = llm_model
        self._llm_timeout_seconds = llm_timeout_seconds
        self._cache: OrderedDict[tuple[str, int, str], MonsterTacticChoice] = (
            OrderedDict()
        )
        self._cache_max_size = cache_max_size
        # Phase 19 / STREAM-01: optional async callback fired BEFORE the LLM
        # oracle call to surface a "🤔 {monster} is sizing up the party..."
        # indicator through the bot's per-channel EmbedCoalescer. Signature:
        # ``(channel_id: str, message_text: str) -> Awaitable[None]``. The
        # invocation is wrapped in ``contextlib.suppress(Exception)`` (D-145)
        # so a closed coalescer queue (shutdown) cannot crash combat — same
        # fail-soft contract as D-58.
        self._embed_update_callback = embed_update_callback
        # Rebind log with smart-component tag
        self._log = log.bind(component="SmartMonsterDriver")

    # ── INT-gating (D-53) ─────────────────────────────────────────────────────

    @staticmethod
    def _route_path(
        monster_int: int | None,
        *,
        channel_id: str,
        round_number: int,
        monster_id: str,
    ) -> Route:
        """Determine LLM vs. random for this monster turn.

        - INT <= 4 → "random"
        - INT >= 8 → "llm"
        - INT in [5, 7] → deterministic 50/50 seeded by (channel, round, monster)
        - None/unknown → "random" (defensive)
        """
        if monster_int is None:
            return "random"
        if monster_int <= 4:
            return "random"
        if monster_int >= 8:
            return "llm"
        # 5..7 — deterministic split
        seed = hash((channel_id, round_number, monster_id))
        rng = _random.Random(seed)
        return "mixed_llm" if rng.random() < 0.5 else "mixed_random"

    # ── Override pick step (Task 5b) ──────────────────────────────────────────

    async def _choose_target(
        self,
        targets: list[dict[str, Any]],
        *,
        channel_id: str,
        round_number: int,
        current_actor: dict[str, Any],
    ) -> dict[str, Any]:
        """Smart pick with full fail-soft to random.

        Returns one element of `targets`. Never raises. Always returns a
        non-None dict (caller guarantees `targets` is non-empty).

        Phase 11 / OBS-01: the entire decision is enclosed in ONE
        ``traced_decision`` span. The inner ``_pick_target_llm`` receives
        the span as a kwarg and decorates it with ``driver.path``,
        ``latency_ms``, tokens, and ``fallback.reason`` as the outcome
        becomes known. No nested spans (D-66).
        """
        monster_id = current_actor.get("character_id", "")
        monster_int = _extract_monster_int(current_actor)
        route = self._route_path(
            monster_int,
            channel_id=channel_id,
            round_number=round_number,
            monster_id=monster_id,
        )

        bound = self._log.bind(
            channel_id=channel_id,
            round_number=round_number,
            monster_id=monster_id,
            monster_int=monster_int,
            route=route,
        )

        # Open ONE decision span. Initial driver_path = route; inner code
        # overrides to "cache", "smart", or "random" as the path is resolved.
        with traced_decision(
            monster_id=monster_id,
            channel_id=channel_id,
            combat_round=round_number,
            driver_path=route,
        ) as span:
            if route in ("random", "mixed_random"):
                span.set_attribute("eldritch.driver.path", "random")
                span.set_attribute("eldritch.tokens.input", 0)
                span.set_attribute("eldritch.tokens.output", 0)
                span.set_attribute("eldritch.latency_ms", 0)
                bound.info("smart_driver_path", path="random")
                return self._random_choice(targets)

            # route in ("llm", "mixed_llm")
            chosen = await self._pick_target_llm(
                targets,
                channel_id=channel_id,
                round_number=round_number,
                current_actor=current_actor,
                bound_log=bound,
                span=span,
            )
            if chosen is None:
                # _pick_target_llm already set fallback.reason + latency.
                # Mark the resolved path as random fallback.
                span.set_attribute("eldritch.driver.path", "random")
                bound.info("smart_driver_path", path="random_fallback")
                return self._random_choice(targets)
            bound.info("smart_driver_path", path="smart_ok")
            return chosen

    # ── LLM oracle (Task 4) ───────────────────────────────────────────────────

    async def _pick_target_llm(
        self,
        targets: list[dict[str, Any]],
        *,
        channel_id: str,
        round_number: int,
        current_actor: dict[str, Any],
        bound_log: Any,
        span: Any = None,
    ) -> dict[str, Any] | None:
        """Call the LLM with a 1500ms hard deadline. Returns chosen PC or None.

        Fail-soft: ANY exception → logged + None (caller falls back to random).

        Includes a per-round cache (D-56) keyed on
        `(channel_id, round_number, monster_id)`. Same key returns the cached
        choice without re-invoking the LLM.

        Phase 11: when ``span`` is provided (always from ``_choose_target``;
        ``None`` when unit-tested in isolation), attributes are stamped on
        the SAME outer span. No nested spans, no ``get_current_span`` magic.
        """
        monster_id = current_actor.get("character_id", "")
        cache_key = (channel_id, round_number, monster_id)
        candidate_ids = {p.get("character_id", "") for p in targets}

        # ── Cache hit short-circuit ──────────────────────────────────────────
        # D-149: validate the full id-set against current candidates so an AOE
        # cached choice that lost a PC between rounds invalidates cleanly.
        cached = self._cache.get(cache_key)
        if cached is not None and set(cached.target_pc_ids).issubset(candidate_ids):
            bound_log.info(
                "smart_driver_cache_hit",
                target_id=cached.target_pc_id,
                target_ids=cached.target_pc_ids,
                tactic_kind=cached.tactic_kind,
            )
            if span is not None:
                span.set_attribute("eldritch.driver.path", "cache")
                span.set_attribute("eldritch.tokens.input", 0)
                span.set_attribute("eldritch.tokens.output", 0)
                span.set_attribute("eldritch.latency_ms", 0)
            # Plan 20-01 preserves single-target return signature: return the
            # FIRST cached id's PC. Plan 20-02 may extend this surface.
            for pc in targets:
                if pc.get("character_id") == cached.target_pc_id:
                    return pc
            # Defensive: cached id slipped out of candidate set — random fallback
            if span is not None:
                span.set_attribute("eldritch.fallback.reason", "hallucinated_id")
            return None

        candidates = [_slim_candidate(p) for p in targets]
        monster_name = current_actor.get("name", "monster")

        # Build prompt (D-57 slim, AI-SPEC §4 prompt discipline)
        system_prompt = (
            "You are a tactical combat oracle for a Dungeons & Dragons 5e "
            "monster. Choose ONE target from the candidate list. Respond ONLY "
            'with JSON of the form {"target_pc_id": "<id>", "rationale": '
            '"<one short sentence>"}. The `target_pc_id` MUST be one of the '
            "provided candidate IDs. Do NOT compute exact HP or AC values "
            "in your rationale; refer to visible cues (armor, posture, "
            "visible wounds, active conditions)."
        )
        user_payload = {
            "monster": {"id": monster_id, "name": monster_name},
            "round": round_number,
            "candidates": candidates,
            "candidate_ids": sorted(candidate_ids),
        }
        user_prompt = json.dumps(user_payload, default=str)

        bound_log.info(
            "smart_driver_llm_call",
            candidate_count=len(candidates),
        )

        # ── Phase 19 / STREAM-01: thinking indicator (cancellation-safe) ─────
        # Fires AFTER the cache-hit short-circuit and BEFORE the LLM call so
        # cache hits remain silent (D-141). The callback's failure mode is
        # swallowed (D-145) so combat continues if the coalescer is closed
        # (shutdown scenario) or the bot lost the message ref.
        if self._embed_update_callback is not None:
            indicator_text = f"🤔 {monster_name} is sizing up the party..."
            with contextlib.suppress(Exception):
                await self._embed_update_callback(channel_id, indicator_text)

        t0 = time.monotonic()

        try:
            completion = await asyncio.wait_for(
                self._openai_client.chat.completions.create(
                    model=self._llm_model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    response_format={"type": "json_object"},
                    temperature=0.2,
                    max_tokens=200,
                ),
                timeout=self._llm_timeout_seconds,
            )
        except TimeoutError:
            latency_ms = int((time.monotonic() - t0) * 1000)
            bound_log.warning(
                "smart_driver_timeout",
                latency_ms=latency_ms,
            )
            if span is not None:
                span.set_attribute("eldritch.latency_ms", latency_ms)
                span.set_attribute("eldritch.tokens.input", 0)
                span.set_attribute("eldritch.tokens.output", 0)
                span.set_attribute("eldritch.fallback.reason", "timeout")
            return None
        except Exception as exc:  # noqa: BLE001 — fail-soft per D-58
            latency_ms = int((time.monotonic() - t0) * 1000)
            bound_log.warning(
                "smart_driver_llm_error",
                latency_ms=latency_ms,
                error_type=type(exc).__name__,
                error=str(exc)[:200],
            )
            if span is not None:
                span.set_attribute("eldritch.latency_ms", latency_ms)
                span.set_attribute("eldritch.tokens.input", 0)
                span.set_attribute("eldritch.tokens.output", 0)
                reason = (
                    "rate_limit"
                    if "RateLimit" in type(exc).__name__
                    else "generic"
                )
                span.set_attribute("eldritch.fallback.reason", reason)
            return None

        latency_ms = int((time.monotonic() - t0) * 1000)

        # Defensive token extraction — MLX may return completion.usage = None.
        usage = getattr(completion, "usage", None)
        tokens_in = (
            getattr(usage, "prompt_tokens", 0) if usage is not None else 0
        ) or 0
        tokens_out = (
            getattr(usage, "completion_tokens", 0) if usage is not None else 0
        ) or 0

        # Extract content defensively (refusal path may have None content)
        try:
            message = completion.choices[0].message
            content = (message.content or "") if message is not None else ""
        except (AttributeError, IndexError, TypeError):
            bound_log.warning("smart_driver_no_content", latency_ms=latency_ms)
            if span is not None:
                span.set_attribute("eldritch.latency_ms", latency_ms)
                span.set_attribute("eldritch.tokens.input", tokens_in)
                span.set_attribute("eldritch.tokens.output", tokens_out)
                span.set_attribute("eldritch.fallback.reason", "refusal")
            return None

        if not content.strip():
            bound_log.warning("smart_driver_empty_response", latency_ms=latency_ms)
            if span is not None:
                span.set_attribute("eldritch.latency_ms", latency_ms)
                span.set_attribute("eldritch.tokens.input", tokens_in)
                span.set_attribute("eldritch.tokens.output", tokens_out)
                span.set_attribute("eldritch.fallback.reason", "refusal")
            return None

        # Strict parse → fall back to regex extractor (D-51)
        # Phase 20 / D-149: try the AOE list-shape regex FIRST (more specific),
        # then the legacy single-id regex. Either path constructs a valid
        # MonsterTacticChoice via the legacy-coercion validator.
        choice: MonsterTacticChoice | None = None
        try:
            choice = MonsterTacticChoice.model_validate_json(content)
        except (ValidationError, ValueError, json.JSONDecodeError):
            # Phase 20: list-shape extraction.
            list_match = _TARGET_LIST_RE.search(content)
            if list_match is not None:
                ids = _QUOTED_ID_RE.findall(list_match.group(1))
                kind_match = _TACTIC_KIND_RE.search(content)
                kind = kind_match.group(1) if kind_match is not None else None
                if ids:
                    try:
                        if kind is not None:
                            choice = MonsterTacticChoice(
                                target_pc_ids=ids, tactic_kind=kind  # type: ignore[arg-type]
                            )
                        else:
                            # No kind hint: infer single iff 1 id, else aoe.
                            inferred_kind = "single" if len(ids) == 1 else "aoe"
                            choice = MonsterTacticChoice(
                                target_pc_ids=ids,
                                tactic_kind=inferred_kind,  # type: ignore[arg-type]
                            )
                    except ValidationError:
                        choice = None
            if choice is None:
                m = _TARGET_RE.search(content)
                if m is not None:
                    try:
                        choice = MonsterTacticChoice(target_pc_id=m.group(1))
                    except ValidationError:
                        choice = None

        if choice is None:
            bound_log.warning(
                "smart_driver_parse_error",
                latency_ms=latency_ms,
                raw_preview=content[:120],
            )
            if span is not None:
                span.set_attribute("eldritch.latency_ms", latency_ms)
                span.set_attribute("eldritch.tokens.input", tokens_in)
                span.set_attribute("eldritch.tokens.output", tokens_out)
                span.set_attribute("eldritch.fallback.reason", "json_parse")
            return None

        # Candidate-ID membership check (D-55, D-149)
        # ALL ids in target_pc_ids must be in the runtime candidate set; any
        # hallucination → fail-soft fallback (D-58/D-153). Also enforce an
        # upper bound (len(ids) <= len(candidates)) as a defensive cap.
        chosen_ids = set(choice.target_pc_ids)
        if (
            not chosen_ids.issubset(candidate_ids)
            or len(choice.target_pc_ids) > len(candidate_ids)
        ):
            bound_log.warning(
                "smart_driver_invalid_choice",
                latency_ms=latency_ms,
                raw_target=choice.target_pc_id,
                raw_targets=choice.target_pc_ids,
                tactic_kind=choice.tactic_kind,
                candidate_ids=sorted(candidate_ids),
            )
            if span is not None:
                span.set_attribute("eldritch.latency_ms", latency_ms)
                span.set_attribute("eldritch.tokens.input", tokens_in)
                span.set_attribute("eldritch.tokens.output", tokens_out)
                span.set_attribute("eldritch.fallback.reason", "hallucinated_id")
            return None

        # ── Cache the validated choice (D-56) ────────────────────────────────
        self._cache[cache_key] = choice
        if len(self._cache) > self._cache_max_size:
            # FIFO eviction
            self._cache.popitem(last=False)

        bound_log.info(
            "smart_driver_llm_ok",
            latency_ms=latency_ms,
            target_id=choice.target_pc_id,
            target_ids=choice.target_pc_ids,
            tactic_kind=choice.tactic_kind,
        )
        if span is not None:
            span.set_attribute("eldritch.latency_ms", latency_ms)
            span.set_attribute("eldritch.tokens.input", tokens_in)
            span.set_attribute("eldritch.tokens.output", tokens_out)
            span.set_attribute("eldritch.driver.path", "smart")

        # Plan 20-01 preserves the single-target return signature: return the
        # FIRST id's PC. Plan 20-02 may extend this surface for AOE resolution.
        for pc in targets:
            if pc.get("character_id") == choice.target_pc_id:
                return pc
        return None  # unreachable given membership check, but defensive
