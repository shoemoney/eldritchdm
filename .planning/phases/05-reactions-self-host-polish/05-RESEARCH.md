# Phase 5: Reactions + Self-Host Polish - Research

**Researched:** 2026-05-22
**Domain:** dm20 reaction-shim + timed-button persistence + macOS self-host packaging
**Confidence:** HIGH (every reaction-related claim verified against dm20 source at `/Users/shoemoney/Services/mcp-servers/dm20-protocol/src/dm20_protocol/`; every codebase claim verified against `src/eldritch_dm/`)

## Summary

Every Phase 5 unknown surfaced in `05-CONTEXT.md` was answered by re-reading dm20 source AND walking the Phase 4 deliverable in `src/eldritch_dm/bot/dynamic_items.py`. The headline findings:

1. **`dm20__combat_action` has no `reaction` argument and no internal reaction budget.** Verified `main.py:1967-2106` — the only kwargs are `attacker, target, action_type, weapon_or_spell, damage_dice, damage_type, save_ability, half_on_save, spell_dc`. Phase 5 must implement riposte as a *normal* combat_action call after a local "is this a riposte?" branch in our orchestrator. **The reaction-budget shim is mandatory** (D-12 path, not D-13).
2. **`combat_action` returns formatted text, not JSON.** `_format_combat_result` (`main.py:1839-1873`) emits headers like `**Miss.** Goblin Scout misses Thorin.` or `**Hit!** ...` or `**CRITICAL HIT!** ...` or `**Natural 1!** ...`. Phase 5 needs a tiny outcome parser to detect `miss` vs `hit` vs `critical` — same regex-on-text discipline as Phase 4's `game_state_parser.py`.
3. **`get_character` returns formatted text, not JSON.** `main.py:472-580`. Subclass is **not** in the rendered text (only `Level {N} {race} {class}`). To detect "Battle Master Fighter" the bot cannot read subclass from `get_character`'s output — Phase 4's `mcp/tools.py:get_character` returns the same text. **Either (a) extend the tool wrapper to call a dm20 internal that exposes the model JSON, OR (b) parse `validate_character_rules`'s validation report, OR (c) persist subclass on the bot-side at ingest time.** Option (c) is the only one that requires no dm20 changes — the bot already calls `dm20__create_character` at ingest (Phase 3) and we can capture subclass into a local table or extend `channel_sessions.payload_json`.
4. **dm20 does NOT track "reaction available" anywhere.** Grepping `main.py` + `models.py` for `has_reaction`, `reaction`, `riposte`, `battle_master`, `swashbuckler` returned zero gameplay references — only the level-up `subclass` parameter (`main.py:410`) and the rulebook lookup (`main.py:2973`). **Reaction budget must be tracked in our `riposte_timers` table**, with a new round-scoped "consumed in round" rule.
5. **5e rules check:** Swashbuckler Rogue does **NOT** have a native Riposte feature. Battle Master Fighter does — when an enemy *misses* you with a melee attack, expend one superiority die, make a melee weapon attack against the creature. [CITED: dnd5e.wikidot.com/fighter:battle-master:maneuvers] [CITED: dndbeyond.com forums]. Swashbuckler at level 3 gets *Fancy Footwork* (deny opportunity attacks) and at level 9 gets *Panache*; neither is a "miss-and-counter" reaction. CONTEXT.md D-04 mis-attributes Riposte to Swashbuckler. **Recommendation: cut Swashbuckler from the v1 eligibility set OR clearly label the Swashbuckler path as a homebrew "Riposte-like" feature, not RAW.**
6. **Phase 4 placed `_maybe_surface_riposte` on the wrong attack flow.** The seam fires in `AttackButton._maybe_surface_riposte` (`dynamic_items.py:752-769`) — which only runs when a **PC clicks Attack and misses a monster**. Battle Master Riposte triggers when a **monster misses the PC**. Phase 5 must add the trigger at the monster-turn resolution path, which **does not exist yet** — Phase 4's `PartyModeOrchestrator` polls player actions only; the "drive monster turn" pattern documented in 04-RESEARCH.md Q3 was scoped out of the Phase 4 deliverable. Phase 5 either (a) adds the monster-turn driver as a precondition, OR (b) defers the actual reaction trigger detection to a "manual fire" path (player clicks a button to declare "I want to riposte the next monster attack against me") with a corresponding refactor.
7. **`riposte_timers` schema is already correct.** `database/schema.sql:36-50` ships with id, channel_id, character_id, user_id, monster_uuid, weapon_used, message_id, custom_id, deadline_ts, status (`pending|consumed|expired|cancelled`), created_at — every column Phase 5 needs. The partial index `idx_riposte_pending_deadline` exists. The repo has `insert`, `list_pending`, `mark_consumed`, `mark_expired` (`riposte_timers_repo.py`). **No migrations needed.** Only an optional `consumed_in_round INTEGER` column for the reaction-budget shim (D-12) — Phase 5 plan should add this in Wave 0.
8. **Ephemeral followup messages do NOT survive bot restart.** [CITED: discordpy.readthedocs.io/en/stable/interactions/api.html] — `interaction.followup` is valid for 15 min after the originating interaction. An ephemeral message **cannot** be re-edited from a fresh bot process. **Implication:** the Riposte button must be either (a) a public message gated by `interaction.user.id == row.user_id` (rebuildable on restart), OR (b) ephemeral and treated as best-effort: on restart, expired timers are marked `expired` and the user simply loses the button (a row in `riposte_timers` exists but no clickable Discord message). Plan must choose. RECOMMEND (a) — public message with permission gating — because it's the only path that gives users the "survives restart" property promised by COMBAT-11 + OPS-01.
9. **`run.py` does not exist** at the project root. `python -m eldritch_dm.bot` is the current entrypoint (`src/eldritch_dm/bot/__main__.py`). Phase 5 must **create** `run.py` (not edit) and document that both invocations work.
10. **`.env.example` discrepancies confirmed.** `MCP_RATE_LIMIT_MS=200` is absent from `.env.example` despite being read by `Settings`. `OMLX_CACHE_STRATEGY` is in `.env.example` but the Python layer ignores it. Phase 5 must (a) add `MCP_RATE_LIMIT_MS` to `.env.example`, (b) either drop `OMLX_CACHE_STRATEGY` from `.env.example` OR add a corresponding `Settings` field with a comment explaining it's forwarded to the oMLX process via environment passthrough.

**Primary recommendation:** Treat Phase 5 as three orthogonal sub-phases: (1) Riposte UI + reaction-budget shim built atop a *new* monster-turn driver (otherwise the differentiator never fires); (2) restart-survival sweeper for `riposte_timers`; (3) self-host polish (bootstrap extension, run.py creation, launchd plist, env audit, full-suite test gate, README walkthrough). The planner must front-load monster-turn driving as Plan 01 Wave 0 — without it, COMBAT-09 has no trigger.

## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01..D-28** — all 28 decisions in `05-CONTEXT.md § decisions` are locked. Plans must conform.
- Key locks for research: reaction detection lives in `PartyModeOrchestrator` (D-01); `src/eldritch_dm/gameplay/reactions.py` introduces `RiposteEligibility` + `check_riposte_eligibility` + `surface_riposte_button` (D-02); RIPOSTE_TTL_SECONDS env-driven, default 8 (D-07); per-channel asyncio.Lock wraps the riposte callback (D-08); sweeper is a background asyncio.Task started in `setup_hook` after persistence (D-09); reuses `idx_riposte_pending_deadline` partial index (D-10); shim adds `riposte_timers.consumed_in_round INTEGER` if dm20 has no reaction tracking (D-12 — research confirms this path is mandatory); bootstrap extension pings oMLX + counts MCP tools with exit-code semantics (D-14); run.py at project root, not under src/ (D-16); `[project.scripts]` entry `eldritch-dm = "eldritch_dm.bot.__main__:main"` (D-23); OPS-01 resume drill is a CI-runnable integration test (D-19).

### Claude's Discretion

- Exact wording of README "first session in 10 minutes" walkthrough
- Sweeper polling cadence — currently `min(sleep_until, 30)` seconds in D-09; tune lower (more responsive) or higher (less CPU) based on plan
- Whether `eligible_classes` is a frozen set (D-04) or read from a YAML config (frozen set is fine for v1)
- Exact launchd plist details (label, KeepAlive, StandardOutPath) — pattern after user's existing `com.user.omlx` per CONTEXT.md Discretion

### Deferred Ideas (OUT OF SCOPE)

- Shield, Counterspell, Hellish Rebuke reactions — v2 (REACT-01..03)
- Reaction queue UI ("multiple PCs eligible, who reacts first?") — v2; for v1 only one PC at a time can have a pending riposte per channel
- Reaction undo — v2
- Discord-native voice prompts for reactions — v2
- Public "play tracker" web page that mirrors the Discord game — v2

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| COMBAT-09 | Riposte detection on monster miss against eligible PC | Q1, Q2, Q3 — requires monster-turn driver; eligibility uses bot-side persisted subclass; trigger parses combat_action text outcome |
| COMBAT-10 | 8s timed button; click → reaction combat_action (or shim); target-only | Q4 — `riposte_timers` schema already correct; per-channel asyncio.Lock; outcome parser |
| COMBAT-11 | Riposte timer survives bot restart | Q5 — sweeper polls `list_pending`; ephemeral followup limitation forces public-message-with-permission-gating |
| HOST-01 | README prerequisites | Q9 — README/.env.example already cover oMLX + dm20 + Discord token; expand with troubleshooting |
| HOST-02 | `.env.example` documents env vars | Q9 — fix `MCP_RATE_LIMIT_MS` missing + `OMLX_CACHE_STRATEGY` orphan |
| HOST-03 | `bootstrap.py` pings oMLX + dm20 | Q7 — extend existing `persistence/bootstrap.py` OR add new `eldritch_dm/bootstrap.py` wrapper |
| HOST-04 | `run.py` validates env, pings oMLX, lists tools, launches | Q8 — new file at project root |
| HOST-05 | `pyproject.toml` pins all deps + scripts entry | Q9 — verify pins exist; add `[project.scripts]` per D-23 |
| HOST-06 | Test suite runnable via `pytest` | Q10 — existing 734-test infrastructure carries forward |
| HOST-07 | README covers macOS-primary, Linux best-effort | Q9 — call out `mlx-lm` Apple-Silicon-only constraint |
| HOST-08 | README documents launchd recipe | Q11 — `com.user.omlx` plist pattern at `~/Library/LaunchAgents/com.user.omlx.plist` is the parity model |
| OPS-01 | Resume drill — kill bot mid-combat, restart, confirm functional | Q5, Q12 — `setup_hook` already rehydrates persistent views (Phase 2); sweeper picks up live timers (Phase 5); CI integration test |

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Riposte eligibility check (class/subclass match) | Discord Bot (gameplay/reactions.py) | local persistence (extended channel_sessions OR new table) | dm20 doesn't expose subclass in get_character text; bot must persist subclass at ingest time |
| Reaction budget enforcement ("one reaction per round per PC") | Discord Bot (riposte_timers.consumed_in_round) | — | dm20 has no reaction model — see Q1 |
| Monster-turn driving (who attacks whom, applies combat_action) | Discord Bot (gameplay/monster_driver.py — NEW) | dm20 combat_action | Phase 4 documented but did not implement this — Phase 5 prerequisite |
| Miss-outcome detection from combat_action text | Discord Bot (gameplay/combat_outcome_parser.py — NEW) | — | dm20 returns formatted strings; bot parses |
| Timed-button rendering (8s deadline) | Discord Bot (bot/dynamic_items.py — extend RiposteButton) | Discord (channel message) | DynamicItem regex template already exists since Phase 2; deadline lives in DB row |
| Restart survival (sweeper) | Discord Bot (gameplay/riposte_sweeper.py — NEW) | local persistence (riposte_timers) | Bot lifecycle responsibility — setup_hook starts it |
| Bot lifecycle (start, oMLX ping, signal handling) | run.py at project root | bot/__main__.py | Self-hoster invokes `python run.py`; module entrypoint stays for `python -m eldritch_dm.bot` compatibility |
| Service supervision (auto-restart on crash) | launchd (macOS) / systemd (Linux best-effort) | run.py | OS-level concern; bot exits non-zero on fatal, supervisor restarts |
| Self-host docs (README walkthrough, troubleshooting) | README.md + docs/ | — | Documentation, not code |
| Environment audit (env vars consistency) | Phase 5 audit task + CONFIGURATION.md | .env.example | docs/CONFIGURATION.md already flagged two discrepancies |

## Standard Stack

No new packages for Phase 5 — every dep is already pinned by Phases 1-4.

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `discord.py` | `==2.7.1` | DynamicItem + View timeout + permission-gated buttons | [CITED: project CLAUDE.md], [CITED: discordpy.readthedocs.io/en/v2.7.1/] |
| `aiosqlite` | `>=0.20,<0.22` | riposte_timers writes via existing WriterQueue | [CITED: project CLAUDE.md] |
| `httpx` | `>=0.27,<0.29` | bootstrap.py oMLX + MCP tools pings | [CITED: project CLAUDE.md]; already used by `MCPClient` |
| `structlog` | `>=24.4,<26.0` | sweeper structured logs, bootstrap status reporting | [CITED: project CLAUDE.md] |
| `pydantic-settings` | (transitive) | `Settings()` validation at run.py startup | already in Phase 1 |

**Installation:** none — `pip install -e .[dev]` from Phase 1 covers it.

## Package Legitimacy Audit

Phase 5 introduces **zero new packages**. Section is informational only.

| Package | Registry | Disposition |
|---------|----------|-------------|
| _no new packages_ | _n/a_ | _n/a_ |

## Architecture Patterns

### System Architecture Diagram

```
                ┌──────────────────────────────────────────────────────┐
                │                  Discord (channel)                    │
                │  ┌────────────┐  ┌──────────────────────────────────┐│
                │  │ Combat     │  │ ⚔️ Riposte!  (8s deadline button) ││
                │  │ Embed      │  │   message_id = persistent row     ││
                │  │ (init+HP)  │  │   custom_id  = riposte:{tid}:{uid}││
                │  └─────▲──────┘  │   permission gate: target user    ││
                │        │ refresh └──────────┬───────────────────────┘│
                └────────┼────────────────────┼──────────────────────────┘
                         │                    │ click (within 8s) OR timeout
                         │                    ▼
        ┌────────────────┴────────────────────────────────────────────────┐
        │  CombatCog + PartyModeOrchestrator + RiposteCog (NEW)           │
        │                                                                 │
        │  Monster-turn path (NEW — Phase 5 prerequisite):                │
        │    next_turn → orchestrator detects current_actor is monster    │
        │      → MonsterDriver.drive() picks target, calls combat_action  │
        │      → outcome_parser detects "Miss." line                      │
        │      → if target is eligible PC AND target has reaction budget: │
        │           reactions.surface_riposte_button(target_id, ...)      │
        │                                                                 │
        │  Riposte click path:                                            │
        │    RiposteButton.callback:                                      │
        │      defer (ephemeral)                                          │
        │      load riposte_timers.get(timer_id)                          │
        │      gate: user_id == row.user_id  → else INVALID_ACTION        │
        │      gate: status == 'pending'    → else RIPOSTE_EXPIRED        │
        │      gate: deadline_ts > now      → else mark expired + warn    │
        │      per-channel asyncio.Lock around mutation:                  │
        │        combat_action(attacker=target_id, target=monster_uuid,   │
        │                      weapon_or_spell=weapon_used)               │
        │        mark_consumed                                            │
        │        delete riposte message (best-effort)                     │
        │        emit narration via party_resolve_action                  │
        │                                                                 │
        │  Sweeper (background asyncio.Task started in setup_hook):       │
        │    every min(next_deadline, 30s):                               │
        │      list_pending() (uses partial idx)                          │
        │      for t in pending where t.deadline_ts <= now:               │
        │        mark_expired(t.id)                                       │
        │        bot.http.delete_message(t.channel_id, t.message_id)      │
        │                                                                 │
        └──────┬──────────────────────────────────────────────────────────┘
               │ HTTP POST :8765/v1/mcp/execute (combat_action)
               ▼
        ┌────────────────────────────────────────────────────────────────┐
        │   oMLX :8765 — dm20 (single global storage, single Party srv) │
        │     • combat_action(attacker, target, ...) → text outcome      │
        │     • get_game_state → markdown text                           │
        │     • NO reaction tracking — bot is sole source of truth       │
        └────────────────────────────────────────────────────────────────┘

        Lifecycle / self-host:
        ┌────────────────────────────────────────────────────────────────┐
        │  launchd (com.shoemoney.eldritch-dm.plist)                     │
        │    KeepAlive=true; RunAtLoad=true                              │
        │    /usr/bin/env python /path/to/DiscordDM/run.py               │
        │      └─ run.py:                                                │
        │           Settings() validates env                             │
        │           bootstrap.ensure_schema(db_path)                     │
        │           bootstrap.preflight() (oMLX + MCP tools pings)       │
        │           EldritchBot + setup_hook                             │
        │           bot.run()  ← propagates exit code to launchd         │
        └────────────────────────────────────────────────────────────────┘
```

### Recommended Project Structure (additions)

```
src/eldritch_dm/
├── gameplay/
│   ├── reactions.py                  # NEW — eligibility + button surfacing (D-02)
│   ├── riposte_sweeper.py            # NEW — background expiry task (D-09)
│   ├── combat_outcome_parser.py      # NEW — parse combat_action text → hit|miss|critical
│   └── monster_driver.py             # NEW (Phase 5 prerequisite) — drives monster turns
├── bot/
│   └── dynamic_items.py              # EXTEND RiposteButton.callback (already a stub)
├── persistence/
│   └── riposte_timers_repo.py        # EXTEND: add list_for_channel, mark_cancelled,
│                                     #          consumed_in_round insertion
└── bootstrap.py                      # NEW package-root entry (wraps persistence.bootstrap
                                     #   + adds oMLX/MCP pings) — D-14
docs/
├── launchd.plist.example             # NEW — com.shoemoney.eldritch-dm parity (HOST-08)
├── eldritch-dm.service.example       # NEW — systemd unit (HOST-07 best-effort)
├── dm20-troubleshooting.md           # NEW (D-18)
└── character-ingest-formats.md       # NEW (D-18)
tests/
├── gameplay/
│   ├── test_reactions.py             # NEW — eligibility + surfacing
│   ├── test_riposte_sweeper.py       # NEW — sweeper expiry
│   ├── test_combat_outcome_parser.py # NEW — parse hit/miss/critical
│   └── test_monster_driver.py        # NEW (prerequisite)
└── integration/
    └── test_resume_drill.py          # NEW — OPS-01 deliverable
run.py                                # NEW at project root (D-16)
```

### Pattern 1: Combat outcome parser (Q3 → real implementation)

```python
# Source: dm20-protocol/main.py:1839-1873 (_format_combat_result)
# Outputs one of:
#   **CRITICAL HIT!** {attacker} strikes {target}!
#   **Hit!** {attacker} hits {target}.
#   **Natural 1!** {attacker} misses {target}.
#   **Miss.** {attacker} misses {target}.

import re
from enum import StrEnum

class AttackOutcome(StrEnum):
    HIT = "hit"
    CRITICAL = "critical"
    MISS = "miss"
    NATURAL_ONE = "natural_one"

_OUTCOME_RE = re.compile(
    r"^\*\*(?P<header>CRITICAL HIT!|Hit!|Natural 1!|Miss\.)\*\*",
    re.MULTILINE,
)

def parse_combat_outcome(raw: str) -> AttackOutcome | None:
    m = _OUTCOME_RE.search(raw)
    if not m:
        return None
    h = m.group("header")
    if h == "CRITICAL HIT!": return AttackOutcome.CRITICAL
    if h == "Hit!":          return AttackOutcome.HIT
    if h == "Natural 1!":    return AttackOutcome.NATURAL_ONE
    if h == "Miss.":         return AttackOutcome.MISS
    return None
```

**Test parity:** mirror the four outcome strings verbatim in unit tests. dm20's format strings are stable (hand-written in source); regex is the right tool for v1.

### Pattern 2: Riposte eligibility (Q2 — D-03 fork resolution)

dm20 does NOT model `has_reaction`. CONTEXT.md D-03 listed two sources of truth — research confirms only the second works:

```python
# Source: dm20 has no public reaction-budget API; bot tracks it via
#         riposte_timers.consumed_in_round (D-12 path).

ELIGIBLE_CLASS_SUBCLASSES: frozenset[tuple[str, str]] = frozenset({
    ("fighter", "battle master"),
    # NOTE: ("rogue", "swashbuckler") — RAW does NOT grant Riposte. Bot ships
    # without it for v1; document as homebrew opt-in for v2.
    # [CITED: dnd5e.wikidot.com/rogue:swashbuckler — Fancy Footwork + Panache,
    #         neither is a miss-and-counter reaction]
})

async def check_riposte_eligibility(
    *,
    channel_id: str,
    character_id: str,
    current_round: int,
    riposte_timers_repo: RiposteTimerRepo,
    character_subclass_lookup: Callable[[str], tuple[str, str] | None],
) -> RiposteEligibility | None:
    """Return RiposteEligibility if PC may riposte THIS round, else None.

    NOTE: character_subclass_lookup MUST come from a bot-side persisted source
    (channel_sessions.payload_json OR a dedicated `pc_classes` table populated
    at Phase 3 ingest), NOT from dm20__get_character (whose text output omits
    subclass per Q2).
    """
    class_sub = await character_subclass_lookup(character_id)
    if class_sub is None or class_sub not in ELIGIBLE_CLASS_SUBCLASSES:
        return None

    # Reaction budget: one reaction per round per PC
    pending_or_consumed_this_round = [
        t for t in await riposte_timers_repo.list_for_character(channel_id, character_id)
        if t.consumed_in_round == current_round
        or (t.status == "pending" and t.deadline_ts > datetime.utcnow())
    ]
    if pending_or_consumed_this_round:
        return None  # reaction already used or queued this round

    return RiposteEligibility(
        character_id=character_id,
        user_id=...,           # from channel_sessions character→user map
        primary_weapon=...,    # from persisted character info OR get_character parse
    )
```

**Action items for the plan:**
- Add `consumed_in_round INTEGER` column to `riposte_timers` (Wave 0 schema migration; idempotent ALTER TABLE under IF NOT EXISTS guard via a one-shot `ALTER TABLE ... ADD COLUMN` wrapped in `try/except OperationalError`).
- Add `list_for_character(channel_id, character_id)` method to `riposte_timers_repo.py`.
- Persist `(character_id → (class_name_lower, subclass_lower))` either in a new tiny `pc_classes` table OR in `channel_sessions.payload_json` (lean: new table; payload_json grows unwieldy). Recommend **new table** `pc_classes(channel_id, character_id, class_name, subclass)` with UNIQUE(channel_id, character_id).

### Pattern 3: Surfacing the timed button (Q4)

```python
# Source: 02-RESEARCH.md (DynamicItem rehydration) + dynamic_items.py:1157-1212
# (existing RiposteButton stub) + discord.py 2.7 docs.

async def surface_riposte_button(
    *,
    interaction: discord.Interaction | None,  # may be None on monster-turn surface
    channel: discord.TextChannel,
    eligibility: RiposteEligibility,
    monster_uuid: str,
    repo: RiposteTimerRepo,
    ttl_seconds: int,
    bot_log: BoundLogger,
) -> int:
    """Post the public-but-permission-gated Riposte button and persist the timer row.

    Returns the new timer_id.

    DESIGN NOTE (Q5): we use a public message, NOT ephemeral. Ephemeral followups
    die when the originating interaction expires (15 min) AND cannot be re-edited
    from a fresh bot process — they break restart-survival (COMBAT-11). Public
    message with permission gating in the callback is the only way to honor
    OPS-01.
    """
    deadline = datetime.utcnow() + timedelta(seconds=ttl_seconds)

    # Insert the row FIRST so the timer_id is available for the custom_id
    row = await repo.insert(RiposteTimer(
        channel_id=str(channel.id),
        character_id=eligibility.character_id,
        user_id=str(eligibility.user_id),
        monster_uuid=monster_uuid,
        weapon_used=eligibility.primary_weapon,
        message_id="",                            # filled in after channel.send
        custom_id="",                             # filled in after channel.send
        deadline_ts=deadline,
        status="pending",
    ))

    custom_id = f"riposte:{row.id}:{eligibility.user_id}"
    view = discord.ui.View(timeout=None)         # persistent — sweeper owns timeout
    view.add_item(RiposteButton(timer_id=row.id, user_id=eligibility.user_id))

    msg = await channel.send(
        content=(
            f"<@{eligibility.user_id}> — a monster missed you! "
            f"You have {ttl_seconds}s to counter-strike."
        ),
        view=view,
        allowed_mentions=discord.AllowedMentions(users=True),
    )

    await repo.update_message_ref(row.id, message_id=str(msg.id), custom_id=custom_id)
    bot_log.info("riposte_button_surfaced",
                 timer_id=row.id, deadline_ts=deadline.isoformat())
    return row.id
```

**Why a public message and not ephemeral:**
1. Ephemeral followups expire when their parent interaction expires (15 min) AND **cannot be rebuilt by a different bot process** after restart [CITED: discordpy.readthedocs.io/en/stable/interactions/api.html] — kills COMBAT-11.
2. A public message with permission gating in the callback achieves the same UX: anyone can *see* the button, only the target user can *use* it (callback first-check is `interaction.user.id != row.user_id` → ephemeral `INVALID_ACTION` warning).
3. The visible button briefly broadcasts game state ("Aria has a riposte open") which can be a feature, not a bug, for the table.

**Anti-pattern (rejected):** ephemeral followup + assume it'll restore on restart. It won't.

### Pattern 4: Restart-survival sweeper (Q5)

```python
# Source: D-09 sweeper pseudocode in CONTEXT.md, refined.

import asyncio
from datetime import datetime

class RiposteSweeper:
    def __init__(self, repo: RiposteTimerRepo, bot: discord.Client,
                 default_sleep_s: float = 30.0,
                 min_sleep_s: float = 0.1) -> None:
        self._repo = repo
        self._bot = bot
        self._default_sleep = default_sleep_s
        self._min_sleep = min_sleep_s
        self._stop = asyncio.Event()
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        self._task = asyncio.create_task(self._run(), name="RiposteSweeper._run")

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            with contextlib.suppress(asyncio.CancelledError):
                await self._task

    async def _run(self) -> None:
        while not self._stop.is_set():
            try:
                pending = await self._repo.list_pending()
                now = datetime.utcnow()
                next_deadline = None
                for t in pending:
                    if t.deadline_ts <= now:
                        await self._repo.mark_expired(t.id)
                        # Best-effort delete the public message
                        try:
                            channel = self._bot.get_channel(int(t.channel_id)) \
                                      or await self._bot.fetch_channel(int(t.channel_id))
                            msg = await channel.fetch_message(int(t.message_id))
                            await msg.delete()
                        except (discord.NotFound, discord.Forbidden,
                                discord.HTTPException, ValueError):
                            pass
                    else:
                        if next_deadline is None or t.deadline_ts < next_deadline:
                            next_deadline = t.deadline_ts

                if next_deadline is not None:
                    sleep_s = (next_deadline - now).total_seconds()
                else:
                    sleep_s = self._default_sleep
                sleep_s = max(self._min_sleep, min(sleep_s, self._default_sleep))

                try:
                    await asyncio.wait_for(self._stop.wait(), timeout=sleep_s)
                except asyncio.TimeoutError:
                    pass  # normal wake-up, continue loop
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("riposte_sweeper_iteration_error")
                await asyncio.sleep(1.0)
```

**Wake-up cadence rationale:** `min(next_deadline, 30s)` (D-09) is correct. With 8s TTLs that's rarely longer than a few seconds in practice; the 30s ceiling exists so that an empty queue doesn't busy-loop and so a freshly inserted timer with `deadline > 30s` (won't happen with the current TTL, but defensive) gets re-examined within 30s.

**On restart:** `setup_hook` starts the sweeper *after* `bootstrap.ensure_schema` and *after* persistence init. Any rows from a prior process whose deadlines are still in the future are picked up on the next iteration (≤30s) — the user gets a button for the remaining TTL slice. Expired rows are marked + cleaned in the same pass.

### Pattern 5: Bootstrap preflight (HOST-03, D-14)

```python
# Source: extend persistence/bootstrap.py + add a new top-level eldritch_dm/bootstrap.py
# that wraps it.

import sys
import httpx
from eldritch_dm.config import get_settings
from eldritch_dm.logging import configure_logging, get_logger
from eldritch_dm.persistence.bootstrap import bootstrap as ensure_schema

log = get_logger(__name__)

EXIT_OK = 0
EXIT_OMLX_UNREACHABLE = 1
EXIT_DM20_NOT_LOADED = 2
EXIT_SCHEMA_FAIL = 3


async def preflight() -> int:
    settings = get_settings()

    # 1. Local schema
    try:
        await ensure_schema(settings.eldritch_db_path)
        log.info("preflight_schema_ok", path=settings.eldritch_db_path)
    except Exception as exc:
        log.error("preflight_schema_failed", error=str(exc))
        return EXIT_SCHEMA_FAIL

    # 2. oMLX /v1/models
    async with httpx.AsyncClient(timeout=httpx.Timeout(5.0, connect=2.0)) as client:
        try:
            r = await client.get(f"{settings.omlx_endpoint}/models")
            r.raise_for_status()
            models = r.json().get("data", []) if r.headers.get("content-type", "").startswith("application/json") else []
            log.info("preflight_omlx_ok", model_count=len(models),
                     loaded=[m.get("id") for m in models])
            if settings.omlx_model not in {m.get("id") for m in models}:
                log.warning("preflight_omlx_model_missing", expected=settings.omlx_model)
        except Exception as exc:
            log.error("preflight_omlx_unreachable", endpoint=str(settings.omlx_endpoint),
                      error=str(exc))
            print(f"oMLX unreachable at {settings.omlx_endpoint}. Is `omlx serve` running?",
                  file=sys.stderr)
            return EXIT_OMLX_UNREACHABLE

        # 3. MCP tools list
        try:
            r = await client.get(str(settings.mcp_tools_url))
            r.raise_for_status()
            tools = r.json()
            dm20_tools = [t for t in tools if isinstance(t, dict) and t.get("name", "").startswith("dm20__")]
            log.info("preflight_mcp_ok", total_tools=len(tools), dm20_tools=len(dm20_tools))
            if len(dm20_tools) == 0:
                print("dm20 MCP tools not exposed. Check your oMLX --mcp-config.",
                      file=sys.stderr)
                return EXIT_DM20_NOT_LOADED
        except Exception as exc:
            log.error("preflight_mcp_tools_failed", error=str(exc))
            return EXIT_DM20_NOT_LOADED

    print("Ready to run.", file=sys.stderr)
    return EXIT_OK


def main() -> None:
    configure_logging(level="INFO", fmt="console")
    code = asyncio.run(preflight())
    sys.exit(code)


if __name__ == "__main__":
    main()
```

### Pattern 6: run.py entrypoint (HOST-04, D-15, D-16)

```python
# Source: D-15 + bot/__main__.py:main() inspection.
"""Top-level EldritchDM entrypoint for self-hosters.

Usage:
    python run.py            # interactive (LOG_FORMAT=console)
    python run.py            # launchd-supervised (LOG_FORMAT=json via env)

The module entrypoint `python -m eldritch_dm.bot` remains valid for backwards
compat with Phase 1-4 muscle memory. run.py adds:
  - bootstrap.preflight() before launching the bot
  - graceful SIGTERM handling (delegates to OPS-04 shutdown chain)
  - exit-code propagation to the supervisor (launchd/systemd)
"""
from __future__ import annotations

import asyncio
import signal
import sys


def main() -> int:
    # Inline imports so `python run.py --help` (if we add it) doesn't pay startup cost.
    from eldritch_dm import bootstrap as preflight_mod
    from eldritch_dm.bot.bot import EldritchBot
    from eldritch_dm.config import Settings
    from eldritch_dm.logging import configure_logging, get_logger

    settings = Settings()                                   # may raise ValidationError
    configure_logging(level=settings.log_level,
                      fmt=settings.log_format,
                      log_file=settings.log_file)
    log = get_logger("eldritch_dm.run")

    # Preflight — short-circuit on infrastructure failures, unless override.
    if not _allow_offline_start():
        code = asyncio.run(preflight_mod.preflight())
        if code != preflight_mod.EXIT_OK:
            log.error("run_preflight_failed", exit_code=code)
            return code

    bot = EldritchBot(settings)

    # SIGTERM-as-KeyboardInterrupt so launchd's SIGTERM exits cleanly.
    def _on_sigterm(signum: int, frame) -> None:
        log.info("run_sigterm_received", signum=signum)
        # bot.run installs its own signal handlers internally; raising
        # KeyboardInterrupt here would conflict. Cleanest path is to let
        # discord.py shut itself down on SIGTERM (OPS-04 already wires this).
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, _on_sigterm)

    try:
        bot.run(settings.discord_token, log_handler=None)
        return 0
    except KeyboardInterrupt:
        log.info("run_shutdown_clean")
        return 0
    except Exception:
        log.exception("run_fatal")
        return 2


def _allow_offline_start() -> bool:
    import os
    return os.environ.get("ELDRITCH_ALLOW_OFFLINE_START", "").lower() in {"1", "true", "yes"}


if __name__ == "__main__":
    sys.exit(main())
```

### Pattern 7: launchd plist (HOST-08, D-Discretion)

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.shoemoney.eldritch-dm</string>
  <key>ProgramArguments</key>
  <array>
    <string>/usr/bin/env</string>
    <string>python3</string>
    <string>/Users/shoemoney/Services/DiscordDM/run.py</string>
  </array>
  <key>WorkingDirectory</key>
  <string>/Users/shoemoney/Services/DiscordDM</string>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key>
  <dict>
    <key>SuccessfulExit</key><false/>   <!-- restart only on non-zero exit -->
    <key>Crashed</key><true/>
  </dict>
  <key>ThrottleInterval</key><integer>10</integer>
  <key>StandardOutPath</key>
  <string>/Users/shoemoney/Services/DiscordDM/eldritch-dm.log</string>
  <key>StandardErrorPath</key>
  <string>/Users/shoemoney/Services/DiscordDM/eldritch-dm.err</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PATH</key><string>/opt/homebrew/bin:/usr/bin:/bin</string>
    <key>LOG_FORMAT</key><string>json</string>
    <!-- DISCORD_TOKEN and other secrets MUST come from a runtime-loaded
         .env file via run.py, NOT from this plist (which is world-readable
         by default). The user's existing com.user.omlx plist does NOT
         contain secrets either. -->
  </dict>
</dict>
</plist>
```

**Parity with `com.user.omlx`:** the user's existing plist (`~/Library/LaunchAgents/com.user.omlx.plist`) uses `KeepAlive=true` (always restart). Phase 5 deliberately uses **dict-form KeepAlive with SuccessfulExit=false** — this means "restart on crash or non-zero exit, but don't restart if the user explicitly stops the bot with `launchctl unload`". This is friendlier for self-hosters debugging startup failures (a bad DISCORD_TOKEN won't infinite-loop). Discussed in the plist comment so operators can flip to plain `KeepAlive=true` if they want unconditional supervision.

**ThrottleInterval=10:** if the bot keeps crashing, launchd waits 10s between restart attempts. Avoids the rapid-restart storm you'd otherwise see when DISCORD_TOKEN is invalid.

### Anti-Patterns to Avoid

- **Don't use `View(timeout=8.0)` with `on_timeout` for the 8s deadline.** discord.py's per-View timeout only fires while the bot process is alive. After a restart, in-process Views are gone — `on_timeout` will not fire. **The sweeper is the authoritative timer.** The View timeout, if set at all, should be `None` (persistent). The 8s deadline is enforced by (a) the sweeper marking expired rows, and (b) the callback's `deadline_ts > now()` check rejecting late clicks.
- **Don't post the Riposte button as ephemeral followup.** Ephemeral messages cannot be re-edited after the originating interaction expires (15 min) and definitely cannot be re-edited from a fresh bot process. Use a regular channel message with permission gating in the callback.
- **Don't trust dm20 to enforce reaction-per-round.** dm20 has no reaction model. Bot tracks `consumed_in_round` in `riposte_timers`.
- **Don't include `("rogue", "swashbuckler")` in `ELIGIBLE_CLASS_SUBCLASSES` without a tag.** Swashbuckler does not have Riposte by RAW. If the user wants it, label it homebrew and document it.
- **Don't add subclass detection by parsing `dm20__get_character` output text.** The rendered string omits subclass (`main.py:535`). Persist subclass at ingest time instead.
- **Don't store DISCORD_TOKEN in the launchd plist.** plist files are world-readable on macOS by default; use a `.env` file loaded by `Settings` instead.
- **Don't extend Phase 4's `_maybe_surface_riposte` seam blindly.** It fires on PC-attacks-monster-and-misses, which is the wrong RAW trigger. Either repurpose it explicitly (document as homebrew "any miss surfaces a riposte if eligible") OR add a parallel seam on the monster-turn driver path.
- **Don't poll oMLX inside the sweeper.** The sweeper is purely local-DB / discord HTTP. oMLX downtime should not delay timer expiry.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| `riposte_timers` schema or repo | Custom timer module | Existing `RiposteTimerRepo` (`riposte_timers_repo.py`) | Phase 1 already shipped CRUD + partial index |
| DynamicItem boilerplate for the Riposte button | New custom_id parser | Existing `RiposteButton` (`dynamic_items.py:1157-1212`) | Phase 2 already shipped the stub with regex + from_custom_id |
| Process supervision | systemd-in-python via subprocess | launchd plist (macOS) / systemd unit (Linux) | OS owns this; bot just exits non-zero on fatal |
| Discord rate-limit handling on the riposte channel.send | tenacity wrapper | discord.py's `HTTPClient` built-in rate limiter | Phase 4 Pitfall 5 — trust discord.py, don't double-wrap |
| Env validation | Bespoke check at startup | `Settings()` pydantic-settings model — raises ValidationError | Phase 1 already wired |
| Schema migrations for the `consumed_in_round` column | full migration framework | One-shot `ALTER TABLE ... ADD COLUMN consumed_in_round INTEGER` guarded by `try/except OperationalError` in `bootstrap.py` | SQLite tolerates idempotent ALTER; no Alembic for a 4-table app |
| OCR / character ingest | n/a — already done | Phase 3 deliverable | already shipped |
| 5e rules lookups | hardcoded class table | `dm20__validate_character_rules` OR dm20's rulebook | dm20 owns SRD |
| Health-check loop | new background task | Phase 1's `HealthCheck` (`mcp/health.py`) keeps running during Phase 5 | already shipped |

**Key insight:** Phase 5 is **mostly orchestration glue**. Every primitive (DB schema, DynamicItem class, repo CRUD, MCP wrappers, embed coalescer, async lock registry) exists from Phases 1-4. The two genuinely new pieces are (a) the sweeper and (b) the bootstrap preflight — both small. The biggest engineering risk is the monster-turn driver (research finding #6), which Phase 4 deferred and Phase 5 needs as a prerequisite.

## Runtime State Inventory

Phase 5 introduces new background-task lifecycle (sweeper) and new bootstrap behavior. Not a rename/refactor phase, but the resume drill (OPS-01) makes runtime state extremely relevant.

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | `riposte_timers` rows (status `pending|consumed|expired|cancelled`) persist across bot restart; `channel_sessions` and `persistent_views` rows already restart-safe (Phase 2). | Sweeper drains expired on startup; pending future-deadline rows light up Discord buttons via DynamicItem rehydration |
| Live service config | dm20 has no per-session state for reactions (research finding #1). All reaction budget lives in our SQLite. | None — already covered |
| OS-registered state | NEW: launchd plist `com.shoemoney.eldritch-dm` at `~/Library/LaunchAgents/`. Once installed, `launchctl bootstrap`/`bootout` controls lifecycle. Removing the bot does NOT auto-remove the plist. | Document install + uninstall in README |
| Secrets/env vars | New optional env: `ELDRITCH_ALLOW_OFFLINE_START` (D-15 fallback). Existing: `RIPOSTE_TTL_SECONDS` (already in `.env.example`). Existing discrepancies: `MCP_RATE_LIMIT_MS` absent from `.env.example` (Q9); `OMLX_CACHE_STRATEGY` orphan in `.env.example` not consumed by `Settings` (Q9). | Add the new var; fix both discrepancies |
| Build artifacts | None new — installed package metadata via `[project.scripts]` adds an `eldritch-dm` CLI entry but no new build outputs | `pip install -e .` after pyproject.toml change refreshes the script |
| Local SQLite | NEW: `riposte_timers.consumed_in_round INTEGER` column (research finding #4 mandates the shim). `pc_classes` table OR `channel_sessions.payload_json` extension to persist subclass at ingest. | Plan Wave 0: idempotent `ALTER TABLE` + (if new table) CREATE TABLE IF NOT EXISTS |
| In-process state | NEW background task: `RiposteSweeper._task` lives on `bot.riposte_sweeper`; cancelled by `bot.close()` via OPS-04 graceful shutdown chain. | `setup_hook` starts; `close` cancels |

**The canonical question (resume drill):** *After killing the bot mid-combat, what state lives where?*
- Combat embed message id → `persistent_views` row → re-renderable by `setup_hook` rehydration (Phase 2 — verified)
- Active turn order, HP, conditions → dm20 storage (we re-fetch via `get_game_state`)
- Pending riposte timer → `riposte_timers` row with `status='pending'` → sweeper picks up + rebuilds the public message via DynamicItem registry
- Reaction budget for this round → `riposte_timers.consumed_in_round` rows (NEW shim) → reaction-eligibility check honors them
- Channel session state (LOBBY / EXPLORATION / COMBAT) → `channel_sessions.state` → setup_hook re-attaches cogs accordingly

If any of those is missing on restart, OPS-01 fails. Phase 5 test must assert each one explicitly.

## Common Pitfalls

### Pitfall 1: 8-second timer measured from button-render time, not monster-miss-resolution time

**What goes wrong:** The miss is resolved in `combat_action`; we then call our reaction-eligibility check, possibly hold an asyncio.Lock briefly, then channel.send the public message. That can take 100-500ms. If the deadline_ts is computed BEFORE channel.send the user only sees ~7.5s of clickable time; if AFTER, they see a full 8s.
**Why it happens:** Async Python doesn't make timing transparent.
**How to avoid:** **Compute `deadline_ts = now() + RIPOSTE_TTL_SECONDS` AFTER `channel.send` succeeds, then `repo.update_message_ref(deadline_ts=...)` to lock it in.** Document this explicitly so the test can assert the deadline is in the future relative to the post-send timestamp.
**Warning signs:** Riposte test "click at T+7.9s succeeds" fails because deadline_ts ended up at T+7.5.

### Pitfall 2: Multi-monster overlap (two monsters miss the same PC in the same round)

**What goes wrong:** Monster A misses PC, we surface a button. Monster B also misses the same PC before the player clicks. We now have either two buttons stacked (UI mess) OR a stale row that contradicts the reaction budget.
**Why it happens:** 5e Battle Master has one reaction per round. The eligibility check already covers this (`Pattern 2` — check for any pending row in current round). But the SURFACE call has to refuse to insert if a pending row exists.
**How to avoid:** Eligibility check is the single source of truth. If `check_riposte_eligibility` returns None because a pending row already exists, `surface_riposte_button` is never called. **Add an integration test that simulates two consecutive monster misses in the same round and asserts exactly one button surfaces.**
**Warning signs:** Players report "I see two Riposte buttons" or "Riposte fired but reaction budget says I have zero left."

### Pitfall 3: Sweeper deletes a Discord message that already had its click in flight

**What goes wrong:** Click arrives at T+7.99s; defer succeeds; meanwhile the sweeper wakes at T+8.0s, sees `deadline_ts <= now`, marks expired, deletes the message. Click callback then loads the row, sees `status='expired'`, sends `RIPOSTE_EXPIRED` warning to the user — even though they clicked in time.
**Why it happens:** Race between defer-success and sweeper-expiry-marking.
**How to avoid:** The callback MUST hold the per-channel asyncio.Lock around the **read-then-mark-consumed** sequence. The sweeper also acquires that lock around its mark-expired call. Both serialize through the lock; whichever wins, the other sees the updated status and skips. **Add `riposte:{channel_id}` to the lock registry namespace.**
**Warning signs:** "I clicked in time but it said expired" complaint; flaky test where the click-at-deadline outcome is non-deterministic.

### Pitfall 4: Restart-survival is only as good as the discord.Channel reachability

**What goes wrong:** Bot restarts. Sweeper loads pending rows. For each row whose deadline is still in the future, the DynamicItem registry routes a fresh click to the right callback (Phase 2 guarantees this) — BUT the View attached to the original message no longer exists in this process. The button is rendered server-side from Discord's persisted state.
**Why it happens:** This is actually fine! `add_dynamic_items(*DYNAMIC_ITEM_CLASSES)` in `setup_hook` (Phase 2) makes the click route correctly. Discord owns the rendering. **The risk is in the OTHER direction**: if `channel.fetch_message(t.message_id)` fails (channel deleted, bot kicked, message manually deleted), the sweeper logs and moves on — but the player STILL sees the button.
**How to avoid:** Idempotency. The callback already checks `status == 'pending'` and `deadline_ts > now()`. If the row is gone (cascade-deleted with the channel) the callback receives `riposte_timers.get(timer_id) → None` and replies `RIPOSTE_EXPIRED`. No additional handling needed.
**Warning signs:** None — this is the happy path post-restart.

### Pitfall 5: Subclass-on-ingest sync gap

**What goes wrong:** Phase 3 ingest already calls `dm20__create_character` with the parsed character. We propose persisting `(class_name, subclass)` locally on the bot at the same moment — BUT what if a user uploads a character that's later level-up'd through dm20 to add a subclass? The local table is stale.
**Why it happens:** Two sources of truth (dm20 character + bot pc_classes table) drift.
**How to avoid:** **On every riposte-eligibility check, re-validate the subclass via the most-current source.** Option A: call `dm20__get_character` and parse its `Level {N} {race} {class}` line + supplement with `dm20__validate_character_rules` (which IS rulebook-aware and DOES surface subclass via its `Validation Report`). Option B: at PC turn start, re-sync `pc_classes`. **Lean Option A** — re-validate at eligibility-check time. It's a single MCP call we already make routinely.
**Warning signs:** "I leveled up to Battle Master mid-session and Riposte never fired" complaint.

### Pitfall 6: bootstrap preflight blocks until oMLX wakes up

**What goes wrong:** User installs the launchd plist that launches the bot at login. The bot starts before oMLX. preflight returns EXIT_OMLX_UNREACHABLE, the bot exits 1, launchd waits ThrottleInterval (10s), restarts. Repeat until oMLX is up.
**Why it happens:** Service start-order dependence; macOS launchd has no built-in "wait for service X" mechanism.
**How to avoid:** Document the `ELDRITCH_ALLOW_OFFLINE_START=1` escape hatch in README — when set, run.py skips preflight and the bot starts immediately. The `OPS-02` circuit breaker (Phase 1) then renders "DM is offline" until oMLX reaches steady state. **Recommend** setting this in the launchd plist's EnvironmentVariables for production self-hosters; document the tradeoff (slower visibility into actually-broken oMLX configs).
**Warning signs:** Bot logs show "preflight_omlx_unreachable" repeatedly at boot; launchd Crashed counter increments.

### Pitfall 7: `python -m eldritch_dm.bootstrap` vs `python -m eldritch_dm.persistence.bootstrap`

**What goes wrong:** README and CONFIGURATION.md instruct users to run `python -m eldritch_dm.bootstrap`. The actual module today is `eldritch_dm.persistence.bootstrap` (`src/eldritch_dm/persistence/bootstrap.py`). Phase 5 needs to either (a) add a top-level `src/eldritch_dm/bootstrap.py` that wraps the persistence one AND adds the oMLX/MCP preflight, OR (b) update all docs to the dotted path. **Recommend (a)** — matches user expectation, and the preflight code (Pattern 5) naturally lives at the package root.
**Why it happens:** Code organization decision drifted from documentation.
**How to avoid:** Plan adds `src/eldritch_dm/bootstrap.py` that re-exports `persistence.bootstrap.bootstrap as ensure_schema` plus exports `preflight()` and `main()` per Pattern 5.
**Warning signs:** `ModuleNotFoundError: No module named 'eldritch_dm.bootstrap'` when a self-hoster follows the README.

### Pitfall 8: Self-host PyMuPDF AGPL footgun

**What goes wrong:** Phase 3's INGEST-04 ships PyMuPDF as primary PDF parser. PyMuPDF is AGPL. If a self-hoster takes EldritchDM, modifies it, deploys it as a hosted service, and refuses to share modifications, they're in license violation.
**Why it happens:** Default behavior favored speed/accuracy over license simplicity.
**How to avoid:** README + docs/ should call out the AGPL boundary explicitly: "PyMuPDF is AGPL — fine for self-hosting (the typical use case) but if you fork-and-close, swap to pypdf via `EXTRA_PDF_LIB=pypdf`." Phase 5 plan doesn't need to refactor — just document. (CLAUDE.md "Version Compatibility Notes" already flags this.)
**Warning signs:** Future GitHub issue: "I want to white-label this for my company; is PyMuPDF a problem?"

## Code Examples

(See Patterns 1-7 above — all code examples are inline with their context.)

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Custom timer threads for D&D reactions | Background asyncio.Task + DB-backed deadline (sweeper pattern) | Standard since asyncio 3.4 (2014); the DB-backed twist comes from restart-survival needs | Survives process restart — critical for self-hosted bots |
| Ephemeral followups for time-limited interactions | Public messages with permission gating in callback | discord.py 2.4+ DynamicItem API (2024) | Survives bot restart; predictable visibility |
| 5/5s per-channel rate limit guesswork | Trust discord.py's built-in HTTPClient rate limiter | discord.py 2.0+ (2022) | One less hand-rolled subsystem |
| `pip install + python main.py` | `pip install -e .` + `python run.py` + launchd | uv + pyproject.toml + macOS supervision standardized 2024-25 | Self-hosters get auto-restart + clean logs without docker |

**Deprecated/outdated:**
- Phase 4's plan to use `("rogue", "swashbuckler")` for Riposte eligibility: incorrect by 5e RAW; either remove or flag homebrew.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `riposte_timers.consumed_in_round` is the right shape for round-scoping the reaction budget — vs. e.g. expiring rows on every `next_turn` | Pattern 2 / D-12 | Bot could over- or under-restrict riposte (one per round vs one per turn vs none) |
| A2 | A user-mentioned public message with permission gating is acceptable UX (not "spammy") | Pattern 3 | Players hate the broadcast → v2 has to swap to a per-user DM, more complexity |
| A3 | Re-validating subclass via `dm20__validate_character_rules` on every eligibility check is cheap enough — under ~50ms | Pitfall 5 | If validate is slow, hot-path latency becomes a problem; mitigation: cache for the duration of the round |
| A4 | launchd `KeepAlive` dict form with `SuccessfulExit=false` is the right default for self-hosters | Pattern 7 | Operators expect "always restart" semantics; we deviate. Counter-mitigated by README documentation. |
| A5 | The user's "ShoeGPT is the only model loaded" memory means we should pin `OMLX_MODEL=ShoeGPT` checks at preflight, not allow free-form models | Pattern 5 | Wrong if user adds a second model intentionally; preflight just WARNs, doesn't exit, so this is soft |
| A6 | `ELDRITCH_ALLOW_OFFLINE_START` is the right escape-hatch env name | Pattern 6 / D-15 | Naming-bikeshed only |
| A7 | The Phase 4 `_maybe_surface_riposte` seam should be **deleted or repurposed** in Phase 5 rather than extended | Q6 + Recommendations | If we extend it, we ship a homebrew "PC misses → PC gets reaction" rule that contradicts 5e — confuses players |
| A8 | A new tiny `pc_classes` table is the right place to persist subclass at ingest (vs growing `channel_sessions.payload_json`) | Pattern 2 | If payload_json approach was preferred, we add a small migration cost; not a real risk |
| A9 | dm20's text format for `combat_action` (verbatim "**Miss.** {a} misses {t}.") is stable enough to regex against | Pattern 1 | If dm20 ships a format change, our parser breaks silently — mitigation: integration test that hits the real dm20 |

## Open Questions

> ⚠️ The planner should resolve Q1 and Q2 before writing Plan 01. Q3 is a known-unknown the plan can document and defer.

1. **Should the Phase 4 `_maybe_surface_riposte` seam in `AttackButton` be deleted or repurposed?**
   - What we know: It fires on the wrong attack path (PC misses monster, not monster misses PC). It's a no-op today.
   - What's unclear: Whether the Phase 4 author intended the seam to also support a homebrew "PC misses → opportunity for *another* PC reaction" pattern (e.g., bardic inspiration redirect).
   - Recommendation: **DELETE** the seam. Phase 5 adds the correct trigger on the monster-turn driver path. Repurposing it for a homebrew rule mid-Phase 5 adds scope without value.

2. **Is monster-turn driving in scope for Phase 5, or does Phase 5 require a Phase 4.5 mini-phase first?**
   - What we know: 04-RESEARCH.md documented `_drive_current_turn` (Pattern 3 there) as a recommended next step but didn't ship it. Phase 4's `PartyModeOrchestrator` polls player actions; monster turns are stalled until a human in the channel does something.
   - What's unclear: How much complexity hides in "pick target via Claudmaster" — the simplest version (random target) ships in <100 LOC; the Claudmaster-driven version is days of work and requires Claudmaster session-state plumbing this phase has not budgeted.
   - Recommendation: **Plan 01 ships the simplest monster driver: deterministic "random PC target" + `combat_action(action='attack')`.** This satisfies COMBAT-09's trigger condition. Smart targeting is a v2 enhancement (REACT-* family).

3. **Should `ELIGIBLE_CLASS_SUBCLASSES` ship without Swashbuckler, or with a "homebrew-tagged" Swashbuckler entry?**
   - What we know: RAW Swashbuckler does not have Riposte. CONTEXT.md D-04 lists it; that decision is wrong by-the-book.
   - What's unclear: Whether Jeremy/the user wants Swashbuckler-as-homebrew for v1 (some tables play it that way) or strict RAW.
   - Recommendation: **Ship strict RAW for v1** (Battle Master only). Add a single TODO comment in `reactions.py` pointing to a v2 task "make eligibility table configurable via YAML so homebrewers can add Swashbuckler / Brute / etc." Document the decision in the plan + README "Known Limitations" section.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| `oMLX :8765/v1/models` | preflight + health-check | ✓ (launchd `com.user.omlx`) | — | `ELDRITCH_ALLOW_OFFLINE_START=1` skips preflight |
| `dm20` MCP tools at `:8765/v1/mcp/tools` | preflight + every MCP call | ✓ (mounted in oMLX) | — | None — circuit breaker handles runtime loss |
| `~/Library/LaunchAgents/` writable | launchd install (HOST-08) | ✓ (standard macOS user agent dir) | — | Linux uses systemd unit at `~/.config/systemd/user/` |
| `discord.py 2.7.1` | Persistent Views | ✓ | 2.7.1 | None |
| `aiosqlite >=0.20` | repo writes | ✓ | already installed | None |
| `Settings.riposte_ttl_seconds` | timer creation | ✓ | 8 default | Hard-coded 8 in code if env unset (already wired) |
| Python 3.11+ | language features | ✓ | 3.11+ enforced via `requires-python` | None |

**Missing dependencies with no fallback:** none — Phases 1-4 delivered everything Phase 5 composes from.

**Missing dependencies with fallback:**
- Linux self-hosters: use systemd unit instead of launchd plist (best-effort per HOST-07).

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest + pytest-asyncio (configured Phase 1; 734 tests green at Phase 4 close) |
| Config file | `pyproject.toml` + `tests/conftest.py` |
| Quick run command | `pytest tests/gameplay/ tests/integration/test_resume_drill.py -x --no-header -q` |
| Full suite command | `pytest` |
| Phase gate | All existing 734 tests + new Phase 5 tests green before `/gsd:verify-work` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| COMBAT-09 | Eligibility check for Battle Master with reaction available | unit | `pytest tests/gameplay/test_reactions.py::test_battle_master_eligible_when_unconsumed -x` | ❌ Wave 0 |
| COMBAT-09 | Eligibility rejects non-eligible class | unit | `pytest tests/gameplay/test_reactions.py::test_wizard_not_eligible -x` | ❌ Wave 0 |
| COMBAT-09 | Eligibility rejects when reaction already consumed this round | unit | `pytest tests/gameplay/test_reactions.py::test_reaction_budget_exhausted -x` | ❌ Wave 0 |
| COMBAT-09 | Monster-driver triggers eligibility check on monster miss | integration | `pytest tests/gameplay/test_monster_driver.py::test_miss_surfaces_riposte -x` | ❌ Wave 0 |
| COMBAT-09 | combat_outcome_parser detects "Miss." vs "Hit!" vs "CRITICAL HIT!" | unit | `pytest tests/gameplay/test_combat_outcome_parser.py -x` | ❌ Wave 0 |
| COMBAT-10 | RiposteButton callback rejects non-target user | unit | `pytest tests/gameplay/test_riposte_callback.py::test_wrong_user_rejected -x` | ❌ Wave 0 |
| COMBAT-10 | RiposteButton callback rejects after deadline | unit | `pytest tests/gameplay/test_riposte_callback.py::test_late_click_rejected -x` | ❌ Wave 0 |
| COMBAT-10 | Successful click calls combat_action with reaction semantics | unit | `pytest tests/gameplay/test_riposte_callback.py::test_click_dispatches_combat_action -x` | ❌ Wave 0 |
| COMBAT-10 | Click marks consumed_in_round | unit | `pytest tests/gameplay/test_riposte_callback.py::test_click_marks_consumed -x` | ❌ Wave 0 |
| COMBAT-11 | Sweeper marks expired rows past deadline | unit | `pytest tests/gameplay/test_riposte_sweeper.py::test_expiry_marks_row -x` | ❌ Wave 0 |
| COMBAT-11 | Sweeper deletes Discord message on expiry (best-effort) | unit | `pytest tests/gameplay/test_riposte_sweeper.py::test_expiry_deletes_message -x` | ❌ Wave 0 |
| COMBAT-11 | Sweeper picks up pending rows on bot restart | integration | `pytest tests/integration/test_resume_drill.py::test_pending_riposte_survives_restart -x` | ❌ Wave 0 |
| HOST-03 | Preflight exits 0 when all green | unit | `pytest tests/test_bootstrap_preflight.py::test_exit_ok_on_full_health -x` | ❌ Wave 0 |
| HOST-03 | Preflight exits 1 on oMLX unreachable | unit | `pytest tests/test_bootstrap_preflight.py::test_exit_1_omlx_down -x` | ❌ Wave 0 |
| HOST-03 | Preflight exits 2 on dm20 not loaded | unit | `pytest tests/test_bootstrap_preflight.py::test_exit_2_dm20_missing -x` | ❌ Wave 0 |
| HOST-04 | run.py executable as `python run.py` | smoke | `python run.py --check-only` (new flag) | ❌ Wave 0 |
| HOST-05 | `[project.scripts]` entry installs `eldritch-dm` CLI | smoke | `pip install -e . && which eldritch-dm` | manual |
| HOST-06 | Full suite green | full | `pytest` | ✅ baseline |
| OPS-01 | Resume drill — kill mid-combat, restart, all functional | integration | `pytest tests/integration/test_resume_drill.py -x -v` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `pytest tests/gameplay/test_reactions.py tests/gameplay/test_riposte_sweeper.py -x --no-header -q`
- **Per wave merge:** `pytest tests/gameplay/ tests/integration/ -x --no-header -q`
- **Phase gate:** Full suite green; OPS-01 resume drill green; bootstrap preflight smoke green

### Wave 0 Gaps
- [ ] `tests/gameplay/test_reactions.py` — eligibility logic
- [ ] `tests/gameplay/test_combat_outcome_parser.py` — text-to-enum parser
- [ ] `tests/gameplay/test_monster_driver.py` — monster-turn driving (prerequisite!)
- [ ] `tests/gameplay/test_riposte_sweeper.py` — sweeper expiry
- [ ] `tests/gameplay/test_riposte_callback.py` — RiposteButton callback paths
- [ ] `tests/integration/test_resume_drill.py` — **the OPS-01 deliverable**
- [ ] `tests/test_bootstrap_preflight.py` — preflight exit codes
- [ ] `tests/gameplay/conftest.py` — extend with `fake_riposte_timer`, `mock_monster_miss_text`, `synthetic_battle_master_pc` fixtures
- [ ] Schema migration: idempotent `ALTER TABLE riposte_timers ADD COLUMN consumed_in_round INTEGER` in `database/schema.sql` AND `bootstrap.py` startup ALTER block guarded by try/OperationalError
- [ ] Schema addition: `CREATE TABLE IF NOT EXISTS pc_classes (channel_id, character_id, class_name, subclass, UNIQUE(channel_id, character_id))` — IF Pattern 2 lands with the new-table option (recommended)
- [ ] `src/eldritch_dm/bootstrap.py` — top-level wrapper with preflight (Pattern 5)
- [ ] `run.py` at project root (Pattern 6)
- [ ] `docs/launchd.plist.example` (Pattern 7)
- [ ] `docs/eldritch-dm.service.example` — systemd unit (Linux best-effort)

## Security Domain

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes | Discord OAuth identity (already Phase 1); preflight does NOT require auth — oMLX is localhost-bound |
| V4 Access Control | yes | RiposteButton callback gates on `interaction.user.id == row.user_id`; sweeper holds same per-channel asyncio.Lock as callback |
| V5 Input Validation | yes | `Settings()` pydantic validates all env vars; sweeper has no user-provided inputs |
| V6 Cryptography | no | No new crypto in Phase 5 |
| V7 Errors & Logging | yes | structlog already binds `timer_id`, `channel_id`, `user_id`, `deadline_ts` on every sweeper + callback action |
| V10 Configuration | yes | `.env.example` audit (Q9); launchd plist must NOT contain DISCORD_TOKEN |

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Player B clicks Player A's Riposte button | Spoofing | Permission gate in callback (`user_id` match); structured log of the rejected attempt |
| Spam-click Riposte button to thrash dm20 | DoS | Per-channel asyncio.Lock + Phase 4 token bucket (OPS-03); idempotent via `status='consumed'` check |
| Race between sweeper-mark-expired and callback-mark-consumed | Tampering / race | Per-channel asyncio.Lock around both code paths (Pitfall 3) |
| Restart steals an in-flight reaction | Tampering | Sweeper waits for `setup_hook` completion before first sweep (D-09) |
| World-readable launchd plist leaks DISCORD_TOKEN | Information disclosure | DISCORD_TOKEN sourced from `.env` (not plist); README enforces |
| Misconfigured oMLX URL causes preflight to leak internal hostnames in logs | Information disclosure | Preflight logs `settings.omlx_endpoint` value — fine for self-hosting (operator already knows it); not a real risk for a local-first bot |

## Sources

### Primary (HIGH confidence)
- `/Users/shoemoney/Services/mcp-servers/dm20-protocol/src/dm20_protocol/main.py:1839-1873` — `_format_combat_result` text format (Q3)
- `/Users/shoemoney/Services/mcp-servers/dm20-protocol/src/dm20_protocol/main.py:1967-2106` — `combat_action` signature (Q1, no reaction arg)
- `/Users/shoemoney/Services/mcp-servers/dm20-protocol/src/dm20_protocol/main.py:472-580` — `get_character` text format (Q2, no subclass)
- `/Users/shoemoney/Services/mcp-servers/dm20-protocol/src/dm20_protocol/main.py:3089-3128` — `validate_character_rules` (Q2 alternative subclass source)
- `/Users/shoemoney/Services/mcp-servers/dm20-protocol/src/dm20_protocol/combat/pipeline.py:177-260` — `CombatResult` schema (Q3 fields hit/critical/auto_miss)
- `/Users/shoemoney/Services/mcp-servers/dm20-protocol/src/dm20_protocol/models.py:155-300` — `CharacterClass`, `Character` Pydantic models (Q2)
- `/Users/shoemoney/Services/DiscordDM/database/schema.sql:36-85` — `riposte_timers` + `idx_riposte_pending_deadline` (Q4)
- `/Users/shoemoney/Services/DiscordDM/src/eldritch_dm/persistence/riposte_timers_repo.py` — repo CRUD surface (Q4)
- `/Users/shoemoney/Services/DiscordDM/src/eldritch_dm/bot/dynamic_items.py:752-829` — `_maybe_surface_riposte` seam location (Q6)
- `/Users/shoemoney/Services/DiscordDM/src/eldritch_dm/bot/dynamic_items.py:1157-1212` — `RiposteButton` DynamicItem stub (Q4)
- `/Users/shoemoney/Services/DiscordDM/src/eldritch_dm/persistence/bootstrap.py` — current schema bootstrap (Q7)
- `/Users/shoemoney/Services/DiscordDM/src/eldritch_dm/bot/__main__.py` — current entrypoint (Q8)
- `/Users/shoemoney/Services/DiscordDM/.env.example` — env reference (Q9)
- `/Users/shoemoney/Services/DiscordDM/docs/CONFIGURATION.md:117-146` — pre-flagged env discrepancies (Q9)
- `/Users/shoemoney/Library/LaunchAgents/com.user.omlx.plist` — user's existing launchd parity model (Q11)
- `/Users/shoemoney/Services/DiscordDM/.planning/phases/04-gameplay-exploration-combat/04-RESEARCH.md:280-330` — monster-turn driver pattern documented but unimplemented (Q6)

### Secondary (MEDIUM confidence)
- [discord.py interactions API reference](https://discordpy.readthedocs.io/en/stable/interactions/api.html) — ephemeral followup 15-min limit, on_timeout view edit pattern (Q4, Q5)
- [Battle Master Riposte (5e)](https://dnd5e.wikidot.com/fighter:battle-master:maneuvers) — RAW reaction trigger (Q1)
- [D&D Beyond forums — Combat maneuvers: riposte](https://www.dndbeyond.com/forums/dungeons-dragons-discussion/rules-game-mechanics/46651-combat-maneuvers-riposte) — community interpretation of Riposte
- [Swashbuckler Rogue 5e](https://dnd5e.wikidot.com/rogue:swashbuckler) — confirms no native Riposte (Q1 footnote)
- [Hiding an ephemeral view after user action (discord.py discussion #8454)](https://github.com/Rapptz/discord.py/discussions/8454) — confirms ephemeral lifecycle constraints

### Tertiary (LOW confidence)
- None — every Phase 5 claim was traceable to either source code or an authoritative external reference.

## Per-Question Answer Index

### Q1 — Does `dm20__combat_action` support a `reaction=true` arg?

**Authoritative answer:** **NO.** Verified `main.py:1967-2106`. The full kwarg list is `attacker, target, action_type, weapon_or_spell, damage_dice, damage_type, save_ability, half_on_save, spell_dc`. There is no reaction-budget tracking anywhere in dm20.

**Shim path (mandatory, D-12):**
1. Bot tracks `riposte_timers.consumed_in_round`
2. Riposte click calls `combat_action` as a normal weapon attack (`action="attack"`, `attacker=PC.character_id`, `target=monster_uuid`, `weapon_or_spell=row.weapon_used`)
3. Bot marks `riposte_timers.status='consumed'` AND `consumed_in_round=current_round`
4. On `next_turn` to a new round, bot cancels any leftover pending rows for the previous round (already covered by status check, but a `mark_cancelled_for_round_before(round_num)` would be cleaner)

**Recommendation:** Plan 01 makes this shim explicit. Add `mark_cancelled` to the repo with a `WHERE status='pending' AND ...` clause.

---

### Q2 — How does the bot learn a PC's subclass for eligibility checks?

**Authoritative answer:** dm20's `get_character` text output (`main.py:535`) renders `Level {N} {race} {class}` but **does NOT include subclass**. `validate_character_rules` (`main.py:3089-3128`) does have rulebook awareness and emits a `# Validation Report` with class info — subclass MAY appear there depending on which rulebook checks are loaded, but it's not guaranteed.

**Three options:**
- **A. Parse `validate_character_rules` output.** Brittle — depends on rulebook configuration.
- **B. Persist on bot side at ingest.** Phase 3 already calls `dm20__create_character` with the parsed `Character` object; we have the subclass at that moment. Persist into a new tiny `pc_classes(channel_id, character_id, class_name, subclass)` table.
- **C. Call dm20 internal API exposing `Character.character_class.subclass`.** Requires dm20 changes. Out of scope.

**Recommendation:** **Option B.** New table, new repo, new ingest-time hook (small Phase 3 cog amendment). Plan 01 Wave 0 introduces the table; Plan 01 Wave 1 amends the ingest cog to populate it; Plan 02 reads from it for eligibility.

**Mitigation for level-up drift (Pitfall 5):** at eligibility-check time, also fire a low-cost `validate_character_rules` and if the report mentions a subclass that differs from `pc_classes`, update the row. This guards against the user level-ing up to Battle Master mid-session.

---

### Q3 — How does the bot detect "monster missed me" from `combat_action`?

**Authoritative answer:** `combat_action` returns formatted text. `_format_combat_result` (`main.py:1839-1873`) always emits one of four headers as the first line:
- `**CRITICAL HIT!** {a} strikes {t}!`
- `**Hit!** {a} hits {t}.`
- `**Natural 1!** {a} misses {t}.`
- `**Miss.** {a} misses {t}.`

The bot regex-parses to one of `{HIT, CRITICAL, MISS, NATURAL_ONE}` (Pattern 1). Riposte trigger is `outcome in {MISS, NATURAL_ONE}` — both count as "missed you with a melee attack" per RAW.

**Gotcha:** The headers are stable in dm20's source. If dm20 ever ships an i18n layer or a structured JSON return, this parser breaks silently. Plan should include an integration test against a real running dm20 (gated behind `RUN_INTEGRATION=1`) so format drift is caught early.

---

### Q4 — Is the `riposte_timers` schema sufficient as-is?

**Authoritative answer:** Yes, with one optional column.

Existing columns (`schema.sql:36-50`):
`id INTEGER PK, channel_id, character_id, user_id, monster_uuid, weapon_used, message_id, custom_id, deadline_ts, status, created_at`
Existing index: `idx_riposte_pending_deadline ON (status, deadline_ts) WHERE status='pending'` — exactly what the sweeper needs.

**Phase 5 addition (mandatory):** `consumed_in_round INTEGER` for the reaction-budget shim (Q1). Idempotent via:
```sql
ALTER TABLE riposte_timers ADD COLUMN consumed_in_round INTEGER;
```
Guard with `try/except aiosqlite.OperationalError` in the bootstrap so re-running it doesn't error.

**Repo additions (mandatory):**
- `list_for_character(channel_id, character_id) -> list[RiposteTimer]` — eligibility check uses this
- `mark_cancelled(id_)` — for D-12's "cancel previous-round pending rows on next_turn"
- `update_message_ref(id, message_id, custom_id)` — for the post-channel.send back-fill (Pattern 3 + Pitfall 1)
- (optional) `mark_consumed_with_round(id, round_n)` — wraps mark_consumed + writes consumed_in_round atomically

---

### Q5 — Does the ephemeral riposte message survive bot restart? What's the restart UX?

**Authoritative answer:** **NO** — ephemeral followups die when the originating interaction expires (15 min) AND cannot be re-edited from a different bot process [CITED: discordpy.readthedocs.io/en/stable/interactions/api.html].

**Decision:** Use a **public channel message with permission gating in the callback** instead.

- `channel.send(content="<@user_id> ...", view=View(...))` — visible to all, mention-pings the target
- `View(timeout=None)` — persistent (sweeper owns the deadline, NOT the View)
- Callback gate: `if interaction.user.id != row.user_id: send WARNING.INVALID_ACTION (ephemeral) and return`
- Restart UX: bot starts, sweeper loads pending rows, the Discord-side message + button still exist (Discord persists message + components), DynamicItem registry routes incoming clicks to the right callback class. The 8s window may have shrunk by the time bot is back, but it works.

**Tradeoff vs ephemeral:** the button is visible to all players in the channel. Not actually a problem — and arguably useful ("ooh, Aria has a riposte open, what'll she do?"). Document in README + plan.

---

### Q6 — Where does the Riposte trigger fire in the current codebase?

**Authoritative answer:** The Phase 4 seam at `AttackButton._maybe_surface_riposte` (`dynamic_items.py:752-769`) is **on the wrong attack path**. It fires when a PC clicks Attack and the result is a miss — i.e., **PC misses monster**. RAW Riposte is **monster misses PC**.

**Correct trigger point** is in the monster-turn handling code path, which **does not exist yet** in Phase 4. Phase 4's `PartyModeOrchestrator` polls player actions and never explicitly drives a monster turn (the orchestrator just observes via `get_game_state` that the turn has advanced; it doesn't call `combat_action(attacker=monster)`).

**Recommendation (per Open Q2):** Plan 01 ships a minimal MonsterDriver:
- Detects current actor is monster (via `get_character` + player_name None check, Phase 4 Q3 pattern)
- Picks a random PC target from `get_game_state` initiative list
- Calls `combat_action(attacker=monster, target=PC, action_type='attack')`
- Parses outcome via Pattern 1
- If outcome ∈ {MISS, NATURAL_ONE} AND eligibility check passes → surfaces riposte button
- Calls `next_turn` to advance

Phase 4's `_maybe_surface_riposte` seam should be **deleted** (Open Q1) — keeping it is a foot-gun.

---

### Q7 — How does the new bootstrap.py extension integrate with the existing `persistence/bootstrap.py`?

**Authoritative answer:** Create a new `src/eldritch_dm/bootstrap.py` at the package root that:
1. Re-exports `from eldritch_dm.persistence.bootstrap import bootstrap as ensure_schema`
2. Adds `preflight()` per Pattern 5 (oMLX + MCP tools pings)
3. Has its own `main()` that calls `preflight()` and exits with the right code
4. Is invokable via `python -m eldritch_dm.bootstrap`

The existing `eldritch_dm.persistence.bootstrap` keeps its CLI (`python -m eldritch_dm.persistence.bootstrap`) for backwards-compat; both paths converge on the same schema-creation code.

Documentation: update README + CONFIGURATION.md to recommend `python -m eldritch_dm.bootstrap` as the canonical pre-run command.

---

### Q8 — What's the run.py contract?

**Authoritative answer:** Per Pattern 6:
1. Construct `Settings()` (validates env)
2. Configure structlog
3. Call `bootstrap.preflight()` unless `ELDRITCH_ALLOW_OFFLINE_START=1`
4. Build `EldritchBot(settings)` — its `setup_hook` (Phase 1-2 wiring) handles all subsystem init
5. Install SIGTERM handler that raises `KeyboardInterrupt` so launchd's SIGTERM = clean exit
6. `bot.run(settings.discord_token)`
7. Return exit code (0 clean, 2 fatal, preflight codes 1/3 propagated)

run.py is **net-new** at the project root (D-16). It's a thin wrapper — the heavy lifting stays in `eldritch_dm.bot.bot.EldritchBot`.

---

### Q9 — What's the actual state of `.env.example` vs `Settings`?

**Authoritative answer:** Two discrepancies, both flagged in `docs/CONFIGURATION.md:117-146`:

| Var | In `.env.example` | In `Settings` | Fix |
|-----|-------------------|---------------|-----|
| `MCP_RATE_LIMIT_MS` | **absent** | `200` (consumed) | Add to `.env.example` with `🧪` tag, default 200 |
| `OMLX_CACHE_STRATEGY` | listed (commented) | **absent** | Either drop from `.env.example` OR add a `Settings` field that exports it (recommend: leave the comment but mark "passed through to oMLX process via env, not consumed by Python") |

Phase 5 plan **must** include a `[ ]` task for each. Test: `python -c "from eldritch_dm.config import Settings; s = Settings(); assert s.mcp_rate_limit_ms == 200"` after wiping shell env.

---

### Q10 — How does the test suite need to grow?

**Authoritative answer:** ~9 new test files (see Wave 0 Gaps above). Total new test count ~30-40. Existing 734 tests must remain green (phase regression gate).

The critical test is `tests/integration/test_resume_drill.py` — it's the proof-of-concept that earns the "survives restart" claim. It:
1. Spins up bot A on a temp DB
2. Seeds a COMBAT-state `channel_sessions` row + a pending `riposte_timers` row (deadline 5s out)
3. Asserts bot A rehydrates persistent views + sweeper sees the row
4. Calls `await bot_a.close()` (clean shutdown)
5. Spins up bot B on the SAME temp DB
6. Asserts bot B's sweeper picks up the still-pending row
7. Simulates a Discord interaction with the matching `custom_id`
8. Asserts the riposte path executes correctly (combat_action mock called, mark_consumed)
9. Asserts a separate already-expired row is marked expired on the next sweep
10. Cleans up

Build this against a mocked `MCPClient` (no real dm20) and a fake `discord.Interaction` (no real Discord). `RUN_INTEGRATION=1` for a parallel test that hits a real dm20.

---

### Q11 — What's the launchd parity reference?

**Authoritative answer:** User's existing `~/Library/LaunchAgents/com.user.omlx.plist` (`Label = com.user.omlx`, `KeepAlive=true`, `RunAtLoad=true`, `StandardOutPath`/`StandardErrorPath` to log files in `~/.omlx/`).

Phase 5 mirrors with `com.shoemoney.eldritch-dm` (Pattern 7). Key differences:
- Use dict-form `KeepAlive` with `SuccessfulExit=false` (don't restart-loop on bad DISCORD_TOKEN)
- `ThrottleInterval=10` to slow down crash-restart storms
- `EnvironmentVariables` sets `LOG_FORMAT=json` for machine-parseable logs (vs. console format the user uses in dev)
- DOES NOT contain DISCORD_TOKEN (plist is world-readable); secrets come from `.env`

---

### Q12 — What does OPS-01 actually require?

**Authoritative answer:** Per CONTEXT.md D-19:
- Seed `channel_sessions` (state=COMBAT)
- Seed `riposte_timers` (status=pending, deadline 5s in future)
- Seed `persistent_views` (combat embed + riposte button row, message_id linked)
- Build bot A; assert it rehydrates everything (combat embed message, DynamicItem registry has RiposteButton)
- `await bot_a.close()` (Phase 2 OPS-04 already wires graceful shutdown)
- Drop bot_a; build bot B fresh on the same DB
- Assert: `setup_hook` reads same `channel_sessions`, registers same DynamicItems, sweeper picks up the still-pending timer
- Simulate the Discord interaction with the matching `custom_id` → assert callback fires correctly (mock combat_action, assert mark_consumed)
- Wait until deadline; assert sweeper marks the timer expired
- All in a `tests/integration/test_resume_drill.py` file, runnable in CI under 5 seconds

## Metadata

**Confidence breakdown:**
- Riposte mechanics / dm20 reaction support: HIGH — verified against dm20 source
- Schema + repo readiness: HIGH — `riposte_timers` shape is correct; minor additive changes
- Restart-survival sweeper design: HIGH — pattern verified against Phase 2's DynamicItem registry semantics + discord.py docs
- Monster-turn driver requirement: HIGH — Phase 4 RESEARCH explicitly documented this gap (04-RESEARCH.md Pattern 3 left unimplemented)
- Swashbuckler Riposte ineligibility: HIGH — multiple 5e source aggregators confirm; SRD doesn't include Riposte at all (it's PHB content), but Swashbuckler in both PHB and SCAG/Xanathar lacks any "miss-and-counter" feature
- Self-host packaging (launchd / run.py / preflight): HIGH — patterns verified against user's existing `com.user.omlx` + extant code
- README + CONFIGURATION.md discrepancies: HIGH — explicitly flagged in `docs/CONFIGURATION.md:117-146`
- Ephemeral followup limitations: MEDIUM-HIGH — confirmed via discord.py docs + community discussion
- Phase 4 `_maybe_surface_riposte` seam being on the wrong path: HIGH — verified by reading `AttackButton.callback` in full (`dynamic_items.py:771-851`)

**Research date:** 2026-05-22
**Valid until:** 30 days for self-host packaging (stable); 14 days for dm20 source claims (active project); 7 days for discord.py API claims (active release cadence)
