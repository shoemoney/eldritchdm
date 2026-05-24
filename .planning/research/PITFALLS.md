# Domain Pitfalls — EldritchDM v1.1 Polish

**Domain:** Discord bot + MCP orchestrator + local-LLM AI DM, layered on a shipped v1.0
**Researched:** 2026-05-23
**Confidence:** HIGH where lessons trace to v1.0 retrospective/audit; MEDIUM for forward-looking Smart Driver patterns (no v1.0 precedent in this repo)
**Source-of-truth lessons:** `.planning/RETROSPECTIVE.md` (cold-start E2E gap), `.planning/milestones/v1.0-MILESTONE-AUDIT.md` (G-1/G-2/TD-1/TD-3), `.planning/debug/resolved/preflight-requires-token.md` (D-26 — "test the user's actual path, not just the layer")

---

## Meta-Pitfall (highest priority, derived from v1.0 audit)

### THE COLD-START E2E GAP — this caused G-1, this caused D-26, this will cause v1.1 regressions
**What goes wrong:** A change wires up correctly at the unit layer, passes 870 tests, and is broken from the perspective of a self-hoster running the documented quickstart. v1.0 shipped with `ReadyButton.callback` never starting the orchestrator (G-1); 870 tests passed because every gameplay test constructed the orchestrator directly or used the RESUME path. Same root cause as D-26: bootstrap raised a pydantic traceback on missing token because nobody ever ran the README's documented `python -m eldritch_dm.bootstrap` without a token set.
**Why it happens:** Tests are written from the developer's mental model of the code, not from a fresh-clone user's actual flow. Mocks, fixtures, and shared `conftest.py` setup hide the wire-up gap.
**Consequences:** Two BLOCKER gaps in v1.0 that should never have reached audit time. Each v1.1 feature introduces a new opportunity for the same class of bug: Smart MonsterDriver wires to Claudmaster, YAML eligibility wires to the riposte path, backfill wires to dm20 + the DB — every wire is a place this can recur.
**Prevention:**
- **First phase of v1.1 must add a "fresh-install smoke" pytest target** that exercises the exact path the README documents: bootstrap (no token) → bootstrap (token) → bot start → `/start_game` → ready → first narrative → first attack → first riposte → bot restart → state resumed. One pytest, no mocks beyond oMLX/dm20 doubles. Runs in CI gate.
- **Every new v1.1 feature plan ships with one "fresh user does X" integration test** in addition to unit tests. Acceptance criterion: the test does not import `conftest` fixtures that pre-create state the user wouldn't have.
- **Run `/gsd:verify-phase` per phase** (procedural gap P-4 from v1.0 audit). Audit-as-verification worked once; institutionalizing it is the v1.1 hygiene fix.
**Detection:** If a v1.1 phase ships without an integration test whose name matches `test_*_cold_start_*` or `test_*_fresh_install_*`, the phase has the v1.0 gap pattern.
**Phase assignment:** **Phase 1 of v1.1, before any feature code.** This is non-negotiable; it is the lesson the retrospective explicitly flagged as `NEEDS IMPROVEMENT v1.1`.

---

## Smart MonsterDriver Pitfalls

### MD-1 (CRITICAL): LLM tactical drift — INT 4 ogre playing chess
**What goes wrong:** Claudmaster returns "optimal" target selection regardless of monster intelligence. A goblin (INT 8) flanks the wizard; an ogre (INT 4) does the same; a zombie (INT 1) does the same. Players lose the tactical-stupidity dimension that makes low-INT monsters fun to fight.
**Why it happens:** LLMs default to "play well." Without explicit INT-conditioning, the prompt produces uniformly optimal play.
**Consequences:** Encounters feel homogeneous and harder than CR suggests; the DM persona collapses to "tactical advisor."
**Prevention:**
- **Three prompt templates keyed by INT band:** `INT ≤ 4` (instinct: nearest target, last thing that hit me, random if equidistant), `INT 5–9` (basic tactics: focus weakest visible, but no metagaming), `INT ≥ 10` (full Claudmaster tactical reasoning, with subclass-aware spell sequencing).
- **Temperature scaling:** 0.9 for INT ≤ 4 (chaotic), 0.6 for mid, 0.3 for INT ≥ 10 (deliberate).
- **Forbid the LLM from seeing PC HP for INT ≤ 4** monsters — they can only see "alive/bloodied/down" presence, not numbers. Removes the "always pick lowest HP" attractor.
**Detection:** Add a `tests/integration/test_monster_int_bands.py` with a fixed seed that asserts an INT 4 ogre, given (wounded wizard, full-HP barbarian), does NOT always pick wizard. Statistical test over 20 runs, χ² against uniform-over-adjacent.
**Phase assignment:** Smart MonsterDriver plan, before merge.

### MD-2 (CRITICAL): Token-cost / latency spiral — 240 LLM calls per combat
**What goes wrong:** 8 monsters × 5 rounds × 6 players = ~240 monster turns. Each turn = one Claudmaster call. At 90 tok/s on the M3 Ultra that's ~3s per call wall-clock = ~12 minutes of LLM time per combat, on top of player turns.
**Why it happens:** Naively, every monster decision is its own request.
**Consequences:** Combat that took 8 minutes in v1.0 (random targeting) takes 20+ minutes in v1.1; embed coalescer rate budget (1/sec/msg, 5/5s/channel) is fine, but the orchestrator falls behind, players see stalled "thinking…" embeds.
**Prevention:**
- **Cache per-monster-per-round decisions when round state is unchanged.** Key: `(monster_id, round_no, set(alive_pc_ids), set(bloodied_pc_ids))`. A second ogre with identical perception this round reuses the first's target rationale.
- **Batch-prompt for grouped-INT monsters:** "There are 4 goblins. Each picks a target from {alive PCs}. Return JSON list of 4 targets." One call, 4 decisions.
- **Hard wall-clock budget per monster turn: 1500ms.** Beyond that, fall back to v1.0 random selector (still mechanically correct).
- **Prefetch next monster's decision while current monster's attack resolves.** Roll resolution is dm20-side and parallelizable with the next prompt.
**Detection:** Add a perf gate: combat fixture with 8 monsters × 4 PCs × 3 rounds must complete in ≤ 60s in CI on the dev box (allow longer in CI runner if needed but log the regression).
**Phase assignment:** Smart MonsterDriver plan; the cache + batch are core, not optimization-later.

### MD-3 (CRITICAL): Timeout cascade — player stares at stalled embed
**What goes wrong:** Claudmaster slow → monster turn slow → orchestrator backs up → embed coalescer queues 10s of "Goblin is thinking…" updates → Discord interaction 3-second-ack budget consumed elsewhere → "This interaction failed."
**Why it happens:** No deadline contract between bot ↔ Claudmaster. The MCP client has a circuit breaker but no per-call SLO.
**Consequences:** Same UX failure as MD-2 but triggered by one slow call instead of cumulative. Players think the bot crashed.
**Prevention:**
- **Hard deadline: 1500ms per `smart_target` MCP call.** `asyncio.wait_for`. On timeout, fall back to random selector, log a structured `monster_decision_fallback` event, increment a counter.
- **Show "decisive" embed update at the deadline regardless of LLM state** — never let the embed sit on "thinking" past 2s.
- **Counter alerts:** if `monster_decision_fallback` rate > 10% in a session, surface a `WarningKind.DM_DEGRADED` ephemeral (related to OPS-02 work — reuse the same plumbing).
**Detection:** Integration test with a `slow_claudmaster` fixture (`asyncio.sleep(5)` in the MCP double) — assert combat still completes and produces random-selector traces.
**Phase assignment:** Smart MonsterDriver plan; the timeout is the contract, not a polish item.

### MD-4 (HIGH): Targeting bias / TPK risk — LLM focus-fires
**What goes wrong:** Even with INT bands, mid-INT monsters all converge on "lowest-HP PC" because that's the locally-rational answer. 4 hobgoblins all attack the wizard → wizard down round 1 → cascade.
**Why it happens:** Each monster decides independently with the same observable state.
**Consequences:** Encounters feel grief-y, not tactical. Players resent the AI specifically (different from resenting bad rolls).
**Prevention:**
- **Pass "who has been targeted this round" into the prompt** as a fairness signal. INT ≥ 8 monsters get instruction: "tactical monsters know overkill is wasted damage; consider unfocused targets."
- **Aggro/threat signal:** track which PC dealt damage to this monster last round; bias toward retaliation, which is both fun and lore-correct for INT ≥ 5.
- **Coalition cap:** no more than `ceil(monsters / 2)` may target the same PC in one round, enforced by the driver post-LLM (deterministic Python override, mechanically honest per the project rule).
**Detection:** Add a TPK-stress test: 4 hobgoblins vs 4-PC party, 10 simulated rounds, assert no single PC takes > 50% of total monster attacks.
**Phase assignment:** Smart MonsterDriver plan.

### MD-5 (HIGH): Recursive / multi-step prompts cause stall loops
**What goes wrong:** "Monster casts haste on itself, then attacks" — Smart Driver tries to plan both, prompts ask "what's the best spell to cast first?", LLM returns a plan that requires another prompt to refine, etc.
**Why it happens:** Tempting to model a monster's full turn as one optimization problem.
**Consequences:** Latency explosion; MD-3 timeout triggers; player gets random fallback even on simple turns.
**Prevention:**
- **Atomic per-action decision.** The driver asks Claudmaster for ONE next action at a time: "pick target for next attack" OR "pick spell to cast." Never both in one prompt.
- **Action sequence is dm20-owned, not driver-owned.** dm20's combat tool already knows monster action economy (action + bonus + reaction); the driver fills in target/spell-choice slots, doesn't orchestrate the action graph.
**Detection:** Lint rule (informal): grep for any `await mcp.smart_target` inside a loop body in `monster_driver.py` — should be one call per `monster_take_turn` invocation.
**Phase assignment:** Smart MonsterDriver plan, architectural decision up-front.

### MD-6 (HIGH): Claudmaster returns garbage — malformed JSON, empty, hallucinated IDs
**What goes wrong:** LLM returns `{"target": "the wizard"}` instead of `{"target": "pc_07"}`. Or returns `{"target": "pc_99"}` which doesn't exist. Or returns empty string. Or returns valid JSON wrapped in markdown code fences.
**Why it happens:** Local quantized LLMs are less reliable than frontier models even when tool-calling works; PROJECT.md notes tool calls are reliable but reliability ≠ correctness.
**Consequences:** Driver crash → unhandled exception in orchestrator → combat stalls.
**Prevention:**
- **Pydantic validation of every Claudmaster response.** `class TargetDecision(BaseModel): target_id: str; rationale: str` with a custom validator that `target_id in alive_combatant_ids`.
- **One retry with stricter prompt** ("Return ONLY a JSON object with key 'target_id' equal to one of: pc_01, pc_03, pc_07. No other text.") on validation failure.
- **After retry: random fallback + structured `monster_decision_validation_failure` log.** Counter feeds OPS-02 degraded warning.
- **NEVER raise from the driver.** It is on the hot path; failures must degrade not crash. Mirror the OPS-01 circuit-breaker philosophy.
**Detection:** Adversarial test corpus (echo of v1.0 sanitizer corpus pattern): fixture file `tests/fixtures/claudmaster_bad_responses.yaml` with ≥ 15 cases (empty, markdown-wrapped, wrong key, nonexistent ID, type confusion, prompt-injection-attempt). Each must produce a valid fallback, not an exception.
**Phase assignment:** Smart MonsterDriver plan. This is the same shape as Phase 1's sanitizer adversarial corpus — proven pattern, reuse it.

---

## YAML Riposte Eligibility Pitfalls

### YAML-1 (CRITICAL): `yaml.load` allows arbitrary code execution
**What goes wrong:** Using `yaml.load()` instead of `yaml.safe_load()` lets a malicious YAML file execute arbitrary Python (`!!python/object/apply:os.system ['rm -rf ~']`).
**Why it happens:** Default PyYAML API. Easy to forget.
**Consequences:** Self-hoster pastes a "homebrew pack" from a forum → RCE on their box.
**Prevention:**
- **`yaml.safe_load` is the only permitted API.** Add a custom ruff/grep CI check: `git grep -nE 'yaml\.load\(' src/` must return zero hits except in `yaml.safe_load`.
- **Pydantic model on top of `safe_load`:** `class RiposteEligibility(BaseModel): subclasses: dict[str, list[str]]` with `model_config = ConfigDict(extra='forbid')`.
**Detection:** A test that loads `tests/fixtures/malicious_riposte.yaml` containing `!!python/object/...` and asserts it raises before the pydantic layer.
**Phase assignment:** YAML eligibility plan. Day 1.

### YAML-2 (HIGH): Hot-reload race vs. live Riposte check
**What goes wrong:** A Riposte trigger fires (`monster misses PC`) and reads the eligibility frozenset at the same instant a file-watcher swaps in a reloaded set. Partial reads, or worse, eligibility flips during the 8s timer.
**Why it happens:** Mutable module-level state with naive reload.
**Consequences:** Inconsistent player experience; potential `AttributeError` mid-callback.
**Prevention:**
- **Atomic swap of an immutable `frozenset[tuple[str,str]]`.** Reload builds the new set fully, then a single attribute assignment swaps. Python attribute assignment on a module is atomic per CPython GIL.
- **Deadline-scoped read:** when the 8s Riposte timer is armed, snapshot the eligibility set into the timer task's local; do not re-read on click.
- **No live reload in v1.1.** Reload requires SIGHUP or `/admin reload-eligibility` command. File-watcher is post-v1.1.
**Detection:** Stress test that fires 100 rapid `is_riposte_eligible(...)` calls while a background task reassigns the module attribute; assert no exception and only old-set or new-set results (no torn read).
**Phase assignment:** YAML eligibility plan.

### YAML-3 (HIGH): Bad YAML at startup crashes the bot
**What goes wrong:** Self-hoster fat-fingers the YAML, bot won't start.
**Why it happens:** Strict parse + no fallback.
**Consequences:** First-run failure for a feature that's meant to be opt-in. Violates the v1.0 ethos that the README path always works.
**Prevention:**
- **Fail-soft with logged warning + default.** If `riposte_eligibility.yaml` is missing OR fails to parse OR fails pydantic validation: log `structlog.warning("riposte.eligibility.fallback", reason=...)`, use the v1.0 hard-coded default (Battle Master Fighter only).
- **`bootstrap.py` preflight check** (token-free, per D-26 pattern): if file present, parse-and-validate; warn but don't fail on errors.
- **Document the warning's exit-code-zero-ness** in README.
**Detection:** Integration test: bot starts with corrupt YAML; assert `bot.is_ready()` true and `bot.riposte_eligibility == DEFAULT_ELIGIBILITY`.
**Phase assignment:** YAML eligibility plan.

### YAML-4 (MEDIUM): Override-vs-extend confusion
**What goes wrong:** User writes `subclasses: {fighter: [echo knight]}` expecting Battle Master to remain eligible. The YAML *replaces* the fighter list, breaks v1.0 behavior, surfaces as "my Battle Master can't Riposte after I added a homebrew."
**Why it happens:** Dict-merge semantics aren't visible to non-coders.
**Consequences:** Support burden; users blame the bot.
**Prevention:**
- **Be explicit in the schema:** top-level `mode: extend | replace` (default `extend`). `extend` deep-merges; `replace` swaps wholesale.
- **Log the resolved set on load** at INFO level: `riposte.eligibility.resolved fighter=[battle_master, echo_knight]`. Self-hoster can grep their logs.
- **README example must show the extend pattern first**, with the replace pattern called out as advanced.
**Detection:** Test both modes; test that default mode preserves v1.0 defaults.
**Phase assignment:** YAML eligibility plan.

### YAML-5 (MEDIUM): Cross-pollination — Hunter rangers getting Riposte
**What goes wrong:** User adds `{ranger: [hunter]}` thinking it grants Riposte. RAW Hunter rangers don't have Riposte; it's a Battle Master maneuver. Bot now offers a non-RAW reaction; flips the "mechanically honest" property.
**Why it happens:** Users conflate "class can react" with "class has the Riposte maneuver."
**Consequences:** Erodes the core value proposition.
**Prevention:**
- **Document YAML as "extends what the bot OFFERS, not what 5e RAW grants."** Self-hoster's responsibility to confirm RAW alignment for homebrew.
- **Validate against dm20's known class/subclass list:** unknown `class:subclass` pairs logged as `riposte.eligibility.unknown_subclass` (warn, but allow — homebrew is the point).
- **Add a `homebrew: true` flag** that subclasses must set to suppress the warning, forcing the user to acknowledge they're going off-RAW.
**Detection:** Test that `{fighter: [made_up_subclass]}` without `homebrew: true` produces a warning log entry.
**Phase assignment:** YAML eligibility plan.

### YAML-6 (LOW): Casing / locale normalization
**What goes wrong:** `Battle Master` vs `battle master` vs `BATTLE MASTER` — frozenset misses depending on input source.
**Prevention:** Normalize on load: `key.casefold().strip().replace(" ", "_")` → canonical `battle_master`. Apply same normalization to the lookup side. One-line `_canonical()` helper, unit test on the boundary.
**Phase assignment:** YAML eligibility plan.

---

## Backfill Script Pitfalls (TD-3)

### BF-1 (CRITICAL): Bot is still running when backfill executes
**What goes wrong:** Script opens SQLite, but bot has the WAL writer open. Either backfill fails on `database is locked` or — worse — races a write and corrupts state.
**Why it happens:** Self-hosters don't know to stop the bot.
**Prevention:**
- **Fail-fast lockfile check.** If `~/.eldritchdm/bot.pid` exists AND points to a live PID, exit with friendly message: "Stop the bot first: `launchctl unload …` or kill PID 12345."
- **Bot writes the pidfile on startup, removes on clean shutdown.** Stale pidfile (PID not alive) → warn and continue.
- **Script-side: open SQLite with `timeout=2.0` and immediate-fail mode.** Don't wait forever on the lock.
**Detection:** Integration test that starts a fake "bot" process holding the DB, runs backfill, asserts exit code = 5 (`EXIT_BOT_RUNNING`) and a friendly stderr.
**Phase assignment:** Backfill plan.

### BF-2 (CRITICAL): Partial-completion poison state
**What goes wrong:** Backfill writes 30 of 100 PCs to `pc_classes`, crashes on PC 31 (dm20 timeout). Re-run: do those 30 get re-processed? Skipped? Double-written? Bot startup: some PCs eligible, some not.
**Prevention:**
- **One transaction per PC.** Each insert is atomic; on failure, that PC simply isn't in the table.
- **Idempotent re-run via `INSERT … ON CONFLICT(channel_id, pc_id) DO UPDATE SET …`.** Re-running the script is always safe.
- **Resume-friendly: list PCs to backfill, skip those already present** unless `--force` flag set.
- **Final report: `processed=N, skipped=M, failed=K, …PC IDs that failed listed for re-run`.** Operator can `--only=pc_03,pc_07` to retry.
**Detection:** Test that backfill, killed at PC 30 of 100 then re-run, ends with exactly 100 rows and no duplicates.
**Phase assignment:** Backfill plan.

### BF-3 (HIGH): dm20 unreachable during backfill
**What goes wrong:** Backfill reads character class data from dm20. If dm20 is down, every PC fails.
**Prevention:**
- **Preflight check first:** ping `dm20__tool_list` (same pattern as `bootstrap.preflight()`); if dm20 down, exit 6 (`EXIT_DM20_UNREACHABLE`) with the same friendly stderr style as D-26.
- **Reuse the production MCP client + circuit breaker.** Don't roll a new HTTP path; share code with the bot.
- **No "best effort" mode** — partial data in `pc_classes` is worse than no data because v1.0 fall-back is "eligibility false." Operator must fix dm20 first.
**Detection:** Test with a 502-returning MCP double; assert exit 6, no DB writes.
**Phase assignment:** Backfill plan.

### BF-4 (HIGH): Schema drift between v1.0 and v1.1
**What goes wrong:** Backfill assumes `pc_classes` shape from v1.0; v1.1 adds a column; backfill writes a row missing the new column, NULL constraint violation.
**Prevention:**
- **Schema version check on script start.** Read `PRAGMA user_version`; if not in known-supported list, refuse and tell operator to upgrade by running the bot once first (migrations run on bot startup).
- **Backfill INSERTs use explicit column lists**, never `INSERT INTO pc_classes VALUES (…)`. New columns added later don't break the script.
**Detection:** Test against a DB at the wrong schema version; assert exit 7 (`EXIT_SCHEMA_MISMATCH`).
**Phase assignment:** Backfill plan.

### BF-5 (MEDIUM): `--dry-run` accidentally writes
**What goes wrong:** Logic bug routes a write through even with `--dry-run`. Self-hoster's "let me see what would happen" mutates DB.
**Prevention:**
- **`--dry-run` opens SQLite read-only.** `sqlite3.connect(f"file:{path}?mode=ro", uri=True)`. The kernel refuses writes; the bug becomes impossible.
- **Explicit test of the dry-run path** that asserts zero rows changed after invocation.
**Phase assignment:** Backfill plan.

---

## SAN-01 Expansion Pitfalls

### SAN-EXP-1 (HIGH): Double-sanitization mangles legitimate input
**What goes wrong:** `WeaponSelectModal` already allow-list-regexes weapon names. Adding `sanitize_player_input` on top might strip apostrophes from "Master's Greatsword" or smart quotes from a pasted name.
**Prevention:**
- **Test the round-trip on real weapon names.** Add a fixture list of all dm20 weapon names + common homebrew (`Master's Greatsword`, `Sword of Sharpness`, `Frostbrand`) and assert `sanitize(allow_list(name)) == name`.
- **If a conflict surfaces: sanitizer wins on free-text fields, allow-list wins on enum-y fields.** Document the layering decision in the code comment.
**Detection:** Round-trip fixture test.
**Phase assignment:** SAN-01 plan.

### SAN-EXP-2 (MEDIUM): Audit table growth
**What goes wrong:** Every modal submission audited → table grows unbounded → SQLite slow over months.
**Prevention:**
- **Retention policy: keep last 30 days OR last 10k rows, whichever is larger.** Sweeper runs at bot startup (same shutdown-order pattern as v1.0 OPS-04 sweeper).
- **Index on `created_at`** for the sweeper query.
**Phase assignment:** SAN-01 plan (defensive — small) or defer to v1.2 if scope tight.

### SAN-EXP-3 (MEDIUM): Modal submission latency
**What goes wrong:** Sanitizer adds CPU work to a callback that has the 3s defer budget. EDM001 lint enforces `defer(thinking=True)` first-line, so we have headroom, but stacked latency hurts UX.
**Prevention:**
- **Benchmark gate:** sanitizer must add ≤ 50ms p99 to modal submission. Add a `pytest-benchmark` test.
- **Defer-first discipline** (already enforced by EDM001) keeps the 3s budget intact; sanitizer runs after defer.
**Phase assignment:** SAN-01 plan.

---

## OPS-02 (DM_OFFLINE warning) Pitfalls

### OPS-02-1 (HIGH): Warning spam
**What goes wrong:** Circuit opens; user clicks 5 buttons in 2 seconds; 5 ephemeral "DM is offline" warnings stack.
**Prevention:**
- **Per-channel debounce window: 30s.** Track last-warned timestamp per channel; suppress within window.
- **Counter even when suppressed**, exposed via diagnostics command for ops visibility.
**Phase assignment:** OPS-02 plan.

### OPS-02-2 (HIGH): False positives on transient blips
**What goes wrong:** Brief network hiccup → 3-strike circuit opens → warning sent → 200ms later circuit closes → user confused.
**Prevention:**
- **Min-duration threshold: only warn if circuit has been open ≥ 5 seconds.** Schedule a delayed warning task that cancels itself if circuit closes first.
- **Pair the warning with the recovery embed:** on circuit-close after a warning was shown, send a "DM is back online" ephemeral to the same channel.
**Phase assignment:** OPS-02 plan.

### OPS-02-3 (MEDIUM): Lost action on warning
**What goes wrong:** User clicks Attack → circuit open → warning shown → user has no way to retry the same action when circuit closes.
**Prevention:**
- **Include in the warning text: "Your action wasn't lost. Click the button again in a few seconds."** The Discord persistent View is already rehydratable; the button stays clickable.
- **For combat-critical buttons (Attack, Riposte) only:** queue the intended action with a 30s expiry, replay on recovery if user hasn't done anything else. v1.1 may defer this to v1.2 if scope tight — call it out.
**Phase assignment:** OPS-02 plan (warning text), defer queue-replay if cost is high.

---

## `__main__` Token-Fix (TD-1) Pitfalls

### TD-1-1 (MEDIUM): Drift from `run.py`
**What goes wrong:** Copy-paste the friendly-error block from `run.py` into `bot/__main__.py`; future change to one is forgotten in the other.
**Prevention:**
- **Extract a shared helper:** `from eldritch_dm.config.token_guard import require_token_or_exit(settings) -> int`. Both `run.py` and `bot/__main__.py` call it.
- **Single test covers both entrypoints** by parametrizing on the entry function.
- **D-26 lesson directly:** test the documented user paths, both of them. Don't trust that "run.py covers it" — `python -m eldritch_dm.bot` is also a documented path.
**Phase assignment:** TD-1 plan (tiny — combine with SAN-01 or YAML if scope-clustering helps).

---

## Ruff Cleanup Pitfalls (TD-2)

### RUFF-1 (HIGH): `--unsafe-fixes` rewrites semantically
**What goes wrong:** `--unsafe-fixes` can convert `dict()` to `{}` literals in places where the call has a side effect, or rewrite comprehensions in ways that change exception behavior.
**Prevention:**
- **Never run `ruff check --fix --unsafe-fixes` in v1.1.** Safe fixes only.
- **Of the 43 auto-fixable: apply in batches of one rule code at a time.** `ruff check --fix --select I` (imports), then run full pytest. Then `--select UP` (pyupgrade), then pytest. Atomic commits per rule.
- **Manual review for the remaining 36 errors.**
**Detection:** Pytest after every rule batch. Bisect-friendly history.
**Phase assignment:** Ruff cleanup phase (likely Phase 1, per PROJECT.md strategy note).

### RUFF-2 (MEDIUM): Import-sort breaks import-linter contracts
**What goes wrong:** Ruff's `I` rule reorders imports; reordering can expose previously-masked import cycles that import-linter now flags. Or, less likely, reordering exposes top-of-file side-effects whose timing matters.
**Prevention:**
- **Re-run `lint-imports` after every ruff batch.** v1.0 has 7 contracts; all must stay green.
- **Atomic commit per file** during the I-rule batch so any contract regression is bisectable to one file.
**Phase assignment:** Ruff cleanup phase.

### RUFF-3 (LOW): `Optional[X]` → `X | None` and eval-string contexts
**What goes wrong:** Python 3.11+ supports `X | None` natively, but `typing.get_type_hints(..., include_extras=True)` and string-annotation `from __future__ import annotations` interplay can surface edge cases (rare).
**Prevention:**
- **Run pyright after the UP-rule batch** in addition to pytest. The type checker catches eval-string issues that runtime tests miss.
**Phase assignment:** Ruff cleanup phase.

---

## Cross-Cutting v1.1 Pitfalls

### CC-1 (CRITICAL): Untracked Phase 4 dirty files affecting executors
**What goes wrong:** v1.0 retrospective's "Lesson 4" — the 23 pre-existing ruff-residue files caused every Phase 5 executor to need an explicit no-touch list. Same hazard for v1.1: now there will be 3 PLAN-* untracked files in `.planning/phases/02-discord-scaffold-persistent-views/` (visible in current `git status`), and the in-progress ROADMAP edits.
**Prevention:**
- **Stash or commit the in-flight planning artifacts before kicking off any v1.1 executor.** Run `git status` as the first step of each phase plan.
- **Explicit "do NOT modify these files" list** in every executor prompt for any file outside the phase's declared scope.
- **Run ruff cleanup FIRST** (PROJECT.md strategy is correct) so the noise floor is zero when feature work starts.
**Phase assignment:** Pre-flight discipline of every v1.1 phase. Ruff cleanup as Phase 1 implements the structural fix.

### CC-2 (HIGH): VERIFICATION.md still skipped
**What goes wrong:** v1.0 procedural gap P-1: zero VERIFICATION.md files were created because `/gsd:verify-phase` was never run. The retrospective tags this `NEEDS IMPROVEMENT v1.1`. If v1.1 proceeds the same way, the next milestone audit finds the next G-1.
**Prevention:**
- **Add `/gsd:verify-phase` as a hard gate** before phase close in every v1.1 phase plan. Acceptance criterion: `VERIFICATION.md` exists and is committed.
- **VERIFICATION.md template includes a "cold-start E2E covered?" checkbox** — forces the meta-pitfall question.
**Phase assignment:** Every v1.1 phase.

### CC-3 (HIGH): REQUIREMENTS.md drift
**What goes wrong:** v1.0 retrospective procedural gap P-2: 11 implemented requirements never ticked. Same hazard for v1.1's 7 deliverables if discipline doesn't change.
**Prevention:**
- **Each plan's closure checklist includes "tick associated requirement(s) in v1.1-REQUIREMENTS.md."** Reviewable as a single diff line per closure.
- **Audit at milestone close cross-checks** (same audit script v1.0 used).
**Phase assignment:** Every v1.1 phase.

### CC-4 (MEDIUM): Background pytest pile-up from autonomous loops
**What goes wrong:** v1.0 retrospective noted ~10 stranded zsh-wrapped pytest processes from cron-driven `/gsd-autonomous` fires.
**Prevention:**
- **Single-instance lock file** for `/gsd-autonomous` runs.
- **Dynamic-mode `/loop`** (event-driven) over fixed-interval cron, per retrospective recommendation.
**Phase assignment:** Process improvement; flag in v1.1 PROJECT.md but no code phase needed.

---

## Phase-Specific Warning Matrix

| Phase candidate | Likely Pitfall(s) | Mitigation |
|---|---|---|
| **Phase 1 (recommended): Cold-start smoke + Ruff cleanup** | Meta-pitfall, CC-1, RUFF-1/2/3 | One commit per rule batch; first E2E test before any feature code |
| Phase: SAN-01 + TD-1 + OPS-02 (small-item cluster) | SAN-EXP-1/2/3, OPS-02-1/2/3, TD-1-1 | Round-trip weapon-name fixtures; per-channel debounce; shared `require_token_or_exit` helper |
| Phase: YAML Riposte eligibility | YAML-1..6 | `safe_load`-only lint check; fail-soft + log warning; extend-vs-replace mode; normalize-on-load |
| Phase: Smart MonsterDriver (largest) | MD-1..6 | INT-band prompt templates + temperature scaling; cache + batch; hard 1500ms deadline; pydantic validation + adversarial corpus |
| Phase: pc_classes backfill script | BF-1..5 | Pidfile lock; per-PC transactions + idempotent re-run; reuse MCP client; schema-version check; read-only mode for `--dry-run` |

---

## Sources

- **Internal:** `.planning/RETROSPECTIVE.md` (v1.0 lessons — cold-start E2E gap is the load-bearing meta-pitfall), `.planning/milestones/v1.0-MILESTONE-AUDIT.md` (G-1/G-2/G-3/G-4 + TD-1/TD-2/TD-3 + P-1..P-4), `.planning/debug/resolved/preflight-requires-token.md` (D-26 — "test the user's actual path"), `.planning/PROJECT.md` (current-state, constraints, key decisions)
- **Domain general:** Discord.py 2.7.1 modal/interaction 3-second ack budget; SQLite WAL single-writer semantics; pydantic v2 `model_config = ConfigDict(extra='forbid')`; PyYAML `safe_load` advisory; MLX local-inference latency profile (~90 tok/s on M3 Ultra per project STACK research)
- **Confidence:** HIGH on v1.0-derived pitfalls (sourced from in-repo audit + retrospective); MEDIUM on Smart MonsterDriver pitfalls (novel for this repo — patterns extrapolated from LLM-tool-calling adversarial-testing literature and the v1.0 sanitizer-corpus precedent)
