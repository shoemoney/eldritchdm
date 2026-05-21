# Phase 2: Discord Scaffold + Persistent Views — Research

**Researched:** 2026-05-21
**Domain:** `discord.py` 2.7.1 — persistent views, DynamicItem rehydration, interaction defer discipline, in-process testing, embed coalescing
**Confidence:** HIGH on DynamicItem/persistent-view mechanics and rate-limit numbers; HIGH on dpytest status (verified recent commits); MEDIUM on dpytest exact compat with 2.7.1 (officially says 2.6, may work).

## Summary

The biggest correction this research yields against CONTEXT.md: **when persistent buttons inherit `discord.ui.DynamicItem`, you do NOT also need `bot.add_view(view, message_id=...)`**. The CONTEXT.md's `setup_hook` flow (D-24 step 5) treats `add_dynamic_items` and per-message `add_view` as both required — they are not, and trying to do both wastes work and creates an inconsistency window during rehydration. `add_dynamic_items(Cls)` registers a regex listener globally; Discord routes any `custom_id` matching the template to `Cls.from_custom_id` regardless of which message it lives on. This means **the `persistent_views` table becomes optional bookkeeping for v1 Phase 2** — useful for the kill-and-restart drill assertion and Phase 4/5 cleanup tasks, but `add_view(message_id=...)` calls during rehydration can be dropped from the hot path.

`dpytest` is alive (commits in January 2026) but officially supports discord.py up to 2.6. Recommend: **try dpytest first** behind a `RUN_DPYTEST=1` gate; if it doesn't import cleanly with 2.7.1, fall back to direct `unittest.mock` of `discord.Interaction` (recipe below). Either way, the restart-drill test is mock-based, not dpytest-based.

The defer-discipline rule (EDM001) should be implemented as a **pre-commit Python AST hook**, not a Rust ruff plugin. Ruff plugins require Rust + Cargo, and our rule is a 60-line AST walker — overkill for a custom plugin. The hook runs in <100ms on the full repo.

Discord message edit rate limit is **5 edits / 5s per channel** (shared bucket across all messages in that channel). Our default `EMBED_EDIT_RATE_LIMIT=1.0` gives a 5× safety margin — correct. For combat with 4 simultaneous embeds (initiative, HP, narration, log) on one channel, the coalescer must serialize across messages within a channel, not just within a message.

**Primary recommendation:** Drop `add_view(message_id=...)` from rehydration. Use `add_dynamic_items` only. Treat `persistent_views` table as audit/cleanup metadata, not a rehydration source. Implement EDM001 as a pre-commit AST hook. Use `asyncio.Event` + latest-value slot for the coalescer (simpler and race-free vs. `Queue(maxsize=1)`).

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|---|---|---|---|
| Slash command dispatch | Discord Gateway → `bot.tree` (orchestrator) | — | discord.py owns the protocol layer |
| Interaction defer | Orchestrator (each callback) | — | Must happen <3s, before any I/O — pure orchestrator concern |
| Persistent button matching | discord.py runtime (`add_dynamic_items`) | `bot/dynamic_items.py` (regex templates) | DynamicItem is a discord.py feature; we only supply the regex + handler |
| Persistent button state | `custom_id` payload + repos (channel_sessions, riposte_timers) | `persistent_views` table (audit only) | All state must be reconstructable from DB queries keyed off custom_id fields |
| Embed rendering | `bot/embeds.py` (pure functions) | — | No I/O, fully testable |
| Embed update rate-limit | `bot/coalescer.py` (per-message asyncio task) | discord.py HTTP client (built-in 429 backoff) | We coalesce to avoid hitting limits; discord.py recovers if we miss |
| Ephemeral warnings | `bot/warnings.py` (helper) | — | Pure formatting + interaction.followup.send |
| Lifecycle / setup_hook | `bot/bot.py` | `bot/setup_hook.py` (extracted for testability) | Single orchestration point for Phase 1 deps + dynamic item registration |
| Cog loading | `bot/cogs/*` | `bot.py` constructor | Cogs are the extension surface for Phase 3-5 |
| Logging context | `structlog` (bound per callback) | `bot/middleware` (if needed) | Every callback binds channel_id/user_id/custom_id on entry |

## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01:** `discord.py>=2.7.1,<3.0`
- **D-02:** Bot at `src/eldritch_dm/bot/`, class `EldritchBot(commands.Bot)`, app commands via `bot.tree`
- **D-03:** Process entrypoint = `src/eldritch_dm/bot/__main__.py`
- **D-04:** Intents = `Intents.default()` + `message_content = False`
- **D-05:** Module layout (see CONTEXT.md)
- **D-06/07/08:** Phase 2 commands are `/ping` + `/status` only; gameplay commands are TODO
- **D-09/11:** Every interaction callback's first non-trivial line MUST be `await interaction.response.defer(...)`; CI-enforced
- **D-12:** Exceptions allowed with `# noqa: EDM001 — <reason>`: autocomplete callbacks, modal-submit handlers responding with another modal
- **D-13–D-18:** Pure-function embed renderers + snapshot tests; color palette; standard footer
- **D-19–D-23:** All persistent buttons inherit `DynamicItem[Button]` with regex `custom_id` templates; 100-char cap; Phase 2 stubs callbacks only
- **D-24:** `setup_hook` order (acquire DB → ensure schema → start tasks → register dynamic items → rehydrate persistent_views → sync command tree → bind logging)
- **D-25:** `setup_hook` failures are fatal, exit code 2
- **D-26:** Graceful shutdown drains WriterQueue, closes MCPClient, cancels tasks
- **D-27–D-30:** Per-message coalescer ≤1 edit/sec, abandons message on persistent error
- **D-31–D-33:** Ephemeral warning helper with `WarningKind` enum
- **D-34–D-37:** dpytest evaluated by researcher; snapshot tests via syrupy or hand-rolled; restart drill is mandatory
- **D-38–D-39:** structlog bound context on every callback

### Claude's Discretion

- EDM001 ruff plugin vs grep/AST pre-commit hook — **researcher recommends AST-based pre-commit hook** (see Q4)
- Snapshot library — **recommend hand-rolled JSON compare against `embed.to_dict()`** (zero new deps; `discord.Embed.to_dict()` is well-defined)
- dpytest vs direct Discord mocks — **recommend mocking `discord.Interaction` directly** for unit tests; gate dpytest behind `RUN_DPYTEST=1` integration label IF a smoke import succeeds with 2.7.1; otherwise skip dpytest entirely (see Q2)
- Coalescer mechanism — **recommend `asyncio.Event` + latest-value slot** over `Queue(maxsize=1)` (see Q5)

### Deferred Ideas (OUT OF SCOPE)

- Multi-guild dashboard
- Discord audit-log integration
- Slash command localization
- Voice/TTS
- Adaptive coalescer rate
- Application emoji registration

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| BOT-01 | discord.py 2.7.1+ bot with slash tree | Q1, Q7 — version verified, setup_hook pattern |
| BOT-02 | First-line `interaction.response.defer(thinking=True)` everywhere | Q3, Q4 — defer semantics + EDM001 AST hook |
| BOT-03 | Embed renderers | Pure-function pattern; snapshot via `embed.to_dict()` |
| BOT-04 | DynamicItem with regex custom_id | Q1 — full pattern + caveats |
| BOT-05 | `setup_hook` rehydrates persistent views | Q1 (corrected: only `add_dynamic_items` needed for DynamicItem subclasses), Q7 |
| BOT-06 | Coalescer ≤1 edit/sec/message | Q5, Q6 — Event + latest-value slot, per-channel awareness |
| BOT-07 | Ephemeral warning helper | Q3 — `interaction.followup.send(..., ephemeral=True)` after defer |
| BOT-08 | Kill-and-restart drill | Q1 + Q2 — restart drill uses mocked Interaction; DynamicItem rehydration verified by re-dispatching mock |
| OPS-04 | Graceful shutdown | Q7 — `bot.close()` override, task cancellation order |

## Standard Stack

### Core (Phase 2 adds)
| Library | Pinned | Purpose | Why |
|---------|--------|---------|-----|
| `discord.py` | `==2.7.1` | Already pinned Phase 1 | Active again; DynamicItem stable since 2.4; bugfixes in 2.6/2.7 for DynamicItem inside Section [CITED: github.com/Rapptz/discord.py changelog] |

### Supporting (Phase 2 adds — new)
| Library | Pinned | Purpose | When to Use |
|---------|--------|---------|-------------|
| `pytest-asyncio` | already in test deps | Async test execution | All Phase 2 tests |
| (no new prod deps) | — | — | Coalescer + warnings + embeds need only stdlib `asyncio`, `enum`, `re` |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Hand-rolled embed snapshot via `to_dict()` | `syrupy>=4.6` | syrupy adds a dep; `embed.to_dict()` is already canonical and stable. **Skip syrupy.** |
| `dpytest` for harness | mock `discord.Interaction` directly | dpytest officially supports up to 2.6, last commit Jan 2026; **safer to mock for unit tests**, optionally try dpytest for integration |
| Ruff plugin for EDM001 | Pre-commit AST hook in Python | Ruff plugins require Rust toolchain. **AST hook is 60 lines + zero deps.** |
| `asyncio.Queue(maxsize=1)` coalescer | `asyncio.Event` + latest-value slot | Queue(maxsize=1) blocks producer on overflow OR drops; Event is non-blocking + lossless of latest value |

**Installation:** No new runtime deps — Phase 1 already pinned `discord.py==2.7.1`, `pytest-asyncio`, `structlog`.

**Version verification:**
- `discord.py 2.7.1` released **2026-03-03** [VERIFIED: PyPI]
- `dpytest 0.7.0` released **2023-06-19**, last commit master 2026-01-13 ("Enable no_implicit_reexport"), README claims discord.py 2.6 support [VERIFIED: github.com/CraftSpider/dpytest commits]

## Package Legitimacy Audit

No new runtime packages installed in Phase 2. All deps inherited from Phase 1 (`pyproject.toml`). Audit:

| Package | Registry | Age | Downloads | Source Repo | slopcheck | Disposition |
|---------|----------|-----|-----------|-------------|-----------|-------------|
| `discord.py` | PyPI | 10+ yrs | 4M+/mo | github.com/Rapptz/discord.py | n/a (inherited) | Approved (Phase 1) |
| `dpytest` (optional dev) | PyPI | 5 yrs | low | github.com/CraftSpider/dpytest | n/a (dev-only, opt-in) | Approved IF used; gate behind `RUN_DPYTEST=1` |

slopcheck not run — Phase 2 introduces no new install lines beyond what Phase 1 already audited. If the planner ends up adding `syrupy` or another snapshot lib, slopcheck gates that decision.

## Architecture Patterns

### System Architecture Diagram

```
┌────────────────┐
│ Discord Gateway│
└───────┬────────┘
        │ (WebSocket: slash cmd / button click)
        ▼
┌─────────────────────────────────────────────────────────┐
│ EldritchBot (commands.Bot)                              │
│                                                         │
│  ┌──────────────────────────────────────────────────┐   │
│  │ setup_hook (one-shot, before gateway connect)    │   │
│  │  1. PersistenceManager.start() → WriterQueue     │   │
│  │  2. bootstrap.ensure_schema()                    │   │
│  │  3. MCPClient init + HealthCheck.start()         │   │
│  │  4. add_dynamic_items(Ready, Declare, EndTurn,   │   │
│  │                       Riposte)                   │   │
│  │  5. (audit) PersistentViewRepo.list_all() →      │   │
│  │     log row count; no add_view calls needed      │   │
│  │  6. tree.sync(guild=…) per DISCORD_GUILD_IDS     │   │
│  │  7. load_cog("cogs.diagnostics")                 │   │
│  └──────────────────────────────────────────────────┘   │
│                                                         │
│  Interaction Router (built into discord.py)             │
│   ├─► slash /ping  ─► cogs/diagnostics.py:ping          │
│   ├─► slash /status ─► cogs/diagnostics.py:status       │
│   └─► button click  ─► DynamicItem.from_custom_id       │
│                          └─► .callback(interaction)     │
│                                │                        │
│                                ▼                        │
│                          send_warning() / followup      │
│                          coalescer.update(embed)        │
└─────────────────────────────────────────────────────────┘
        │                          │
        ▼                          ▼
┌──────────────┐         ┌────────────────────┐
│ Repos        │         │ EmbedCoalescer     │
│ (Phase 1)    │         │  per-message task  │
└──────────────┘         │  drains latest     │
                         │  payload ≤1/sec    │
                         └────────────────────┘
```

### Recommended Project Structure

Matches CONTEXT.md D-05 verbatim. No changes.

### Pattern 1: DynamicItem Persistent Button

**What:** Subclass `discord.ui.DynamicItem[discord.ui.Button]` with a class-level `template=` regex. Discord routes any incoming button click whose `custom_id` matches the template to your class.

**When to use:** Every Phase 2 persistent button — Ready, DeclareAction, EndTurn, Riposte.

**Example:**
```python
# Source: github.com/Rapptz/discord.py/blob/master/examples/views/dynamic_counter.py (verified pattern)
import re
import discord
from discord.ext import commands

class EndTurnButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"endturn:(?P<channel_id>\d+):(?P<actor_id>\d+)",
):
    def __init__(self, channel_id: int, actor_id: int) -> None:
        super().__init__(
            discord.ui.Button(
                label="End Turn",
                style=discord.ButtonStyle.secondary,
                custom_id=f"endturn:{channel_id}:{actor_id}",
                emoji="⏭️",
            )
        )
        self.channel_id = channel_id
        self.actor_id = actor_id

    @classmethod
    async def from_custom_id(
        cls,
        interaction: discord.Interaction,
        item: discord.ui.Button,
        match: re.Match[str],
        /,
    ) -> "EndTurnButton":
        return cls(
            channel_id=int(match["channel_id"]),
            actor_id=int(match["actor_id"]),
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        # PHASE 2 STUB — wired up in Phase 4
        await interaction.response.defer(thinking=True, ephemeral=True)  # noqa: EDM001 — defer is the rule
        await interaction.followup.send(
            f"⏭ Phase 2 stub: would end turn for actor {self.actor_id}",
            ephemeral=True,
        )

# Registration in setup_hook
class EldritchBot(commands.Bot):
    async def setup_hook(self) -> None:
        self.add_dynamic_items(EndTurnButton)  # NO add_view needed
```

**Watch out for:**
- The class **must** be a Generic over the item type — `DynamicItem[discord.ui.Button]`. Without the type parameter, registration is silently a no-op in 2.7.x (recently fixed bug — confirmed in changelog).
- The `template` MUST anchor at start/end implicitly — Discord uses `fullmatch` semantics. Bare prefixes like `endturn:.*` will match too greedily.
- Inside `__init__`, you pass an **item** instance (a `discord.ui.Button(...)`) to `super().__init__()`. Don't try to inherit Button + DynamicItem simultaneously.
- `from_custom_id` is a `@classmethod` and the signature `(cls, interaction, item, match, /)` is positional-only.

### Pattern 2: setup_hook with Failure-is-Fatal Semantics

**What:** discord.py's `setup_hook` runs after login (token validated) but **before** gateway connection. Any uncaught exception bubbles up to `Client.start`, which is awaited from `bot.run`/`bot.start`. The bot will **not** retry; the exception propagates to the caller.

**Watch out for:** Do NOT call `bot.close()` inside `setup_hook` to force shutdown — there's a known issue ([github.com/Rapptz/discord.py#8210](https://github.com/Rapptz/discord.py/issues/8210)) where the bot's `.run` loop will still attempt to login afterward and raise `RuntimeError: Session is closed`. Just **raise** — let the exception propagate.

```python
# Source: github.com/Rapptz/discord.py issue #8210 (canonical pattern)
import sys
import structlog
from discord.ext import commands

log = structlog.get_logger()

class EldritchBot(commands.Bot):
    async def setup_hook(self) -> None:
        try:
            await self._persistence.start()
            await self._bootstrap.ensure_schema()
            await self._mcp_client.start()
            await self._health.start()
            self.add_dynamic_items(
                ReadyButton, DeclareActionButton, EndTurnButton, RiposteButton
            )
            view_count = len(await self._views_repo.list_all())  # audit
            await self.load_extension("eldritch_dm.bot.cogs.diagnostics")
            await self.tree.sync(guild=self._guild_obj)
            log.info(
                "setup_hook_complete",
                persistent_views_in_db=view_count,
                dynamic_items=4,
            )
        except Exception:
            log.exception("setup_hook_failed_fatal")
            # Let the exception propagate — bot.start will re-raise to __main__
            raise

# __main__.py
def main() -> int:
    try:
        bot.run(settings.discord_token)
        return 0
    except Exception:
        log.exception("bot_startup_failed")
        return 2

if __name__ == "__main__":
    sys.exit(main())
```

### Pattern 3: Defer-First Callback (the EDM001 contract)

**What:** Every interaction-handling callback's first non-docstring statement is `await interaction.response.defer(...)`. This gives us **15 minutes** of follow-up budget instead of 3 seconds.

**Example:**
```python
import discord
from discord import app_commands

@app_commands.command(name="ping", description="Health check")
async def ping(interaction: discord.Interaction) -> None:
    """Reply with MCP circuit state + last ping age."""
    await interaction.response.defer(thinking=True, ephemeral=True)
    # Now we have ~15 min. Do the slow thing.
    state = get_circuit_state(bot.health.breaker)
    age = bot.health.last_success_age()
    embed = discord.Embed(
        title="🔌 ShoeGPT Status",
        description=f"Circuit: **{state.value}**\nLast ping: {age}s ago",
        color=0x57F287 if state == CircuitState.CLOSED else 0xED4245,
    )
    await interaction.followup.send(embed=embed, ephemeral=True)
```

### Pattern 4: Embed Coalescer (Event + Latest-Value Slot)

**What:** Per-message background task that holds the latest pending `(embed, view)` payload and applies it at most 1×/sec.

**Why Event + slot, not Queue(maxsize=1):**
- `asyncio.Queue(maxsize=1)` either blocks the producer if full or requires a `try/except QueueFull` with manual drop-and-replace — awkward, race-prone.
- A latest-value slot (`self._pending`) protected by `self._event` is **lossless of the latest value** (older values are simply overwritten in the slot — exactly the desired semantic), **non-blocking for the producer**, and trivially testable.

```python
# Source: hand-rolled, derived from asyncio.Condition + latest-value patterns
# https://codepr.github.io/posts/asyncio-pubsub/ (background)
import asyncio
from typing import Optional, Tuple
import discord
import structlog

log = structlog.get_logger(__name__)

class EmbedCoalescer:
    """Per-message coalescer: edits ≤1×/sec; latest payload wins."""

    def __init__(self, message: discord.Message, *, min_interval: float = 1.0) -> None:
        self._message = message
        self._interval = min_interval
        self._pending: Optional[Tuple[discord.Embed, Optional[discord.ui.View]]] = None
        self._event = asyncio.Event()
        self._abandoned = False
        self._task: Optional[asyncio.Task[None]] = None
        self._logger = log.bind(message_id=message.id, channel_id=message.channel.id)

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._run(), name=f"coalescer:{self._message.id}")

    async def update(self, embed: discord.Embed, view: Optional[discord.ui.View] = None) -> None:
        if self._abandoned:
            return
        # Atomic-overwrite slot (asyncio is single-threaded; no lock needed)
        self._pending = (embed, view)
        self._event.set()

    async def _run(self) -> None:
        while not self._abandoned:
            await self._event.wait()
            if self._pending is None:
                self._event.clear()
                continue
            # Snapshot + clear-and-recheck pattern: ensures any update arriving
            # *after* we snapshot wakes us on the next loop iteration.
            embed, view = self._pending
            self._pending = None
            self._event.clear()
            try:
                if view is not None:
                    await self._message.edit(embed=embed, view=view)
                else:
                    await self._message.edit(embed=embed)
            except discord.NotFound:
                self._logger.warning("coalescer_message_deleted_abandoning")
                self._abandoned = True
                return
            except discord.Forbidden:
                self._logger.error("coalescer_forbidden_abandoning")
                self._abandoned = True
                return
            except discord.HTTPException as e:
                self._logger.warning("coalescer_http_error", status=e.status, code=e.code)
                # discord.py handles 429 internally; just log and continue
            await asyncio.sleep(self._interval)

    async def stop(self) -> None:
        self._abandoned = True
        if self._task is not None:
            self._event.set()  # wake task so it sees _abandoned
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
```

**Race-window analysis:**
- T=0.0s: update(A) called → `_pending=A`, `_event.set()`
- T=0.0s: render task wakes, snapshots A, clears `_pending` and `_event`, edits
- T=0.5s: update(B) called → `_pending=B`, `_event.set()`
- T=1.0s: render task sleep ends, loop top → `await _event.wait()` → already set → snapshots B → edits
- ✅ B is not lost.

Critical: **clear `_pending` and `_event` BEFORE awaiting `message.edit`.** If clearing happens after the edit, an update arriving during the edit gets overwritten by the clear. The "snapshot first, clear immediately, then I/O" ordering is the heart of the pattern.

### Anti-Patterns to Avoid

- **DON'T:** Call both `add_dynamic_items(Cls)` AND `add_view(view, message_id=...)` for the same button kind. The CONTEXT.md draft suggests both. Use only `add_dynamic_items`.
- **DON'T:** Store closure state in a `View` subclass and expect it to survive restart. All state must be reconstructable from `custom_id` + DB.
- **DON'T:** Use `timeout=180` (the default) for persistent views. Always `timeout=None`. DynamicItems live on `View(timeout=None)` containers when you build a fresh view server-side.
- **DON'T:** `await interaction.response.send_message(...)` from a callback that calls MCP/LLM/DB after — that's a 3-second cliff bug waiting to happen. Defer first.
- **DON'T:** `bot.close()` from inside `setup_hook` on validation failure — raise instead.
- **DON'T:** Use `asyncio.Queue(maxsize=1)` for the coalescer — the dropped-update behavior is awkward.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Button → handler dispatch by custom_id | Manual `on_interaction` listener that parses custom_id and routes | `discord.ui.DynamicItem` with `template=re.compile(...)` | Built-in; survives restart with one `add_dynamic_items` call |
| Cross-restart view persistence registry | Manual table → `add_view(view, message_id=...)` loop | `add_dynamic_items(Cls)` — Discord matches custom_ids regardless of message_id | Removes an entire failure mode (message deleted between restarts) |
| Per-edit 429 retry/backoff | Manual `asyncio.sleep(retry_after)` loops | Trust `discord.py.HTTPClient` rate limiter; coalesce upstream | discord.py 2.7.1 handles 429 backoff; we just need to not generate edits faster than budget |
| Embed equality / snapshot comparison | Pickle / repr / custom diff | `embed.to_dict()` returns canonical dict; `json.dumps(sort_keys=True)` for stable hash | Discord's own serialization is the source of truth |
| In-process Discord harness | Build mocks for `Client`, `Gateway`, `HTTPClient` | `dpytest` (if compat) OR mock just `discord.Interaction` | Most Phase 2 tests are interaction-level, not gateway-level — direct mocks are easier |
| Cog discovery / loading | Walk filesystem | `bot.load_extension("eldritch_dm.bot.cogs.diagnostics")` | Built-in; supports hot-reload in Phase 5+ if we want |

**Key insight:** discord.py 2.7.1 has matured enough that nearly every Phase 2 mechanic has a first-class API. The custom code shrinks to: regex templates, embed renderers, the coalescer, the EDM001 hook, and the warning helper. That's it.

## Common Pitfalls

### Pitfall 1: Treating `add_view(message_id=...)` as required for DynamicItem persistence

**What goes wrong:** Following CONTEXT.md D-24 step 5 literally — calling both `add_dynamic_items` AND iterating `PersistentViewRepo.list_all()` to call `bot.add_view(View(), message_id=int(row.message_id))`. This wastes startup time and creates an inconsistency window: rows in `persistent_views` for messages that no longer exist will cause noise (not an error per se — `add_view` accepts any message_id — but the manual View wrappers add no value over the DynamicItem-only path).

**Why it happens:** Pre-2.4 discord.py guidance still circulates online. The CONTEXT.md was written from older guides.

**How to avoid:** **`add_dynamic_items` is sufficient.** Discord matches incoming button-click `custom_id` against registered templates *regardless of which message* the button is on. The `persistent_views` table is now bookkeeping: useful for "list all active buttons" admin queries and Phase 4/5 cleanup, but not load-bearing for rehydration.

**Warning signs:** A startup log line "rehydrated N views from M rows" where N = M but the bot wouldn't break if you dropped the loop entirely.

### Pitfall 2: 3-second ack cliff (PITFALLS.md #3, mapped to Phase 2)

**What goes wrong:** A button callback does `await mcp_client.execute(...)` or `await openai_client.chat.completions.create(...)` before deferring. Discord invalidates the interaction at 3.0s; the followup raises `discord.NotFound: 10062 Unknown interaction`.

**Why it happens:** Forgetting the defer, especially on "fast path" callbacks where dev environment latency hides the issue.

**How to avoid:** EDM001 lint rule (Q4 below). For Phase 2 the only network call is `/ping` to MCP health — fast in dev, can timeout in production.

**Warning signs:** Logs containing `discord.errors.NotFound: 404 ... 10062 Unknown interaction`.

### Pitfall 3: DynamicItem class missing `[discord.ui.Button]` generic

**What goes wrong:** `class EndTurn(discord.ui.DynamicItem, template=r"..."):` — no type parameter. Registration silently does nothing. Buttons appear unresponsive.

**How to avoid:** ALWAYS write `class X(discord.ui.DynamicItem[discord.ui.Button], template=r"..."):`. Add a test that asserts each subclass has `__orig_bases__` containing `discord.ui.DynamicItem[discord.ui.Button]`.

### Pitfall 4: Edit rate-limit conflict between multiple coalescers in one channel

**What goes wrong:** Phase 4 combat will have ≥3 coalescers active per channel (initiative embed, HP embed, narration message). Each ticks at 1/s = 3 edits/s in the channel. Channel bucket is 5/5s = 1/s. **We will hit the limit on busy channels.**

**Why it happens:** Per-message coalescer rate-limit doesn't compose to a per-channel rate-limit.

**How to avoid (Phase 2 prep, Phase 4 actual use):** The `EmbedCoalescer` API should support a shared channel-scoped semaphore that the Phase 4 builder threads through. For Phase 2, document this design intent in `coalescer.py`'s module docstring so Phase 4 inherits it. Concretely: `class ChannelEditBudget` that wraps a token bucket (3 tokens, 1s refill), passed to each `EmbedCoalescer` for that channel. Phase 2 implements with budget=None (per-message-only); Phase 4 turns it on.

### Pitfall 5: `dpytest` import breaks on `discord.py 2.7.1`

**What goes wrong:** `import dpytest` errors with `ImportError` on something discord.py renamed between 2.6 and 2.7.

**How to avoid:** Wrap dpytest import in `try/except ImportError`; skip dpytest-based tests with `pytest.skip("dpytest unavailable")`. Restart drill **does not depend on dpytest** — it uses direct `unittest.mock.AsyncMock` on `discord.Interaction`.

### Pitfall 6: Mocked Interaction missing `.response` or `.followup` attributes

**What goes wrong:** `AsyncMock(spec=discord.Interaction)` doesn't auto-populate sub-mocks for `interaction.response.defer` and `interaction.followup.send`, causing tests to fail in confusing ways.

**How to avoid:** Use the recipe in Q2 — explicitly assign `interaction.response = AsyncMock()` and `interaction.followup = AsyncMock()`.

## Code Examples

### Q1 Reference: Full DynamicItem + setup_hook integration

See Pattern 1 above.

### Q3 Reference: defer + followup

```python
# Source: discordpy.readthedocs.io/en/stable/interactions/api.html
async def callback(self, interaction: discord.Interaction) -> None:
    # WITHIN 3s OF DISPATCH — defer first.
    await interaction.response.defer(thinking=True, ephemeral=True)
    #                                  ^^^^^^^^^^^^^^^^^^^^^^^^
    #                                  Shows "Bot is thinking..." spinner
    #                                  Ephemeral=True means followups default to ephemeral

    # Now we have 15 minutes.
    result = await some_slow_thing()

    # First followup respects the defer's ephemeral flag.
    await interaction.followup.send(content=f"Done: {result}")

    # Or edit the placeholder response in-place:
    # await interaction.edit_original_response(content=f"Done: {result}")
```

`defer(thinking=True)` vs `defer()`:
- `thinking=True` → UI shows "Bot is thinking…" spinner, requires a followup to "satisfy" it. Use for actions that will produce visible output.
- `defer()` (no thinking) → silent ack; nothing visible to user. Use for actions whose result is a state change (e.g., the click was valid, no message needed).

`ephemeral=True` only takes effect when `thinking=True`. Defer-without-thinking ignores ephemeral.

### Q2 Reference: Mocking `discord.Interaction` directly

```python
# tests/bot/conftest.py
import pytest
from unittest.mock import AsyncMock, MagicMock
import discord

@pytest.fixture
def interaction_factory():
    """Build a mock discord.Interaction with the right shape."""
    def _make(
        *,
        user_id: int = 100,
        channel_id: int = 200,
        guild_id: int | None = 300,
        custom_id: str | None = None,
    ) -> discord.Interaction:
        interaction = MagicMock(spec=discord.Interaction)
        interaction.user = MagicMock(spec=discord.Member)
        interaction.user.id = user_id
        interaction.channel_id = channel_id
        interaction.guild_id = guild_id
        interaction.data = {"custom_id": custom_id} if custom_id else {}

        # These need explicit AsyncMock — spec doesn't reach into nested attrs cleanly
        interaction.response = AsyncMock()
        interaction.response.defer = AsyncMock()
        interaction.response.send_message = AsyncMock()
        interaction.response.is_done = MagicMock(return_value=False)

        interaction.followup = AsyncMock()
        interaction.followup.send = AsyncMock()

        interaction.edit_original_response = AsyncMock()
        return interaction
    return _make

# Example test
@pytest.mark.asyncio
async def test_end_turn_callback_defers_first(interaction_factory):
    interaction = interaction_factory(user_id=42, channel_id=999)
    button = EndTurnButton(channel_id=999, actor_id=42)

    await button.callback(interaction)

    interaction.response.defer.assert_awaited_once_with(thinking=True, ephemeral=True)
    interaction.followup.send.assert_awaited_once()
```

### Q4 Reference: EDM001 AST Pre-Commit Hook

```python
# tools/lint_edm001.py
"""EDM001: Every Discord interaction callback's first non-docstring statement
must be `await interaction.response.defer(...)`.

Detects:
  - Functions decorated with @app_commands.command / @tree.command
  - Functions decorated with @discord.ui.button / @discord.ui.select
  - `async def callback(self, interaction)` methods on classes that subclass
    discord.ui.DynamicItem, discord.ui.View, or discord.ui.Modal
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

EXIT_OK = 0
EXIT_VIOLATION = 1

DEFER_NAMES = {"defer"}  # interaction.response.defer
ALLOWED_BASE_CLASSES = {"DynamicItem", "View", "Modal"}
DECORATOR_NAMES = {
    "command",         # @app_commands.command, @bot.tree.command
    "button",          # @discord.ui.button
    "select",          # @discord.ui.select
    "context_menu",    # @app_commands.context_menu
}

# Exemptions
NOQA_TAG = "# noqa: EDM001"


def _has_noqa(source_line: str) -> bool:
    return NOQA_TAG in source_line


def _decorator_name(dec: ast.expr) -> str | None:
    if isinstance(dec, ast.Call):
        return _decorator_name(dec.func)
    if isinstance(dec, ast.Attribute):
        return dec.attr
    if isinstance(dec, ast.Name):
        return dec.id
    return None


def _is_target_callback(node: ast.AsyncFunctionDef, class_stack: list[ast.ClassDef]) -> bool:
    # 1) Decorated with one of our trigger decorators
    for dec in node.decorator_list:
        if _decorator_name(dec) in DECORATOR_NAMES:
            return True
    # 2) Named `callback` on a UI subclass
    if node.name == "callback" and class_stack:
        bases = {_decorator_name(b) for b in class_stack[-1].bases}
        # DynamicItem[Button] arrives as ast.Subscript — handle separately
        for base in class_stack[-1].bases:
            if isinstance(base, ast.Subscript):
                inner = _decorator_name(base.value)
                if inner in ALLOWED_BASE_CLASSES:
                    return True
        if bases & ALLOWED_BASE_CLASSES:
            return True
    return False


def _first_real_statement(body: list[ast.stmt]) -> ast.stmt | None:
    """Skip leading docstring."""
    if not body:
        return None
    first = body[0]
    if (
        isinstance(first, ast.Expr)
        and isinstance(first.value, ast.Constant)
        and isinstance(first.value.value, str)
    ):
        return body[1] if len(body) > 1 else None
    return first


def _is_defer_call(stmt: ast.stmt) -> bool:
    """Match `await interaction.response.defer(...)` (any kwargs)."""
    if not isinstance(stmt, ast.Expr):
        return False
    if not isinstance(stmt.value, ast.Await):
        return False
    call = stmt.value.value
    if not isinstance(call, ast.Call):
        return False
    func = call.func
    # We expect Attribute access chain ending in .defer
    if not isinstance(func, ast.Attribute):
        return False
    if func.attr not in DEFER_NAMES:
        return False
    # Walk: interaction.response.defer → confirm .response in chain
    middle = func.value
    if isinstance(middle, ast.Attribute) and middle.attr == "response":
        return True
    return False


def check_file(path: Path) -> list[tuple[int, str]]:
    source = path.read_text()
    source_lines = source.splitlines()
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError as e:
        return [(e.lineno or 0, f"SyntaxError: {e.msg}")]

    violations: list[tuple[int, str]] = []
    class_stack: list[ast.ClassDef] = []

    class Visitor(ast.NodeVisitor):
        def visit_ClassDef(self, node: ast.ClassDef) -> None:
            class_stack.append(node)
            self.generic_visit(node)
            class_stack.pop()

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
            if _is_target_callback(node, class_stack):
                # Check the noqa on the def line
                def_line = source_lines[node.lineno - 1] if node.lineno <= len(source_lines) else ""
                if not _has_noqa(def_line):
                    first = _first_real_statement(node.body)
                    if first is None or not _is_defer_call(first):
                        violations.append((
                            node.lineno,
                            f"EDM001: callback '{node.name}' first statement is not "
                            f"`await interaction.response.defer(...)`",
                        ))
            self.generic_visit(node)

    Visitor().visit(tree)
    return violations


def main(argv: list[str]) -> int:
    exit_code = EXIT_OK
    for arg in argv[1:]:
        p = Path(arg)
        if not p.is_file() or p.suffix != ".py":
            continue
        for line, msg in check_file(p):
            print(f"{p}:{line}: {msg}", file=sys.stderr)
            exit_code = EXIT_VIOLATION
    return exit_code


if __name__ == "__main__":
    sys.exit(main(sys.argv))
```

`.pre-commit-config.yaml` entry:
```yaml
- repo: local
  hooks:
    - id: edm001-defer-discipline
      name: EDM001 — defer-discipline for Discord callbacks
      entry: python tools/lint_edm001.py
      language: system
      types: [python]
      files: ^src/eldritch_dm/bot/.*\.py$
```

`pyproject.toml` `[tool.pytest.ini_options]` add a smoke test that runs the linter against a small fixtures dir of GOOD and BAD examples (`tests/bot/lint_edm001_fixtures/`).

**CI integration:** Add a `lint-edm001` GitHub Actions step (or wherever CI lives) that runs `python tools/lint_edm001.py $(git ls-files 'src/eldritch_dm/bot/**/*.py')`. Exit code 1 fails the build.

## Runtime State Inventory

Phase 2 is greenfield code added to an existing repo. No rename/refactor. The only runtime state we touch:

| Category | Items Found | Action Required |
|----------|-------------|-----------------|
| Stored data | `persistent_views` table (Phase 1, shipped) | Phase 2 may insert rows when persistent buttons are posted; **does NOT depend on rows for restart correctness** (DynamicItem handles that) |
| Live service config | Discord guild app-command registrations (managed by `tree.sync`) | `setup_hook` will sync per `DISCORD_GUILD_IDS` env; document this in HOST docs |
| OS-registered state | None — no launchd/cron/systemd in this phase | None (Phase 5 covers launchd for the bot itself) |
| Secrets/env vars | `DISCORD_TOKEN`, `DISCORD_GUILD_IDS`, `EMBED_EDIT_RATE_LIMIT` (already in `.env.example`) | None — read-only |
| Build artifacts | None — pure Python | None |

**Section explicitly included** because the planner may otherwise leave it out; greenfield phases should still answer "what state exists that we touch."

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|-------------|-----------|---------|----------|
| `discord.py` 2.7.1 | All Phase 2 code | ✓ | inherited from Phase 1 | — |
| `pytest` + `pytest-asyncio` | Tests | ✓ | inherited | — |
| `dpytest` 0.7.0 | Optional integration test | ✗ (not installed) | — | Mock `discord.Interaction` directly (recipe Q2) |
| Discord bot token | Live smoke test | likely ✓ in user's `.env` | — | All Phase 2 tests are offline; live smoke test is HOST-04 (Phase 5) |
| Python AST module | EDM001 hook | ✓ (stdlib) | 3.11+ | — |

**No blocking missing deps.** dpytest is opt-in.

## Validation Architecture

`workflow.nyquist_validation` is not explicitly disabled → include this section.

### Test Framework
| Property | Value |
|---|---|
| Framework | `pytest` 8.x + `pytest-asyncio` (inherited from Phase 1) |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` |
| Quick run command | `pytest tests/bot/ -x --asyncio-mode=auto` |
| Full suite command | `pytest -x --asyncio-mode=auto` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|--------------|
| BOT-01 | Bot constructs with intents + tree | unit | `pytest tests/bot/test_bot_lifecycle.py::test_constructs_with_correct_intents` | ❌ Wave 0 |
| BOT-02 | EDM001 catches missing defer | unit | `pytest tests/bot/test_lint_edm001.py::test_flags_missing_defer` | ❌ Wave 0 |
| BOT-02 | EDM001 passes correct defer | unit | `pytest tests/bot/test_lint_edm001.py::test_allows_correct_defer` | ❌ Wave 0 |
| BOT-03 | `lobby_embed` returns stable shape | snapshot | `pytest tests/bot/test_embeds.py::test_lobby_embed_snapshot` | ❌ Wave 0 |
| BOT-03 | `room_embed`, `combat_embed`, `character_confirm_embed` snapshots | snapshot | `pytest tests/bot/test_embeds.py` | ❌ Wave 0 |
| BOT-04 | `EndTurnButton.from_custom_id` parses regex | unit | `pytest tests/bot/test_dynamic_items.py::test_end_turn_parses_custom_id` | ❌ Wave 0 |
| BOT-04 | All 4 DynamicItem subclasses have `[Button]` generic | unit | `pytest tests/bot/test_dynamic_items.py::test_all_subclasses_have_generic` | ❌ Wave 0 |
| BOT-05 | `setup_hook` calls `add_dynamic_items` with all 4 classes | unit | `pytest tests/bot/test_setup_hook.py::test_registers_all_dynamic_items` | ❌ Wave 0 |
| BOT-05 | `setup_hook` failure raises (does not call bot.close) | unit | `pytest tests/bot/test_setup_hook.py::test_failure_propagates` | ❌ Wave 0 |
| BOT-06 | Coalescer applies latest payload, drops intermediate | unit | `pytest tests/bot/test_coalescer.py::test_latest_value_wins` | ❌ Wave 0 |
| BOT-06 | Coalescer respects min_interval | unit | `pytest tests/bot/test_coalescer.py::test_rate_limited_to_1hz` | ❌ Wave 0 |
| BOT-06 | Coalescer abandons on NotFound | unit | `pytest tests/bot/test_coalescer.py::test_abandons_on_message_deleted` | ❌ Wave 0 |
| BOT-07 | `send_warning` formats each WarningKind | unit | `pytest tests/bot/test_warnings.py` | ❌ Wave 0 |
| BOT-08 | Kill-and-restart drill: button still dispatches after re-init | integration | `RUN_INTEGRATION=1 pytest tests/bot/test_restart_drill.py` | ❌ Wave 0 |
| OPS-04 | Graceful shutdown cancels tasks in correct order | unit | `pytest tests/bot/test_bot_lifecycle.py::test_close_cancels_tasks` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `pytest tests/bot/ -x --asyncio-mode=auto` (quick — all unit tests)
- **Per wave merge:** `pytest -x --asyncio-mode=auto` (full suite — includes Phase 1's 177 tests)
- **Phase gate:** Full suite + `RUN_INTEGRATION=1 pytest tests/bot/test_restart_drill.py` green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/bot/__init__.py`
- [ ] `tests/bot/conftest.py` — `bot_factory`, `interaction_factory`, `tmp_db` fixtures
- [ ] `tests/bot/lint_edm001_fixtures/good_callback.py` — passes
- [ ] `tests/bot/lint_edm001_fixtures/bad_callback.py` — violates
- [ ] `tools/lint_edm001.py` — the linter itself (Phase 2 deliverable, but the test file goes alongside)
- [ ] All `tests/bot/test_*.py` files listed in the table above
- [ ] `.pre-commit-config.yaml` — add `edm001-defer-discipline` local hook

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|------------------|
| V2 Authentication | yes | Discord OAuth (bot token in `.env`, gitignored) — inherited from Phase 1 config |
| V3 Session Management | no | Discord owns gateway session |
| V4 Access Control | yes | Turn-gating in callbacks: `interaction.user.id == current_actor_id` (Phase 4 usage; Phase 2 sets the warning helper for it) |
| V5 Input Validation | partial | Phase 2 doesn't accept user free-text yet (modals are Phase 3); but custom_id parsing via regex IS input validation — must reject malformed |
| V6 Cryptography | no | None hand-rolled |

### Known Threat Patterns for `discord.py` 2.7.1 bot

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| `custom_id` injection via crafted button payload | Tampering | Regex `template` is `fullmatch` by Discord; type-cast all match groups (`int(match["channel_id"])`) so non-digit → ValueError → log + ephemeral error |
| Unauthorized button click (Player B clicks Player A's End Turn) | Elevation of Privilege | Each callback checks `interaction.user.id` against the actor encoded in `custom_id`; mismatch → `send_warning(NOT_YOUR_TURN)` |
| Embed XSS via reflected user content | Tampering | Phase 2 embeds use only Phase-1-validated data (campaign_name from `channel_sessions`, sanitized at insert time); never embed raw modal input |
| 3s ack DoS (slow callback fails token, bot looks dead) | Denial of Service | EDM001 enforces defer-first |
| Discord token leak in logs/error traces | Information Disclosure | structlog config (Phase 1) does not log env vars; verify by greping log fixtures for `DISCORD_TOKEN` |
| Persistent button orphaned after channel delete | Availability | `coalescer` catches `NotFound`/`Forbidden` and abandons; periodic cleanup of orphaned `persistent_views` rows deferred to Phase 5 |

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|---|---|---|---|
| `add_view(View(), message_id=...)` per active persistent button | `add_dynamic_items(Cls)` once at startup | discord.py 2.4 (2023) | Removes per-message bookkeeping; supersedes a large class of "view rehydration" tutorials |
| Hardcoded `custom_id="combat:attack:12345"` strings | Regex `template=r"combat:attack:(?P<id>\d+)"` with `DynamicItem` | discord.py 2.4 | Pattern-based dispatch — no manual switch/case in `on_interaction` |
| `commands.Bot.event(on_ready)` for setup | `commands.Bot.setup_hook()` | discord.py 2.0 | Setup runs before gateway; failures cleanly abort startup |
| Sync slash commands every startup | `tree.copy_global_to(guild=...)` + scoped sync | discord.py 2.0+ | Faster guild-scoped updates; global sync limited to ≤200/day rate limit |
| Manual rate-limit handling | Trust `discord.py.HTTPClient` internal limiter | discord.py 1.x → 2.x | Don't reinvent — coalesce upstream of the HTTP layer instead |

**Deprecated/outdated:**
- `discord.py 1.x` View/Button patterns — fully superseded by 2.x UI module
- `pycord`/`nextcord` as the "active alternative" — discord.py is active again in 2026, no longer needed
- Rapptz-archived 1.x examples that say `add_view(message_id=...)` is mandatory for persistence — DynamicItem path is the modern way

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|----------------|
| A1 | dpytest 0.7.0 imports cleanly on discord.py 2.7.1 (README says 2.6) | Q2 / Standard Stack | Low — fallback to mock-based testing already documented; just skip dpytest if import fails |
| A2 | Discord's edit rate limit is 5/5s per channel (no separate per-message bucket) | Q6 / Pitfall 4 | Medium — if there's a stricter per-message bucket, our 1/s/message coalescer is still safe; the Phase 4 multi-coalescer concern stands |
| A3 | `add_dynamic_items` alone is sufficient for restart-survival (no `add_view(message_id=...)` needed) | Q1 / Pitfall 1 | LOW — backed by official `dynamic_counter.py` example + thegamecracks tutorial; restart drill will verify empirically |
| A4 | `setup_hook` exceptions propagate up to `bot.start` and abort startup cleanly | Q7 | LOW — confirmed by github.com/Rapptz/discord.py issue #8210 |
| A5 | `embed.to_dict()` is stable across 2.7.x patch versions | snapshot test plan | LOW — Discord's REST API is the schema, discord.py mirrors it |

## Open Questions

1. **Does dpytest 0.7.0 import cleanly on discord.py 2.7.1?**
   - What we know: dpytest README claims 2.6 support; last commit January 2026 is type-checking work, not a 2.7 bump.
   - What's unclear: Whether the discord.py 2.6 → 2.7 changes broke any imports dpytest relies on.
   - **Recommendation:** First task of Phase 2 Wave 0 includes `pip install dpytest && python -c "import dpytest"` in `tests/bot/conftest.py` as a `pytest.importorskip("dpytest")` gate. If skip — we just don't use it. Restart drill works without it.

2. **Should Phase 2 implement the `ChannelEditBudget` shared rate-limiter, or defer to Phase 4?**
   - What we know: Per-channel limit (5/5s) means 3+ active coalescers per channel will collide.
   - What's unclear: Whether Phase 4 will hit it before we've built the shared budget.
   - **Recommendation:** Phase 2 ships `EmbedCoalescer` accepting an optional `channel_budget: ChannelEditBudget | None = None` parameter. Phase 2 leaves it `None` (per-message limiter is sufficient for Phase 2's single `/status` and stub buttons). Phase 4 wires it up. **Stub the class** (`class ChannelEditBudget: pass`) in `coalescer.py` so Phase 4 has the integration seam.

3. **Sync app command tree globally vs per-guild on every startup?**
   - What we know: Global sync rate-limited to ~200/day. Per-guild propagates instantly.
   - **Recommendation:** If `DISCORD_GUILD_IDS` env is set (dev/staging case), sync to those guilds. Else global sync **only if** a flag like `--sync-global` is passed (avoid hitting the limit on every restart in prod). Document in `.env.example`.

## Sources

### Primary (HIGH confidence)
- [discord.py persistent.py example](https://github.com/Rapptz/discord.py/blob/master/examples/views/persistent.py) — verified pattern for `add_view`
- [discord.py dynamic_counter.py example](https://github.com/Rapptz/discord.py/blob/master/examples/views/dynamic_counter.py) — verified DynamicItem pattern
- [discord.py PyPI 2.7.1](https://pypi.org/project/discord.py/) — verified release date 2026-03-03
- [discord.py changelog](https://discordpy.readthedocs.io/en/latest/whats_new.html) — DynamicItem bugfixes in 2.6/2.7
- [discord.py Interactions API](https://discordpy.readthedocs.io/en/stable/interactions/api.html) — defer/followup semantics
- [github.com/Rapptz/discord.py issue #8210](https://github.com/Rapptz/discord.py/issues/8210) — `setup_hook` + `bot.close()` failure mode
- [github.com/Rapptz/discord.py discussion #9851](https://github.com/Rapptz/discord.py/discussions/9851) — persistent dynamic buttons

### Secondary (MEDIUM confidence)
- [thegamecracks "Writing Persistent Views"](http://blog.thegamecracks.xyz/discord.py/persistent_views.html) — definitive explanation of `add_view` vs `add_dynamic_items`
- [space-node.net Discord rate limiting guide 2026](https://space-node.net/blog/discord-bot-rate-limiting-guide-2026) — 5/5s edit rate limit confirmed
- [Discord API rate-limits doc](https://discord.com/developers/docs/topics/rate-limits) — official rate-limit semantics
- [github.com/CraftSpider/dpytest commits](https://github.com/CraftSpider/dpytest/commits/master) — last commit 2026-01-13

### Tertiary (LOW confidence — verified via cross-source, kept for completeness)
- [codepr.github.io asyncio-pubsub](https://codepr.github.io/posts/asyncio-pubsub/) — background on Event-based pubsub patterns

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all packages inherited from Phase 1, no new deps
- DynamicItem + add_view relationship: HIGH — verified via official example file + tutorial
- Defer / followup semantics: HIGH — multiple sources agree
- dpytest 2.7.1 compatibility: MEDIUM — claim is 2.6; need import-smoke-test
- Rate limit (5/5s per channel): HIGH — Discord docs + multiple guides
- EDM001 implementation: HIGH — AST module is stable, recipe is concrete
- Coalescer race-free design: HIGH — single-threaded asyncio + slot/event pattern is well-understood

**Research date:** 2026-05-21
**Valid until:** 2026-06-20 (30 days — `discord.py` stable, dpytest activity slow)
