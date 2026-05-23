---
phase: 05-reactions-self-host-polish
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - database/schema.sql
  - src/eldritch_dm/persistence/bootstrap.py
  - src/eldritch_dm/persistence/riposte_timers_repo.py
  - src/eldritch_dm/persistence/pc_classes_repo.py
  - src/eldritch_dm/persistence/models.py
  - src/eldritch_dm/gameplay/combat_outcome_parser.py
  - src/eldritch_dm/gameplay/monster_driver.py
  - src/eldritch_dm/gameplay/reactions.py
  - src/eldritch_dm/gameplay/party_mode.py
  - src/eldritch_dm/bot/dynamic_items.py
  - src/eldritch_dm/bot/cogs/combat.py
  - src/eldritch_dm/bot/cogs/ingest.py
  - src/eldritch_dm/bot/bot.py
  - src/eldritch_dm/bot/setup_hook.py
  - src/eldritch_dm/bot/warnings.py
  - tests/persistence/test_bootstrap.py
  - tests/persistence/test_riposte_timers_repo.py
  - tests/persistence/test_pc_classes_repo.py
  - tests/gameplay/test_combat_outcome_parser.py
  - tests/gameplay/test_monster_driver.py
  - tests/gameplay/test_reactions.py
  - tests/gameplay/test_riposte_callback.py
  - tests/bot/test_setup_hook.py
autonomous: true
requirements:
  - COMBAT-09
  - COMBAT-10
tags: [reactions, riposte, monster-driver, combat, schema-migration, pc-classes]

must_haves:
  truths:
    - "When a monster's `combat_action` returns `Miss.` or `Natural 1!` against an eligible PC (Battle Master Fighter, RAW), a public-message Riposte button appears in the channel within one orchestrator tick, pinging the target user and showing an 8s window."
    - "Only the target Discord user can successfully click the Riposte button; other clickers receive an ephemeral `INVALID_ACTION` warning and the timer is unaffected."
    - "A successful click within the deadline invokes `dm20__combat_action(attacker=PC, target=monster, action_type='attack', weapon_or_spell=row.weapon_used)` exactly once, marks the timer `status='consumed'` AND writes `consumed_in_round=current_round`, and the public Riposte message is deleted."
    - "Within a single combat round, no PC can have more than one pending OR consumed Riposte timer — the eligibility check enforces this against the bot-side `riposte_timers` table because dm20 has no native reaction-budget model."
    - "The Phase 4 `_maybe_surface_riposte` seam in `AttackButton` (which fired on the wrong RAW path — PC-miss-monster) is DELETED in this plan; the only Riposte trigger lives in the new MonsterDriver path."
    - "The minimal MonsterDriver picks a uniformly-random eligible PC target from `get_game_state` (per D-B), calls `dm20__combat_action(attacker=monster, target=PC, action_type='attack')`, parses the text outcome via the new `combat_outcome_parser`, and on MISS/NATURAL_ONE fires the riposte-surface path (smart Claudmaster-driven targeting is explicitly deferred to v2)."
    - "PC subclass is captured at character-ingest time (Phase 3 cog) into a new `pc_classes(channel_id, character_id, class_name, subclass)` table — eligibility never parses subclass out of `dm20__get_character` text (which omits it per RESEARCH Q2)."
    - "`riposte_timers` schema gains an additive `consumed_in_round INTEGER` column via an idempotent ALTER TABLE in `persistence/bootstrap.py`; re-running bootstrap does not error."
    - "Eligibility set is strict RAW Battle Master Fighter only per D-C — `ELIGIBLE_CLASS_SUBCLASSES = frozenset({('fighter', 'battle master')})` with a code-level TODO noting v2 YAML-configurable expansion (Swashbuckler is not RAW Riposte; CONTEXT.md D-04 wording is corrected by this plan)."
  artifacts:
    - path: "database/schema.sql"
      provides: "Adds `pc_classes` table CREATE TABLE IF NOT EXISTS; documents (does not duplicate) the additive `riposte_timers.consumed_in_round` column added at bootstrap time"
      contains: "pc_classes"
    - path: "src/eldritch_dm/persistence/bootstrap.py"
      provides: "Idempotent ALTER TABLE riposte_timers ADD COLUMN consumed_in_round INTEGER guarded by try/except aiosqlite.OperationalError; ensures pc_classes table exists"
      contains: "consumed_in_round"
    - path: "src/eldritch_dm/persistence/pc_classes_repo.py"
      provides: "PCClassesRepo with upsert(channel_id, character_id, class_name, subclass), get(channel_id, character_id) -> PCClassInfo | None"
      contains: "class PCClassesRepo"
    - path: "src/eldritch_dm/persistence/riposte_timers_repo.py"
      provides: "Extended with list_for_character(channel_id, character_id), mark_cancelled(id), update_message_ref(id, message_id, custom_id, deadline_ts), mark_consumed_with_round(id, round_n)"
      contains: "list_for_character"
    - path: "src/eldritch_dm/gameplay/combat_outcome_parser.py"
      provides: "AttackOutcome StrEnum {HIT, CRITICAL, MISS, NATURAL_ONE} + parse_combat_outcome(raw: str) -> AttackOutcome | None (regex on dm20 _format_combat_result headers)"
      contains: "class AttackOutcome"
    - path: "src/eldritch_dm/gameplay/monster_driver.py"
      provides: "MonsterDriver — minimal: detect monster-actor turns, pick random PC target, call combat_action, parse outcome, on miss/nat1 call reactions.surface_riposte_button. Smart targeting deferred to v2."
      contains: "class MonsterDriver"
    - path: "src/eldritch_dm/gameplay/reactions.py"
      provides: "RiposteEligibility dataclass + ELIGIBLE_CLASS_SUBCLASSES frozenset + check_riposte_eligibility(...) + surface_riposte_button(...) per RESEARCH Patterns 2-3"
      contains: "class RiposteEligibility"
    - path: "src/eldritch_dm/bot/dynamic_items.py"
      provides: "RiposteButton.callback fully wired (was Phase 2 stub); AttackButton._maybe_surface_riposte DELETED along with its callsite at line 829"
      contains: "RiposteButton"
  key_links:
    - from: "src/eldritch_dm/gameplay/monster_driver.py"
      to: "src/eldritch_dm/gameplay/reactions.py"
      via: "On AttackOutcome.MISS or NATURAL_ONE for monster→PC attack, monster_driver awaits reactions.check_riposte_eligibility then reactions.surface_riposte_button"
      pattern: "surface_riposte_button|check_riposte_eligibility"
    - from: "src/eldritch_dm/gameplay/reactions.py"
      to: "src/eldritch_dm/persistence/riposte_timers_repo.py"
      via: "surface_riposte_button inserts a pending row; eligibility check queries list_for_character to enforce one reaction per round"
      pattern: "riposte_timers|RiposteTimerRepo"
    - from: "src/eldritch_dm/gameplay/reactions.py"
      to: "src/eldritch_dm/persistence/pc_classes_repo.py"
      via: "Eligibility uses bot-side persisted subclass (not dm20__get_character text which omits subclass)"
      pattern: "pc_classes|PCClassesRepo"
    - from: "src/eldritch_dm/bot/dynamic_items.py"
      to: "src/eldritch_dm/gameplay/reactions.py"
      via: "RiposteButton.callback delegates the gate→combat_action→mark_consumed→cleanup sequence to a helper in reactions.py (held under per-channel asyncio.Lock from bot.rate_limiter or a new SessionLocks registry)"
      pattern: "handle_riposte_click|reactions\\."
    - from: "src/eldritch_dm/bot/cogs/ingest.py"
      to: "src/eldritch_dm/persistence/pc_classes_repo.py"
      via: "After successful dm20__create_character at ingest, upserts (channel_id, character_id, class, subclass) into pc_classes"
      pattern: "pc_classes_repo|upsert"
    - from: "src/eldritch_dm/gameplay/party_mode.py"
      to: "src/eldritch_dm/gameplay/monster_driver.py"
      via: "PartyModeOrchestrator's COMBAT-tick path detects monster-actor turns (player_id is None) and delegates the turn to MonsterDriver.drive()"
      pattern: "MonsterDriver|drive\\("
---

<objective>
Ship the Riposte feature end-to-end (COMBAT-09 + COMBAT-10) by (1) closing the Phase 4 gap where monster-turn driving was scoped out, (2) adding the additive schema and lookup table the reaction-budget shim requires, (3) wiring the correct RAW trigger (monster-miss-PC) via a new minimal MonsterDriver, and (4) deleting the misplaced Phase 4 `_maybe_surface_riposte` seam.

Purpose: COMBAT-09 has no trigger today — Phase 4 documented but did not implement a monster-turn driver (04-RESEARCH.md Q3, 05-RESEARCH.md finding #6). The seam that DID land in Phase 4 fires on the wrong attack path (PC-miss-monster). Plan 01 corrects both: deletes the wrong seam, adds the correct trigger, and ships the minimal "random target" monster driver per user decision D-B.

Output:
- Wave 0 schema additions: `pc_classes` table + idempotent ALTER on `riposte_timers.consumed_in_round`
- `src/eldritch_dm/gameplay/combat_outcome_parser.py` (regex parser for dm20 text)
- `src/eldritch_dm/gameplay/monster_driver.py` (random-target minimal driver per D-B)
- `src/eldritch_dm/gameplay/reactions.py` (eligibility + button surface + click handler)
- Promoted `RiposteButton.callback` (Phase 2 stub → real)
- Deleted `AttackButton._maybe_surface_riposte` and its callsite at line 829 (per D-A)
- Ingest-time `pc_classes` upsert in `bot/cogs/ingest.py`
- Eligibility set ships RAW Battle Master only (D-C); v2 YAML TODO comment
- ~25 new tests across 6 new test files
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/ROADMAP.md
@.planning/REQUIREMENTS.md
@.planning/phases/05-reactions-self-host-polish/05-CONTEXT.md
@.planning/phases/05-reactions-self-host-polish/05-RESEARCH.md
@.planning/phases/04-gameplay-exploration-combat/04-SUMMARY.md
@database/schema.sql
@src/eldritch_dm/persistence/bootstrap.py
@src/eldritch_dm/persistence/riposte_timers_repo.py
@src/eldritch_dm/persistence/models.py
@src/eldritch_dm/gameplay/party_mode.py
@src/eldritch_dm/gameplay/game_state_parser.py
@src/eldritch_dm/gameplay/turn_gatekeeper.py
@src/eldritch_dm/bot/dynamic_items.py
@src/eldritch_dm/bot/cogs/combat.py
@src/eldritch_dm/bot/cogs/ingest.py
@src/eldritch_dm/bot/warnings.py
@src/eldritch_dm/bot/setup_hook.py
@src/eldritch_dm/mcp/tools.py
@src/eldritch_dm/mcp/rate_limit.py
@src/eldritch_dm/config.py

**User decisions baked in (do not re-litigate):**
- **D-A:** Delete `AttackButton._maybe_surface_riposte` and its callsite — wrong RAW path. Commit the deletion atomically in Task 2.
- **D-B:** Minimal MonsterDriver only — random PC target via `get_game_state` initiative list. Smart Claudmaster-driven targeting is v2.
- **D-C:** Strict RAW eligibility — Battle Master Fighter only. Override CONTEXT.md D-04 (which mis-attributed Riposte to Swashbuckler). Code-level TODO for v2 YAML config. REQUIREMENTS.md COMBAT-09 line is updated in Plan 03's closure (do not edit it here).

**Side findings baked in:**
- Public message + permission gate for the Riposte button — NOT ephemeral followup (RESEARCH finding #8: ephemeral followups die at 15 min and CANNOT be re-edited from a fresh bot process — kills COMBAT-11).
- `riposte_timers.consumed_in_round INTEGER` is the reaction-budget shim column (RESEARCH Q1: dm20 has no native reaction tracking).
- `pc_classes` is a new table because dm20's `get_character` text omits subclass (RESEARCH Q2).
- Plan 02 owns the per-channel `asyncio.Lock` namespacing for `riposte:{channel_id}` to prevent the click-at-deadline race with the sweeper. Plan 01 ships the callback's mutation sequence; Plan 02 wraps it in the lock. Document the seam clearly.

<interfaces>
<!-- Already-existing contracts the executor must reuse. -->

From src/eldritch_dm/persistence/riposte_timers_repo.py:
```python
class RiposteTimer(BaseModel):  # pydantic v2 frozen
    id: int | None = None
    channel_id: str
    character_id: str            # dm20 character id
    user_id: str                 # Discord user id
    monster_uuid: str | None
    weapon_used: str | None
    message_id: str
    custom_id: str
    deadline_ts: datetime
    status: Literal["pending", "consumed", "expired", "cancelled"] = "pending"
    # NEW (this plan adds): consumed_in_round: int | None = None

class RiposteTimerRepo:
    async def insert(self, timer: RiposteTimer) -> RiposteTimer  # returns row with id assigned
    async def mark_consumed(self, id_: int) -> None
    async def mark_expired(self, id_: int) -> None
    async def get(self, id_: int) -> RiposteTimer | None
    async def list_pending(self) -> list[RiposteTimer]
    # NEW (this plan adds):
    #   list_for_character(channel_id, character_id) -> list[RiposteTimer]
    #   mark_cancelled(id_) -> None
    #   update_message_ref(id_, message_id, custom_id, deadline_ts) -> None
    #   mark_consumed_with_round(id_, round_n) -> None
```

From src/eldritch_dm/bot/dynamic_items.py (RiposteButton stub):
```python
class RiposteButton(discord.ui.DynamicItem[discord.ui.Button],
                    template=r"^riposte:(?P<timer_id>\d+):(?P<user_id>\d+)$"):
    def __init__(self, timer_id: int, user_id: int) -> None:
        self.timer_id = timer_id
        self.user_id = user_id
        super().__init__(...)
    # callback is currently a Phase 2 stub — this plan promotes it
```

From src/eldritch_dm/mcp/tools.py:
```python
async def combat_action(client, *, action: str, attacker: str, target: str,
                        weapon_or_spell: str | None = None,
                        damage_dice: str | None = None, damage_type: str | None = None,
                        save_ability: str | None = None, half_on_save: bool | None = None,
                        spell_dc: int | None = None) -> dict[str, Any]
async def get_game_state(client, *, campaign_name: str) -> dict[str, Any]
async def get_character(client, *, character_id: str) -> dict[str, Any]
async def next_turn(client, *, campaign_name: str) -> dict[str, Any]
# NOTE per RESEARCH Q1: combat_action has NO `reaction` kwarg. Bot tracks reaction budget itself.
```

From src/eldritch_dm/gameplay/turn_gatekeeper.py:
```python
def is_actor(*, clicker_user_id: int, current_actor_player_id: str | None) -> bool
def current_actor_from_game_state(state: dict) -> dict | None
def player_id_for_actor(actor: dict) -> str | None  # returns None for monsters
```

From src/eldritch_dm/gameplay/game_state_parser.py:
```python
@dataclass(frozen=True)
class CombatState:
    in_combat: bool
    round_number: int
    current_turn: str  # actor display name
    combatants: list[Combatant]  # has .name, .player_id (None for monsters), .character_id, .hp, .ac
def parse_get_game_state(text: str) -> CombatState
```

From src/eldritch_dm/bot/warnings.py:
```python
class WarningKind(StrEnum):
    INVALID_ACTION = "invalid_action"
    RATE_LIMITED = "rate_limited"
    DM_OFFLINE = "dm_offline"
    # NEW (this plan adds): RIPOSTE_EXPIRED = "riposte_expired"
async def send_warning(interaction, kind: WarningKind, **ctx) -> None
```

From src/eldritch_dm/config.py:
```python
class Settings(BaseSettings):
    riposte_ttl_seconds: PositiveInt = 8        # already wired (D-07)
    mcp_rate_limit_ms: PositiveInt = 200        # already wired (Phase 4)
    omlx_endpoint: HttpUrl                       # already wired
    mcp_tools_url: HttpUrl                       # already wired
    omlx_model: str = "ShoeGPT"                  # already wired
```

From dm20 _format_combat_result (verbatim text headers — RESEARCH Q3):
- `**CRITICAL HIT!** {attacker} strikes {target}!`
- `**Hit!** {attacker} hits {target}.`
- `**Natural 1!** {attacker} misses {target}.`
- `**Miss.** {attacker} misses {target}.`
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Wave 0 schema migration + pc_classes table + repo extensions (RED→GREEN)</name>
  <files>
    database/schema.sql,
    src/eldritch_dm/persistence/bootstrap.py,
    src/eldritch_dm/persistence/models.py,
    src/eldritch_dm/persistence/riposte_timers_repo.py,
    src/eldritch_dm/persistence/pc_classes_repo.py,
    tests/persistence/test_bootstrap.py,
    tests/persistence/test_riposte_timers_repo.py,
    tests/persistence/test_pc_classes_repo.py
  </files>
  <behavior>
    Bootstrap migration (src/eldritch_dm/persistence/bootstrap.py):
      - Test 1: After bootstrap runs on a fresh DB, `PRAGMA table_info(riposte_timers)` includes a column named `consumed_in_round` with type `INTEGER` and nullable.
      - Test 2: Running bootstrap a SECOND time on the same DB does NOT raise (idempotent ALTER guarded by try/except aiosqlite.OperationalError catching "duplicate column name").
      - Test 3: After bootstrap, `pc_classes` table exists with columns (channel_id TEXT, character_id TEXT, class_name TEXT, subclass TEXT NOT NULL DEFAULT '', PRIMARY KEY(channel_id, character_id)).
      - Test 4: `pc_classes` has FOREIGN KEY (channel_id) REFERENCES channel_sessions(channel_id) ON DELETE CASCADE.
      - Test 5: bootstrap.py logs `riposte_timers_migrated_consumed_in_round` on the first run and SKIPS the log on the second run (it sees the column already present).

    PCClassesRepo (src/eldritch_dm/persistence/pc_classes_repo.py):
      - Test 6: `upsert(channel_id, character_id, class_name, subclass)` inserts a new row.
      - Test 7: A second `upsert` for the same (channel_id, character_id) UPDATES the existing row (no duplicate).
      - Test 8: `get(channel_id, character_id)` returns a `PCClassInfo(class_name, subclass)` pydantic v2 frozen model, or None if missing.
      - Test 9: class_name and subclass are stored lowercased + whitespace-collapsed (e.g. "Battle  Master" → "battle master") for stable eligibility comparison.
      - Test 10: get() on a non-existent row returns None (not raising).

    RiposteTimerRepo extensions (src/eldritch_dm/persistence/riposte_timers_repo.py):
      - Test 11: `list_for_character(channel_id, character_id)` returns all timer rows ordered by id ASC (any status).
      - Test 12: `mark_cancelled(id_)` sets status='cancelled'; idempotent if called twice (second call no-ops).
      - Test 13: `update_message_ref(id_, message_id, custom_id, deadline_ts)` writes all three columns atomically (used by `surface_riposte_button` post-channel.send back-fill per RESEARCH Pitfall 1).
      - Test 14: `mark_consumed_with_round(id_, round_n)` sets status='consumed' AND consumed_in_round=round_n in one statement; reading back via `get(id_)` shows both fields populated.
      - Test 15: A timer inserted with `consumed_in_round=None` and then `mark_consumed_with_round(id, 3)` produces a row with consumed_in_round=3.
      - Test 16: `RiposteTimer` pydantic model accepts an optional `consumed_in_round: int | None = None` field.
  </behavior>
  <action>
    Edit `database/schema.sql`:
      - Append a new `CREATE TABLE IF NOT EXISTS pc_classes` block AFTER `combat_conditions`, BEFORE the CREATE INDEX section. Columns: channel_id TEXT NOT NULL, character_id TEXT NOT NULL, class_name TEXT NOT NULL, subclass TEXT NOT NULL DEFAULT '', PRIMARY KEY(channel_id, character_id), FOREIGN KEY(channel_id) REFERENCES channel_sessions(channel_id) ON DELETE CASCADE.
      - Add a comment block above pc_classes explaining (per RESEARCH Q2) that dm20's get_character text omits subclass, so the bot persists class+subclass at ingest time for eligibility checks.
      - DO NOT add `consumed_in_round` to the schema.sql `riposte_timers` CREATE TABLE — keep schema.sql aligned with Phase 1's shape. The column is added at bootstrap-time via ALTER for backwards-compat with existing self-host DBs. Add an explicit comment in schema.sql above riposte_timers noting this and pointing to bootstrap.py.

    Edit `src/eldritch_dm/persistence/bootstrap.py`:
      - After existing schema execution, add a guarded idempotent migration:
        ```python
        try:
            await conn.execute("ALTER TABLE riposte_timers ADD COLUMN consumed_in_round INTEGER")
            log.info("riposte_timers_migrated_consumed_in_round")
        except aiosqlite.OperationalError as exc:
            if "duplicate column name" in str(exc).lower():
                pass  # already migrated; no log
            else:
                raise
        ```
      - Tests for bootstrap idempotency live in tests/persistence/test_bootstrap.py (extend the existing file; do not create a new one).
      - Update the expected-tables set in `tests/persistence/test_bootstrap.py` to include `pc_classes`.

    Create `src/eldritch_dm/persistence/pc_classes_repo.py`:
      - Module-level `class PCClassInfo(BaseModel, frozen=True)`: `class_name: str`, `subclass: str` (both lowercased + space-collapsed at construction via field_validator).
      - `class PCClassesRepo` mirroring Phase 4's CombatConditionsRepo construction pattern (sync `_connect()` returning unstarted Connection — see deviation #1 in 04-SUMMARY; do NOT repeat that bug):
        - `__init__(self, db_path: Path | str)`
        - `_connect(self) -> aiosqlite.Connection` — synchronous, returns unstarted; caller does `async with self._connect() as conn:`; apply pragmas via `_configure(conn)` helper.
        - `async def upsert(self, channel_id, character_id, class_name, subclass) -> None` — uses `INSERT INTO pc_classes(...) VALUES(?,?,?,?) ON CONFLICT(channel_id, character_id) DO UPDATE SET class_name=excluded.class_name, subclass=excluded.subclass`.
        - `async def get(self, channel_id, character_id) -> PCClassInfo | None`.
      - Lowercase + collapse-whitespace via the validator so callers can pass arbitrary capitalization from ingest.

    Edit `src/eldritch_dm/persistence/riposte_timers_repo.py`:
      - Add `consumed_in_round: int | None = None` to the `RiposteTimer` pydantic model.
      - Update existing `insert()` SQL to include the new column (`INSERT INTO riposte_timers(..., consumed_in_round) VALUES (..., ?)`); existing callers that don't pass it get None.
      - Add `async def list_for_character(self, channel_id: str, character_id: str) -> list[RiposteTimer]` — `SELECT * FROM riposte_timers WHERE channel_id=? AND character_id=? ORDER BY id ASC`.
      - Add `async def mark_cancelled(self, id_: int) -> None` — `UPDATE riposte_timers SET status='cancelled' WHERE id=? AND status != 'consumed'` (don't override a consumed row).
      - Add `async def update_message_ref(self, id_: int, *, message_id: str, custom_id: str, deadline_ts: datetime) -> None` — `UPDATE riposte_timers SET message_id=?, custom_id=?, deadline_ts=? WHERE id=?`.
      - Add `async def mark_consumed_with_round(self, id_: int, round_n: int) -> None` — `UPDATE riposte_timers SET status='consumed', consumed_in_round=? WHERE id=?`.

    Edit `src/eldritch_dm/persistence/models.py` if `PCClassInfo` lives there instead of in the repo file (executor's choice; keep import-linter happy — `persistence` modules may not import `bot` or `gameplay`).

    Write the 16 tests above. Use the existing aiosqlite-backed test fixtures in tests/persistence/conftest.py (precedent: tests/persistence/test_combat_conditions_repo.py from Plan 04-02).
  </action>
  <verify>
    <automated>uv run pytest tests/persistence/test_bootstrap.py tests/persistence/test_riposte_timers_repo.py tests/persistence/test_pc_classes_repo.py -x -v</automated>
  </verify>
  <done>
    Idempotent ALTER adds `consumed_in_round` to `riposte_timers`; `pc_classes` table exists with the correct shape and FK; `PCClassesRepo` upserts case-folded class/subclass; `RiposteTimerRepo` exposes the four new methods; all 16 tests green.
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: combat_outcome_parser + reactions.py + MonsterDriver + delete old seam + RiposteButton.callback (RED→GREEN)</name>
  <files>
    src/eldritch_dm/gameplay/combat_outcome_parser.py,
    src/eldritch_dm/gameplay/reactions.py,
    src/eldritch_dm/gameplay/monster_driver.py,
    src/eldritch_dm/gameplay/party_mode.py,
    src/eldritch_dm/bot/dynamic_items.py,
    src/eldritch_dm/bot/warnings.py,
    src/eldritch_dm/bot/bot.py,
    tests/gameplay/test_combat_outcome_parser.py,
    tests/gameplay/test_reactions.py,
    tests/gameplay/test_monster_driver.py,
    tests/gameplay/test_riposte_callback.py
  </files>
  <behavior>
    combat_outcome_parser.py:
      - Test 1: `parse_combat_outcome("**CRITICAL HIT!** Goblin Scout strikes Thorin!")` → `AttackOutcome.CRITICAL`.
      - Test 2: `parse_combat_outcome("**Hit!** Goblin Scout hits Thorin.")` → `AttackOutcome.HIT`.
      - Test 3: `parse_combat_outcome("**Natural 1!** Goblin Scout misses Thorin.")` → `AttackOutcome.NATURAL_ONE`.
      - Test 4: `parse_combat_outcome("**Miss.** Goblin Scout misses Thorin.")` → `AttackOutcome.MISS`.
      - Test 5: Unrecognized header (e.g. "Goblin Scout takes 5 damage.") → `None`.
      - Test 6: Multiline input — header on second line still matches (re.MULTILINE).

    reactions.py:
      - Test 7: `ELIGIBLE_CLASS_SUBCLASSES == frozenset({("fighter", "battle master")})` — RAW only. The module includes a TODO comment block referencing Plan 03's REQUIREMENTS update and v2 YAML config.
      - Test 8: `check_riposte_eligibility(...)` returns None when pc_classes lookup returns a non-eligible class (e.g. wizard) — verified by mocked PCClassesRepo.
      - Test 9: Returns None when pc_classes row is missing (PC never ingested or pre-Phase-5 character).
      - Test 10: Returns None when `riposte_timers.list_for_character(...)` shows a row with `status='pending'` (queued reaction blocks new one).
      - Test 11: Returns None when a row exists with `consumed_in_round == current_round` (reaction budget exhausted this round).
      - Test 12: Returns `RiposteEligibility(character_id, user_id, primary_weapon)` when eligible class + no pending + no consumed-this-round.
      - Test 13: A row with `status='consumed'` AND `consumed_in_round == current_round - 1` does NOT block — that was a different round.
      - Test 14: `surface_riposte_button(...)` happy path: inserts a pending row, calls `channel.send(content=..., view=...)` with `<@user_id>` mention, captures the returned message_id, then calls `repo.update_message_ref(id, message_id, custom_id=f"riposte:{id}:{user_id}", deadline_ts=NOW+ttl_seconds)`. CRITICAL: deadline_ts is computed AFTER channel.send (RESEARCH Pitfall 1) — assert the deadline written via update_message_ref is later than a timestamp captured immediately after the mocked channel.send returns.
      - Test 15: `surface_riposte_button` uses `discord.ui.View(timeout=None)` — persistent View (sweeper owns the deadline, NOT the View — RESEARCH anti-pattern callout).
      - Test 16: `surface_riposte_button` returns the new timer_id (int).

    monster_driver.py:
      - Test 17: `MonsterDriver.drive(channel_id, campaign_name, current_actor)` is a no-op when `current_actor.player_id is not None` (it's a PC turn — not the driver's job).
      - Test 18: On monster-actor turn, driver picks a target uniformly at random from `parse_get_game_state(...).combatants` where `player_id is not None AND character_id != current_actor.character_id` (PCs only, exclude the monster itself). Uses injectable `random.choice` for determinism in tests.
      - Test 19: Driver calls `mcp_tools.combat_action(action='attack', attacker=monster_actor.character_id, target=chosen_pc.character_id)` through `bot.rate_limiter.acquire(channel_id)` (mutating per D-29).
      - Test 20: On `AttackOutcome.MISS` or `AttackOutcome.NATURAL_ONE`, driver calls `reactions.check_riposte_eligibility(...)` then, if non-None, `reactions.surface_riposte_button(...)`. On HIT/CRITICAL, driver does NOT call reactions.
      - Test 21: After resolution (regardless of outcome), driver calls `mcp_tools.next_turn(campaign_name=...)` to advance the turn — same rate_limiter.
      - Test 22: When the initiative list has zero eligible PC targets (e.g. all PCs are downed), driver logs `monster_driver_no_eligible_target` WARNING and still calls `next_turn` to advance (does NOT call combat_action).
      - Test 23: Driver code-level TODO: `# Phase 5 v1 ships random targeting per user D-B; Phase 6+ may add Claudmaster-driven smart targeting (REQ TODO).`

    PartyModeOrchestrator monster-turn dispatch (gameplay/party_mode.py):
      - Test 24: When the orchestrator's COMBAT-tick observes that the current actor has `player_id is None`, it awaits `monster_driver.drive(channel_id, campaign_name, current_actor)` exactly once per turn (idempotent via tracking `(channel_id, round_number, current_actor.character_id)` as the last-driven key to prevent double-fires on consecutive ticks).
      - Test 25: When the same monster's turn appears on two consecutive ticks (e.g. dm20 hasn't yet advanced), driver is NOT called again — last-driven key matches.

    RiposteButton.callback (bot/dynamic_items.py — promoted from Phase 2 stub):
      - Test 26: Wrong-user click → `send_warning(WarningKind.INVALID_ACTION, reason="Only the targeted player can Riposte.")` (ephemeral); timer row status unchanged.
      - Test 27: Click on a row with `status='expired'` (sweeper already marked it) → `send_warning(WarningKind.RIPOSTE_EXPIRED)`; no combat_action issued.
      - Test 28: Click on a row with `deadline_ts < now()` (even if still pending — sweeper hadn't run yet) → bot marks expired itself, sends `RIPOSTE_EXPIRED` warning, deletes the public message best-effort.
      - Test 29: Successful click: `mcp_tools.combat_action(action='attack', attacker=row.character_id, target=row.monster_uuid, weapon_or_spell=row.weapon_used)` is awaited through `bot.rate_limiter.acquire(channel_id)`; on success, `repo.mark_consumed_with_round(id, current_round)` is called; the public message is deleted; an ephemeral "✅ Riposte!" followup is sent.
      - Test 30: Concurrent clicks (asyncio.gather of two click events) — only ONE results in mark_consumed; the second sees status='consumed' and emits `RIPOSTE_EXPIRED`. Implementation today uses a simple status check; Plan 02 hardens this via the per-channel asyncio.Lock — note in the callback docstring that lock-wrapping is added in Plan 02.

    AttackButton._maybe_surface_riposte DELETION (D-A):
      - Test 31: `grep -c "_maybe_surface_riposte" src/eldritch_dm/bot/dynamic_items.py` returns 0.
      - Test 32: `grep -c "_maybe_surface_riposte" src/eldritch_dm/bot/` returns 0 (no orphan references anywhere).
      - Test 33: The existing `tests/bot/test_dynamic_items_combat_real.py` AttackButton tests still pass after the deletion (no regression — the seam was a no-op).

    WarningKind.RIPOSTE_EXPIRED (bot/warnings.py):
      - Test 34: New `WarningKind.RIPOSTE_EXPIRED = "riposte_expired"` exists; `send_warning(WarningKind.RIPOSTE_EXPIRED)` produces an ephemeral with text matching the existing per-kind dispatcher pattern.
  </behavior>
  <action>
    Create `src/eldritch_dm/gameplay/combat_outcome_parser.py` per RESEARCH Pattern 1 verbatim. StrEnum + module-level compiled regex with re.MULTILINE. Module docstring cites dm20's `_format_combat_result` (main.py:1839-1873) as the source-of-truth for the headers.

    Create `src/eldritch_dm/gameplay/reactions.py`:
      - Module docstring: cite RESEARCH Patterns 2-3, the D-A/B/C decisions, and the "public message NOT ephemeral" decision (with the COMBAT-11 rationale).
      - `@dataclass(frozen=True) class RiposteEligibility`: `character_id: str`, `user_id: int`, `primary_weapon: str | None`.
      - `ELIGIBLE_CLASS_SUBCLASSES: frozenset[tuple[str, str]] = frozenset({("fighter", "battle master")})` with a TODO comment block (multiline) per RESEARCH Open Q3 spelling out v2 YAML-configurable eligibility.
      - `async def check_riposte_eligibility(*, channel_id, character_id, user_id, primary_weapon, current_round, pc_classes_repo, riposte_timers_repo) -> RiposteEligibility | None` — implementation per RESEARCH Pattern 2 (but reads from PCClassesRepo, not a generic lookup callable).
      - `async def surface_riposte_button(*, channel: discord.TextChannel, eligibility, monster_uuid, round_number, repo, ttl_seconds, log) -> int` — per RESEARCH Pattern 3 verbatim. Insert row first with placeholder message_id="" and a temporary deadline (NOW + ttl, will be overwritten); construct the View with `timeout=None`; channel.send a public message with `<@user_id>` mention; recompute deadline_ts = datetime.utcnow() + timedelta(seconds=ttl_seconds) (Pitfall 1); call repo.update_message_ref with the real message_id, custom_id=f"riposte:{row.id}:{user_id}", and the recomputed deadline. Return row.id.
      - Helper `async def handle_riposte_click(*, interaction, timer_id, expected_user_id, repo, mcp, rate_limiter, log, current_round_provider) -> None` extracted so RiposteButton.callback is small. This is the function Plan 02 will wrap in a per-channel asyncio.Lock; document the seam at the top of the function with a `# PLAN-02-LOCK-SEAM:` marker comment.

    Create `src/eldritch_dm/gameplay/monster_driver.py`:
      - `class MonsterDriver` with constructor: `mcp: MCPClient`, `rate_limiter: ChannelRateLimiter`, `pc_classes_repo`, `riposte_timers_repo`, `random_choice: Callable[[Sequence], Any] = random.choice` (injectable), `log` bound logger.
      - `async def drive(self, *, channel_id, campaign_name, current_actor) -> None`:
        1. Early-return if current_actor.player_id is not None.
        2. Fetch fresh `get_game_state(campaign_name=...)`, parse → CombatState.
        3. Collect eligible PC targets: `[c for c in state.combatants if c.player_id is not None and c.character_id != current_actor.character_id]`.
        4. If empty list: log warning, await next_turn through rate_limiter, return.
        5. Pick target via `self._random_choice(targets)`.
        6. Acquire rate_limiter, call `combat_action(action='attack', attacker=current_actor.character_id, target=target.character_id)` — capture the text result.
        7. Parse outcome via `parse_combat_outcome(result_text)`.
        8. If outcome in {MISS, NATURAL_ONE}: lookup `target.user_id` via `channel_sessions` / discord member resolution (CombatState.Combatant should already carry user_id — verify; if not, look up via `channel_sessions.character_user_map(channel_id)`). Call `reactions.check_riposte_eligibility(...)`. If non-None, await `reactions.surface_riposte_button(channel=bot.get_channel(int(channel_id)), eligibility, monster_uuid=current_actor.character_id, round_number=state.round_number, repo=riposte_timers_repo, ttl_seconds=settings.riposte_ttl_seconds, log=log)`.
        9. Regardless of outcome (or no eligibility), call `next_turn(campaign_name=...)` through rate_limiter.
      - structlog binding: every step binds `channel_id, monster_id=current_actor.character_id, round_number, action_kind='monster_attack'`.
      - **The TODO comment per D-B is mandatory:** `# Phase 5 v1: random PC targeting (user decision D-B). v2 may add Claudmaster-driven smart targeting; see REQUIREMENTS REACT-* family.`

    Wire MonsterDriver into PartyModeOrchestrator (gameplay/party_mode.py):
      - In the COMBAT-cadence branch of the orchestrator loop, after detecting state.current_actor, if `current_actor.player_id is None`, await `self._monster_driver.drive(...)`. Track last-driven via `self._last_monster_drive: dict[str, tuple[int, str]] = {}` mapping channel_id → (round_number, monster_character_id); skip if unchanged.
      - Add `monster_driver: MonsterDriver` to the orchestrator constructor; setup_hook wiring in bot.py instantiates it with all dependencies.

    Add `WarningKind.RIPOSTE_EXPIRED` to `bot/warnings.py` and its dispatcher message ("⚔️ Riposte window expired or already used.").

    Promote `RiposteButton.callback` in `bot/dynamic_items.py` (delete the Phase 2 stub log line "phase2_stub_callback_invoked" for RiposteButton). Callback:
      1. `await interaction.response.defer(ephemeral=True)` (EDM001).
      2. Delegate to `reactions.handle_riposte_click(interaction, timer_id=self.timer_id, expected_user_id=self.user_id, repo=interaction.client.riposte_timers, mcp=interaction.client.mcp, rate_limiter=interaction.client.rate_limiter, log=log, current_round_provider=lambda: <get_current_round_for_channel>)`. The current-round-provider helper lives on the bot (`bot.current_round_for_channel(channel_id)` — fetch `parse_get_game_state(get_game_state(...))` cached for ≤500ms, executor's choice on cache structure; OK to just re-fetch).
      3. The handler returns; callback returns. All branching (wrong user / expired / late / success) lives in `handle_riposte_click`.

    **DELETE `AttackButton._maybe_surface_riposte` and the callsite at line 829.** Single atomic commit (D-A). Test 31-33 prove the deletion is clean.

    Wire MonsterDriver onto `EldritchBot` in `bot/bot.py`:
      - Construct `self.monster_driver = MonsterDriver(mcp=self.mcp, rate_limiter=self.rate_limiter, pc_classes_repo=self.pc_classes, riposte_timers_repo=self.riposte_timers, log=log)` in setup_hook AFTER existing rate_limiter / pc_classes / riposte_timers are constructed.
      - Pass it to the existing `PartyModeOrchestrator(...)` construction (extend the orchestrator's __init__ signature).

    Add `bot.pc_classes: PCClassesRepo` and `bot.riposte_timers: RiposteTimerRepo` as bot attributes (likely already exists for riposte_timers; pc_classes is new).

    Ingest-time pc_classes upsert (bot/cogs/ingest.py):
      - In the existing `_create_character_flow` or wherever `dm20__create_character` returns successfully, after recording the character, also call `await bot.pc_classes.upsert(channel_id=str(interaction.channel_id), character_id=created.character_id, class_name=parsed.class_name, subclass=parsed.subclass)`. Use the `CharacterSheet` model fields the ingest pipeline already parses (Phase 3 INGEST-07).
      - If the parsed sheet has no subclass (level 1-2 characters), pass empty string "" — the PCClassesRepo validator normalizes it.

    Write all 34 tests across the 4 new test files. Use AsyncMock for MCPClient, fake combatants for `parse_get_game_state` results, and the same async fixture style as Phase 4 tests.
  </action>
  <verify>
    <automated>uv run pytest tests/gameplay/test_combat_outcome_parser.py tests/gameplay/test_reactions.py tests/gameplay/test_monster_driver.py tests/gameplay/test_riposte_callback.py tests/bot/test_dynamic_items_combat_real.py -x -v && grep -c "_maybe_surface_riposte" src/eldritch_dm/bot/dynamic_items.py | tee /tmp/gate.txt && [ "$(cat /tmp/gate.txt)" = "0" ]</automated>
  </verify>
  <done>
    `_maybe_surface_riposte` is fully deleted (grep returns 0); MonsterDriver random-targets eligible PCs and surfaces Riposte on miss/nat1 via the public-message + permission-gate pattern; RiposteButton.callback runs the full gate→combat_action→mark_consumed_with_round→cleanup sequence; reaction-budget is enforced by `consumed_in_round`-aware eligibility; 30+ tests green; existing Phase 4 tests still pass.
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 3: setup_hook wiring + RiposteButton rehydration + end-to-end smoke (RED→GREEN)</name>
  <files>
    src/eldritch_dm/bot/setup_hook.py,
    src/eldritch_dm/bot/bot.py,
    tests/bot/test_setup_hook.py,
    tests/integration/test_riposte_smoke.py
  </files>
  <behavior>
    setup_hook (bot/setup_hook.py):
      - Test 1: `_get_dynamic_item_classes()` includes `RiposteButton` (already true from Phase 2 — assert it still does; regression guard since this plan modifies dynamic_items.py heavily).
      - Test 2: After bot.setup_hook completes, `bot.pc_classes` is a PCClassesRepo and `bot.monster_driver` is a MonsterDriver instance.
      - Test 3: The PartyModeOrchestrator instance on `bot.orchestrator` has a non-None `_monster_driver` reference.

    Restart-survival of RiposteButton's DynamicItem registration:
      - Test 4: Seed `persistent_views` with a row keyed `riposte:42:99` + a fake channel_session in COMBAT. Build a fresh bot, run setup_hook (mocked). Assert the bot's dynamic item registry contains `RiposteButton` ready to dispatch an incoming click with custom_id `riposte:42:99`. (No real Discord interaction — pure class_map check.)
      - Test 5: A click event with custom_id matching the regex routes to `RiposteButton.callback` (verified via `_PARAM_REMAP` if needed; the existing template `riposte:(?P<timer_id>\d+):(?P<user_id>\d+)` does NOT need a remap since param names match — assert no entry needed in `_PARAM_REMAP` for "timer_id"/"user_id"; if Phase 4 added one accidentally, remove it).

    End-to-end smoke (tests/integration/test_riposte_smoke.py — happy path only; the restart-survival drill is OPS-01 in Plan 02):
      - Test 6: Synthetic monster-attack scenario end-to-end with mocks: seed channel_sessions (state=COMBAT, round=1), seed pc_classes (Battle Master Fighter), drive MonsterDriver against a synthetic get_game_state returning monster as current_actor + one BM Fighter PC + one wizard PC. Force `random.choice` to pick the BM. Mock combat_action to return "**Miss.** Goblin Scout misses Thorin." Assert:
          - `riposte_timers` has exactly one row with status='pending', user_id=BM's user_id, monster_uuid=monster_character_id, weapon_used populated, deadline_ts ~8s in future.
          - The mocked channel.send received a content string containing `<@{bm_user_id}>` and a non-empty View.
          - `next_turn` was called after the surface.
      - Test 7: Same scenario but monster attacks the wizard (force random.choice to pick wizard). Assert: NO riposte row created (wizard not eligible); next_turn still called.
      - Test 8: Same scenario but a previous riposte row already exists with `consumed_in_round=1` for the BM. Assert: NO new riposte row (budget exhausted); next_turn still called.

    Smoke uses respx for MCP HTTP layer and AsyncMock for discord.TextChannel/Interaction. Keep total wall-clock under 2s.
  </behavior>
  <action>
    Verify `_get_dynamic_item_classes()` in `bot/setup_hook.py` already includes `RiposteButton` (Phase 2 added it — regression-test only; no edit unless missing).

    Construct in `EldritchBot.setup_hook` AFTER existing Phase 4 rate_limiter / batch_coordinator construction:
      1. `self.pc_classes = PCClassesRepo(db_path=self._db_path)` — share the same path used by other repos.
      2. `self.riposte_timers` (likely already exists from Phase 1 — verify and add if missing).
      3. `self.monster_driver = MonsterDriver(...)` with all dependencies.
      4. Update PartyModeOrchestrator construction to pass `monster_driver=self.monster_driver`.

    `bot.current_round_for_channel(channel_id) -> int` helper:
      - Implementation: `state = parse_get_game_state(await get_game_state(self.mcp, campaign_name=session.campaign_name)); return state.round_number`.
      - No caching for v1; called rarely (only on Riposte clicks). Plan 02 may add caching if profiling shows a hotspot.

    Update `tests/bot/test_setup_hook.py` to add the three new attribute checks (pc_classes, monster_driver, orchestrator wiring).

    Create `tests/integration/test_riposte_smoke.py` with the three end-to-end scenarios. Use the same respx + AsyncMock fixtures as `tests/integration/test_combat_flow.py` from Phase 4 (precedent).
  </action>
  <verify>
    <automated>uv run pytest tests/bot/test_setup_hook.py tests/integration/test_riposte_smoke.py -x -v && uv run ruff check src/eldritch_dm/gameplay/ src/eldritch_dm/bot/dynamic_items.py src/eldritch_dm/persistence/ && uv run lint-imports</automated>
  </verify>
  <done>
    setup_hook wires pc_classes + monster_driver + orchestrator-with-monster-driver; RiposteButton dispatches correctly post-restart (class_map check); 3 happy-path smoke scenarios prove the monster→miss→surface→eligibility-respected path; ruff + lint-imports clean.
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| Discord user → RiposteButton.callback | Untrusted click; gated by `interaction.user.id == row.user_id` (T-05-01). |
| MonsterDriver → dm20 | Server-internal; rate-limited (OPS-03 via ChannelRateLimiter). |
| Player ingest sheet → pc_classes upsert | Untrusted parse output already validated by Phase 3 INGEST-07 pydantic CharacterSheet; we trust that and store lowercased. |
| Sweeper (Plan 02) ↔ RiposteButton.callback | Per-channel asyncio.Lock seam — documented here (PLAN-02-LOCK-SEAM marker in reactions.handle_riposte_click); fully enforced in Plan 02. |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-05-01 | Spoofing | RiposteButton.callback | mitigate | `interaction.user.id != row.user_id` → `WarningKind.INVALID_ACTION` ephemeral; structured log line `riposte_wrong_user_rejected` with both ids. |
| T-05-02 | Tampering | combat_outcome_parser regex against dm20 text | accept | dm20 format strings are hand-coded in source (RESEARCH Q3 stable); integration test pinned to dm20 source if it ever drifts. |
| T-05-03 | Tampering | Reaction budget bypass — duplicate riposte click in same round | mitigate | Eligibility check rejects when any `consumed_in_round == current_round` row exists; surface_riposte_button is never called twice in a round. Test 11 + 30 + 8. |
| T-05-04 | Tampering | Click-at-deadline race vs sweeper | mitigate (PARTIAL — Plan 02 finishes) | Plan 01 ships the status check (callback returns RIPOSTE_EXPIRED on already-marked row); Plan 02 adds per-channel `asyncio.Lock` wrapping read-then-mark. PLAN-02-LOCK-SEAM marker in reactions.handle_riposte_click. |
| T-05-05 | Repudiation | "I never clicked Riposte" | mitigate | Every callback path structured-logs `timer_id, user_id, channel_id, outcome` (success/expired/wrong-user); audit trail in stdout. |
| T-05-06 | Information Disclosure | Public Riposte button broadcasts game state | accept | Per RESEARCH Pattern 3 tradeoff: ephemeral is incompatible with restart-survival (COMBAT-11). Public + permission gate is the only architecturally-correct path; broadcast is arguably feature-positive. |
| T-05-07 | DoS | Spam-click Riposte to thrash dm20 | mitigate | `bot.rate_limiter.acquire(channel_id)` gates the combat_action call (OPS-03 200ms cap from Phase 4); `status='consumed'` check after first success makes further clicks no-ops. |
| T-05-08 | Tampering | Subclass drift after level-up (Pitfall 5) | accept (v1) | RESEARCH Pitfall 5 — v1 trusts pc_classes from ingest. v2 may add `validate_character_rules` re-sync per RESEARCH Mitigation. Document in `reactions.py` module docstring. |
| T-05-09 | Elevation of Privilege | MonsterDriver mis-targets a PC across channels | mitigate | get_game_state is campaign-scoped; MonsterDriver passes campaign_name from `channel_sessions` row; cross-channel targeting is structurally impossible. |
| T-05-SC | Supply chain | No new third-party packages | accept | Plan 01 introduces zero new pip dependencies — stdlib + existing pins only. RESEARCH § Package Legitimacy Audit confirmed. |
</threat_model>

<verification>
**Plan-level checks (in addition to per-task `<verify>`):**

1. `uv run pytest tests/persistence/test_riposte_timers_repo.py tests/persistence/test_pc_classes_repo.py tests/persistence/test_bootstrap.py tests/gameplay/test_combat_outcome_parser.py tests/gameplay/test_reactions.py tests/gameplay/test_monster_driver.py tests/gameplay/test_riposte_callback.py tests/bot/test_dynamic_items_combat_real.py tests/bot/test_setup_hook.py tests/integration/test_riposte_smoke.py -v` — all green.
2. `uv run ruff check src/eldritch_dm/gameplay/ src/eldritch_dm/persistence/pc_classes_repo.py src/eldritch_dm/persistence/bootstrap.py src/eldritch_dm/bot/dynamic_items.py` — clean.
3. `uv run lint-imports` — passes; gameplay → persistence is allowed; gameplay does not import bot.
4. `grep -v '^#' src/eldritch_dm/bot/dynamic_items.py | grep -c '_maybe_surface_riposte'` — returns 0. (per D-A; uses comment-stripped count to avoid self-invalidating doc references.)
5. `grep -v '^#' src/eldritch_dm/gameplay/reactions.py | grep -c '("rogue", "swashbuckler")'` — returns 0. (per D-C strict RAW.)
6. `grep -c 'PLAN-02-LOCK-SEAM' src/eldritch_dm/gameplay/reactions.py` — returns ≥1 (the seam marker for Plan 02).
7. Full prior test suite still green: `uv run pytest -q` — 728+ tests pass (no regressions). Riposte tests bring total to ~760.

**Risks:**
- **MonsterDriver targeting fidelity:** v1 random-target may produce "boring" combat (every PC attacked equally often). Acceptable per D-B; v2 work item.
- **`pc_classes` ingest gap:** If a Phase 5 self-hoster runs the bot on an existing eldritch.sqlite3 from Phase 3 (before this plan), pc_classes will be empty for already-ingested characters. Eligibility silently fails (returns None — safe). Document in Plan 03's README "Upgrading from a Phase 4 deployment" section. Plan 03 adds a one-shot backfill script as Claude's discretion.
- **Outcome parser brittleness:** RESEARCH Pitfall on dm20 format-string changes. Mitigation: gated `RUN_INTEGRATION=1` integration test against real dm20 (out of scope for this plan; documented as a follow-up).
- **The PLAN-02-LOCK-SEAM** is a deliberate two-plan handoff. Plan 01 ships a status-check-based correctness path; Plan 02 hardens it under sweeper contention. The Plan-01-only path is correct under single-click scenarios but the test in Test 30 currently passes by luck of the status-check ordering — Plan 02 makes it robust under load. Plan 02's tests prove the hardening.

**Open question (resolved here):**
- Whether `RiposteButton`'s callback should re-fetch current_round on every click or cache it. Lean re-fetch (no cache); Riposte clicks are rare; Plan 02 may add caching if profiling shows it matters.
</verification>

<success_criteria>
- `database/schema.sql` adds `pc_classes` table; `persistence/bootstrap.py` idempotently ALTERs `riposte_timers` to add `consumed_in_round INTEGER`.
- `PCClassesRepo` upserts + gets case-folded class/subclass; tests prove second upsert is an UPDATE, not duplicate.
- `RiposteTimerRepo` exposes `list_for_character`, `mark_cancelled`, `update_message_ref`, `mark_consumed_with_round`.
- `gameplay/combat_outcome_parser.py` correctly classifies all four dm20 outcome headers from raw text.
- `gameplay/reactions.py` ships `ELIGIBLE_CLASS_SUBCLASSES = {("fighter", "battle master")}` (RAW only per D-C); enforces reaction-per-round via consumed_in_round; ships `surface_riposte_button` with the post-channel-send deadline-recompute (Pitfall 1).
- `gameplay/monster_driver.py` ships a minimal random-target driver per D-B; logs and TODOs document the v2 smart-targeting deferral.
- `AttackButton._maybe_surface_riposte` is DELETED per D-A; grep -c (comment-stripped) returns 0.
- `RiposteButton.callback` runs the full gate-and-dispatch sequence; sets `consumed_in_round=current_round` atomically.
- Ingest cog upserts pc_classes after every successful character creation.
- PartyModeOrchestrator detects monster-actor turns and delegates to MonsterDriver exactly once per turn (no double-fire).
- 30+ new tests pass; existing 728 Phase 4 tests still pass; ruff + lint-imports clean.
- Requirements COMBAT-09 and COMBAT-10 are functionally satisfied (final [x] marks in REQUIREMENTS.md happen in Plan 03's closure).
</success_criteria>

<output>
On completion, create `.planning/phases/05-reactions-self-host-polish/05-01-SUMMARY.md` per the standard template, including:
- new files + LOC counts
- decisions made (any divergence from CONTEXT D-XX with justification, especially D-04 → D-C correction)
- test count delta (~30 new)
- the PLAN-02-LOCK-SEAM marker location (file + line) so Plan 02's executor finds it instantly
- next-plan readiness signal: "Plan 02 may now wrap reactions.handle_riposte_click and the sweeper's mark-expired in a shared per-channel asyncio.Lock; both code paths exist."
</output>
