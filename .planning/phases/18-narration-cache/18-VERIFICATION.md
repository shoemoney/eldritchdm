---
phase: 18-narration-cache
status: complete
verified: 2026-05-25
---

# Phase 18 — Verification

## Success criteria

- [x] 18-01-PLAN.md + 18-02-PLAN.md committed (`bada380`).
- [x] `src/eldritch_dm/observability/narration_cache.py` ships `NarrCache`
  (L1 `OrderedDict` + monotonic TTL + `asyncio.Lock`) and `NarrCacheGate`
  (20 compiled fail-CLOSED regexes).
- [x] `NARRCACHE_ENABLED` defaults to **False** (verified by
  `Settings.narrcache_enabled` and tested in
  `test_bypass_when_disabled_via_env`).
- [x] `NarrCacheGate.is_pure_narration(text)` — fail-CLOSED — rejects on
  ANY pattern match (short-circuits).
- [x] 50-scenario corpus at `tests/eval/narration_corpus/corpus.jsonl` —
  25 cacheable + 25 non-cacheable — Apache-2.0 original content
  (pydantic-validated).
- [x] Per-entry test asserts `gate.is_pure_narration(text) ==
  expected_cacheable` for ALL 50 entries. **0% false-negative rate**
  enforced by `test_corpus_zero_false_negatives` AND the per-entry
  parametrized assertion.
- [x] Cache key SHA-256 over `(model_id, system, user, max_tokens,
  temperature)` (verified by `test_cache_key_differs_per_input`).
- [x] L1-only; honors `NARRCACHE_L1_SIZE` (default 256) +
  `NARRCACHE_L1_TTL_S` (default 3600) env (verified by
  `test_lru_eviction_at_size_limit` + `test_ttl_expiry_drops_entry`).
- [x] `eldritch-dm-cache-disable --narration [--enable]` CLI (runtime
  override); registered in `pyproject.toml`.
- [x] `eldritch-dm-cache-stats --narration` CLI reads from Phase 13 span
  buffer; markdown + JSON output.
- [x] KPIs `eldritch.narrcache.layer` + `eldritch.narrcache.savings_usd`
  surfaced via Phase 11 OTel + Phase 13 buffer; emitted by every
  `NarrCache.acompletion` call.
- [ ] Integration into `src/eldritch_dm/ingest/translate.py` narration
  call site — **NOT MET. See "Deviations" below for the architectural
  reason.**
- [x] ≥30 new tests — actual: 148 (Plan 18-01) + 27 (Plan 18-02) = **175
  new tests**.
- [x] ruff + lint-imports clean (8 contracts kept, 0 broken).
- [x] NARRCACHE-01 / NARRCACHE-02 / NARRCACHE-03 ticked in REQUIREMENTS.md.
- [x] 18-01-SUMMARY.md + 18-02-SUMMARY.md + 18-VERIFICATION.md committed.
- [x] STATE.md + ROADMAP.md NOT modified (per phase objective).

### Hard constraint (mechanical-honesty contract)

- [x] **0% false-negative rate** on the 50-scenario corpus —
  `test_corpus_zero_false_negatives` passes; mechanical text is NEVER
  accepted by the gate.
- [x] **0% false-positive rate** also achieved (quality bar) — no
  cacheable corpus entry is wrongly rejected.

## Deviations

### [Rule 4 — Architectural finding] D-138 obsoleted

CONTEXT decision D-138 names `src/eldritch_dm/ingest/translate.py` as
"the narration AsyncOpenAI call site". Discriminator grep
(`chat.completions.create` with free-form content) returns three sites:

1. `src/eldritch_dm/ingest/translate.py` — `response_format=json_object`, `temperature=0.05`, character-sheet schema parser.
2. `src/eldritch_dm/gameplay/smart_monster_driver.py` — `response_format=json_object`, `temperature=0.2`, monster routing.
3. `src/eldritch_dm/eval/judge.py` — `response_format=json_object`, `temperature=0.0`, eval scoring.

**None is free-form narration.** The project's own `config/__init__.py`
docstring is explicit:

> the ingest pipeline is the ONLY direct LLM call site in this codebase
> (dm20 owns narration internally)

Wiring `NarrCache` into the JSON-mode character-sheet parser would be
(a) inert at runtime — the gate would reject any field containing
`hit_points` — and (b) a footgun if a future operator flipped
`NARRCACHE_ENABLED=true` expecting narration caching.

**Resolution:** `NarrCache` ships as a **standalone public API** ready
to wrap a future in-repo narration generator (or a `dm20` pre-narration
hook) the moment one is added. The success criterion is intentionally
unmet, and is documented at every layer:

- 18-01-PLAN.md "Integration scope (deviation from CONTEXT D-138)"
- 18-01-SUMMARY.md "Deviations from PLAN → [Rule 4]"
- This file (18-VERIFICATION.md)

## Regex risk register (advisor consultations)

Two advisor consultations during Plan 18-01 shaped the gate:

1. **Pre-design** — confirmed standalone-API approach was correct (D-138 obsolete) and recommended deferring regex-set review until adversarial corpus entries were drafted.
2. **Pre-implementation** — recommended:
   - Per-pattern compiled tuple (`re.IGNORECASE`) at module load. **Done.**
   - Short-circuit on first match. **Done.**
   - Split condition-stem regex (`paralyz\w*`) from complete-word regex
     (`\bprone\b`) so `\bprone\w*` doesn't swallow word boundary on
     additions. **Done — D-130's single pattern was split into two.**
   - Per-entry parametrized corpus assertion (not aggregate). **Done —
     `test_gate_classification_matches_corpus[entry.id]` reports the
     offending entry's rationale on failure.**
   - Document the `temperature` cache-key trade-off (real narration runs
     at `temp ≥ 0.5`, so hit-rate is rare). **Done — 18-01-SUMMARY.md
     "Known limitations" + the CLI's markdown output footer.**

## Known limitations

- **Cache hit-rate is effectively zero for nondeterministic narration.**
  Cache key includes `temperature` (D-132). Real narration uses
  `temperature ≥ 0.5`, so identical-key tuples are rare. Hit-rate fires
  for deterministic prompts (offline benches, repeated identical
  smoke-tests). See 18-01-SUMMARY.md.
- **L1-only.** D-133 — narration responses are large; disk write
  latency would negate the savings.
- **No streaming response handling.** Streaming would require an
  accumulator wrapper; v1.5 callers do not stream.
- **No integration call site.** See "Deviations" above.

## Files (created + modified)

### Created
- `src/eldritch_dm/observability/narration_cache.py`
- `src/eldritch_dm/observability/narrcache_runtime.py`
- `src/eldritch_dm/tools/cache_disable.py`
- `src/eldritch_dm/tools/cache_stats.py`
- `tests/observability/test_narration_gate.py`
- `tests/observability/test_narration_cache.py`
- `tests/observability/test_narrcache_runtime.py`
- `tests/observability/test_narrcache_spans.py`
- `tests/tools/test_cache_disable.py`
- `tests/tools/test_cache_stats.py`
- `tests/eval/narration_corpus/__init__.py`
- `tests/eval/narration_corpus/loader.py`
- `tests/eval/narration_corpus/corpus.jsonl` (50 entries)
- `tests/eval/narration_corpus/README.md`
- `tests/eval/narration_corpus/test_loader.py`
- `tests/eval/test_narration_gate_corpus.py`
- `.planning/phases/18-narration-cache/18-01-PLAN.md`
- `.planning/phases/18-narration-cache/18-02-PLAN.md`
- `.planning/phases/18-narration-cache/18-01-SUMMARY.md`
- `.planning/phases/18-narration-cache/18-02-SUMMARY.md`
- `.planning/phases/18-narration-cache/18-VERIFICATION.md` (this file)

### Modified
- `src/eldritch_dm/config/__init__.py` — `narrcache_*` Settings fields
- `src/eldritch_dm/observability/instrumentation.py` — `traced_narrcache` + `_to_row` mapping
- `pyproject.toml` — `eldritch-dm-cache-disable` + `eldritch-dm-cache-stats` scripts
- `.planning/REQUIREMENTS.md` — ticked NARRCACHE-01/02/03

## Test totals

| Suite | Count |
|-------|-------|
| `tests/observability/test_narration_gate.py` | 79 |
| `tests/observability/test_narration_cache.py` | 20 |
| `tests/observability/test_narrcache_runtime.py` | 9 |
| `tests/observability/test_narrcache_spans.py` | 6 |
| `tests/eval/narration_corpus/test_loader.py` | 7 |
| `tests/eval/test_narration_gate_corpus.py` | 52 |
| `tests/tools/test_cache_disable.py` | 5 |
| `tests/tools/test_cache_stats.py` | 7 |
| **Total new tests** | **185** |

(Plan said ≥30; delivered 185.)

## Self-Check

- All listed files exist on disk.
- All 6 task commits present in `git log` on branch
  `worktree-agent-a39582424f8d2f2b3`.
- Final pytest invocation:
  `pytest tests/observability/ tests/eval/ tests/tools/ -q` →
  **all passing**.
