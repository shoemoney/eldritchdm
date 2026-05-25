---
phase: 18-narration-cache
plan: 18-01
subsystem: observability
tags: [narration-cache, mechanical-honesty, opt-in, fail-closed, cache]
requirements: [NARRCACHE-01, NARRCACHE-02]
status: complete
completed: 2026-05-25
requirements_completed:
  - NARRCACHE-01
  - NARRCACHE-02
---

# Phase 18 Plan 18-01: NarrCache + NarrCacheGate + 50-scenario corpus — Summary

## One-liner

Opt-in narration response cache (default OFF) with a fail-CLOSED regex
classifier (`NarrCacheGate`) and a 50-scenario corpus that pins **0%
false-negative rate** as the non-negotiable mechanical-honesty bar.

## What landed

- `src/eldritch_dm/observability/narration_cache.py`
  - `NarrCacheGate.is_pure_narration(text) -> bool` — fail-CLOSED, 20
    compiled-once `re.IGNORECASE` patterns, short-circuits on first match.
  - `NarrCache.acompletion(client, *, model, messages, max_tokens,
    temperature, **kwargs)` — opt-in wrapper around
    `client.chat.completions.create`. Bypass when disabled / runtime-
    disabled / messages != exactly `[system, user]`. **Double-gate**: gate
    upstream response before STORE; re-gate cached content before SERVE.
  - L1 = `OrderedDict` + `asyncio.Lock` + monotonic-time TTL +
    `NARRCACHE_L1_SIZE` LRU bound.
  - Cache key = SHA-256 over `(model, system, user, max_tokens,
    temperature)` (D-132).
- `Settings.narrcache_enabled` (default **False**, D-129),
  `narrcache_l1_size` (256), `narrcache_l1_ttl_s` (3600).
- 50-scenario corpus at `tests/eval/narration_corpus/corpus.jsonl` — 25
  cacheable + 25 non-cacheable, all original Apache-2.0 text,
  pydantic-validated by `loader.py`. Includes 6 `adversarial_safe`
  cacheable entries (`took N`, `fell to one knee`, `dealer`, `critique`,
  `conditioner`, `invisibly`) that lock in regex precision, and 1
  `adversarial_leak` non-cacheable entry where `HP` means *Hidden
  Passage* (fail-CLOSED rejects regardless of intent).
- 148 new tests across:
  - `tests/observability/test_narration_gate.py` — 79 cases
  - `tests/observability/test_narration_cache.py` — 20 cases
  - `tests/eval/narration_corpus/test_loader.py` — 7 cases
  - `tests/eval/test_narration_gate_corpus.py` — 52 cases (50
    parametrized per-entry + 2 aggregate guards)

## Verification

- ruff check + ruff format: clean
- lint-imports: 8 contracts kept, 0 broken
- pytest target (all four files above): **148 passed**
- corpus 0% false-negative rate confirmed by `test_corpus_zero_false_negatives`
- corpus 0% false-positive rate confirmed by `test_corpus_zero_false_positives`

## Deviations from PLAN

### [Rule 4 — Architectural finding] D-138 obsoleted

The Phase 18 CONTEXT decision D-138 names
`src/eldritch_dm/ingest/translate.py` as "the narration AsyncOpenAI call
site" for `NarrCache` integration. Verification of every
`chat.completions.create` site in the codebase
(`ingest/translate.py`, `gameplay/smart_monster_driver.py`,
`eval/judge.py`) shows that **all three use `response_format=json_object`**
with low temperatures and small max-tokens — they parse character sheets,
route monster decisions, or judge eval scenarios. None is free-form
narration. The project's own config docstring is explicit:

> the ingest pipeline is the ONLY direct LLM call site in this codebase
> (dm20 owns narration internally) (`config/__init__.py:88-90`)

`NarrCache` therefore ships as a **standalone public API** with
`NARRCACHE_ENABLED=false` by default. It is ready to wrap a future
in-repo narration generator (or a dm20 pre-narration hook) but is NOT
wired into the JSON-mode character-sheet parser — wiring it there would
be (a) inert at runtime (gate would reject `hit_points` fields) and (b)
a mechanical-honesty footgun if a future operator flipped
`NARRCACHE_ENABLED=true` expecting narration caching.

This is documented in 18-01-PLAN.md ("Integration scope (deviation from
CONTEXT D-138)") and surfaced again in 18-VERIFICATION.md so the
decision is visible at every layer.

## Known limitations

- **Cache hit-rate is effectively zero for nondeterministic narration.**
  Cache key includes `temperature` (D-132 — needed to keep
  cross-temperature non-determinism from leaking). Real narration uses
  `temperature ≥ 0.5`, so two identical (model, system, user, max_tokens,
  temperature) tuples are rare. Hit-rate only meaningfully fires for
  deterministic prompts (e.g. an offline narration smoke-bench). This is
  documented in the cache-stats CLI output (Plan 18-02).
- **No L2 disk cache.** D-133 — narration responses are large and disk
  write latency would negate the savings. L1-only is intentional.
- **No streaming response handling.** Streaming would require an
  accumulator wrapper; v1.5 callers do not use streaming, so this is
  deferred.

## Key files

### Created
- `src/eldritch_dm/observability/narration_cache.py` (~370 lines)
- `tests/observability/test_narration_gate.py`
- `tests/observability/test_narration_cache.py`
- `tests/eval/narration_corpus/__init__.py`
- `tests/eval/narration_corpus/loader.py`
- `tests/eval/narration_corpus/corpus.jsonl` (50 entries)
- `tests/eval/narration_corpus/README.md`
- `tests/eval/narration_corpus/test_loader.py`
- `tests/eval/test_narration_gate_corpus.py`

### Modified
- `src/eldritch_dm/config/__init__.py` — `narrcache_*` Settings fields
- `.planning/REQUIREMENTS.md` — ticked NARRCACHE-01, NARRCACHE-02

## Commits

| Commit | Description |
|--------|-------------|
| `bada380` | docs(18): plans 18-01 + 18-02 |
| `73bad24` | feat(18-01): settings + narration_cache module skeleton |
| `3db875a` | test(18-01): NarrCacheGate per-pattern coverage (69 cases) |
| `96b5510` | feat(18-01): 50-scenario narration corpus + pydantic loader |
| `212ffff` | test(18-01): per-entry corpus gate classification (0% false-neg) |
| `001a727` | feat(18-01): NarrCache.acompletion with fail-CLOSED double-gate + L1 LRU+TTL |

## Self-Check: PENDING — run at phase end
