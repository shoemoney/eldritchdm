# Phase 5: Reactions + Self-Host Polish - Context

**Gathered:** 2026-05-21
**Status:** Ready for research + planning (prepped in advance)
**Mode:** Synthesized from REQUIREMENTS (COMBAT-09..11, HOST-01..08, OPS-01) + Phase 1-4 deliverables

<domain>
## Phase Boundary

Closes v1. Two interleaved goals:

1. **Reactions** — the EldritchDM differentiator. Timed 8-second Riposte button surfaces after an eligible monster miss; click executes a counter-strike via `dm20__combat_action(reaction=true)`; the timer survives bot restart. This is the only Phase 5 gameplay feature.

2. **Self-host polish** — make the project actually installable and runnable end-to-end by a person who has oMLX + dm20 already configured. Includes: README expansion to walk through "I have oMLX + dm20 + a Discord token" → "I am playing D&D in 10 minutes", `bootstrap.py` enrichment (already exists from Phase 1 — extend with oMLX/dm20 health pings per HOST-03), `run.py` entrypoint (already a stub from Phase 1 — flesh out), launchd recipe in README, full test suite green including the restart-survival drill (OPS-01), `pyproject.toml` clean dep pin & metadata, optional installable script entry point.

**In scope:**
- COMBAT-09: Riposte detection on monster attack resolution where target is eligible (Fighter/Battle Master, Rogue/Swashbuckler — verified via `dm20__validate_character_rules`) and target has reaction available
- COMBAT-10: Riposte button persists 8s with `deadline_ts` in `riposte_timers`; click → `dm20__combat_action(reaction=true, weapon=primary)` (or shim); only target player can click
- COMBAT-11: Riposte timer survives bot restart — `riposte_timers` row drives a sweeper that cleans expired buttons on restart and any time before expiry
- HOST-01..08: README, `.env.example` (already exists; verify completeness), `python -m eldritch_dm.bootstrap` extends to ping oMLX + count dm20 tools (HOST-03), `run.py` validates env + pings + launches bot (HOST-04), pyproject.toml clean (HOST-05), test suite via pytest (HOST-06), README covers macOS-primary + Linux best-effort (HOST-07), launchd recipe in README (HOST-08)
- OPS-01: Resume drill — kill bot mid-combat, restart, confirm turn order/HP/buttons functional from `channel_sessions` + `dm20__get_claudmaster_session_state`. This is a CI-runnable integration test, not just docs.

**NOT in scope:**
- Other reactions (Shield, Counterspell, Hellish Rebuke) — v2 (REACT-01..03)
- Voice/TTS, map/grid visuals, human-DM override — v2 (EXUI-01..03)
- Advanced workflows: adventure browser UX, sheet sync, pack import/export — v2 (ADV-01..03)

</domain>

<decisions>
## Implementation Decisions

### Reaction system architecture
- **D-01:** Reaction-detection hook lives in `PartyModeOrchestrator` (from Phase 4). When `combat_action` returns `outcome=miss` for a monster attacking a PC, the orchestrator checks Riposte eligibility and surfaces the button.
- **D-02:** New module `src/eldritch_dm/gameplay/reactions.py`:
  - `RiposteEligibility(character_id, user_id, primary_weapon) | None` — query result
  - `check_riposte_eligibility(channel_id, character_id) -> RiposteEligibility | None` — async; calls `dm20__validate_character_rules(character_id)` and inspects the result for Fighter/Battle Master or Rogue/Swashbuckler with available reaction
  - `surface_riposte_button(interaction_context, eligibility) -> None` — posts the ephemeral timed button, inserts `riposte_timers` row, schedules a sweeper coroutine

### Eligibility check
- **D-03:** Two sources of truth:
  - dm20 says character has reaction available via `validate_character_rules` (preferred — single source)
  - If dm20 doesn't directly model `has_reaction`, fall back to: query `riposte_timers` for any active row for this character_id in this round. If none, reaction is available. Plan 5 RESEARCH must verify which is the case.
- **D-04:** Eligible classes hard-coded for v1 (`ELIGIBLE_CLASSES = {("fighter", "battle_master"), ("rogue", "swashbuckler")}`). v2 may expand to more class/subclass combos.
- **D-05:** Class info from `dm20__get_character(character_id) → character.class + character.subclass`. Compare to ELIGIBLE_CLASSES set.

### Riposte button mechanics
- **D-06:** `RiposteButton` exists as a Phase 2 DynamicItem with `riposte:(?P<timer_id>\d+):(?P<user_id>\d+)` template. Phase 5 makes the callback real:
  1. Defer ephemeral
  2. Read `riposte_timers.get(timer_id)`
  3. If `status != 'pending'` → ephemeral "Riposte expired or already used" warning (`WarningKind.RIPOSTE_EXPIRED`)
  4. If `deadline_ts < now()` → mark `status='expired'`, ephemeral warning
  5. If `interaction.user.id != user_id` → ephemeral `INVALID_ACTION` warning (only target player can click)
  6. Else: `dm20__combat_action(action="attack", weapon=primary_weapon, target=monster_uuid, reaction=true)` (or shim)
  7. Mark `riposte_timers.status='consumed'`
  8. Forward narrative request through party_action: `"{player} executed a Riposte counter-strike: {outcome}. Narrate."`
  9. Delete the ephemeral message hosting the button (cleanup)
- **D-07:** 8-second TTL: `deadline_ts = now() + RIPOSTE_TTL_SECONDS` (env, default 8).
- **D-08:** Concurrency: per-channel `asyncio.Lock` (existing pattern) wraps the callback to prevent double-click races.

### Restart survival
- **D-09:** Background sweeper task: `src/eldritch_dm/gameplay/riposte_sweeper.py`. Started in `setup_hook` after persistence comes online. Loops:
  ```python
  while True:
      pending = await riposte_timers_repo.list_pending()
      now_ts = datetime.utcnow()
      for timer in pending:
          if timer.deadline_ts <= now_ts:
              await riposte_timers_repo.mark_expired(timer.id)
              # best-effort: delete the ephemeral message (if Discord still has it)
              try: await bot.http.delete_message(timer.channel_id, timer.message_id)
              except discord.NotFound: pass
      next_deadline = min((t.deadline_ts for t in pending if t.status == 'pending'), default=None)
      sleep_until = (next_deadline - now_ts).total_seconds() if next_deadline else 30
      await asyncio.sleep(max(0.1, min(sleep_until, 30)))
  ```
- **D-10:** Sweeper uses the `idx_riposte_pending_deadline` partial index already in schema.sql for fast pending lookups.
- **D-11:** On startup, sweeper picks up any pending timer whose deadline is still in the future and lets the user click it; expired ones are immediately marked.

### Reaction-budget shim (if dm20 doesn't track reactions)
- **D-12:** If Plan 5 RESEARCH confirms dm20 has no native `has_reaction` field:
  - Add column `riposte_timers.consumed_in_round INTEGER` so we can scope reactions to a single round (a character has one reaction per round)
  - On `next_turn` to a new round, mark all `pending` riposte rows from the previous round as `cancelled`
  - This is the "Phase 5 shim" called out in PROJECT.md
- **D-13:** If dm20 DOES track reactions natively, the shim is unnecessary — just call `dm20__combat_action(reaction=true)` and trust dm20.

### Self-host: bootstrap.py extension (HOST-03)
- **D-14:** Phase 1's `bootstrap.py` currently only creates the local DB. Extend to also:
  - Ping `OMLX_ENDPOINT/v1/models` — print whether oMLX is up + which models are loaded
  - Ping `MCP_TOOLS_URL` — count MCP tools available; warn if `dm20` tools are missing
  - Print a "Ready to run" / "Issues to fix" status block
  - Exit code 0 if everything green, exit code 1 if oMLX unreachable, exit code 2 if dm20 not loaded

### Self-host: run.py (HOST-04)
- **D-15:** `run.py` is the entrypoint a self-hoster runs. Should:
  1. Load `Settings` (already validates required env)
  2. Run `bootstrap.ensure_schema(db_path)`
  3. Ping oMLX once (fail fast if unreachable — unless `ELDRITCH_ALLOW_OFFLINE_START=1`)
  4. Build `EldritchBot`, attach persistence + MCP client + sanitizer
  5. Call `bot.start(settings.discord_token)` — propagate exit code
  6. Handle SIGTERM / SIGINT for graceful shutdown (catch and call `bot.close()`)
- **D-16:** `run.py` lives at the project root (not under `src/eldritch_dm/`) so users invoke `python run.py` from a checkout directly.

### README expansion (HOST-01, HOST-07, HOST-08)
- **D-17:** README already covers the architecture, env vars, and the 30-second quickstart. Phase 5 adds:
  - "First session in 10 minutes" — step-by-step walkthrough, with screenshots/ascii of what each Discord interaction looks like
  - Troubleshooting section: "common failures and what they mean" (oMLX down, dm20 not loaded, character upload failed, etc.)
  - launchd recipe for supervising `python run.py` on macOS (HOST-08) — full plist example
  - systemd recipe for Linux (best-effort per HOST-07)
- **D-18:** Add a `docs/` directory for longer-form supporting docs:
  - `docs/launchd.plist.example` (com.user.eldritch-dm)
  - `docs/eldritch-dm.service.example` (systemd unit)
  - `docs/dm20-troubleshooting.md` — how to verify dm20 is loaded in oMLX
  - `docs/character-ingest-formats.md` — what sheet formats work well, what doesn't

### Tests + verification (HOST-06, OPS-01)
- **D-19:** **OPS-01 resume drill** is the single most important test in Phase 5:
  - Setup: seed `channel_sessions` (state=COMBAT), seed `riposte_timers` (status=pending, deadline 5s in future), seed `persistent_views` (the combat embed + the riposte button)
  - Build bot A; verify it rehydrates everything (combat embed message, button DynamicItem)
  - Kill bot A (terminate the event loop, simulating SIGKILL — use `bot.close()` then drop reference)
  - Build bot B fresh on the same DB
  - Assert: `setup_hook` reads same `channel_sessions`, registers same DynamicItems, sweeper task picks up the still-pending riposte timer
  - Simulate a Discord interaction with the matching `custom_id` → assert callback fires correctly
  - Wait until deadline; assert sweeper marks the timer expired
- **D-20:** Full test suite: `python -m pytest -q` shows all green (260+ tests by end of Phase 5). Stress tests gated by env var. README shows how to run.
- **D-21:** New test fixtures in `tests/gameplay/test_reactions.py`, `tests/gameplay/test_riposte_sweeper.py`, `tests/integration/test_resume_drill.py`.

### pyproject.toml polish (HOST-05)
- **D-22:** Verify all deps pinned, version-stable, MIT-compatible (PyMuPDF AGPL — already documented as acceptable for self-host project; if Phase 5 RESEARCH discovers it's a problem, swap to `pypdf` primary)
- **D-23:** Add `[project.scripts]` entry: `eldritch-dm = "eldritch_dm.bot.__main__:main"` so installed users can run `eldritch-dm` instead of `python -m eldritch_dm.bot`
- **D-24:** Clean up any leftover dev-only deps that don't need to ship (probably none, but verify)
- **D-25:** Add `[project.urls]` with homepage, repository, issues

### Phase 5 SUMMARY + milestone close
- **D-26:** Phase 5 SUMMARY documents all phases' deliverables holistically — this is the document a new contributor reads to onboard.
- **D-27:** After Phase 5, run `/gsd:audit-milestone` (autonomous workflow handles this) — verify every v1 requirement is marked [x] in REQUIREMENTS.md.
- **D-28:** After audit passes, `/gsd:complete-milestone v1.0` archives the milestone and cleans up.

### Claude's Discretion
- Exact wording of README "first session in 10 minutes" walkthrough
- Sweeper polling cadence — currently `min(sleep_until, 30)`; could go lower (more responsive) or higher (less CPU)
- Whether `eligible_classes` is a frozen set or read from a YAML config (frozen set is fine for v1; YAML if Phase 5 RESEARCH finds more classes the user wants supported)
- Exact launchd plist details (label, KeepAlive, StandardOutPath, etc.) — pattern after `com.user.omlx` from user's existing setup

</decisions>

<canonical_refs>
## Canonical References

### Phase scope
- `.planning/REQUIREMENTS.md` § Combat (COMBAT-09, COMBAT-10, COMBAT-11), § Self-Host (HOST-01..08), § Operational (OPS-01)
- `.planning/ROADMAP.md` § Phase 5 — goal + 5 success criteria

### Phase 1-4 deliverables (interfaces this phase composes from)
- `src/eldritch_dm/persistence/riposte_timers_repo.py` — primary persistence for timers; already has `list_pending`, `insert`, `mark_expired`, `mark_consumed` per Phase 1 contract
- `src/eldritch_dm/bot/dynamic_items.py` — `RiposteButton` exists with regex template since Phase 2; Phase 5 makes the callback real
- `src/eldritch_dm/bot/warnings.py` — `WarningKind.RIPOSTE_EXPIRED`, `INVALID_ACTION`
- `src/eldritch_dm/gameplay/party_mode.py` — Phase 4 introduces; Phase 5 adds a reaction-detection hook
- `src/eldritch_dm/mcp/tools.py` — `validate_character_rules`, `combat_action`, `get_character` — all wired Phase 1
- `bootstrap.py`, `run.py` — already exist (Phase 1 + Phase 2 entrypoint scaffolding); Phase 5 extends
- README.md — Phase 0 docs scaffold; Phase 5 expands into a polished self-host guide
- `.env.example` — Phase 0 already complete; Phase 5 verifies + adds any new env vars (likely none, possibly `ELDRITCH_ALLOW_OFFLINE_START`)

### MCP tool reference
- `ddmcpskills.md` § dm20 § Combat (`combat_action` with reaction flag — verify in research), `apply_effect`/`remove_effect`, `validate_character_rules`, `get_character`

### External
- [launchd.plist man page](https://www.unix.com/man-page/osx/5/launchd.plist/) — service supervision on macOS
- [systemd.unit](https://www.freedesktop.org/software/systemd/man/systemd.unit.html) — Linux equivalent
- [discord.py custom emoji / interactions](https://discordpy.readthedocs.io/en/v2.7.1/) — for the Riposte button's `↩️` glyph

</canonical_refs>

<code_context>
## Existing Code Insights

### Phase 1-4 delivered (this phase composes from)
- `riposte_timers` table and repo from Phase 1
- `RiposteButton` DynamicItem from Phase 2 (stub callback)
- `PartyModeOrchestrator` from Phase 4 (reaction-detection hook is a new module that listens to it)
- `WarningKind.RIPOSTE_EXPIRED` from Phase 2's `warnings.py`
- Per-channel `asyncio.Lock` registry from Phase 1
- `bootstrap.py` (Phase 1) + `run.py` (Phase 2/3 entrypoint) — both extended in Phase 5

### Reusable Assets
- `Settings.riposte_ttl_seconds` (already in env, default 8)
- structlog binding pattern
- Adversarial corpus pattern (could add a riposte-injection corpus if v2 needs)

### New Modules This Phase Introduces
- `src/eldritch_dm/gameplay/reactions.py` — eligibility checks + button surfacing
- `src/eldritch_dm/gameplay/riposte_sweeper.py` — background expiry task
- `docs/launchd.plist.example`, `docs/eldritch-dm.service.example`, `docs/dm20-troubleshooting.md`, `docs/character-ingest-formats.md`

### Integration Points
- Phase 5 closes v1 — after this, only audit + complete-milestone remain.
- The eligibility shim (D-12) is the most fragile piece — if dm20 doesn't track reactions, our reaction-budget table grows additional columns. Plan 5 RESEARCH must answer this BEFORE the executor starts.

</code_context>

<specifics>
## Specific Ideas

- The OPS-01 resume drill is the proof EldritchDM works as advertised. Treat it like a marketing demo — make it concise, dramatic, and runnable.
- The launchd plist example should mirror the user's existing `com.user.omlx` setup so it feels familiar — same naming convention `com.shoemoney.eldritch-dm`.
- README's "first session in 10 minutes" should literally include the slash-command lines a user types in order. Keep it as concrete as possible.
- The reaction-budget shim is gross but necessary if dm20 doesn't model it. We can hide the gross-ness behind the `reactions.py` API surface — callers just see `check_riposte_eligibility()` and don't know whether dm20 or our table is the source of truth.

</specifics>

<deferred>
## Deferred Ideas

- Shield, Counterspell, Hellish Rebuke reactions — v2 (REACT-01..03)
- Reaction queue UI ("multiple PCs eligible, who reacts first?") — v2; for v1 only one PC at a time can have a pending riposte per channel
- Reaction undo — v2
- Discord-native voice prompts for reactions — v2
- Public "play tracker" web page that mirrors the Discord game — v2

</deferred>

---

*Phase: 05-reactions-self-host-polish*
*Context gathered: 2026-05-21 (prepped in advance during Phase 2 Plan 03 / Phase 3 research)*
