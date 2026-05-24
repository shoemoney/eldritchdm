# Feature Landscape — EldritchDM v1.1 Polish

**Domain:** Local-first AI-DM Discord adapter (combat AI + homebrew extensibility + one-shot upgrade tooling)
**Researched:** 2026-05-23
**Scope:** Only the three user-facing v1.1 deliverables — Smart MonsterDriver (#5), YAML Riposte eligibility (#6), `pc_classes` ingest-backfill (#7). SAN-01 / OPS-02 / `__main__` parity / ruff cleanup are pure plumbing and excluded by request.

---

## Feature 1: Smart MonsterDriver (Claudmaster-routed targeting)

Replaces the v1.0 uniformly-random `random.choice(targets)` (see `src/eldritch_dm/gameplay/monster_driver.py:167-170`) with a deliberate target-selection signal sourced from dm20's Claudmaster autonomous-DM tool. The integrity rule is unchanged — the LLM still does not compute math; it only emits a `target_character_id` from the candidate set, which the rules engine then resolves normally.

### Ecosystem context

Three distinct schools exist in the AI-DM/tabletop space:

| Tool | Approach | Notes |
|---|---|---|
| **Avrae** | No monster AI at all — DM types `!init attack -t <pc>` manually | Avrae is an *initiative tracker*, not an autonomous DM (see Avrae GitHub) |
| **Friends & Fables** | LLM-as-oracle with rules-engine gating | Closest to our hybrid architecture; commercial SaaS |
| **Oracle RPG "Monster AI Rules"** | Pure deterministic flowchart, no LLM | Solo-D&D community standard — Special → Basic → Default tactics, top-to-bottom |
| **Keith Ammann ("The Monsters Know")** | Statblock-driven prose tactics | Most cited heuristics: target spellcasters first, fragile NPCs flee at ≤70% HP, INT-gated reactivity (turns-to-figure-out-weakness ≈ 19 − INT) |
| **gameandtechfocus 5E Monster AI** | Hybrid: INT + WIS thresholds gate access to "smart" branches | Heuristic: critical-wounded > most-wounded > closest > random |

The clear ecosystem consensus is that **pure-random is the floor** (which v1.0 explicitly is, per D-B) and **rule-based heuristics with INT/WIS gating are the expected baseline**. LLM-as-oracle is the SOTA but only when the rules engine still owns the math and the LLM choice is constrained to the candidate set.

### Table stakes (must-have)

| Feature | User behavior | Complexity | Depends on |
|---|---|---|---|
| **Claudmaster target query** | When a monster turn fires, the bot asks dm20's Claudmaster "given this initiative state, who does <monster> attack?" and gets back one `character_id` from the existing PC list | M | dm20 Claudmaster tool surface; `state_provider` already exists in `MonsterDriver.__init__` |
| **Candidate-set constraint** | The LLM's response MUST be one of the PCs already in `state["pcs"]`. If it returns garbage or a non-candidate id, fall back to v1.0 random selection. Never blindly trust LLM output | M | Validation logic + structured-output schema (already a project convention per CLAUDE.md) |
| **Hard latency budget** | Monster-turn target decision returns within 3 s (matches Discord interaction-ack budget already enforced by EDM001 lint). Tested via virtual clock | S | Existing `tenacity` retry stack + new per-call timeout |
| **Random-fallback on Claudmaster failure** | If Claudmaster errors / times out / returns invalid id, fall back to `random.choice(targets)` and log the degradation. Combat never stalls | S | v1.0 random path stays in place as the fallback |
| **INT-gated cleverness** | Low-INT monsters (INT ≤ 5: beasts, oozes, zombies) skip the Claudmaster call entirely and use cheap rules: closest PC, or last PC who damaged them. Don't pay LLM latency for a zombie. Aligns with Oracle RPG + Ammann | M | Need monster INT from dm20 statblock; reasonable cutoffs are INT ≤ 5 = "dumb", 6-11 = "tactical-lite", 12+ = "tactical-smart" |
| **Concealment of LLM identity** | Players don't see "Claudmaster picked you" — narration is unchanged, ShoeGPT voice remains | XS | No UI changes; routing is purely internal |
| **Single-actor scope** | One Claudmaster call per monster turn, not per attack in a multi-attack sequence. All attacks in one turn go at the chosen target unless that target drops | S | Cache the choice for the turn |

### Differentiators (nice-to-have)

| Feature | Value proposition | Complexity |
|---|---|---|
| **Tactical signals in prompt** | Include each PC's current HP%, AC, spellcaster flag (Ammann's "throws fire" heuristic), and conditions in the Claudmaster prompt so it can do the "target the wizard at 30% HP" trick | M |
| **Threat-memory across turns** | Monster remembers who damaged it last round — biases target choice toward retaliation. Cheap: just pass last_attacker_id into the prompt | S |
| **Self-preservation toggle** | INT ≥ 8 monsters at HP ≤ 30% may Dash away instead of attacking (Ammann's wizard-flee heuristic). Returns a non-attack `action` to `combat_action` | L — touches action verbs, defer to v1.2 |
| **Per-monster style override** | Statblock tag like `tactics: "berserker"` or `tactics: "kiter"` shifts the heuristic. Loadable from dm20 monster data | M |
| **Async pre-roll** | Start the Claudmaster call as soon as the *previous* PC's turn ends (during narration time) so by the time the monster's turn fires the answer is cached. Hides latency entirely | L — defer to v1.2 |

### Anti-features (explicitly do not build)

| Anti-feature | Why avoid | Instead |
|---|---|---|
| **LLM rolls dice or computes damage** | Violates the v1.0 integrity rule that has held through 873 tests | LLM picks target id only; dm20 resolves the attack mechanically |
| **LLM picks the *attack action***  (multi-attack, spell choice, item use) | Surface explosion; v1.0 monsters only attack-attack-attack; adding spell-choice is a v2 milestone scope | Keep v1.1 to *targeting* only |
| **Per-attack re-query** | Multi-attack monsters would burn 3 LLM calls per turn — 9s+ latency | One query per turn, cache for the turn |
| **Free-text "monster strategy"** | Inviting "monster casts banishment on cleric" hallucinations — Claudmaster might cite features the monster doesn't have | Structured output: `{target_character_id: <id>}` only, validated against candidate set |
| **Trust the LLM with combatant ids** | id-hallucination is the #1 failure mode for LLM tool-calls (see [codeant.ai poor tool calling](https://www.codeant.ai/blogs/poor-tool-calling-llm-cost-latency)) | Pass enumerated short labels (`P1, P2, P3`), map back server-side |
| **Cross-channel learning** | Tactical state must not leak between channels (privacy + dm20 already isolates) | Each Claudmaster call is stateless from the bot's side — channel-scoped only |
| **Auto-DM mode for the *whole* turn** | Already in PROJECT.md Out of Scope | n/a |

### Dependencies on v1.0 surface

- `MonsterDriver._random_choice` (the injection seam in `monster_driver.py:110`) — replace with `_target_resolver` that has random as the fallback branch
- `state_provider` callable already returns enriched `pcs` list — extend the dict shape with `hp_current`, `hp_max`, `is_spellcaster`, `conditions` (additive; v1.0 callers ignore extras)
- `mcp_tools` — needs a new `claudmaster_pick_target` wrapper or reuse an existing `claudmaster_query` tool from dm20's 97-tool surface
- `ChannelRateLimiter` — Claudmaster call is a mutating MCP call equivalent → must `acquire()` first (same pattern as existing combat_action)
- `circuit_breaker` — Claudmaster failure must not differ from any other MCP failure path

---

## Feature 2: YAML Riposte Eligibility

Replaces the hardcoded `ELIGIBLE_CLASS_SUBCLASSES: frozenset[tuple[str, str]] = frozenset({("fighter", "battle master")})` at `src/eldritch_dm/gameplay/reactions.py:84-88` with a config-file-driven set. The TODO comment in the source already names the pattern (`v2: Make this set configurable via a YAML file so homebrew DMs can extend it`).

### Ecosystem context

| Tool | Convention | Notes |
|---|---|---|
| **Foundry VTT** | JSON in `Data/modules/<id>/`; modules ship as packages | Module system is heavy; user installs a folder under their data dir ([Foundry system development](https://foundryvtt.com/article/system-development/)) |
| **5eTools / Plutonium** | JSON brew files in `homebrew/` directory, hot-loadable | Schema-validated; one file per content type ([Plutonium](https://5e.tools/plutonium.html)) |
| **Super's Homebrew Compendium** | JSON blobs in module dir, requires Foundry restart | Defacto-standard pattern for FVTT 5e community |
| **D&D Unleashed** | Module folder convention | Same as above — JSON, restart-to-apply |
| **autofishbot** | YAML reloaded via watchdog ([github discussion](https://github.com/thejoabo/autofishbot/discussions/132)) | Pattern for hot-reload-on-edit |

The community standard is **JSON files in a known directory + restart to apply**. Hot reload exists but is a differentiator, not table stakes. XDG-style config-home placement is good Linux citizenship; on macOS the conventions are looser but `~/.config/eldritchdm/` works.

### Table stakes (must-have)

| Feature | User behavior | Complexity | Depends on |
|---|---|---|---|
| **Single YAML file at known path** | A self-hoster creates `~/.config/eldritchdm/reactions.yaml` (XDG) or `./reactions.yaml` (project-local override). On startup, bot loads it; if absent, falls back to the hardcoded RAW set | S | New `safety/yaml_loader.py` or extend `config/`; `python-dotenv` is already in deps but YAML isn't — need to add `PyYAML` (or use `ruamel.yaml`) |
| **Schema validation via pydantic** | Malformed YAML (missing required keys, unknown class names, wrong types) fails at startup with a clear error. CLAUDE.md already mandates pydantic v2 for LLM JSON; same model fits here | S | `pydantic >=2.8` already pinned |
| **Normalization parity with `PCClassesRepo`** | YAML entries are lowercased + whitespace-collapsed using the exact same normalizer that `PCClassesRepo` already uses for character data (otherwise eligibility silently mismatches) | XS | Reuse existing normalizer — TODO at reactions.py:81 already names this |
| **Extend semantics (not override)** | The user's YAML *adds* subclasses; RAW Battle Master Fighter is always eligible unless the user explicitly opts out. Default-on for RAW protects naive self-hosters | XS | Merge sets; document override syntax separately |
| **Per-channel scoping NOT required** | Riposte eligibility is a server-wide table-rules decision, not per-game. One file, one set | XS | n/a |
| **Restart-to-apply (no hot reload required)** | Self-hosters edit the file, restart the bot. Matches Foundry/5eTools convention | XS | n/a |
| **Clear error on unknown class names** | If YAML says `class: "warlokk"`, startup fails with a list of canonical class names. Catches typos before they cause silent eligibility misses | S | Validate against a known-class enum |

### Differentiators (nice-to-have)

| Feature | Value proposition | Complexity |
|---|---|---|
| **Hot-reload on file change** | watchdog observer on the YAML — edit + save without restart. Plays well with self-hosters iterating on house rules | M |
| **Per-subclass eligibility metadata** | YAML row carries `trigger: "monster_misses_melee"` so future reactions (Hellish Rebuke, Shield, Absorb Elements) reuse the same loader. Forward-compatible for v1.2 reaction families | M |
| **Override syntax** | Explicit `disable_raw: true` to strip Battle Master Fighter for purists running an alt-Riposte ruleset | XS |
| **YAML lint subcommand** | `python -m eldritch_dm.bot validate-config` parses + validates without booting Discord — like our existing `bootstrap.py` preflight pattern | S |
| **Sample file shipped in `examples/`** | A commented `reactions.example.yaml` so self-hosters copy-and-edit instead of guessing schema | XS |
| **Reload via slash command** | `/admin reload_config` for live editing (admin-gated). Belongs in a v1.2 admin-cog pass, not v1.1 | L — defer |

### Anti-features (explicitly do not build)

| Anti-feature | Why avoid | Instead |
|---|---|---|
| **Per-character eligibility overrides** | Surface explosion — would need migration, UI, audit. Riposte is a class feature, not a character feature | YAML registers subclasses; characters get eligibility from their `pc_classes` row |
| **In-Discord YAML editing** | UX is hostile; would force re-validation on every message edit | File-on-disk only |
| **Arbitrary Python expressions in YAML** | Code execution from a config file is the #1 self-host CVE pattern (see Ansible/SaltStack history) | Pure data: class/subclass strings + booleans only |
| **Database-stored eligibility** | Would need migration tooling and admin UI for what is fundamentally a static table rule | File is the right granularity |
| **Per-guild different configs** | Single self-hoster = single ruleset. The product is local-first, not multi-tenant SaaS | One file per install |
| **Hot reload as a v1.1 requirement** | Adds watchdog dep + threading complexity for marginal UX win. Self-hosters restart for everything else (token changes, dm20 swap) | Restart-to-apply |

### Dependencies on v1.0 surface

- `pc_classes` table normalization rules — must reuse for the YAML loader or the comparison at `reactions.py:152` silently fails
- `ELIGIBLE_CLASS_SUBCLASSES` constant at `reactions.py:84` — becomes a default that is *unioned* with the loaded YAML
- `Settings` / config layer (`src/eldritch_dm/config/`) — extend with `reactions_config_path: Optional[Path]`
- `bootstrap.py` preflight — should fail-fast on malformed YAML so launchd doesn't loop-restart against a bad config

---

## Feature 3: `pc_classes` ingest-backfill (one-shot upgrade tool)

A CLI script that self-hosters run **once** after upgrading from a Phase 4 deployment (pre-Phase 5 schema) to populate the new `pc_classes` table for characters that were ingested before the table existed. Without it, those characters' Riposte eligibility silently returns `False` until they're re-ingested manually. Already named as TD-3 in the audit (`milestones/v1.0-MILESTONE-AUDIT.md:69`).

### Ecosystem context

| Tool | Approach | Relevance |
|---|---|---|
| **Alembic data migrations** | Python op script with explicit batch + idempotency; supports SQL-emit-without-execute for dry-run ([Alembic ops](https://alembic.sqlalchemy.org/en/latest/ops.html)) | Closest reference — Alembic ships data migrations alongside schema ones in the same revision file |
| **Django `RunPython`** | Custom management command, `--dry-run` is a per-command flag convention; reversible function pair | Convention is `class Command(BaseCommand): def add_arguments(...)` |
| **Prisma migrate** | Schema-only — explicitly punts data migration to user scripts | Tells us "ship a separate tool, don't conflate with schema migration" |
| **django-tqdm** | Progress-bar wrapper that integrates with BaseCommand | Establishes that progress UI is expected for long backfills |
| **General Python CLI patterns** | `--dry-run` + idempotent re-run + Rich progress + structured logging | These are 2026 baseline expectations for any CLI tool |

The pattern is **separate one-shot script + dry-run flag + idempotency + progress reporting**. Calling it `migrate` is misleading (the schema is already current; this populates data). Calling it `backfill` or `repair` is clearer.

### Table stakes (must-have)

| Feature | User behavior | Complexity | Depends on |
|---|---|---|---|
| **Discoverable entrypoint** | `python -m eldritch_dm.tools.backfill_pc_classes` OR `eldritch-dm backfill-pc-classes` (via `[project.scripts]` in pyproject.toml — already a v1.0 pattern per audit `## PASSED Integration Surface`) | S | Existing `pyproject.toml` scripts table |
| **Reads from dm20, writes to local DB** | For each channel session in `channel_sessions`, fetch each PC from dm20's character store, extract class+subclass, upsert into `pc_classes` | M | `MCPClient` + `PCClassesRepo` (both v1.0) |
| **Idempotent re-run** | Running twice produces the same end-state. Already-populated rows are skipped (or re-verified). Safe to abort and resume | S | `INSERT OR REPLACE` or pre-read existence check |
| **`--dry-run` flag** | Shows what *would* be inserted/updated without writing. Critical for self-hoster trust (CLAUDE.md "FORCED VERIFICATION") | S | Bypass writer queue in dry-run mode |
| **Progress reporting** | tqdm or Rich progress bar showing characters-processed / total. For small worlds (≤8 PCs) this is trivial but the pattern matters | XS | `tqdm` is a new dep (not in v1.0 pins); Rich is also new. PyMuPDF/PIL deps already pull transitive heavy stuff so adding one CLI lib is acceptable |
| **Exit codes** | 0 = success, 1 = partial (some characters failed but progress made), 2 = config error (no DB, no MCP). Self-hosters script around it | XS | Standard CLI hygiene |
| **Read-only when bot is running** | If lock file (`.eldritch_dm.bot.pid` or similar) exists, refuse to run unless `--force`. The bot's writer queue + this script writing concurrently is the WAL-SQLite anti-pattern | S | Detect via PID file or by attempting an exclusive write lock |
| **Structured log output** | Uses the existing `structlog` JSON renderer so `journalctl` / `launchctl log` capture it. Mirrors v1.0 conventions | XS | Existing logging stack |

### Differentiators (nice-to-have)

| Feature | Value proposition | Complexity |
|---|---|---|
| **`--channel <id>` filter** | Backfill just one channel instead of all — useful for "I added a new player" cases | XS |
| **Re-verify mode (`--verify`)** | Re-reads from dm20 and warns if local row diverges (e.g. player multiclassed since ingest). Belongs in a v1.2 sync-tool though | M |
| **README quickstart snippet** | Single-line copy/paste in the upgrade section ("Run this after pulling v1.1"). Discoverability is half the battle | XS |
| **Rich-rendered diff table** | Show old vs new state in pretty columns for `--dry-run` | M |
| **Single-character mode** | `--character <id>` for surgical fixes | XS |
| **Auto-detect need** | On bot startup, count empty `pc_classes` rows vs `channel_sessions` rows; log a hint ("Run backfill — N characters missing class data") | S |

### Anti-features (explicitly do not build)

| Anti-feature | Why avoid | Instead |
|---|---|---|
| **Auto-run on bot startup** | Schema-vs-data-migration timing is the #1 silent-corruption pattern (Django + Alembic both warn against it). Data migrations need explicit operator consent | Hint-on-startup that backfill is needed; require explicit invocation |
| **Schema migration in same tool** | Conflates two distinct operations; schema lives in code/SQLite migration, data lives here | Schema is already shipped — this populates data only |
| **Rollback / undo** | Backfilling is additive — no rows to "un-backfill". If user wants a row gone, they delete it manually | One-way operation |
| **Recursive re-ingest of OCR/PDF source** | Would need original source paths, modals, user consent — that's the v1.0 ingest flow, not a backfill | Re-ingest is a manual UX action, not a CLI tool |
| **Web UI** | Local-first, CLI is the right surface; the rest of the project doesn't have a web UI either | CLI only |
| **Cross-version migration coordinator** | Over-engineered for "one new column needs filling once". When v1.2 ships, write a new one-shot tool | One script per upgrade, not a framework |
| **Mandatory before-`/start_game` gate** | Would punish new installs that don't need it at all | Optional, opt-in |

### Dependencies on v1.0 surface

- `MCPClient` from `eldritch_dm.mcp.client` — reuse the v1.0 httpx + tenacity + circuit-breaker stack
- `PCClassesRepo` from `eldritch_dm.persistence.pc_classes_repo` — its upsert method
- `ChannelSessionsRepo` — source of truth for "which channels exist"
- `Settings` loader — same `.env`/config resolution as `run.py`
- `bootstrap.py` preflight pattern — copy the 3-stage discipline (deps OK / config OK / MCP reachable) before doing any DB writes

---

## Cross-feature anti-features

| Anti-feature | Applies to | Why |
|---|---|---|
| **New SQLite tables for v1.1** | All three | Schema is locked at v1.0. Backfill writes to *existing* `pc_classes`; YAML is file-based; Smart MonsterDriver writes nothing |
| **New Discord-side persistent Views** | All three | v1.0's `DynamicItem` regex registry is complete. v1.1 is plumbing + smarts |
| **External web service calls** | All three | Local-first invariant from PROJECT.md. dm20 + oMLX only |
| **Breaking API to dm20 MCP** | Smart MonsterDriver | If we need new MCP tools, dm20 must ship them first — coordinate or use existing 97-tool surface |
| **Synchronous code in callbacks** | All three | EDM001 lint enforces `defer(thinking=True)` first line; no blocking calls anywhere on the event loop |

---

## MVP recommendation for v1.1

**Ship order (smallest first, lowest risk first):**

1. **YAML Riposte eligibility** (Feature 2) — XS/S, no new deps beyond PyYAML, zero LLM coupling
2. **`pc_classes` ingest-backfill** (Feature 3) — S/M, reuses every v1.0 component, fixes acknowledged TD-3 debt
3. **Smart MonsterDriver** (Feature 1) — M/L, the largest item, LLM-coupling risk, needs latency testing

Justification: 1 and 2 are pure mechanical engineering with deterministic test surfaces. 3 introduces new LLM latency and failure modes — finishing it last lets us test the smart-targeting against a stable v1.1 baseline rather than mixing risks.

**Defer to v1.2:**

- Smart MonsterDriver: tactical signals beyond `target_character_id`, self-preservation/Dash, async pre-roll
- YAML config: hot reload, reload-via-slash-command
- Backfill tool: verify mode, rich diff table

---

## Sources

- [Oracle RPG — Monster AI Rules for Solo DnD Encounters](https://oracle-rpg.com/2021/11/monster-ai-rules-for-solo-dnd/) — MEDIUM confidence — deterministic flowchart pattern
- [The Monsters Know What They're Doing — NPC Tactics: Mages](https://www.themonstersknow.com/npc-tactics-mages/) — HIGH confidence — Keith Ammann's "fragile spellcasters target prioritization" heuristic
- [Game & Tech Focus — Making of 5E Monster AI](https://gameandtechfocus.com/dd-making-of-5e-monster-ai/) — MEDIUM confidence — INT-gated tactical heuristics
- [Game & Tech Focus — 5E Monster AI Target & Attack Adaptation](https://gameandtechfocus.com/dd-5e-monster-ai-statblock-translation-target-attack-adaptation/) — MEDIUM confidence — "19 − INT turns to figure out weakness" heuristic
- [SlyFlourish — Choosing Targets](https://slyflourish.com/choosing_targets.html) — MEDIUM confidence — "most wounded" / "critically wounded" target categories
- [DMDave — Monster Intelligence](https://dmdave.com/monster-abilities-intelligence/) — MEDIUM confidence — INT-band behavior categories (≤5, 6-11, 12+)
- [Friends & Fables](https://fables.gg/) — MEDIUM confidence — closest commercial peer for LLM+rules-engine combat
- [codeant.ai — Poor Tool Calling LLM Cost & Latency](https://www.codeant.ai/blogs/poor-tool-calling-llm-cost-latency) — HIGH confidence — id-hallucination as primary tool-call failure mode
- [Foundry VTT — System Development](https://foundryvtt.com/article/system-development/) — HIGH confidence — JSON-in-module-folder convention for homebrew
- [Foundry VTT — DnD Content Manager](https://foundryvtt.com/packages/dnd5e-content-manager) — HIGH confidence — community convention for homebrew distribution
- [Plutonium (5eTools) Features](https://5e.tools/plutonium.html) — HIGH confidence — JSON brew file convention with schema validation
- [autofishbot — Config Hot Reload Discussion](https://github.com/thejoabo/autofishbot/discussions/132) — MEDIUM confidence — YAML+watchdog hot-reload pattern
- [OneUptime — Implement Configuration Hot-Reload](https://oneuptime.com/blog/post/2025-12-11-configuration-hot-reload/view) — MEDIUM confidence — Python hot-reload reference implementation
- [Alembic Operation Reference](https://alembic.sqlalchemy.org/en/latest/ops.html) — HIGH confidence — data-migration idempotency + SQL-emit dry-run
- [Hevalhazalkurt — Handling Data in Alembic Migrations](https://hevalhazalkurt.com/blog/handling-data-in-alembic-migrations-when-schema-changes-arent-enough/) — MEDIUM confidence — backfill-after-add-nullable-then-NOT-NULL pattern
- [django-tqdm on PyPI](https://pypi.org/project/django-tqdm/) — HIGH confidence — progress bar in management-command pattern
- [Leapcell — Database Schema Evolution with Alembic and Django Migrations](https://leapcell.io/blog/database-schema-evolution-with-alembic-and-django-migrations) — MEDIUM confidence — separating schema vs data migrations
- [Avrae GitHub](https://github.com/avrae/avrae) — HIGH confidence — confirms Avrae has no monster AI (negative finding informs our positioning)
