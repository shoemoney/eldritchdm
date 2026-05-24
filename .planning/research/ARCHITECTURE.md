<!-- generated-by: gsd researcher (v1.1 Polish milestone) -->
# v1.1 Architecture Integration Research

**Milestone:** v1.1 Polish
**Date:** 2026-05-23
**Confidence:** HIGH (all findings verified against current source)
**Scope:** How v1.1's 7 deliverables fit into the existing layered architecture.

## TL;DR

All 7 v1.1 items fit inside the existing 7 import-linter contracts **without
adding a new layer**. The only new module is a single YAML loader (lives in
`gameplay/`). The largest item — Smart MonsterDriver — is a parameter swap
plus one new `mcp_tools` wrapper plus an in-process cache; it does **not**
need a new layer or contract. Build order is dictated by test-debt: ruff
cleanup first (so subsequent diffs aren't fighting 79 pre-existing errors),
then the small fixes (SAN-01, OPS-02, `__main__`, backfill), then YAML
eligibility, then Smart MonsterDriver last (largest blast radius).

---

## 1. Smart MonsterDriver Integration

### 1.1 Import-linter contract impact — none

`gameplay/monster_driver.py` already imports `eldritch_dm.mcp.tools` (see
line 54 of the file: `from eldritch_dm.mcp import tools as mcp_tools`). The
existing contract `gameplay must not import bot or ingest` does NOT forbid
`gameplay → mcp`. Smart targeting is just additional `mcp_tools.*` calls
from the same module.

**No new contract needed. No layer change.**

### 1.2 Which MCP tool to call — verified

`src/eldritch_dm/mcp/tools.py` already has wrappers for the two relevant
dm20 tools:

| Wrapper | dm20 tool | Status |
|---|---|---|
| `party_thinking` | `dm20__party_thinking` | Exists (line 188) |
| `party_get_prefetch` | `dm20__party_get_prefetch` | Exists (line 203) |
| `get_claudmaster_session_state` | `dm20__get_claudmaster_session_state` | Exists (line 347) |
| `player_action` | `dm20__player_action` | Exists (line 510) |
| **`claudmaster_choose_target`** | **`dm20__claudmaster_choose_target`** | **MISSING — must add** |

The Smart driver's "ask Claudmaster who to attack" path needs a new wrapper
in `mcp/tools.py` plus an entry in `TOOL_TO_FUNCTION`. v1.1 research should
confirm the dm20 tool name; if dm20 exposes the decision via
`get_claudmaster_session_state` (returning a `next_target` field) instead of
a dedicated tool, **prefer that** — fewer wrappers, less surface area.

### 1.3 Caching — per-channel in-memory, scoped to (round, monster_id)

The orchestrator already tracks `self._last_monster_drive: dict[str,
tuple[int, str]]` keyed by `(round_number, character_id)` for idempotency
(`gameplay/party_mode.py:115`). Reuse that same shape:

```python
# In MonsterDriver
self._target_cache: dict[str, tuple[int, str, str]] = {}
#                        channel_id → (round, monster_id, chosen_target_id)
```

Cache lives in the MonsterDriver instance (one per bot), invalidates
naturally because (round_number, monster_id) is unique. **No persistence
needed** — restart starts a fresh combat tick anyway, dm20 owns the
authoritative game state.

**Do NOT use dm20's `party_get_prefetch`** for this — prefetch is keyed on
`turn_id` (PC turns), not monster turns; the prefetch payload is narration
warm-up, not targeting.

### 1.4 Error / fallback path — graceful degrade to random

The Smart driver must NEVER deadlock combat. Failure modes and responses:

| Failure | Response |
|---|---|
| `MCPCircuitOpen` | Fall back to existing `random.choice` path, log `monster_driver_circuit_open_fallback_random` |
| `MCPTimeoutError` (30s read timeout) | Fall back to random, log warning |
| `MCPToolError` (4xx — bad arguments) | Fall back to random, log `monster_driver_smart_target_4xx` at ERROR level (likely a bug, surface to ops) |
| Claudmaster returns "no target" / empty | Fall back to random (defensive — match `no_eligible_target` branch shape) |
| Returned `target_id` not in our `pcs` list | Fall back to random, log `monster_driver_smart_target_unknown_id` — Claudmaster may have stale state |
| All targets dead / monster killed mid-think | Existing `targets = [p for p in pcs if ...]` filter handles it, advance turn |

Wrap the smart call in `try/except (MCPError, KeyError, ValueError)` and
delegate to a private `_pick_random_target` helper on the failure branch.

### 1.5 `MONSTER_DRIVER` env var — yes

Add a `monster_driver_mode: Literal["smart", "random"] = "smart"` field to
`Settings` (env var `ELDRITCH_MONSTER_DRIVER_MODE`). Wire through
`bot/bot.py` constructor → MonsterDriver. Defaults to `"smart"`; tests and
INT≤4 monsters (future work) can force `"random"`. The driver class itself
should accept a `mode: str` constructor kwarg — orchestrator passes
`settings.monster_driver_mode`.

**Per-monster override (INT≤4 always-random) is OUT of v1.1 scope** — the
roadmap should note it as a v1.2 candidate. v1.1 ships the channel-wide
toggle.

### 1.6 New / modified files

| File | Change |
|---|---|
| `src/eldritch_dm/gameplay/monster_driver.py` | Add `_pick_smart_target` method, `mode` kwarg, `_target_cache` |
| `src/eldritch_dm/mcp/tools.py` | Add `claudmaster_choose_target` wrapper + `TOOL_TO_FUNCTION` entry (or use existing `get_claudmaster_session_state` — TBD by Phase 1 of this milestone) |
| `src/eldritch_dm/config.py` | Add `monster_driver_mode` Settings field |
| `src/eldritch_dm/bot/bot.py` | Pass `settings.monster_driver_mode` to MonsterDriver |
| `tests/gameplay/test_monster_driver_smart.py` | NEW — covers smart-path success, every fallback branch, cache hit/miss |

---

## 2. YAML Riposte Eligibility Integration

### 2.1 File location — in-repo defaults + per-install override

Three-tier resolution (closest wins):

```
1. $ELDRITCH_ELIGIBILITY_YAML  (env override — tests, ops)
2. ./eligibility.yaml          (per-install — sits next to .env)
3. database/eligibility.yaml   (in-repo default — Battle Master only)
```

Ship a `database/eligibility.yaml` with the v1.0 D-C frozenset so vanilla
installs work identically to v1.0. The `.env.example` documents
`ELDRITCH_ELIGIBILITY_YAML` for advanced users. **Per-user
(`~/.eldritch/`) is NOT recommended** — this bot is per-server, not
per-user; mixing user-scoped config into a server-scoped bot would surprise
self-hosters.

### 2.2 Load timing — startup-only, fail-fast

Load once in `bot.setup_hook` BEFORE orchestrators start. The loaded
frozenset replaces the module-level `ELIGIBLE_CLASS_SUBCLASSES` in
`gameplay/reactions.py` via a setter, OR — cleaner — `reactions.py`
accepts an injected `eligibility_set: frozenset[tuple[str, str]]` and the
module-level constant becomes the in-repo default.

**No hot-reload in v1.1.** Hot-reload would require a file watcher
(`watchfiles`?) — out of scope. Self-hosters restart the bot to pick up
changes. Document this in the YAML's header comment.

**Fail-fast on malformed YAML at startup.** Better to refuse to boot with
a clear "your eligibility.yaml has a typo on line 7" than to boot with
silent empty eligibility (turns Riposte off without warning).

### 2.3 Schema — pydantic v2 model

```python
# gameplay/eligibility_loader.py
class EligibilityFile(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: int = 1            # for forward-compat migration
    eligible: list[ClassSubclass]

class ClassSubclass(BaseModel):
    model_config = ConfigDict(extra="forbid")
    class_name: str
    subclass: str
    # field_validator runs the same _normalize() used by PCClassesRepo
```

`load_eligibility(path: Path | None = None) → frozenset[tuple[str, str]]`
applies the same normalization as `PCClassesRepo._normalize` (lowercase +
whitespace-collapse). **Re-use the existing helper** by importing
`from eldritch_dm.persistence.pc_classes_repo import _normalize` — that
import is allowed under the current import-linter contracts because
`gameplay` may import from `persistence` (the only forbidden direction is
`gameplay → bot/ingest`).

Wait — that's not quite right. `_normalize` is a private function. Cleaner:
**move `_normalize` to a small new `gameplay/normalize.py`** module (pure
stdlib `re`, no deps), and have both `pc_classes_repo` and the new YAML
loader import it. This avoids the awkward private-import-across-packages
smell.

### 2.4 Interaction with `pc_classes` table — none

`pc_classes` table still stores per-PC (class, subclass) — unchanged. YAML
provides the **eligibility set** (which combinations grant Riposte). The
eligibility check in `reactions.check_riposte_eligibility` does:

```python
key = (info.class_name, info.subclass)   # from pc_classes table
if key not in eligibility_set:           # from YAML
    return None
```

Same logic as today. Only difference: `eligibility_set` is now
constructor-injected instead of a module-level constant.

### 2.5 New / modified files

| File | Change |
|---|---|
| `database/eligibility.yaml` | NEW — ships v1.0 D-C set |
| `src/eldritch_dm/gameplay/eligibility_loader.py` | NEW — pydantic schema + `load_eligibility()` |
| `src/eldritch_dm/gameplay/normalize.py` | NEW — extract `_normalize` (used by repo + loader) |
| `src/eldritch_dm/gameplay/reactions.py` | Accept injected `eligibility_set` (default = module constant for backwards compat in tests) |
| `src/eldritch_dm/persistence/pc_classes_repo.py` | Import `_normalize` from the new module |
| `src/eldritch_dm/bot/setup_hook.py` | Call `load_eligibility()` before constructing reaction handlers |
| `src/eldritch_dm/config.py` | Add `eligibility_yaml_path: Path \| None = None` Settings field |
| `.env.example` | Document `ELDRITCH_ELIGIBILITY_YAML` |
| `tests/gameplay/test_eligibility_loader.py` | NEW |

**Import-linter:** all changes stay inside `gameplay` + `persistence`
+ `config` + `bot/setup_hook.py`. No new contract.

---

## 3. `pc_classes` Ingest-Backfill Script

### 3.1 Location — packaged module, console-script entry point

`src/eldritch_dm/scripts/backfill_pc_classes.py` (NEW package `scripts/`).
Importable from tests; runnable as `python -m eldritch_dm.scripts.backfill_pc_classes`.

Add to `pyproject.toml`:

```toml
[project.scripts]
eldritch-dm = "eldritch_dm.bot.__main__:main"
eldritch-dm-backfill = "eldritch_dm.scripts.backfill_pc_classes:main"
```

After `pip install -e .` self-hosters run `eldritch-dm-backfill` from
PATH. Mirrors the existing `eldritch-dm` console script (D-23).

### 3.2 dm20 communication — re-use `MCPClient`

**Do NOT call `dm20__get_character` directly with `httpx`.** Re-use the
existing `MCPClient` + `mcp_tools.get_character` / `mcp_tools.list_characters`
wrappers. That gives us:

- The same retry/timeout/circuit-breaker behavior the bot uses
- Structured logging via `structlog`
- Zero divergence in error handling

Script construction mirrors `run.py`'s pattern:

```python
async def _run() -> int:
    settings = Settings()
    configure_logging(...)
    mcp = MCPClient(base_url=settings.omlx_url, ...)
    repo = PCClassesRepo(db_path=settings.eldritch_db_path)
    # iterate channel_sessions → list_characters per session →
    #   parse class+subclass from character dict → repo.upsert
```

### 3.3 Locking — refuse to run if bot is live

The bot opens the DB with WAL, and writes go through `WriterQueue`. The
backfill script also writes (via `PCClassesRepo.upsert`). Two writers
on WAL → `SQLITE_BUSY` after the 5s busy_timeout.

**Refuse to run if a bot process is detected.** Two cheap checks:

1. **PID file** — write `eldritch.pid` from `bot.setup_hook`, delete on
   shutdown. Backfill checks for it.
2. **`PRAGMA wal_checkpoint(PASSIVE)` test** — if it returns non-zero
   `busy` count, another writer is active.

Recommend (1) (PID file) — explicit, cross-platform, and consistent with
launchd / systemd patterns already in v1.0 (`HOST-04`).

### 3.4 Logging — structlog (matches the bot)

Use the same `configure_logging(...) + get_logger(__name__)` pattern as
`run.py`. Self-hosters running the backfill see the same JSON / console
output they're used to. **Do not use `print()` or `rich`** — adds a dep,
breaks log aggregation.

Add a `--dry-run` flag (default off) that prints what would change
without writing. Add a `--channel-id` flag to scope the backfill.

### 3.5 New / modified files

| File | Change |
|---|---|
| `src/eldritch_dm/scripts/__init__.py` | NEW (empty) |
| `src/eldritch_dm/scripts/backfill_pc_classes.py` | NEW |
| `pyproject.toml` | Add `[project.scripts]` entry |
| `tests/scripts/test_backfill_pc_classes.py` | NEW — mocks MCPClient, asserts upserts |
| `src/eldritch_dm/bot/setup_hook.py` | Add PID-file write |
| `src/eldritch_dm/bot/bot.py` | Add PID-file cleanup in shutdown chain |

**Import-linter:** new `scripts/` package needs a contract entry — same
as `gameplay`: may import `mcp`, `persistence`, `config`, `logging`; may
NOT import `bot` or `ingest`. Add one new `[[tool.importlinter.contracts]]`
block.

---

## 4. Sanitizer Expansion (SAN-01) Integration

### 4.1 Current state — only `exploration.py` wired

`make_async_audit_callback(repo)` is wired exactly once in
`bot/setup_hook.py` and passed into the ExplorationCog declare-action flow.
`WeaponSelectModal.on_submit` (line 469) and `CharacterReviewModal.on_submit`
(line 206) are **not yet sanitized.**

### 4.2 Access pattern — bot instance attribute

The cleanest path: store the audit callback on `bot` as
`bot.sanitizer_audit_callback`, set in `setup_hook`. Both modals are
constructed by their cogs (not by the bot directly), so the cog passes
the callback into the modal constructor as a kwarg.

| Modal | Cog that constructs it | Existing constructor pattern |
|---|---|---|
| `WeaponSelectModal` | `bot/cogs/combat.py` | already takes `on_submit_cb` |
| `CharacterReviewModal` | `bot/cogs/ingest.py` | already takes `on_submit_cb` |

Add a second kwarg `sanitize_cb: Callable[..., Awaitable[str]] | None = None`
to both modals (default None for tests that don't care about sanitization).
On `on_submit`, after deferring, sanitize the relevant free-text field
before passing to the cog callback.

**Free-text fields that need sanitization:**

- `WeaponSelectModal.weapon` — already regex-validated (`_WEAPON_VALID_RE`)
  to alphanumeric + space + apostrophe + plus; ChatML tokens like
  `<|im_start|>` CANNOT match the regex. Sanitization is **defense in
  depth** — log audit row, don't actually expect a strip. Probably skip
  this one as low-value and document why.
- `WeaponSelectModal.target_id` — regex-restricted to `[a-z0-9-]+`. Same
  conclusion: skip.
- `CharacterReviewModal.name` (80 chars), `character_class` (40),
  `class_level` (2), `race` (40), `abilities_str` (23) — **`name` and
  `race` ARE free-text and SHOULD be sanitized.** Class/level/abilities
  are short or numeric.
- `CharacterEntryModal` — same as ReviewModal.
- `OptionalFieldsModal.skills`, `.spells`, `.background` — free-text,
  SHOULD be sanitized.

**Revised SAN-01 scope:** wire sanitization into `CharacterReviewModal`,
`CharacterEntryModal`, and `OptionalFieldsModal` on their free-prose
fields. `WeaponSelectModal` is left as-is with a documentation comment
explaining why regex validation already covers the threat.

### 4.3 New / modified files

| File | Change |
|---|---|
| `src/eldritch_dm/bot/modals.py` | Add `sanitize_cb` kwarg to 3 modals; sanitize free-text fields before callback |
| `src/eldritch_dm/bot/cogs/ingest.py` | Pass `bot.sanitizer_audit_callback` into modal constructors |
| `src/eldritch_dm/bot/setup_hook.py` | Bind audit callback to `bot.sanitizer_audit_callback` attr |
| `tests/bot/test_modals.py` | Extend — assert sanitizer fired for malicious name/race input |

---

## 5. OPS-02 `MCPCircuitOpen` Surfacing

### 5.1 Current state — uncaught

`MCPCircuitOpen` raises from `mcp/client.py:121`. Catchers today:

- `gameplay/party_mode.py:_loop` has a bare `except Exception` on the
  pop call (line 276) and on resolve (line 372). These log the error
  but do NOT surface a Discord warning. The orchestrator silently retries.
- Cog button callbacks (e.g. `bot/cogs/combat.py` action buttons) propagate
  `MCPCircuitOpen` up to discord.py's default unhandled-error path.

### 5.2 Recommended pattern — decorator on cog callbacks

A `@catch_circuit_open` decorator wraps cog interaction callbacks:

```python
# bot/circuit_decorator.py (NEW)
def catch_circuit_open(fn):
    @functools.wraps(fn)
    async def wrapper(self, interaction, *a, **kw):
        try:
            return await fn(self, interaction, *a, **kw)
        except MCPCircuitOpen:
            await send_warning(interaction, WarningKind.DM_OFFLINE)
    return wrapper
```

Apply to every cog method that touches MCP. Auto-recovery is already free:
the CircuitBreaker flips back to CLOSED on the next successful health-check
ping (60s cadence) — no code change needed for that side. The decorator
just makes the *user-visible* response clean.

**For the orchestrator loop** (`gameplay/party_mode.py`), the existing
`except Exception` blocks catch `MCPCircuitOpen` already (it's a subclass).
Add a narrower `except MCPCircuitOpen` BEFORE the broad block so we can
emit a structured `orchestrator_circuit_open_skipping_tick` log line
rather than `orchestrator_pop_error` with a generic traceback. **No
Discord-side warning from the orchestrator** — users get the warning when
they click a button, not when the background poll fails.

### 5.3 `WarningKind.DM_OFFLINE` — add to enum

Check `bot/warnings.py` for the existing `WarningKind` enum and add a
new `DM_OFFLINE` member with appropriate copy ("⚠️ The DM is unreachable
right now. Please try again in a moment.").

### 5.4 New / modified files

| File | Change |
|---|---|
| `src/eldritch_dm/bot/warnings.py` | Add `WarningKind.DM_OFFLINE` |
| `src/eldritch_dm/bot/circuit_decorator.py` | NEW |
| `src/eldritch_dm/bot/cogs/combat.py` | Decorate MCP-touching callbacks |
| `src/eldritch_dm/bot/cogs/exploration.py` | Decorate MCP-touching callbacks |
| `src/eldritch_dm/bot/cogs/lobby.py` | Decorate MCP-touching callbacks |
| `src/eldritch_dm/gameplay/party_mode.py` | Add narrow `except MCPCircuitOpen` before broad except blocks |
| `tests/bot/test_circuit_decorator.py` | NEW |

---

## 6. `__main__` Token-Fix Parity (TD-1)

### 6.1 Current state — verified

`src/eldritch_dm/bot/__main__.py:44` calls `bot.run(settings.discord_token, ...)`
unconditionally. Since `discord_token: str | None` after D-26, a missing
token reaches `bot.run` as `None` → discord.py raises `TypeError` with an
unfriendly traceback.

### 6.2 Fix — mirror `run.py` lines 122-137

Insert the token-check block from `run.py` (the `if not token:` paragraph)
into `__main__.main` between line 39 (`bot = EldritchBot(settings)`) and
line 44 (`bot.run(...)`). Re-export the `EXIT_MISSING_TOKEN` constant
from `eldritch_dm.bootstrap` so the two entrypoints agree on exit code 4.

**Update the docstring** at the top of `__main__.py` to list exit code 4
alongside 0 and 2.

### 6.3 New / modified files

| File | Change |
|---|---|
| `src/eldritch_dm/bot/__main__.py` | Add friendly token check, update docstring |
| `tests/bot/test_main_entrypoint.py` | NEW — assert missing-token exits 4 with stderr message |

---

## 7. Ruff Cleanup (D-RUFF)

### 7.1 Scope — pre-existing 79 errors across 23 files

43 auto-fixable (mostly `I`/imports + `UP006`/`UP007` typing modernization).
The remaining 36 are likely:

- `B904` (raise without `from`) — needs human review
- `E501` long lines — wrap or per-file-ignore
- `F841` unused variables — delete or `_var =` rename

### 7.2 Build-order implication — FIRST

Per **Step 0 Rule** in CLAUDE.md: dead code accelerates context compaction.
Doing ruff cleanup AFTER touching files for MonsterDriver / OPS-02
guarantees diff noise (every other phase fights formatting churn). Do
ruff first as its own commit so later diffs are clean.

### 7.3 New / modified files

23 files (per the v1.1 plan note). No new files. No layer change.
**Run `ruff check --fix` + `ruff format`, then `import-linter` and the
full test suite, then commit as a single mechanical PR.**

---

## Suggested Build Order (for the Roadmapper)

| # | Phase | Item | Why this order |
|---|---|---|---|
| 1 | P1 | **Ruff cleanup** (D-RUFF) | Clears 79 errors / 23 files of noise before any other diffs. Mechanical, low-risk. |
| 2 | P2 | **`__main__` token-fix** (TD-1) | Tiny, isolated, no interaction with other items. Could pair with P1 in one PR. |
| 3 | P3 | **SAN-01** + **OPS-02** | Both touch `bot/cogs/*` and `bot/setup_hook.py`. Bundle to avoid two passes over the same files. New `WarningKind.DM_OFFLINE` member feels paired with sanitizer audit work. |
| 4 | P4 | **YAML eligibility** | Small new feature, isolated to `gameplay/` + `database/` + one config field. Ships before backfill because backfill MAY want to validate against the eligibility set (it doesn't strictly, but the option exists). |
| 5 | P5 | **`pc_classes` backfill script** | New `scripts/` package + new import-linter contract. Needs PID-file plumbing added to `bot/setup_hook.py` — best done after SAN-01/OPS-02 stabilize that file. |
| 6 | P6 | **Smart MonsterDriver** | Largest blast radius (mcp wrapper + driver class + Settings field + cache + tests). Goes last so all preceding items are stable foundations. |

**Phase-independence:** P3 / P4 / P5 / P6 don't depend on each other's
content (only on P1/P2 stability), so a parallel-track team could pair
P4 + P5 (different files) while P3 lands; P6 still last.

---

## Confidence Assessment

| Area | Confidence | Verification |
|---|---|---|
| Import-linter contract impact | HIGH | Read pyproject.toml lines 138-227; gameplay→mcp is allowed today |
| Existing MCP tool wrappers | HIGH | Grepped `mcp/tools.py` directly |
| Sanitizer wiring sites | HIGH | Read `bot/modals.py` line-by-line |
| `__main__` defect | HIGH | Read `bot/__main__.py:44` and `run.py:118-137` |
| `MCPCircuitOpen` catchers (none today) | HIGH | Searched `gameplay/party_mode.py` and modals |
| Need for `claudmaster_choose_target` wrapper | MEDIUM | dm20's exact tool name for "smart targeting" needs Phase 1 of v1.1 to confirm — may already exist as `get_claudmaster_session_state` |
| YAML loader path resolution | MEDIUM | Three-tier suggested; final placement may shift after STACK.md research on config patterns |
| Backfill script PID-file approach | MEDIUM | Alternative (lock-file via `fcntl.flock`) would also work; PID file is more portable |
| Build order | HIGH | Driven by file-overlap analysis + Step 0 Rule |

---

## Open Questions for Phase Planning

1. **Does dm20 expose smart-target picking as its own tool, or do we have
   to compose it from `get_claudmaster_session_state` + parsing?** Resolves
   the "MISSING wrapper" question in §1.2. PITFALLS.md research should
   answer this before Phase 6 starts.
2. **Should the YAML loader also expose `eligibility_for(class_name)` to
   support future per-class metadata (e.g. action-type, recharge)?**
   v1.1 only needs the frozenset; over-engineering risk vs. v2 readiness.
3. **PID-file location** — `./eldritch.pid` (cwd) vs `~/.eldritch/eldritch.pid`
   (user-scoped). Self-hosters launching via launchd may have a weird cwd.
4. **Where do v1.1 release notes live?** Add a `docs/CHANGELOG.md` if
   one doesn't exist; otherwise append to existing `docs/RELEASE_NOTES.md`.
   Not blocking but should appear in the milestone-close phase.
