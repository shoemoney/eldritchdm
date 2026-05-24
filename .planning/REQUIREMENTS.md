# EldritchDM — Requirements (v1.1 Polish)

**Milestone:** v1.1 Polish
**Goal:** Close v1.0 audit deferrals, add homebrew extensibility (YAML Riposte eligibility), close the v1.0 → v1.1 upgrade gap (`pc_classes` backfill), and level up combat AI from random to Claudmaster-routed targeting.
**Total v1.1 requirements:** 9 across 5 categories.

---

## v1.1 Requirements

### DEBT — Debt Paydown + Cold-Start Discipline

- [x] **DEBT-01**: All 79 ruff errors across the 23 pre-existing files reduced to 0. Ruff floor bumped to `>=0.15,<1.0` in `pyproject.toml`. Existing rule set (`E,F,I,UP,B,ASYNC`) preserved — no new rules in v1.1.
- [x] **DEBT-02**: Cold-start E2E smoke test (`tests/integration/test_cold_start_e2e.py`) exercises the documented quickstart path end-to-end with NO shared fixtures pre-creating state: bot.setup_hook → simulate `/start_game` → simulate ready-up → assert orchestrator task is alive in the SAME process lifetime. Closes the v1.0 audit G-1 lesson (test failed before fix, passes after).

### SAFETY — Audit Gap Closure (G-3 + G-4 + TD-1 from v1.0)

- [x] **SAFETY-01**: `sanitize_player_input` wired into **3 modals** (per Synthesizer refinement of Architecture finding — Brief said 2): `CharacterReviewModal`, `CharacterEntryModal`, `OptionalFieldsModal`. `WeaponSelectModal` scope **dropped**: its regex-restricted weapon-name field is already tight enough that sanitization is redundant defense-in-depth. Each modal submission writes a `sanitizer_audit` row when stripping occurs. Closes SAN-01.
- [x] **SAFETY-02**: `MCPCircuitOpen` caught at cog layer (via `@catch_circuit_open` decorator OR explicit `try/except` in each MCP-touching callback). Ephemeral `WarningKind.DM_OFFLINE` dispatched to user with rate-limit debouncing (1 warning per channel per 30s). Closes OPS-02.
- [x] **SAFETY-03**: `python -m eldritch_dm.bot` validates `DISCORD_TOKEN` first; emits friendly structured-log + stderr error (exit `EXIT_MISSING_TOKEN=4`) on missing token instead of opaque `discord.errors.LoginFailure`. Shared helper extracted with `run.py` (no copy-paste). Closes TD-1.

### HOMEBREW — Extensibility (Riposte Subclass Configuration)

- [x] **HOMEBREW-01**: YAML Riposte eligibility loader at `src/eldritch_dm/gameplay/eligibility_loader.py` with **3-tier precedence**: env override (`ELDRITCH_ELIGIBILITY_YAML`) > per-install (`~/.eldritch/eligibility.yaml`) > in-repo default (`database/eligibility.yaml`). `safe_load` only (CI grep gate against `yaml.load`). Pydantic schema with `extra='forbid'`. Fail-soft to v1.0 hardcoded defaults (Battle Master Fighter only) on bad YAML — emit structured-log warning, don't crash bot.
- [x] **HOMEBREW-02**: **Extend-not-override** semantics by default — user YAML adds subclasses to the RAW defaults. Explicit `mode: replace` opt-in for full override. Casing normalized via reused `_normalize` helper extracted to `gameplay/normalize.py`. Restart-to-apply (no hot-reload in v1.1).

### UPGRADE — Migration Tooling (TD-3 from v1.0)

- [x] **UPGRADE-01**: Console script `eldritch-dm-backfill-pc-classes` (registered in `pyproject.toml [project.scripts]`) populates the `pc_classes` table from existing dm20 characters. Reuses `MCPClient` + circuit breaker (don't roll new HTTP). Idempotent re-run via CLI-level `repo.get()` pre-check + skip (repo SQL is `DO UPDATE`; gate sits at the CLI per Phase 9 C-3). `--dry-run` opens SQLite read-only (`mode=ro` URI; driver-level write prohibition). `--force` reprocesses already-populated rows. DB-lock detection returns `EXIT_FATAL`=3 with operator hint (PID-file deferred to v1.2 per Phase 9 C-2). Progress reported via plain stdout summary table + structlog console renderer (`rich` not required for v1.1). Closes TD-3. **Implemented Phase 9 Plan 01** — see `09-01-SUMMARY.md`. Caveat: subclass left empty because dm20 schema omits subclass; operators hand-edit `pc_classes` for Battle Master Riposte until v1.2 ships a richer ingest path.

### COMBAT — Smart MonsterDriver (replaces v1.0 random targeting per D-B)

- [x] **COMBAT-13**: Smart `MonsterDriver` replaces v1.0 random target selection with **Claudmaster-routed** targeting. Implementation per research convergence:
  - **INT-gating**: Monsters with `INT <= 4` (ogres, zombies, beasts) bypass the LLM and fall back to v1.0 random — keeps low-INT monsters in character + saves tokens.
  - **Constrained candidate set**: LLM prompt receives the live PC list with IDs; output validated against pydantic `MonsterTacticChoice` model; any deviation (hallucinated ID, malformed JSON) triggers fallback to random.
  - **Hard 1500ms deadline** per decision via `asyncio.wait_for`; on timeout, fall back to random + structured-log warning. Player never sees an embed stalled for >2s.
  - **Per-round cache** keyed on `(channel_id, round_n, monster_id)` so re-asking the same question in the same round returns cached choice (combats with re-engagement won't blow up token costs).
  - **Fairness signal**: prompt includes "PCs hit recently" so LLM is biased away from focus-fire-to-TPK without hard-coding a rule.
  - **`MONSTER_DRIVER` env var**: `smart` (default), `random` (v1.0 behavior, escape hatch), `mixed` (smart for INT≥8, random for INT<8).
- [x] **COMBAT-14**: Smart `MonsterDriver` adversarial test corpus at `tests/gameplay/test_monster_driver_corpus.py` with **15+ scenarios** modeled on the v1.0 sanitizer corpus pattern. Cases: malformed LLM JSON, hallucinated PC ID, empty candidate set, timeout, sub-INT bypass, focus-fire detection over multiple rounds, recursive-decision attempt, etc. Required: every scenario falls back gracefully — no exception leaks to the orchestrator.

---

## Out of Scope (v1.1)

Explicitly NOT shipping in v1.1 to keep the milestone narrow:

- **YAML hot-reload** for eligibility — restart-to-apply is fine for v1.1. SIGHUP/file-watcher → v1.2 if requested.
- **Smart MonsterDriver via dedicated dm20 tool** — v1.1 uses LLM-as-oracle via existing `AsyncOpenAI` (Stack research said no new MCP deps). If dm20 ships `dm20__smart_target` in 2026-Q3+, switch in v1.2.
- **New SQLite tables** — schema is locked at v1.0's 6 tables.
- **Per-PC eligibility overrides** — YAML is per-server only (matches dm20's campaign-scoped model).
- **Voice/TTS narration**, **image generation**, **hosted SaaS variant** — all v2 territory per PROJECT.md.
- **Sanitizer retention/expiry policy** — `sanitizer_audit` table grows unbounded for v1.1; cleanup tool deferred until size becomes an actual issue.
- **`SIM`/`PERF` ruff rules** — keep existing ruleset; don't conflate debt cleanup with raising the bar.

---

## Future Requirements (v1.2+ candidates)

- YAML hot-reload via SIGHUP or file-watcher
- Smart MonsterDriver tuning UI (Discord admin command to set INT threshold per server)
- `sanitizer_audit` retention policy + cleanup tool
- `pc_classes` backfill scheduled task (autoamtic on bot startup detecting drift)
- New ruff rules (`SIM`, `PERF`) after v1.1 debt is paid
- v1.1 release notes file (`CHANGELOG.md`)
- Webhook for v1.x release announcements

---

## Traceability

Mapping every v1.1 requirement to its phase. Populated by gsd-roadmapper or hand-verified.

| REQ-ID | Phase | Source Plan |
|---|---|---|
| DEBT-01 | Phase 6 | 06-01-PLAN-ruff-cleanup |
| DEBT-02 | Phase 6 | 06-02-PLAN-cold-start-e2e |
| SAFETY-01 | Phase 7 | 07-01-PLAN-safety-bundle |
| SAFETY-02 | Phase 7 | 07-01-PLAN-safety-bundle |
| SAFETY-03 | Phase 7 | 07-01-PLAN-safety-bundle |
| HOMEBREW-01 | Phase 8 | 8-01-PLAN-yaml-eligibility |
| HOMEBREW-02 | Phase 8 | 8-01-PLAN-yaml-eligibility |
| UPGRADE-01 | Phase 9 | 09-01-PLAN-pc-classes-backfill |
| COMBAT-13 | Phase 10 | 10-01 |
| COMBAT-14 | Phase 10 | 10-02 |

---
*Created: 2026-05-24 from v1.1 Polish research synthesis (STACK / FEATURES / ARCHITECTURE / PITFALLS)*
