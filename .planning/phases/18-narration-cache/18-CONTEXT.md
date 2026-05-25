---
phase: 18-narration-cache
milestone: v1.5
generated: 2026-05-25
mode: auto-generated (autonomous-flow)
source_requirements:
  - NARRCACHE-01 (opt-in cache, prompt-hash keyed)
  - NARRCACHE-02 (NarrCacheGate fail-CLOSED mechanical-honesty classifier)
  - NARRCACHE-03 (operator off-switch + savings observability)
---

# Phase 18 — Narration response cache (CONTEXT)

## Mission

Opt-in LLM-response cache for narration prompts. Default OFF (safest stance — operators must explicitly enable). HARD mechanical-honesty gate: only PURE NARRATIVE text is cacheable. Any response with HP/AC/damage/effect tokens bypasses. Operator off-switch + cost-savings observability via Phase 13 cost calculator.

## Locked Decisions

| ID | Decision | Rationale |
|----|----------|-----------|
| **D-129** | **NARRCACHE_ENABLED defaults to FALSE.** This is the riskiest cache (potential to leak mechanical effects); operators must opt in. Document the trade-off in INSTALL.md "Optional caches" section. | Conservative default; v1.0 mechanical-honesty contract takes precedence over cost savings |
| **D-130** | **NarrCacheGate fail-CLOSED classifier**: `is_pure_narration(text: str) -> bool` returns `True` only if NONE of these regex patterns match (case-insensitive):<br>- `\b(HP|hit points?|hp\d+)\b`<br>- `\b(AC|armor class)\b`<br>- `\b(damage|dmg|takes? \d+|deals? \d+|reduced to|drops? to)\b`<br>- `\b(critical hit|crit|natural \d+)\b`<br>- `\b(saves? against|saving throw|DC \d+)\b`<br>- `\b(condition|status|prone|paralyz|stunn|charm|frighten|grappl|incapacit|invisib|petrif|poison|restrain|unconsc)\w*` (covers SRD condition words)<br>- `\b(\d+d\d+|\d+\s*hit\s*die|hp\s*[=:]\s*\d+)\b` (dice notation, HP assignment)<br>- `<player_action>` / `<damage>` / `<effect>` sentinel tokens<br>NarrCacheGate.STORE_CHECK rejects on FIRST match — no second-pass. | Fail-CLOSED: if uncertain, don't cache. Coverage validated by 50-scenario corpus (D-131) |
| **D-131** | **50-scenario test corpus** at `tests/eval/narration_corpus/`: 25 cacheable (pure flavor/description/atmosphere) + 25 non-cacheable (each demonstrates a different mechanical leak). Format: JSONL with `{id, text, expected_cacheable: bool, rationale}`. Pydantic-validated on load. Test asserts gate's classification matches `expected_cacheable` for every entry. Corpus is original Apache-2.0 (no copyrighted RPG text). | Concrete coverage of the classifier; regression guard |
| **D-132** | **Cache key**: `SHA-256(model_id + "\n" + system_prompt + "\n" + user_prompt + "\n" + str(max_tokens) + "\n" + str(temperature))`. Storing `model_id` in the key means cache hits never serve a different model's output. Storing `temperature` means deterministic-prompt assumption is baked in (if temperature > 0.3, cache hit rate will be near 0 — document this). | Avoid cross-model collisions; respect non-deterministic sampling |
| **D-133** | **L1-only architecture** (no L2 disk) — narration responses are large (kB-MB each); disk write overhead negates savings. L1 = TTLCache (cachetools-style, but stdlib OrderedDict + manual TTL since cachetools isn't in deps). `NARRCACHE_L1_SIZE` env (default 256), `NARRCACHE_L1_TTL_S` (default 3600). | Smaller scope; lower risk |
| **D-134** | **Runtime override**: `NarrCache.disable_at_runtime()` flips a process-wide `_runtime_disabled` flag. `eldritch-dm-cache-disable --narration` CLI calls this via the SmartMonsterDriver's existing degraded-mode-style mutable singleton pattern (Phase 13 D-87). Re-enable on bot restart OR `--narration --enable` flag. | Operator emergency-disable without restart |
| **D-135** | **Cost-savings KPI**: `eldritch.narrcache.savings_usd` (counter) — on each cache HIT, compute the cost the cache call WOULD HAVE incurred (using Phase 13 cost calculator) and accumulate. `eldritch.narrcache.hit_rate` + `eldritch.narrcache.rejected_count` (gate rejections). Honors OBSERVABILITY_ENABLED. | Phase 13 cost-calc tie-in proves the cache pays for itself |
| **D-136** | **CLI**: `eldritch-dm-cache-stats --narration [--since DATE] [--format json\|markdown]` reports hit_rate, total_calls, cached_calls, rejected_by_gate, savings_usd. Reads from Phase 13's span buffer (narration_cache spans). | Operator can see if cache is paying off |
| **D-137** | **Module location**: `src/eldritch_dm/observability/narration_cache.py` (sibling of cost.py, kpi.py). Tests at `tests/observability/test_narration_cache.py` + `tests/eval/test_narration_gate.py`. CLI at `src/eldritch_dm/tools/cache_stats.py`. | Observability package since cache integration is observability-heavy |
| **D-138** | **Integration point**: wraps the narration AsyncOpenAI call site in `src/eldritch_dm/ingest/translate.py` (Phase 11 already instruments that path) and the bot's narration callbacks (find via grep). `NarrCache.aget(model, system, user, **kwargs)` returns cached-or-fresh. The CALL SITE doesn't gate — `NarrCache` itself gates internally before storing (D-130). | Single integration point; gate is centralized |
| **D-139** | **2 plans**: 18-01 = narration cache + NarrCacheGate fail-closed classifier + 50-scenario corpus. 18-02 = runtime override + savings observability + eldritch-dm-cache-stats CLI. | ROADMAP plans section |

## Success Criteria
1. NARRCACHE_ENABLED=false by default
2. NarrCacheGate rejects all 25 non-cacheable corpus entries; accepts all 25 cacheable
3. 50-scenario corpus is original Apache-2.0 content
4. Cache key includes model_id + temperature (no cross-model collisions)
5. L1 with TTL eviction; respects NARRCACHE_L1_SIZE/TTL env vars
6. Runtime disable via `eldritch-dm-cache-disable --narration` + re-enable on restart or flag
7. Cost-savings KPI accumulates on hit using Phase 13 calculator
8. `eldritch-dm-cache-stats --narration` CLI reports stats
9. ≥30 new tests; ruff + lint-imports clean

## Deferred (post-v1.5)
- L2 disk cache for narration (probably never — responses too large)
- Streaming-response handling (cache stores full response; streaming requires accumulator)
- Semantic-similarity matching (current is exact-key only)
- Cross-channel cache sharing (currently per-process)
