---
phase: 12-llm-judge-tactical
milestone: v1.2
generated: 2026-05-24
mode: auto-generated (autonomous-flow, discuss skipped per 'go with recommendations')
source_requirements:
  - EVAL-01 (TacticalJudge + versioned prompt)
  - EVAL-02 (50-scenario corpus across 5 archetypes)
  - EVAL-03 (eldritch-dm-eval CLI + baseline diff)
source_design:
  - .planning/phases/10-smart-monsterdriver/10-AI-SPEC.md §1b (4 evaluation dimensions) + §5 (judge pattern) + §6 (offline flywheel)
---

# Phase 12 — LLM-as-Judge Tactical Scoring (CONTEXT)

## Mission

Build the evaluation flywheel. A separate `TacticalJudge` LLM scores each
SmartMonsterDriver decision against the AI-SPEC §1b dimensions (Tactical
Intent, Meta-knowledge Guardrails, Narrative Fairness, Edge-Case Handling).
A 50-scenario hand-curated corpus exercises the 5 archetypes that AI-SPEC
identified as the highest-stakes failure modes. The `eldritch-dm-eval` CLI
runs corpus → driver → judge → aggregate report, with `--baseline` for
regression detection.

## Locked Decisions (autonomous)

| ID | Decision | Rationale |
|----|----------|-----------|
| **D-71** | **Judge uses the SAME AsyncOpenAI client pattern as SmartMonsterDriver** (local oMLX/ShoeGPT by default; configurable via `--judge-model` to swap to hosted OpenAI for higher-quality eval). NEVER use OpenAI `.beta.chat.completions.parse` strict mode — same compatibility caveat as D-51. | Mirrors Phase 10's pattern; allows operators to escape-hatch to a stronger judge for higher-stakes audits |
| **D-72** | **Judge prompt versioned via SemVer header** in `src/eldritch_dm/eval/prompts/judge.txt`: first line is `# judge-prompt-version: 1.0.0`. Eval runs record this version in their JSON output. Bumping judge prompt → bump major if scoring semantics change, minor if rubric clarifies. | AI-SPEC §5 reproducibility — prior eval runs must remain comparable to new ones |
| **D-73** | **JudgeVerdict pydantic model**: `overall_score: float [0.0, 1.0]`, `per_dimension: dict[Literal["tactical_intent","meta_knowledge","narrative_fairness","edge_case"], float [0.0, 1.0]]`, `reasoning: str` (≤500 chars), `would_a_veteran_dm_approve: bool`. Post-parse validator: `overall_score == mean(per_dimension.values())` ± 0.05 (catches judge math errors). | AI-SPEC §1b dimensions + verifier-driven sanity check |
| **D-74** | **Corpus is JSONL** (one scenario per line) at `tests/eval/dataset/tactical_corpus.jsonl`. Each entry: `{scenario_id, archetype, monster_stats, pc_list, environment, expected_target_pool, expected_avoidance, rationale}`. ScenarioEntry pydantic schema validates on load. | JSONL — easy to diff in PRs; archetype-balanced 10×5 = 50 |
| **D-75** | **5 archetypes (10 scenarios each)** mapping 1:1 to AI-SPEC §1b dimensions: low-INT brute (tests tactical-intent floor), high-INT spellcaster (tactical-intent ceiling), swarm tactician (focus-fire avoidance — narrative fairness), predator/executioner (anti-griefing baited scenario — narrative fairness lower bound), edge-case (cover/invisibility — edge-case handling). | AI-SPEC §1b Known Failure Modes mapped to detectable signals |
| **D-76** | **Corpus is ORIGINAL Apache-2.0 content**. Each scenario is hand-authored (not derived from *The Monsters Know What They're Doing* or any copyrighted RPG content). Names/places use SRD-safe references only. License header at top of file documents this. | Ammann's book is copyrighted; we use it as inspiration NOT source material |
| **D-77** | **`eldritch-dm-eval` CLI**: new `[project.scripts]` entry. Flags: `--dataset PATH` (default: bundled corpus), `--judge-model NAME` (default ShoeGPT, alias `gpt-4o` documented for escape-hatch use), `--driver-model NAME` (default ShoeGPT), `--limit N` (run only first N scenarios), `--baseline PATH` (diff against prior eval JSON), `--output DIR` (default `./eval-runs/`), `--verbose`. | Phase 9 backfill CLI pattern; baseline diff is the regression-detection hook |
| **D-78** | **Output format**: `eval-{ISO timestamp}-{git short sha}.json` summary with per-scenario verdict + aggregate stats + judge-prompt-version + driver-model + judge-model. Alongside, `eval-{...}.md` human-readable report (markdown table of failures, top 3 reasons). | Machine-readable diff + human-readable triage |
| **D-79** | **Exit codes**: 0 = passed (avg overall ≥ 0.7, no dimension avg < 0.5); 1 = regression (baseline supplied, avg dropped > 0.05); 2 = critical (any dimension avg < 0.5 regardless of baseline). Documented in `--help`. | CI/CD-friendly; operator can gate releases on `eldritch-dm-eval --baseline last-release.json` returning 0 |
| **D-80** | **Driver invocation bypasses Discord**: eval CLI imports `make_monster_driver(env_override="smart")` and calls `_pick_target()` directly. NO mock dm20, NO mock combat state — just raw monster + PC list + environment. The OBS-01 spans STILL emit during eval (judge_eval traces visible in Phoenix for debug). | Tests the actual production code path; spans give us debug visibility |
| **D-81** | **Judge call SHOULD be observability-instrumented too** (re-use Phase 11's `traced_decision`): wraps the judge call with span attributes `eldritch.eval.scenario_id`, `eldritch.eval.judge_model`, `eldritch.eval.driver_model`, `eldritch.eval.archetype`. | Closes the loop — eval runs ARE part of the data we want to observe |
| **D-82** | **Module location**: `src/eldritch_dm/eval/__init__.py`, `eval/judge.py`, `eval/scenarios.py` (loader), `eval/cli.py` (entry point), `eval/aggregator.py` (stats + diff), `eval/reporter.py` (markdown). Tests at `tests/eval/` + corpus at `tests/eval/dataset/`. | New package; mirrors `tools/` (Phase 9) and `observability/` (Phase 11) |

## Implementation Sketch

**Plan 01 (12-01-PLAN.md) — TacticalJudge + prompt + corpus loader:**
1. `eval/judge.py`: `TacticalJudge` class (AsyncOpenAI wrapper), `JudgeVerdict` pydantic model with post-parse validator
2. `eval/prompts/judge.txt`: versioned prompt (SemVer header) describing 4 dimensions + 0-1 scoring rubric + JSON output schema
3. `eval/scenarios.py`: `ScenarioEntry` pydantic schema + `load_scenarios(path)` (JSONL streaming) + corpus validation script
4. Unit tests: schema validation, judge prompt loads, mocked LLM happy path + malformed-JSON fallback + dimension-mean validation

**Plan 02 (12-02-PLAN.md) — 50-scenario corpus + eldritch-dm-eval CLI + baseline diff:**
1. `tests/eval/dataset/tactical_corpus.jsonl`: 50 scenarios across 5 archetypes (10 each), all original Apache-2.0 content
2. `eval/cli.py`: argparse with D-77 flags; orchestrates driver + judge; writes JSON + Markdown outputs to `--output` dir
3. `eval/aggregator.py`: aggregates per-scenario verdicts → overall stats + per-archetype breakdown; baseline-diff logic (D-79 exit codes)
4. `eval/reporter.py`: Markdown report (failures table, top 3 reasons, archetype scoreboard)
5. Phase 11 OTel integration: judge call wrapped with `traced_decision` (D-81 attributes)
6. Tests: end-to-end CLI smoke (mocked LLM, 1 scenario), aggregator math, baseline-diff exit codes, schema validation against malformed corpus

## Success Criteria (from ROADMAP)

1. TacticalJudge returns `JudgeVerdict` per D-73; judge prompt versioned
2. 50-scenario corpus across 5 archetypes (10 each)
3. `eldritch-dm-eval` CLI with --dataset/--judge-model/--driver-model/--limit/--baseline flags
4. Exit codes: 0 passed, 1 regression, 2 critical
5. Corpus is original Apache-2.0 content (license header documents this)
6. Tests: schema validation, end-to-end CLI smoke (mocked LLM)

## Deferred (post-v1.2)

- Crowd-sourced corpus expansion (veteran DM contributions via GitHub PRs) — v1.3
- Inter-judge agreement studies (run 2 different judges, compute Cohen's kappa) — v1.3
- Auto-detect drift (judge model upgrade → re-baseline) — v1.3
- Judge with chain-of-thought reasoning visible in Phoenix dashboards — could be added now if simple
