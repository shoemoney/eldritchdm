---
phase: 23-cog-wiring
plan: 23-01
requirements_completed: [WIRE-02]
title: WIRE-02 — Lobby /end_game → MonsterMemoryRegistry.purge_session
status: complete
scope: PARTIAL (concentration half deferred — see 23-HALT-REPORT.md)
generated: 2026-05-25
key-files:
  created: []
  modified:
    - src/eldritch_dm/bot/bot.py
    - src/eldritch_dm/bot/cogs/lobby.py
    - tests/bot/cogs/test_lobby.py
    - .planning/REQUIREMENTS.md
decisions:
  - D-178 (session-close ordering): dm20 close → memory purge → LOBBY upsert → ephemeral embed
  - D-179 (fail-soft contract): dm20 close failure does NOT block purge or LOBBY flip
  - Registry exposure: bot.monster_memory_registry constructed at bot scope, threaded into make_monster_driver so /end_game and the smart driver share one instance
---

# Phase 23 Plan 01: Lobby /end_game Session Close Summary

**One-liner:** Wired `/end_game` slash command on `LobbyCog` to call
`MonsterMemoryRegistry.purge_session` after best-effort `dm20__end_claudmaster_session`,
then flip the channel back to `LOBBY` — closing v1.6's WIRE-02 honest-gap.

## What was built

1. **`bot.monster_memory_registry`** is now constructed in `EldritchBot.setup_hook`
   before `make_monster_driver(...)` and threaded into the driver factory as
   `monster_memory=self.monster_memory_registry`. Without this, the lobby cog
   would purge a separate (empty) instance.

2. **`LobbyCog.end_game`** — new `@app_commands.command(name="end_game", ...)`
   running the D-178 sequence:
   - `defer(thinking=True, ephemeral=True)` first (EDM001 / D-09).
   - DM-only permission gate via `can_act_on_character` (parity with
     `/load_adventure`).
   - `channel_sessions.get(...)` → ephemeral "nothing to end" if no session.
   - Best-effort `dm20__end_claudmaster_session(session_id=...)` — failure is
     logged but NON-FATAL (D-179 fail-soft).
   - Best-effort `monster_memory_registry.purge_session(channel_id, session_id)`
     — already fail-soft per L-07; defensive try in cog catches the
     attribute-missing case for legacy bots.
   - `channel_sessions.upsert(..., claudmaster_session_id=None, state=LOBBY)` —
     preserves the channel row as audit history.
   - Ephemeral 🛑 embed with the purged-count and LOBBY confirmation.

3. **Tests** (7 new in `TestEndGame`):
   - defers first
   - happy path (asserts all four side-effects)
   - no active session bailout
   - dm20 close fails → purge + LOBBY still happen
   - registry attribute missing → command does not crash
   - non-DM permission denial
   - registry purge raises → command still completes

## What was deferred (Option B of halt-report)

- **WIRE-01** (`observe_hit` cog wiring) — blocked on missing dm20 structured
  damage-event surface. dm20 returns markdown narration, not
  `(attacker, target, damage)` tuples. Parsing damage from LLM text would
  violate D-176 / EldritchDM mechanical-honesty contract.
- **Concentration observation** (originally inferred from D-177) — blocked by
  the same missing event surface; no concentration-cast emission exists.

Annotated in `REQUIREMENTS.md` and the traceability table.

## Commits

- `701870f` feat(23-01): expose MonsterMemoryRegistry on EldritchBot + thread to driver
- `fb70ad2` feat(23-01): add /end_game slash command (D-178 close-and-purge sequence)
- `f9136da` test(23-01): cover /end_game close-and-purge sequence
- `b8c120a` docs(23-01): tick WIRE-02 + annotate WIRE-01 deferred (halt-report)

## Tests

- New: 7 in `tests/bot/cogs/test_lobby.py::TestEndGame`
- Regression: `tests/bot/cogs/` 226 passed (no failures)
- Wider: 670 passed across `tests/bot/cogs/`, `tests/gameplay/`, `tests/observability/`

## Deviations from Plan

None — plan executed as written. Tests passed first run after `PYTHONPATH`
adjustment to point at the worktree (`.venv` is installed editable from the
main repo and pytest needs `PYTHONPATH=$WT/src` to pick up worktree edits;
this is environment, not a code deviation).

## Self-Check: PASSED

- `src/eldritch_dm/bot/bot.py`: registry construction at line 412-419, threading kwarg at make_monster_driver call.
- `src/eldritch_dm/bot/cogs/lobby.py`: `end_game` method present at line 454, AST-verified on class `LobbyCog`.
- `tests/bot/cogs/test_lobby.py`: `TestEndGame` class added with 7 test methods.
- `.planning/REQUIREMENTS.md`: WIRE-02 ticked `[x]`, WIRE-01 annotated deferred.
- All commits visible in `git log --oneline`.
