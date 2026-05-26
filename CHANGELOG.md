# Changelog

All notable changes to **EldritchDM** are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Each entry below condenses the headline accomplishments from a shipped milestone. For full per-phase detail (success criteria, deferred items, key decisions) follow the archive link at the foot of each entry.

---

## [v1.11] - 2026-05-26

### Added
- 8-surface cross-cutting security audit (`SECURITY-AUDIT-v1.11.md`, 289 lines with grep evidence per surface) — read-only investigation covering 11 milestones of accumulated surface, **0 findings across CRITICAL/HIGH/MEDIUM/LOW**.
- New `.planning/SECURITY-BACKLOG.md` future-tracking surface with filing template and guidelines.

### Changed
- Methodology-disclosure documentation substitutes for findings list per the honesty clause — operators can audit the audit.
- Branch B remediation (SECFIX-01/02/03) closes as no-op because nothing was found to fix; mirrors the Phase 25 CONC-03 / Phase 28 TUNE-01 honest-closure pattern.

> 📜 Full archive: [v1.11-ROADMAP.md][v1.11] · audit: [v1.11-MILESTONE-AUDIT.md](.planning/v1.11-MILESTONE-AUDIT.md)

---

## [v1.10] - 2026-05-26

### Added
- `docker-compose.yml` + multi-stage `Dockerfile` (python:3.11-slim + uv + non-root user) — `docker compose up -d` brings up the whole stack.
- `scripts/ops/test_docker_smoke.sh` — operator-opt-in smoke test (NOT default CI) with exit-code discrimination (2=no Docker, 1=smoke fail, 0=ok).
- `docs/TROUBLESHOOTING.md` — 14 FAQ entries grounded in real v1.0-v1.9 SUMMARY surface.
- `docs/UPGRADE.md` — 11 version transitions (v1.0 → v1.10) with concrete operator actions per transition.

### Changed
- `INSTALL.md` refresh — Docker quickstart + 12 env vars + 7 CLIs + 4 optional dep groups; every claim cross-referenced to a phase/SUMMARY.
- Bidirectional cross-links established between `INSTALL.md` ↔ `docs/TROUBLESHOOTING.md` ↔ `docs/UPGRADE.md`.

> 📜 Full archive: [v1.10-ROADMAP.md][v1.10] · audit: [v1.10-MILESTONE-AUDIT.md](.planning/v1.10-MILESTONE-AUDIT.md)

---

## [v1.9] - 2026-05-26

### Added
- v1.9.0 performance baseline (`perf-baseline-v1.9.0.json`) — 6 hot paths × ~10 sub-paths profiled; every operation p99 ≥45× under its budget.
- `docs/PERFORMANCE.md` — per-operation budget table with WARN (110%) / FAIL (125%) thresholds.
- `eldritch-dm-perf-baseline` CLI with `--baseline` diff mode (3-tier exit codes: 0=±10%, 1=>10%, 2=>25%) — mirrors the Phase 12 eval-baseline pattern.
- `.github/workflows/perf.yml` — weekly Sun 02:00 UTC + `[perf]`-tagged-push regression detection, `continue-on-error` (non-blocking).

### Changed
- TUNE-01 closure (Branch B): profile-driven analysis surfaced no real optimization targets — honest no-op closure rather than manufactured work.

> 📜 Full archive: [v1.9-ROADMAP.md][v1.9] · audit: [v1.9-MILESTONE-AUDIT.md](.planning/v1.9-MILESTONE-AUDIT.md)

---

## [v1.8] - 2026-05-25

### Added
- 4-channel concurrent-session stress test (~0.27s wall clock) — closes v1.0's oldest open Blockers/Concerns item ("Verify dm20 supports concurrent multi-campaign sessions in one process"). All 5 D-195 assertions pass; no architectural bugs surfaced.
- 3 new operational dashboards (`degraded_mode`, `budget`, `eval`) — total now 9 bundled Phoenix dashboards.
- 2 new entries in `UPSTREAM-ISSUES.md` (backfill auto-discovery resolved; dm20 damage-event surface remains open).

### Changed
- `backfill_summary_frontmatter.py` rewritten with `rglob` + sibling-PLAN frontmatter inference — the hardcoded-paths debt class is now architecturally impossible.

> 📜 Full archive: [v1.8-ROADMAP.md][v1.8] · audit: [v1.8-MILESTONE-AUDIT.md](.planning/v1.8-MILESTONE-AUDIT.md)

---

## [v1.7] - 2026-05-25

### Added
- `/end_game` slash command (WIRE-02) — calls `MonsterMemoryRegistry.purge_session` on success; ephemeral confirmation embed.
- AOE addendum live integration (WIRE-03) — SmartMonsterDriver conditionally injects the Phase 20 versioned addendum when `available_actions` contains ≥2 AOE-kind entries; `eldritch.aoe.addendum_version` OTel attribute on outer decision span.
- Cross-platform CI matrix (`.github/workflows/ci.yml`) — macos-latest + ubuntu-latest × Python 3.11; Linux runner verifies the Phase 14 skip-gates work cleanly.
- 3 bundled Phoenix dashboards for v1.5 caches (`mcp_cache.json`, `character_cache.json`, `narrcache.json`).

### Changed
- Mid-execution discovery: 14 SUMMARYs (Phases 16-22) missing `requirements_completed:` frontmatter — backfilled inline; CI gate now reports `OK: 35 SUMMARY files`.
- Full test suite reaches 1644 passed / 17 skipped / 0 failed.

### Deferred
- WIRE-01 (MonsterMemory cog-side observe_hit wiring) — honest deferral, blocked on dm20 structured damage-event surface (tracked in `UPSTREAM-ISSUES.md` as ISSUE-3).

> 📜 Full archive: [v1.7-ROADMAP.md][v1.7] · audit: [v1.7-MILESTONE-AUDIT.md](.planning/v1.7-MILESTONE-AUDIT.md)

---

## [v1.6] - 2026-05-25

### Added
- Streaming "monster is thinking" embed — SmartMonsterDriver oracle calls now surface in the combat embed via Phase 2's coalescer; `STREAM_ENABLED` env opt-out; cancellation-safe double-wrap.
- AOE / multi-target tactic selection — `MonsterTacticChoice` extended with `target_pc_ids` + `tactic_kind` Literal; backwards-compatible `target_pc_id` @property preserves existing call sites; 26-scenario corpus (10 new AOE-specific).
- Cross-round monster memory — `MonsterMemory` bounded LRU (200/session) tracks damage_dealt_by / concentrating_on / marked_dangerous; INT-gated marking; LLM sees CATEGORIZED damage only (never raw HP).
- Operator quality-of-life bundle — hot-reload `eligibility.yaml` (60s mtime poll), Discord DM-to-owner on budget breach (1 DM/event-type/hour), Phase 16 schema-poller fires Phase 17 character_cache invalidation.

### Changed
- 122 new tests across v1.6 (9 + 36 + 54 + 23); 8/8 import-linter contracts kept; ruff clean throughout.

> 📜 Full archive: [v1.6-ROADMAP.md][v1.6] · audit: [v1.6-MILESTONE-AUDIT.md](.planning/v1.6-MILESTONE-AUDIT.md)

---

## [v1.5] - 2026-05-25

### Added
- dm20 MCP query cache — L1 in-process LRU + L2 aiosqlite WAL (opt-in); PYTHONHASHSEED-stable SHA-256 args_hash; **fail-CLOSED allow-list of 6 truly-static reference tools** (advisor-corrected); auto-invalidation on dm20 schema-version change via 60s background poller.
- Persistent character cache — `CharacterCacheRepo` with 14-field static-only allow-list; synthetic SHA-256 ETag with TTL short-circuit; `eldritch-dm-cache-clear --characters` CLI.
- Opt-in narration response cache (`NARRCACHE_ENABLED=false` default) — `NarrCacheGate` with 8 regex patterns; 50-scenario Apache-2.0 corpus verifies **0% false-negative + 0% false-positive** classification; `eldritch-dm-cache-disable` + `eldritch-dm-cache-stats` CLIs.

### Changed
- Phase 13 cost-calculator tie-in: narration-cache `savings_usd` KPI confirms cache pays for itself.
- 276 new tests across v1.5 (40 + 61 + 175); 8/8 import-linter contracts kept; mechanical-honesty contract propagates cleanly because every cache layer has an explicit fail-CLOSED allow-list.

> 📜 Full archive: [v1.5-ROADMAP.md][v1.5] · audit: [v1.5-MILESTONE-AUDIT.md](.planning/v1.5-MILESTONE-AUDIT.md)

---

## [v1.4] - 2026-05-25

### Fixed
- FLAKE-02 closure via `tests/conftest.py` autouse fixture (snapshot+restore of `sys.modules[cog]` around every test) + `tests/bot/conftest.py` extension-unload teardown — first full-suite GREEN since v1.1 (1244 passed / 17 skipped / 0 failed, two consecutive runs).
- HANG-01 + HANG-02 verified not reproducible at HEAD — v1.3's writer-queue-hang diagnosis was an artifact; resolved upstream by v1.3 Phase 14's logging-polluter fix.

### Changed
- v1.3 carry-forward partial closed: `v1.3-REQUIREMENTS.md` FLAKE-02 ticked `[x]` with v1.4 cross-reference.
- 169-line `15-HALT-REPORT.md` preserved as artifact — canonical example of the autonomous-mode honest-report contract working under stress.

> 📜 Full archive: [v1.4-ROADMAP.md][v1.4] · audit: [v1.4-MILESTONE-AUDIT.md](.planning/v1.4-MILESTONE-AUDIT.md)

---

## [v1.3] - 2026-05-25

### Fixed
- OCR + `prometheus_client` skip-gates (FLAKE-01) — `pip install -e ".[dev]"` no longer needs the `[mac-ocr]` extras for a clean suite run.
- SUMMARY.md frontmatter backfilled (FLAKE-03) — all 14 v1.1+v1.2 SUMMARYs now carry `requirements_completed:` YAML; CI gate (`scripts/ci/check_summary_frontmatter.sh`) added.

### Changed
- 75% reduction in targeted-suite test failures (8 failed → 2 failed); the 2 remaining failures are newly-surfaced pre-existing pytest hangs, properly scoped to v1.4.
- Honest-report contract honored: executor halted-and-reported on FLAKE-02 rather than silently marking complete (accepted-partial disposition documented in audit).

> 📜 Full archive: [v1.3-ROADMAP.md][v1.3] · audit: [v1.3-MILESTONE-AUDIT.md](.planning/v1.3-MILESTONE-AUDIT.md)

---

## [v1.2.1] - 2026-05-24

### Fixed
- `database/pricing.yaml` — dropped the PLACEHOLDER warning and verified pricing values against multiple live 2026 vendor sources, calibrating the cost-guard alerts shipped in v1.2 Phase 13.

### Changed
- Closes the v1.2 audit's `pricing.yaml` deviation row (originally recommended "Schedule a v1.2.1 patch within 2 weeks of v1.2 GA").

> 📜 Hotfix tag: `git show v1.2.1`. Sourced from [v1.2-MILESTONE-AUDIT.md](.planning/v1.2-MILESTONE-AUDIT.md) ("Pricing table refresh (v1.2.1)" deviation row + closing Recommendation).

---

## [v1.2] - 2026-05-24

### Added
- OpenTelemetry instrumentation for every `AsyncOpenAI` call from `SmartMonsterDriver` + the bot's narration path — D-65 8-attribute span schema (`monster.id`, `channel.id`, `combat.round`, `driver.path`, `latency_ms`, `tokens.input`, `tokens.output`, `fallback.reason`); lazy-import gated by `OBSERVABILITY_ENABLED` (off by default — zero cold-start cost when disabled).
- Self-hostable Arize Phoenix stack via `docker-compose.observability.yml` (Phoenix on `:6006`) — 3 default dashboards seeded (latency P50/P95/P99, fallback rate by reason, cache hit rate).
- `TacticalJudge` LLM-as-judge oracle + 50-scenario Apache-2.0 corpus (10×5 across archetypes) — scores SmartMonsterDriver decisions on AI-SPEC §1b dimensions; judge prompt carries a SemVer header for reproducibility.
- `eldritch-dm-eval` CLI — runs corpus → judge → aggregator → JSON+Markdown report; `--baseline` flag enables regression detection via 3-tier exit codes.
- 5 KPI live monitors + opt-in Prometheus `/metrics` endpoint + `database/alerts.yaml` 3-tier loader + degraded-mode auto-trip with hysteresis + `eldritch-dm-cost-report` CLI with `ELDRITCH_DAILY_LLM_BUDGET_USD` enforcement.

### Changed
- Mechanical-honesty contract preserved through observability/monitoring layers — degraded mode swaps the SmartMonsterDriver for the v1.0 random driver but never touches HP/AC math.

### Known Issues
- `pricing.yaml` ships PLACEHOLDER values — refresh recommended within 2 weeks of v1.2 GA. Closed by v1.2.1.

> 📜 Full archive: [v1.2-ROADMAP.md][v1.2] · audit: [v1.2-MILESTONE-AUDIT.md](.planning/v1.2-MILESTONE-AUDIT.md)

---

## [v1.1] - 2026-05-24

### Added
- YAML-configurable Riposte eligibility — 3-tier loader (`$ELDRITCH_ELIGIBILITY_YAML` > `~/.eldritch/eligibility.yaml` > `database/eligibility.yaml`); fail-soft to v1.0 defaults; CI `safe_load`-only gate. Homebrew DMs can now add Riposte-eligible subclasses without code edits.
- `eldritch-dm-backfill-pc-classes` CLI with `--dry-run` (SQLite `mode=ro`) + `--force` + idempotent default — closes the v1.0 → v1.1 upgrade gap (TD-3).
- Smart MonsterDriver — LLM-routed targeting via the existing `AsyncOpenAI` client (no new MCP deps); INT-gated (≤4 random, ≥8 LLM, 5-7 mixed with deterministic seed); 1500ms hard timeout with structured-log fallback; pydantic post-parse validation rejects hallucinated target_pc_ids; per-round FIFO cache; 16-scenario adversarial corpus.

### Fixed
- Ruff debt zeroed (Phase 6) — 79 errors → 0 across 23 files; ruff floor bumped to `>=0.15,<1.0`.
- All v1.0 audit deferrals closed (Phase 7): SAN-01 modal sanitization wired into 3 modals; OPS-02 `DM_OFFLINE` warning with 30s-per-channel debouncer + `@catch_circuit_open` decorator; TD-1 shared `config.token_guard` helper makes `run.py` and `python -m eldritch_dm.bot` parity-identical on missing-token error handling.

### Changed
- Cold-start E2E regression guard added — fails at v1.0 commit `7d307a1` (proving it would have caught the G-1 bug class) and passes on current main.

> 📜 Full archive: [v1.1-ROADMAP.md][v1.1] · audit: [v1.1-MILESTONE-AUDIT.md](.planning/v1.1-MILESTONE-AUDIT.md)

---

## [v1.0] - 2026-05-23

### Added — initial release
- **Three-brain architecture (Phase 1):** async `MCPClient` to dm20 at oMLX `:8765/v1/mcp/execute` with httpx + tenacity retry + 3-strike circuit breaker; WAL SQLite with single-writer async queue + `BEGIN IMMEDIATE`; player-input sanitizer with 35-scenario adversarial corpus (control-token strip + sentinel wrap + 500-char cap + audit trail).
- **Discord scaffold + persistent views (Phase 2):** `discord.py 2.7.1` bot with `DynamicItem` regex `custom_id`s for every persistent button; `EmbedCoalescer` (≤1 edit/sec/message); custom `EDM001` AST lint rule enforcing `await interaction.response.defer(thinking=True)` as the first line of every callback.
- **Lobby + character ingest (Phase 3):** `/start_game` provisions dm20 campaign + Claudmaster + Party Mode; `/load_adventure` for prebuilt campaigns; character ingest via D&D Beyond URL OR photo/PDF (ocrmac on macOS, easyocr fallback) routed through confidence-gated `CharacterReviewModal` / `CharacterEntryModal`.
- **Gameplay — exploration + combat (Phase 4):** `PartyModeOrchestrator`; action batching (30s window); `CombatCog` with four turn-gated action buttons (Attack/Dodge/Cast/EndTurn) + `WeaponSelectModal`; `MonsterTurnDriver`; 8-actor virtual-clock load test proves the coalescer + rate-limiter + edit-budget triad stays under Discord's 5/5s channel ceiling.
- **Riposte + self-host polish (Phase 5):** timed Riposte UI on the corrected RAW trigger path; public-message persistent-View button with permission gating; `RiposteSweeper` background task; restart-survival drill proves button survives bot restart until `deadline_ts`; top-level `bootstrap.py` 3-stage preflight; `run.py` entrypoint; launchd plist + systemd unit + install/uninstall scripts; full README + 6 canonical docs.

### Notes
- 5 phases · 16 plans · 873 tests (864 passing, 9 skipped) · 7/7 import-linter contracts kept · 71/73 requirements satisfied (97%) · 110 commits over 2 days.
- **Integrity contract:** ShoeGPT narrates; deterministic Python computes. The LLM never touches HP/AC math.

> 📜 Full archive: [v1.0-ROADMAP.md][v1.0] · audit: [v1.0-MILESTONE-AUDIT.md](.planning/milestones/v1.0-MILESTONE-AUDIT.md) · milestone notes: [MILESTONES.md](.planning/MILESTONES.md)

---

[v1.11]: .planning/milestones/v1.11-ROADMAP.md
[v1.10]: .planning/milestones/v1.10-ROADMAP.md
[v1.9]: .planning/milestones/v1.9-ROADMAP.md
[v1.8]: .planning/milestones/v1.8-ROADMAP.md
[v1.7]: .planning/milestones/v1.7-ROADMAP.md
[v1.6]: .planning/milestones/v1.6-ROADMAP.md
[v1.5]: .planning/milestones/v1.5-ROADMAP.md
[v1.4]: .planning/milestones/v1.4-ROADMAP.md
[v1.3]: .planning/milestones/v1.3-ROADMAP.md
[v1.2]: .planning/milestones/v1.2-ROADMAP.md
[v1.1]: .planning/milestones/v1.1-ROADMAP.md
[v1.0]: .planning/milestones/v1.0-ROADMAP.md
