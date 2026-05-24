# Roadmap: EldritchDM

## Milestones

- ✅ **v1.0 MVP — Mechanically Honest AI Dungeon Master** — Phases 1-5 (shipped 2026-05-23) — see [`milestones/v1.0-ROADMAP.md`](milestones/v1.0-ROADMAP.md)
- 🚧 **v1.1 Polish** — Phases 6-10 (in progress) — close v1.0 audit deferrals + add Smart MonsterDriver + homebrew YAML eligibility

## Phases

<details>
<summary>✅ v1.0 MVP (Phases 1-5) — SHIPPED 2026-05-23</summary>

- [x] **Phase 1**: MCP Client + Local State (3/3 plans)
- [x] **Phase 2**: Discord Scaffold + Persistent Views (3/3 plans)
- [x] **Phase 3**: Lobby + Character Ingest (3/3 plans)
- [x] **Phase 4**: Gameplay — Exploration + Combat (3/3 plans)
- [x] **Phase 5**: Reactions + Self-Host Polish (3/3 plans)

**Final stats:** 5 phases · 15 plans · 110 commits · 864 tests passing / 873 collected · 7/7 import-linter contracts kept · 71/73 requirements satisfied (97%).

**Tag:** `v1.0` · **Repo:** https://github.com/shoemoney/eldritchdm

</details>

### 🚧 v1.1 Polish (Phases 6-10)

- [ ] **Phase 6**: Debt Paydown + Cold-Start Smoke — 2 plans
- [ ] **Phase 7**: Safety Gap Closure (G-3 + G-4 + TD-1) — 1 plan
- [ ] **Phase 8**: YAML Riposte Eligibility — 1 plan
- [ ] **Phase 9**: pc_classes Ingest-Backfill Script — 1 plan
- [ ] **Phase 10**: Smart MonsterDriver (Claudmaster-routed targeting) — 2 plans

**Total v1.1 plan estimate:** 7 plans · ~9 requirements · estimated 4–6 working days

## Phase Details

### Phase 6: Debt Paydown + Cold-Start Smoke
**Goal**: Reduce ruff debt to zero and lock in the cold-start E2E discipline that v1.0 audit's G-1 lesson taught — first commit of v1.1 makes the recurrence of that bug class impossible.
**Mode:** infrastructure (no user-visible behavior change)
**Depends on**: Nothing (v1.0 baseline)
**Requirements**: DEBT-01, DEBT-02
**Success Criteria**:
  1. `ruff check src/ tests/ run.py` returns **0 errors** (was 79); ruff floor in pyproject bumped to `>=0.15,<1.0`
  2. New `tests/integration/test_cold_start_e2e.py` exists, uses zero shared fixtures, exercises bot.setup_hook → lobby → ready → orchestrator-alive assertion within a single process lifetime
  3. The new cold-start test **fails** when applied against v1.0 commit `7d307a1` (Phase 5 Plan 03 closure, before G-1 fix landed) and **passes** against current main — proves the test would have caught G-1
  4. Full test suite passes; 7/7 import-linter contracts still kept; pre-commit hooks unchanged
**Plans**:
- [ ] Plan 01: Ruff cleanup (`fix(debt): ruff cleanup — 79 errors → 0 across 23 files`) — apply `--fix` to 43 auto-fixable, hand-fix remaining 36, bump pyproject floor, atomic-commit per file group
- [ ] Plan 02: Cold-start E2E smoke (`test(debt): cold-start E2E smoke test (DEBT-02)`) — write test that constructs a fresh bot, simulates lobby + ready click, asserts orchestrator is alive; verify it catches G-1 against the historical commit before passing on current main

### Phase 7: Safety Gap Closure
**Goal**: Close the three v1.0 audit deferrals (SAN-01 modal coverage, OPS-02 DM_OFFLINE warning, `__main__` token-fix parity) with shared infrastructure.
**Mode:** mvp (closes audit debt)
**Depends on**: Phase 6 (clean ruff baseline; cold-start test infrastructure)
**Requirements**: SAFETY-01, SAFETY-02, SAFETY-03
**Success Criteria**:
  1. `sanitize_player_input` wired into `WeaponSelectModal` + `CharacterReviewModal` + `OptionalFieldsModal` (3 modals per Architecture research). Each strip event writes a `sanitizer_audit` row in the existing v1.0 table; integration test proves it
  2. `MCPCircuitOpen` no longer escapes to discord.py's default error handler; ephemeral `DM_OFFLINE` warning dispatched within 100ms; per-channel debounce caps the warning to 1 per 30s
  3. `python -m eldritch_dm.bot` with unset `DISCORD_TOKEN` exits **4** with friendly stderr referencing `.env.example` — no opaque `discord.errors.LoginFailure` traceback. Shared token-validation helper extracted between `run.py` and `__main__.py`
  4. 15+ new tests cover the 3 modal sanitization paths, circuit-open warning surface, debounce behavior, and `__main__` token-missing path
**Plans**:
- [ ] Plan 01: Safety bundle (`fix(audit-v1.1): SAN-01 + OPS-02 + TD-1 close — shared token helper + circuit-open decorator`) — single plan with 3 atomic commits, one per gap

### Phase 8: YAML Riposte Eligibility
**Goal**: Let homebrewers add Riposte-eligible subclasses (Swashbuckler Rogue, third-party content) without touching code, while keeping the v1.0 D-C strict-RAW Battle Master Fighter as the shipped default.
**Mode:** mvp (user-visible extensibility surface)
**UI hint:** no (config-file feature; users restart bot to apply)
**Depends on**: Phase 7 (clean safety baseline; helper patterns established)
**Requirements**: HOMEBREW-01, HOMEBREW-02
**Success Criteria**:
  1. New `database/eligibility.yaml` ships with `{fighter: [battle master]}` — matches v1.0 RAW default exactly
  2. New `src/eldritch_dm/gameplay/eligibility_loader.py` resolves YAML in 3-tier precedence (env > per-install > in-repo), pydantic-validated, `safe_load` only, fail-soft to defaults on bad YAML with structured-log warning
  3. CI grep gate fails the build if `yaml.load` (unsafe) ever appears in the codebase
  4. Extend-not-override is the default; explicit `mode: replace` opt-in. Override semantics documented in INSTALL.md with an example
  5. `reactions.ELIGIBLE_CLASS_SUBCLASSES` no longer hardcoded — pulled from loader. Existing v1.0 Riposte tests still green (default YAML preserves v1.0 behavior)
**Plans**:
- [ ] Plan 01: YAML loader + Riposte wiring (`feat(homebrew): YAML-configurable Riposte eligibility (HOMEBREW-01/02)`) — normalize helper extraction, loader implementation, default YAML, reactions.py refactor, pydantic schema, fail-soft tests, CI safe_load gate

### Phase 9: pc_classes Ingest-Backfill Script
**Goal**: Give self-hosters upgrading from v1.0 → v1.1 a one-shot tool to populate the `pc_classes` table from their existing dm20 characters — closes the silent-no-Riposte-fires gap TD-3 documented in v1.0 audit.
**Mode:** mvp (operational tooling)
**Depends on**: Phase 8 (eligibility loader stable — backfill must populate data the loader will consume)
**Requirements**: UPGRADE-01
**Success Criteria**:
  1. `pip install -e .` exposes `eldritch-dm-backfill-pc-classes` on PATH (new `[project.scripts]` entry); imports tested in CI
  2. Script reuses `MCPClient` + circuit breaker — no new HTTP code; pulls character class/subclass from dm20, writes to local `pc_classes` table
  3. `--dry-run` opens SQLite read-only; impossible to mutate. `--force` reprocesses already-populated rows. `--help` documents both
  4. Idempotent re-run via `INSERT … ON CONFLICT DO NOTHING`; running script twice produces no duplicate rows and no errors
  5. PID-file lock check at `eldritch.pid` aborts with "❌ Bot is running, stop it first" if pidfile exists; otherwise creates pidfile + removes on exit
  6. New `tests/scripts/test_backfill_pc_classes.py` covers: dry-run safety, idempotency, dm20-unreachable graceful exit, bot-running lock check, --force behavior
**Plans**:
- [ ] Plan 01: Backfill script + import-linter contract (`feat(upgrade): pc_classes ingest-backfill script (UPGRADE-01)`) — new `src/eldritch_dm/scripts/` subpackage, new import-linter contract block (scripts may import mcp + persistence, not bot/ingest), console-script entry, lock helper, integration tests

### Phase 10: Smart MonsterDriver (Claudmaster-Routed Targeting)
**Goal**: Replace v1.0's random monster target selection with INT-gated, Claudmaster-routed targeting — using LLM-as-oracle with the existing AsyncOpenAI client, no new MCP dependencies. Largest v1.1 deliverable; lands last after every other piece is stable.
**Mode:** mvp (combat UX improvement)
**UI hint:** no (transparent to players — monsters just pick smarter targets)
**Depends on**: Phase 9 (stable v1.1 baseline; full test corpus in place)
**Requirements**: COMBAT-13, COMBAT-14
**Success Criteria**:
  1. New `src/eldritch_dm/gameplay/smart_monster_driver.py` replaces `monster_driver.py`'s random `_pick_target`. `MONSTER_DRIVER` env var (`smart` default, `random` escape hatch, `mixed` per-INT) wired into the orchestrator's MonsterDriver factory
  2. **INT-gating** verified: monster with `INT <= 4` calls v1.0 random path; monster with `INT >= 8` calls LLM oracle; corpus tests prove both paths
  3. **1500ms hard deadline** verified: synthetic test injects a 2000ms-delayed LLM response and asserts random fallback fired with structured-log entry. Player-visible embed stalls do not exceed 2s
  4. **Pydantic-validated output** (`MonsterTacticChoice` model with `target_pc_id: str` field whose validator rejects IDs not in the candidate set): hallucinated IDs trigger fallback, NOT exception
  5. **Per-round cache**: re-asking the LLM for the same `(channel_id, round, monster_id)` returns cached value; assertion in test that LLM mock was called once across two reads
  6. New `tests/gameplay/test_smart_monster_driver.py` + `tests/gameplay/test_monster_driver_corpus.py` cover: 15+ adversarial scenarios (malformed JSON, hallucinated ID, timeout, empty candidates, sub-INT bypass, focus-fire-detection, recursive decision)
  7. Full v1.1 test suite green; pc_classes table populated by Phase 9's backfill so eligibility checks resolve correctly during smart targeting
**Plans**:
- [ ] Plan 01: dm20 contract verification + smart driver core (`feat(combat-13a): smart MonsterDriver — dm20 surface check + INT-gating + LLM oracle`) — verify whether `dm20__get_claudmaster_session_state` returns `next_target` (research's open question); implement smart driver with INT-gating, pydantic validation, 1500ms timeout, random fallback
- [ ] Plan 02: Adversarial corpus + per-round cache + closure (`test(combat-14): smart MonsterDriver adversarial corpus + cache + Phase 10 closure`) — 15-scenario corpus, per-round cache implementation, MONSTER_DRIVER env-var integration, v1.1 SUMMARY.md, REQUIREMENTS.md [x] marks, STATE.md cursor

## Traceability

| REQ-ID | Phase | Source Plan |
|---|---|---|
| DEBT-01 | 6 | 6-01-PLAN-ruff-cleanup |
| DEBT-02 | 6 | 6-02-PLAN-cold-start-e2e |
| SAFETY-01 | 7 | 7-01-PLAN-safety-bundle |
| SAFETY-02 | 7 | 7-01-PLAN-safety-bundle |
| SAFETY-03 | 7 | 7-01-PLAN-safety-bundle |
| HOMEBREW-01 | 8 | 8-01-PLAN-yaml-eligibility |
| HOMEBREW-02 | 8 | 8-01-PLAN-yaml-eligibility |
| UPGRADE-01 | 9 | 9-01-PLAN-pc-classes-backfill |
| COMBAT-13 | 10 | 10-01-PLAN-smart-monster-driver |
| COMBAT-14 | 10 | 10-02-PLAN-smart-driver-corpus |

## Progress

| Phase | Milestone | Plans Complete | Status | Completed |
|---|---|---|---|---|
| 1. MCP Client + Local State | v1.0 | 3/3 | ✅ Complete | 2026-05-21 |
| 2. Discord Scaffold + Persistent Views | v1.0 | 3/3 | ✅ Complete | 2026-05-21 |
| 3. Lobby + Character Ingest | v1.0 | 3/3 | ✅ Complete | 2026-05-21 |
| 4. Gameplay — Exploration + Combat | v1.0 | 3/3 | ✅ Complete | 2026-05-22 |
| 5. Reactions + Self-Host Polish | v1.0 | 3/3 | ✅ Complete | 2026-05-23 |
| 6. Debt Paydown + Cold-Start Smoke | v1.1 | 2/2 | Complete   | 2026-05-24 |
| 7. Safety Gap Closure | v1.1 | 1/1 | Complete   | 2026-05-24 |
| 8. YAML Riposte Eligibility | v1.1 | 0/1 | Not started | — |
| 9. pc_classes Ingest-Backfill Script | v1.1 | 0/1 | Not started | — |
| 10. Smart MonsterDriver | v1.1 | 0/2 | Not started | — |

---
*Last revised: 2026-05-24 after v1.1 Polish research synthesis (Stack + Features + Architecture + Pitfalls all converged on this 5-phase build order)*
