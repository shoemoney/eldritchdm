# v1.1 Polish — Research Summary

**Project:** EldritchDM
**Milestone:** v1.1 Polish (post-`v1.0` ship 2026-05-23)
**Researched:** 2026-05-23 → 2026-05-24
**Confidence:** HIGH on closure items (SAN-01, OPS-02, TD-1, TD-2, TD-3, YAML eligibility); MEDIUM on Smart MonsterDriver (novel for this repo — dm20 tactical-tool exact surface still TBD).
**Source files:** `STACK.md`, `FEATURES.md`, `ARCHITECTURE.md`, `PITFALLS.md` (all v1.1, written 2026-05-23).

---

## 1. Headline

v1.1 is a **polish + extensibility milestone**, not a new product. Its job is to close the four audit deferrals from v1.0 (SAN-01 modal coverage, OPS-02 `DM_OFFLINE` warning, TD-1 `__main__` token parity, TD-2 ruff cleanup), discharge one acknowledged debt (TD-3 `pc_classes` backfill), and add **two small forward features** (YAML-configurable Riposte eligibility, Smart Claudmaster-routed monster targeting). Net dependency change is **one promoted dep** (`pyyaml` from `[dev]` → core) plus a ruff floor bump — zero new SQLite tables, zero new MCP servers, zero new Discord-side persistent View shapes. **The one constraint to keep front-of-mind:** v1.0's "mechanically honest" integrity rule (the LLM never computes game math) must survive Smart MonsterDriver intact — Claudmaster picks a target id from the candidate set; dm20 still resolves every attack, every die, every HP change.

## 2. Stack Delta vs v1.0

| Change | Direction | What | Why | Risk |
|---|---|---|---|---|
| **`pyyaml>=6.0.3,<7.0`** | `[dev]` → core | Riposte eligibility YAML loader | YAML beats TOML for homebrew-DM author UX; `safe_load` is the only permitted API | LOW |
| **`ruff>=0.6,<1.0`** → **`ruff>=0.15,<1.0`** | floor bump | Dev tool | 0.15.14 (2026-05-21) is current stable; clears noise floor before feature diffs | LOW |
| `eldritch-dm-backfill` | NEW entry | `[project.scripts]` | Mirrors v1.0 `eldritch-dm` console script (D-23) | LOW |

### Explicitly NOT new

- **Zero new top-level pip packages.** No `jinja2`, `click`, `typer`, `rich`, `tqdm`, `watchfiles`, `ruamel.yaml`, `pydantic-yaml`, `pydantic-ai`, `instructor`, `langchain`, `pydantic-settings`.
- **Zero new SQLite tables.** Backfill writes to existing `pc_classes`; YAML on disk; Smart MonsterDriver persists nothing.
- **Zero new MCP servers.** Smart MonsterDriver adds **at most one** wrapper to `eldritch_dm.mcp.tools` (verify dm20 surface in Phase 5 spike).
- **Zero new Discord persistent View shapes.** 7 v1.0 `DynamicItem` regex registrations suffice.
- **Zero new SIM/PERF ruff rule families** (deferred to v1.2).

## 3. Per-Deliverable Matrix

| # | Deliverable | Complexity | v1.0 surface deps | Key risk | Phase |
|---|---|---|---|---|---|
| 1 | TD-2: Ruff cleanup (79 errors / 23 files) | S | All of `src/` | RUFF-2 — import-sort exposes masked cycle | 1 (FIRST) |
| 2 | TD-1: `__main__` token-fix parity | XS | `run.py` D-26 helper | TD-1-1 drift from `run.py` | 2 (bundle) |
| 3 | SAN-01: Sanitizer in 3 modals — **CharacterReviewModal + CharacterEntryModal + OptionalFieldsModal** (WeaponSelectModal scope dropped: its regex is tight enough that sanitization is redundant defense-in-depth) | S | `bot/setup_hook` audit-callback wiring | SAN-EXP-1 double-sanitization; SAN-EXP-2 table growth | 2 (bundle) |
| 4 | OPS-02: `DM_OFFLINE` ephemeral | S | `bot/warnings`; `MCPCircuitOpen` | OPS-02-1 spam (30s debounce); OPS-02-2 false positives (5s min) | 2 (bundle) |
| 5 | YAML Riposte eligibility | S | `reactions.ELIGIBLE_CLASS_SUBCLASSES`; `_normalize` | YAML-1 (`safe_load` only); YAML-3 (fail-soft); YAML-4 (extend vs replace) | 3 |
| 6 | TD-3: `pc_classes` backfill script | M | `MCPClient` + `PCClassesRepo`; new `scripts/` subpackage + 8th import-linter contract | BF-1 PID-file lock; BF-2 idempotent re-run; BF-5 read-only dry-run | 4 (parallel w/ 3) |
| 7 | Smart MonsterDriver | L | `monster_driver._random_choice` seam; `mcp/tools` (verify dm20 first) | MD-1 INT-band drift; MD-2 latency spiral; MD-3 timeout cascade; MD-6 garbage JSON | 5 (LAST) |

## 4. Convergent Build Order (all 4 researchers agreed)

**Phase 6 (was: Phase 1 in synthesizer numbering) — Ruff cleanup + cold-start E2E smoke test (FIRST, non-negotiable).** Atomic commit per ruff rule (`--select I`, `--select UP`, hand-fix). Lint-imports re-run after every batch. First commit of v1.1 is `tests/integration/test_v11_cold_start_e2e.py` (bootstrap-without-token → bootstrap-with-token → bot-start → `/start_game` → ready → narrative → attack → riposte → restart → resume; zero fixtures that pre-create state). **Gates:** `ruff check .` returns 0; lint-imports 7/7 green; pytest still 864 passing.

**Phase 7 — Small-item bundle: SAN-01 + OPS-02 + TD-1.** All three touch `bot/cogs/*` and/or `bot/setup_hook.py` — bundle to avoid two passes. TD-1 extracts shared `config/token_guard.py` helper used by both `run.py` and `__main__.py` (TD-1-1). **Closes:** G-3 + G-4 + TD-1.

**Phase 8 — YAML Riposte eligibility.** Smaller change than backfill; lands first so smart driver consumes an already-loaded eligibility set. New `gameplay/normalize.py` extracts `_normalize` from `pc_classes_repo`. **Closes:** active YAML req + `TODO(v2)` at `reactions.py:84-88`.

**Phase 9 — `pc_classes` ingest-backfill script (parallel with Phase 8).** New `scripts/` subpackage — zero file overlap with Phase 8. Adds 8th import-linter contract block. Schedule to land after Phase 7 so PID-file diff in `setup_hook` is clean. **Closes:** TD-3.

**Phase 10 — Smart MonsterDriver (LAST, largest, LLM risk).** Plan-01 is a 30-min spike to confirm dm20 exposes `claudmaster_choose_target` vs composing from `get_claudmaster_session_state`. Wrapper signature `pick_target(channel_id, monster_id, alive_pc_ids) → str` is stable either way. Up-front decisions: INT-band prompt templates (≤4 / 5-9 / ≥10) with temp 0.9 / 0.6 / 0.3; hard 1500ms `asyncio.wait_for` deadline with `random.choice` fallback; per-(round, monster_id) cache + batched goblin prompts; pydantic `TargetDecision` + adversarial corpus (≥15 cases); coalition cap (no more than `ceil(monsters/2)` may target one PC). **Logs D-28** ("LLM-as-oracle path keeps dm20 the rules-engine of record; supersedes D-B's optimistic 'route via Claudmaster' phrasing").

## 5. Top 10 Pitfalls (Severity × Likelihood)

| # | ID | Sev | Pitfall | Mitigation |
|---|---|---|---|---|
| 1 | META | CRITICAL | Cold-start E2E gap (G-1 + D-26 recurrence) | Phase 6 `test_*_cold_start_*` smoke; every feature ships fresh-user integration test |
| 2 | BF-1 | CRITICAL | Backfill races live bot → WAL writer conflict | `~/.eldritchdm/bot.pid` lock; backfill exits 5 on live PID |
| 3 | MD-3 | CRITICAL | Smart driver stall → 3s Discord ack cliff | `asyncio.wait_for(1500ms)` + random fallback; never sit on "thinking" past 2s |
| 4 | YAML-1 | CRITICAL | `yaml.load` RCE via `!!python/object/apply` | `safe_load` only; CI grep gate |
| 5 | MD-6 | CRITICAL | Claudmaster garbage JSON / hallucinated IDs | Pydantic validator `target_id in alive_combatant_ids`; one stricter retry → random fallback; never raise from driver |
| 6 | BF-2 | CRITICAL | Partial backfill leaves DB poisoned | One txn/PC; `INSERT … ON CONFLICT DO UPDATE`; resume-safe; failed-PC list in final report |
| 7 | CC-1 | CRITICAL | Untracked planning artifacts contaminate executor (v1.0 Lesson 4) | `git status` first step of every phase; explicit "do NOT touch" list; Phase 6 makes noise floor zero |
| 8 | MD-1 | HIGH | INT-4 ogre playing chess; uniform encounters | INT-band templates + temp scaling; INT≤4 sees only alive/bloodied/down, no HP numbers |
| 9 | MD-2 | HIGH | 240 LLM calls per combat | Cache per `(monster_id, round, set(alive), set(bloodied))`; batch grouped goblins; 1500ms budget |
| 10 | CC-2/CC-3 | HIGH | VERIFICATION.md skipped + REQUIREMENTS drift (v1.0 P-1/P-2) | Per-phase committed VERIFICATION.md + REQUIREMENTS tick diff line; milestone audit re-runs reconciliation |

**Also flagged for plans:** YAML-2 (no hot reload in v1.1), YAML-4 (default `extend`), MD-4 (coalition cap), MD-5 (one decision/turn architectural), BF-3 (preflight exit 6), BF-4 (`PRAGMA user_version` check), BF-5 (read-only SQLite for `--dry-run`), SAN-EXP-1 (round-trip fixture), SAN-EXP-2 (audit sweeper), OPS-02-1/2/3, TD-1-1, RUFF-1 (`--unsafe-fixes` forbidden), RUFF-2 (lint-imports per batch), RUFF-3 (pyright after UP), CC-4 (autonomous lock).

## 6. Critical Contracts to Preserve

| Contract | What it means for v1.1 | Enforced by |
|---|---|---|
| **dm20 integrity rule** — bot never computes game math | Smart MonsterDriver returns `target_character_id` only; dm20 resolves the attack. LLM is oracle, not calculator. | Architectural review gate |
| **7/7 import-linter contracts** | All v1.1 stays in existing layers; backfill adds **8th block** (`scripts/` may import `mcp`/`persistence`/`config`/`logging`; not `bot`/`ingest`) | `lint-imports` CI gate, re-run after every ruff batch + after Phase 9 |
| **EDM001 defer-discipline lint** | `await interaction.response.defer(thinking=True)` first line of every callback. SAN-01 + OPS-02 must not violate. | Custom AST lint rule |
| **Apache 2.0 license + Co-Authored-By footer** | All v1.1 commits carry footer. License unchanged. | Commit convention |
| **Atomic-commit + conventional-prefix discipline** | `feat(NN-…)`, `test(NN-NN)`, `fix(audit-v1.x)`, `docs(NN-…)`, `chore(NN-…)`. Bisect-friendly. | v1.0 retrospective Lesson 5 |
| **PLAN-N-LOCK-SEAM markers** | Not expected for v1.1; listed defensively if any phase ships a temp path | Next phase's first test grep-asserts marker gone |

## 7. Open Questions for Requirements Phase

| # | Question | Recommendation |
|---|---|---|
| 1 | dm20 tool surface — dedicated `claudmaster_choose_target` or compose from `get_claudmaster_session_state`? | 30-min Phase 10 plan-01 spike against dm20 `tool_list`. Wrapper signature `pick_target(channel_id, monster_id, alive_pc_ids) → str` is stable. |
| 2 | YAML loader path — 3-tier (env / per-install / in-repo) or `.eldritch/`? | **3-tier env > per-install > in-repo default** per ARCHITECTURE §2.1. Ship `database/eligibility.yaml` with v1.0 D-C frozenset so vanilla installs are byte-identical. |
| 3 | PID-file location — cwd or user-home? | **`~/.eldritchdm/bot.pid`** — launchd/systemd cwd is non-obvious. Document in CONFIGURATION.md. |
| 4 | YAML reload trigger — SIGHUP / admin command / file-watcher? | **None in v1.1 — restart-to-apply.** Matches Foundry/5eTools convention. v1.2 candidate. |
| 5 | Backfill `--force` semantics — overwrite or reprocess-failed? | **`--force` = overwrite existing.** Default = skip present. `--only=pc_03,pc_07` for surgical retries. |

## 8. Lessons from v1.0 to Enforce in v1.1

1. **REQUIREMENTS.md tick at plan closure is a hard gate.** Every plan's closure checklist includes "tick associated req(s) in `v1.1-REQUIREMENTS.md`" as a reviewable diff line. Milestone close re-runs v1.0 reconciliation script.
2. **VERIFICATION.md is a hard gate per phase.** Template includes "cold-start E2E covered?" checkbox.
3. **First commit of v1.1 is a fresh-install smoke test.** `tests/integration/test_v11_cold_start_e2e.py` — no `conftest` fixtures that pre-create state a fresh user wouldn't have. CI gate.
4. **Subagent prompts list "do NOT touch" files explicitly when working tree has unrelated dirty files.** Prefer: stash/commit planning artifacts before kicking off executors.
5. **Decision IDs continue v1.0 sequence.** v1.0 ended at D-A, D-B, D-C, …, D-26, D-F, D-27. **Next available is D-28.** Smart MonsterDriver supersedes D-B as a *new* D-28, not as an edit.
6. **Atomic commits, conventional prefixes, one rule per ruff batch.** Phase 6: `chore(06-ruff): apply --select I` → `chore(06-ruff): apply --select UP` → `fix(06-ruff): hand-fix B904 in <file>`. Pytest + lint-imports after every batch.
7. **Single-instance lock for `/gsd-autonomous` runs.** v1.0 stranded ~10 zsh-wrapped pytest processes. Flag in PROJECT.md "Strategy notes".

---

## Confidence Assessment

| Area | Confidence | Notes |
|---|---|---|
| Stack | HIGH | All 4 libs verified against PyPI 2026-05-23; Context7 confirms `safe_load` + ruff `--unsafe-fixes` |
| Features | MEDIUM-HIGH | YAML/backfill HIGH (Foundry/Alembic/5eTools converge); Smart MonsterDriver MEDIUM-HIGH (no in-repo precedent) |
| Architecture | HIGH | All 7 deliverables fit existing layers; one new contract block; wiring sites verified line-by-line |
| Pitfalls | HIGH on v1.0-derived; MEDIUM on Smart MonsterDriver (novel) |

**Overall:** HIGH. Closure-heavy milestone (4/7 are v1.0 deferrals with known fixes) + 2 contained features. Dominant residual risk: Smart MonsterDriver latency/integrity — addressed by hard deadline + random fallback + adversarial corpus + integrity-rule audit.

## Gaps for Requirements Phase

- Smart driver budget — 1500ms vs 1000ms? (Recommend 1500ms; instrument; tighten in v1.2.)
- Backfill binary name — `eldritch-dm-backfill-pc-classes` vs `eldritch-dm-backfill`? (Recommend latter — shorter, v1.2 can subcommand.)
- YAML `version` field — optional default 1, reject 2+ until v1.2 exists.
- OPS-02 queue-replay for combat-critical buttons — v1.1 or v1.2? Make the call up-front.
- Cold-start E2E test exact step list — confirm before Phase 6 plan starts.

## Sources

- **PyPI (2026-05-23):** PyYAML 6.0.3, ruamel.yaml 0.19.1, click 8.4.1, ruff 0.15.14
- **Context7:** `/astral-sh/ruff` (`--unsafe-fixes` semantics), `/yaml/pyyaml` (safe_load posture)
- **In-repo:** RETROSPECTIVE.md, v1.0-MILESTONE-AUDIT.md, PROJECT.md, debug/resolved/preflight-requires-token.md (D-26), src/eldritch_dm/gameplay/{reactions,monster_driver}.py, src/eldritch_dm/bot/{__main__,modals,setup_hook}.py, src/eldritch_dm/persistence/pc_classes_repo.py, pyproject.toml
- **Domain general:** discord.py 2.7.1 3s ack budget; SQLite WAL single-writer semantics; pydantic v2 `ConfigDict(extra='forbid')`; Foundry VTT / 5eTools homebrew JSON convention; Alembic data-migration idempotency; Keith Ammann + Oracle-RPG monster-AI heuristics; Friends & Fables LLM-oracle + rules-engine pattern
