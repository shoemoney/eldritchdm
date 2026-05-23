# EldritchDM Living Retrospective

Cumulative lessons across all milestones. New milestone sections are inserted at the top.

## Milestone: v1.0 — MVP (Mechanically Honest AI Dungeon Master)

**Shipped:** 2026-05-23
**Phases:** 5 | **Plans:** 15 | **Commits:** 110 | **Tests:** 873 collected (864 passing) | **Duration:** 2 days

### What Was Built

A local-first Discord bot that runs full D&D 5e games end-to-end on a self-hosted oMLX server. Three-brain architecture: oMLX/ShoeGPT narrates, dm20 MCP server enforces rules, this repo orchestrates Discord. 873 tests cover the seams between layers; 7 import-linter contracts enforce the layered architecture; a custom EDM001 AST lint rule enforces `await interaction.response.defer(thinking=True)` as the first line of every Discord callback.

### What Worked

- **MCP-hybrid pivot was the highest-leverage decision.** Discovering dm20 already implemented ~70% of the original PRD collapsed scope from 11 phases (87 reqs) → 5 phases (~73 reqs) without losing any user-facing capability. Time saved: ~3 weeks.
- **Atomic commits + RED→GREEN test gates produced clean bisect history.** Every commit landed with a failing test followed by the fix. When the audit found G-1 (orchestrator never starts), the fix was 5 lines and a single integration test — the surrounding code was untouched.
- **Subagent fan-out parallelized non-overlapping work.** Wave 1 + Wave 2 doc-writers + Phase 5 researcher (5 agents in parallel) cut docs-update from a serial 25 minutes to ~6. The pattern only works when file-ownership is disjoint; tried to fan out during Plan 01 → Plan 02 hand-off and correctly held back because the marker file was about to mutate.
- **Pinned tech stack with zero new deps after Phase 1.** All 5 phases shipped on the dependency list locked in research-phase. Made dependency review skippable in plans 02-05.
- **Restart-survival drill caught real bugs.** The kill-bot-mid-X-then-restart pattern surfaced two correctness issues that no other test would have caught: Plan 02's CombatConditionsRepo double-start aiosqlite bug (fixed at `6457212`) and a sweeper/click race that motivated the shared `SessionLocks` design.
- **Decision IDs anchored conversations across context boundaries.** D-A/D-B/D-C/D-26/D-F let executors find the relevant choice in a paragraph instead of re-deriving it. Saved several "wait what did we decide" cycles.

### What Was Inefficient

- **The autonomous loop never ran `/gsd:verify-phase`.** This was caught only at milestone audit time, when zero VERIFICATION.md files were found. The cross-phase integration check in the audit was the first time anyone looked at whether Phase N's outputs actually wired up to Phase N+1's inputs. It found G-1 (orchestrator-never-starts) — a single missing function call that 870 tests didn't catch because no test covered the cold-start lobby→ready→narrative path within a single bot lifetime.
- **REQUIREMENTS.md drifted from reality.** Phases 1-3 requirements were never ticked even though their code shipped and tests passed. By milestone audit time, 11 implemented requirements showed as `[ ]`. The audit-fix executor reconciled them in one commit (`25cb7a0`), but the lesson is that requirement-tick discipline needs to be a hard gate inside each plan's closure, not a hand-wavey "make sure to update."
- **Phase-level SUMMARYs missing for Phases 1 and 3.** Only plan-level `01-01-SUMMARY.md`, `01-02-SUMMARY.md`, `01-03-SUMMARY.md` exist for Phase 1. Phase 4 and 5 got phase-aggregation SUMMARYs because their planners wrote them explicitly; this should be the default.
- **Smoke-tested the README's documented preflight path at the very end.** The token-bug (D-26) was found at the human-verify checkpoint — `python -m eldritch_dm.bootstrap` raised a pydantic traceback when DISCORD_TOKEN was unset, defeating the README's "verify deps before pasting your token" promise. This should have been caught at Plan 03 close, not at milestone audit time.
- **Background pytest processes piled up.** Cumulative cron fires of `/gsd-autonomous` with `*/1 * * * *` and background pytest invocations stranded ~10 zsh-wrapped processes. Future autonomous loops should either skip pytest if not needed or use a single-instance lock file.

### Patterns Established

- **PLAN-N-LOCK-SEAM markers.** When Plan N ships a temporary correctness path that Plan N+1 will replace, embed a grep-able marker comment with a precise file:line and a one-line description of what gets replaced. Plan 02 found the marker at `reactions.py:280` and replaced it cleanly at `reactions.py:345`. Plan N+1's first test grep-asserts the marker is gone.
- **Shared per-channel `asyncio.Lock` registry** (`SessionLocks`) over module-global locks. Lets sweeper task + click callback serialize without either knowing about the other's existence. Pattern is reusable for any future timer/click race in the bot.
- **DynamicItem regex custom_ids over closures.** Phase 2's investment in `bot.add_view(view, message_id=...)` rehydration paid off in every later phase. Phase 5's RiposteButton plugged into the same machinery with zero changes to setup_hook.
- **Audit-substitutes-for-VERIFICATION when the autonomous loop skips it.** The milestone audit's cross-phase integration check turned out to be more thorough than per-phase VERIFICATION.md would have been because it traced E2E flows across all 5 phases simultaneously. For autonomous runs, audit-as-verification is acceptable; for interactive runs, VERIFICATION.md per phase remains the better unit.
- **`grep -v '^#' | grep -c` for code-vs-comment gating.** When deleting a feature (D-A `_maybe_surface_riposte` seam), the gate counts non-comment hits. Comments mentioning the deleted feature are fine to leave — they're historical context, not dead code.

### Key Lessons

1. **Test the documented user flow end-to-end before declaring a phase done.** Every test in v1.0 worked at a layer (sanitizer corpus, MCP client mocked, DynamicItem regex, OPS-01 restart drill). No test exercised "user clones repo → runs install.sh → bootstraps → runs the bot → starts a game → all-ready → ShoeGPT narrates." The audit caught it at the wire-up layer; production users would have caught it on day 1.
2. **The autonomous loop is not a substitute for a verification step.** Skipping `/gsd:verify-phase` to save time meant the same gaps surfaced later — but with the additional cost of having to write a hotfix plan, re-test, re-audit.
3. **License decisions should be explicit at project init, not at ship time.** Flipping MIT → Apache 2.0 at v1.0 close required edits across 8 files. Apache's patent grant matters for AI/LLM projects; the choice should have been made at the PRD stage.
4. **Subagent prompts need explicit "do NOT touch" lists when the working tree has unrelated dirty files.** The 23 pre-existing ruff-residue files from Phase 4 caused every Phase 5 executor and the audit-fix executor to need an explicit no-touch list in its prompt. Cleaner: stash before phase start, or run cleanup before kicking off the next phase.
5. **Decisions like "delete this no-op seam" should be atomic single-line-changes-as-commits.** D-A's deletion of `_maybe_surface_riposte` was its own commit (`1d2edc8`). Future bisect can isolate it. Don't bundle deletions with the replacement implementation in one commit.

### Cost Observations

- **Model mix (approximate):** Most executor work ran on Sonnet 4.6; gsd-debugger + gsd-integration-checker on Sonnet 4.6; this orchestrator on Opus 4.7 (xhigh effort).
- **Sessions:** 1 long-running session across 2 calendar days (background cron + manual `/gsd-autonomous` triggers).
- **Notable efficiency win:** Fanning out 4 doc-writers + Phase 5 researcher in parallel during one yield cycle reduced wall-clock by ~70% vs. serial.
- **Notable inefficiency:** The hourly `/loop /gsd-autonomous` cron created several wake-cycles where Plan 01/02/03 were still running and no new parallel work was available — those cron fires were waste motion. Dynamic-mode `/loop` (self-pacing on completion events) would have been more efficient than fixed-interval cron.

## Cross-Milestone Trends

*(First milestone — table populates as v1.1+ ship.)*

| Trend | v1.0 | Direction |
|---|---|---|
| Tests per phase | 175 avg | — |
| Plans per phase | 3.0 avg | — |
| Atomic commit discipline | Strong (110 commits, all with conventional prefixes) | — |
| Subagent fan-out usage | High during plan execution; low when seam-locked | — |
| VERIFICATION.md compliance | 0/5 | NEEDS IMPROVEMENT v1.1 |
| Cold-start E2E test coverage | 0 (caught at audit) | NEEDS IMPROVEMENT v1.1 |

---
