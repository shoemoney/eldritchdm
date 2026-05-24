# Feature Landscape: EldritchDM

**Domain:** AI-orchestrated D&D 5e Discord bot (three-brain architecture)
**Researched:** 2026-05-21
**Confidence:** MEDIUM-HIGH (cross-verified against shipping products: Avrae, Fables.gg/Friends & Fables, AI Dungeon, AI Realm, RoleForge, WorldSmith, plus reddit/blog post-mortems on ChatGPT-as-DM)

---

## Category 1: Table Stakes for *Any* Discord D&D Bot

These are baseline expectations set by Avrae (the de facto Discord D&D standard, now owned by WotC/D&D Beyond). Missing any of these makes the product feel broken on day one.

| Feature | Why Expected | Complexity | Dependencies | Phase |
|---------|--------------|------------|--------------|-------|
| **Persistent character storage** | Avrae stores sheets per-user across servers; players expect their PC to survive bot restarts | Medium | SQLite schema, user-id keying | Phase 1 (Foundation) |
| **Dice parser with advantage/disadvantage/crit** | Avrae's `!r 1d20+5 adv` is muscle memory for 5e Discord players | Medium | Python expression parser, RNG | Phase 1 |
| **Initiative tracker with turn order** | The single most-used Avrae feature; combat without it is unusable | Medium | State machine, ordered list, current-turn pointer | Phase 3 (Combat) |
| **Per-channel concurrent sessions** | One bot, many tables; servers expect isolation | Medium-High | DB row-level keying by `channel_id`, WAL locking | Phase 1 |
| **Rich embeds for stat blocks / HP bars** | Discord's visual grammar for TTRPG; plain text feels like 1995 | Low | `discord.py` Embed API | Phase 2 |
| **Slash command surface (`/start_game`, `/roll`, `/attack`)** | Post-2022 Discord norm; legacy `!` prefix is dated | Low | `discord.app_commands` | Phase 1 |
| **Ephemeral error/warning messages** | Out-of-turn attempts, invalid inputs — must not pollute channel | Low | Discord ephemeral message flag | Phase 2 |
| **5e rules/spell/monster lookup** | Avrae's killer feature post-WotC acquisition; users will type `/lookup fireball` | Medium | Open5e API client + local cache | Phase 2 |
| **Full resume across bot restarts** | Long campaigns are the point; in-memory-only state is a non-starter | High | DB bootstrap on connect, view rehydration | Phase 1 + Phase 4 |

**Comparison point:** Avrae nailed all of these by ~2019. Any new Discord D&D bot is measured against this baseline before it gets credit for anything novel.

---

## Category 2: Table Stakes for *AI* DM Products

These are expectations set by Fables.gg/Franz, AI Realm, RoleForge, WorldSmith — the current AI-DM market. Missing these makes it "ChatGPT roleplay" not "AI DM."

| Feature | Why Expected | Complexity | Dependencies | Phase |
|---------|--------------|------------|--------------|-------|
| **Distinct DM persona** | Franz, AI Realm's GMs all have voice/style — ShoeGPT is this for EldritchDM | Low | System prompt design | Phase 2 |
| **Long-term campaign memory** | #1 ChatGPT-as-DM complaint (40% of solo RPG players cite memory loss). Fables tiers memory explicitly (25/100 memories) | High | `campaign_memory` table, summarization pipeline, retrieval | Phase 4 (Memory) |
| **Narrative continuity across sessions** | NPCs you befriended must remember you; quest threads must persist | High | Memory + retrieval + prompt injection | Phase 4 |
| **Rule-enforced combat (not vibes-based)** | ChatGPT-as-DM "combat is whatever sounds good" is the meme failure mode | High | Rules engine, deterministic resolver | Phase 3 |
| **HP / AC / condition tracking that actually sticks** | Documented failure: "ChatGPT sometimes gets AC wrong" — must be impossible by design | Medium | DB-backed state, no LLM writes to numbers | Phase 3 |
| **Inventory + character stat persistence** | Franz auto-manages this; users expect zero manual bookkeeping | Medium | Item table, inventory mutations through engine only | Phase 2 |
| **NPC voice variation in narration** | Fables/Franz uses TTS-distinct character voices; minimum: textual voice differentiation | Low | Prompt templates per NPC | Phase 2 |
| **Multiplayer turn discipline** | Documented failure: "AI asks what you do next without giving monsters their turn" | Medium | Turn-gatekeeping in orchestrator, not LLM | Phase 3 |
| **Scene/state awareness in narration** | Narrator must know current location, present NPCs, time of day | Medium | State serialization into prompt context | Phase 2 |

**Comparison point:** Fables.gg leads on memory/world-building; AI Dungeon lags on rule enforcement. The gap EldritchDM targets is the union: Fables-grade persistence + Avrae-grade rule rigor.

---

## Category 3: Differentiators — Three-Brain Architecture

These are EldritchDM-specific advantages. No shipping competitor combines all of them.

| Feature | Value Proposition | Complexity | Dependencies | Phase |
|---------|-------------------|------------|--------------|-------|
| **Mechanically honest narration** | LLM is *forbidden* from emitting numbers; all math originates in Python and is passed *to* LLM as facts to narrate. Eliminates the #1 AI-DM failure mode by construction, not by prompt-prayer | High | Strict prompt contract, output validator, engine-first resolution pipeline | Phase 2 + Phase 3 |
| **Riposte timed reactive UI** | 8-second class-gated button after monster miss; turns Discord's async UI into reactive combat. No competitor does this | Medium-High | `discord.ui.View` with timeout, eligibility gate, race-safe interaction handler | Phase 3 |
| **OCR + PDF character ingest** | Drop a character sheet PNG/PDF into Discord, get a playable PC in <6s. Fables makes you fill forms; Avrae requires D&D Beyond import. EldritchDM accepts anything | Medium-High | EasyOCR, pypdf, LLM-as-translator to JSON schema, validation | Phase 2 |
| **Action-batching exploration phase** | Collect all players' intents via modals, auto-roll relevant skill checks, batch into one narration prompt. Cuts token cost, prevents one-player-monopolizing | Medium | Modal collector, intent queue, batched prompt assembler | Phase 2 |
| **Local-first, zero API spend** | MLX on Apple Silicon; no OpenAI bill, no rate limits, no data egress. Fables/RoleForge all charge per-player or per-turn | Medium | `mlx-lm.server`, OpenAI-compatible client, hardware tuning | Phase 1 |
| **MCP-style tool registry for the LLM** | `lookup_open5e_rule`, `search_monster_guide`, `save_session_memory` exposed as tools — LLM requests data instead of fabricating it | Medium | Tool dispatcher, OpenAI tool-calling schema, MCP-style declarations | Phase 2 |
| **Dodge mechanic with auto-disadvantage** | Action economy enforced: dodging sets `is_dodging`, forces disadvantage on incoming attacks, auto-resets next turn. Most AI DMs ignore action economy entirely | Low-Medium | Status flag on character, attack resolver checks flag | Phase 3 |
| **8+ player initiative UI** | Fables caps at 6; home games often have 7-8. EldritchDM's embed/view design must handle this from day one | Medium | Pagination or compact UI in initiative embed | Phase 3 |
| **Self-hostable, single-binary install** | Clone, set token, run. Fables/AI Realm are SaaS-only. Privacy-conscious tables (and DMs who don't want vendor lock) need this | Medium | `requirements.txt`, config template, schema bootstrap, README | Phase 5 (Polish) |

**Comparison point:** No shipping product in 2026 combines local inference + rule-rigid combat + reactive Discord UI + self-host. Fables has memory & UI but is SaaS+LLM-as-judge. Avrae has rigor but no AI DM. EldritchDM occupies the empty quadrant.

---

## Category 4: Anti-Features — Deliberately NOT Built

These are temptations that would either dilute the value prop or recreate the very failure modes EldritchDM is designed to prevent. Each is non-trivial because *they're what most AI DM products do*.

### Anti-Feature 1: Free-form "chat with the DM" without state transitions
**What it would look like:** Users `@ShoeGPT` and chat naturally, AI infers context.
**Why avoid:** This is exactly the ChatGPT-as-DM failure mode. Without explicit state (`LOBBY/EXPLORATION/COMBAT_INIT/COMBAT`), the bot can't enforce turn order, can't gate actions, can't even know whose turn it is. Documented failure: combat re-starting after enemies are dead, AI skipping monster turns.
**Do instead:** All player actions flow through *typed UI affordances* (slash commands, buttons, modals) that map cleanly to state-machine transitions. The LLM never decides what's allowed; the engine does.

### Anti-Feature 2: LLM-computed math, dice, or numerical effects
**What it would look like:** "ShoeGPT, the goblin hits Thorin for 7 damage." LLM emits the 7.
**Why avoid:** This is *the* architectural thesis of the project. Documented failure across every LLM-DM product: HP drift, AC errors, crit math wrong, save DCs invented. Once you allow it, you can't audit it. Even GPT-4-class models fabricate numbers under load.
**Do instead:** Python engine resolves everything. LLM receives a structured result (`{attack: hit, damage: 7, target: Thorin, hp_before: 24, hp_after: 17}`) and is prompted to *narrate the fact*, not derive it. Output validator rejects narration containing unsanctioned numbers.

### Anti-Feature 3: Unbounded narration length / "infinite rambling DM"
**What it would look like:** Let the LLM generate until it stops. Tolerate 800-word combat narrations.
**Why avoid:** Discord embeds have hard limits (~2k/4k chars). Latency on local MLX scales with tokens — a 500-word narration on a 4-bit MoE is 8-15s, which breaks Discord's 3-second interaction ack. Long narration also crowds the channel for 8 players. Documented as a top AI Dungeon complaint ("inconsistent prose and pacing").
**Do instead:** Hard cap at ~150 words per narration (per PROJECT.md constraint). Enforce via `max_tokens` and persona prompt. If more is needed, follow-up embed.

### Anti-Feature 4: LLM-as-judge for rule disputes
**What it would look like:** "Hey ShoeGPT, can I shove this enemy off the cliff with my bonus action?" — LLM rules on it.
**Why avoid:** Inconsistency across sessions, no auditability, players will argue with the LLM and waste tokens, and ambiguous rulings will favor whoever phrased their request more persuasively. Avrae solved this by deferring to actual rule text from licensed content.
**Do instead:** Tool-call `lookup_open5e_rule` and present the actual rule. Hard-coded resolver covers the common 5e rules (attack, save, skill check, dodge, opportunity attack). Edge cases prompt the *human table* to rule, not the LLM.

### Anti-Feature 5: Image/map generation
**What it would look like:** Fables.gg-style battlemaps and image studio.
**Why avoid:** Scope explosion, hardware cost (image models compete with LLM for memory on Apple Silicon), latency unacceptable on local inference, and Discord's UX for tactical maps is bad anyway. Fables has a whole team on this; EldritchDM doesn't.
**Do instead:** Optional Phase-N feature. Theater-of-the-mind is a legitimate 5e play style and aligns with text-Discord medium.

### Anti-Feature 6: Cross-server character portability / cloud sync
**What it would look like:** Avrae-style "your character travels with you."
**Why avoid:** Self-host model means each instance is its own world. Cross-instance sync requires hosted infra, identity, auth — all of which violate the local-first thesis.
**Do instead:** Export/import character JSON manually. Document the schema.

### Anti-Feature 7: Voice / TTS narration
**What it would look like:** Franz-style TTS character voices.
**Why avoke:** Discord voice integration is a different async surface, TTS competes for local compute, and most home tables already have voice channels with humans talking. Not the differentiator.
**Do instead:** Excellent textual voice differentiation (per-NPC prompt templates). Defer TTS indefinitely.

### Anti-Feature 8: "Auto-DM mode" that plays without player input
**What it would look like:** AI Dungeon-style narration that continues if no one types.
**Why avoid:** Removes player agency, burns tokens, and is the exact opposite of "honest mechanical DM." The bot waits.
**Do instead:** Explicit prompts ("Whose turn is it? Click your action.") and idle timeouts that *pause*, not advance.

---

## Feature Dependencies

```
Phase 1 (Foundation):
  SQLite + WAL  →  Slash commands  →  MLX client
       ↓                ↓                 ↓
       └──── Persistent state ──────────────┘
                    ↓
Phase 2 (Exploration + Ingest):
  Character ingest (OCR/PDF)  →  Persona prompt  →  MCP tools
                                       ↓
                                Open5e lookup
                                       ↓
                             Action batching + narration
                                       ↓
Phase 3 (Combat):
  Initiative  →  Turn gatekeeping  →  Attack resolver
                       ↓                    ↓
                   Dodge state         Riposte UI
                                            ↓
Phase 4 (Memory + Continuity):
  campaign_memory table  →  Summarization  →  Retrieval injection
                                ↓
                       Multi-session continuity
                                ↓
Phase 5 (Polish + Self-Host):
  README + config template  →  Test suites  →  Resume-from-restart verification
```

---

## MVP Recommendation

Per PROJECT.md ("Full PRD scope as v1 — sub-MVPs would feel broken"), MVP = full PRD. But within that, the *order* matters:

1. **Phase 1 (Foundation):** DB, slash commands, MLX client, lobby — the skeleton.
2. **Phase 2 (Exploration):** Character ingest, persona, MCP tools, action batching — proves the three-brain split works.
3. **Phase 3 (Combat):** The hardest, riskiest phase. Initiative, dodge, riposte, attack math. Where the architecture earns its keep.
4. **Phase 4 (Memory):** Campaign continuity. Required for "forever DM" promise.
5. **Phase 5 (Polish + Self-host):** README, tests, resume verification, performance pass.

**Defer:** Image gen, TTS, cross-server sync, web dashboard. None block the core value prop.

---

## Sources

- [Avrae](https://avrae.io/) — Discord D&D bot, owned by WotC; canonical feature baseline
- [Avrae GitHub](https://github.com/avrae/avrae) — Source for feature surface
- [Friends & Fables / Fables.gg](https://fables.gg/) — Leading AI DM product, 100k+ users; Franz feature set, memory tiers
- [Fables: A New Chapter](https://fables.gg/blog/a-new-chapter) — Roadmap and worldbuilding features
- [Best AI Dungeon Masters 2026 (AIDungeonMaster.ai)](https://aidungeonmaster.ai/blog/best-ai-dungeon-masters-2026/) — Market survey
- [Best AI Game Master Tools (RoleForge)](https://roleforge.ai/blog/best-ai-game-master-tools-compared/) — Competitive comparison
- [Best AI Dungeon Masters (StoryRoll)](https://storyroll.app/blog/best-ai-dungeon-masters-2026) — Cross-product comparison
- [AI Dungeon Alternatives (Worldsmith)](https://www.worldsmith.io/blog/ai-dungeon-alternatives-what-to-use-if-you-actually-want-to-play-dd-1774295313692) — Documented failure modes
- [Why ChatGPT Forgets (Worldsmith)](https://www.worldsmith.io/blog/the-dms-assistant-why-chatgpt-forgets-and-worldsmith-remembers-1771373971322) — Memory-loss failure mode, 40% complaint stat
- [3 Wise DMs: ChatGPT DM Pros/Cons](https://3wisedms.com/our-final-thoughts-the-5-pros-and-cons-of-the-chatgpt-dungeon-master/) — Documented combat/state failures
- [How to Play D&D Solo with AI GM (RoleForge)](https://roleforge.ai/blog/how-to-play-dnd-solo-with-ai-game-master/) — Solo-play feature expectations
- [Mnehmos D&D MCP Server (Skywork)](https://skywork.ai/skypage/en/ai-dungeon-master-toolkit/1980458059440967680) — MCP-for-D&D prior art

**Confidence notes:**
- HIGH on Avrae feature baseline (multiple sources, owned by WotC, longstanding).
- HIGH on documented ChatGPT-as-DM failure modes (cross-confirmed by 3+ blog post-mortems and reddit threads).
- MEDIUM on Fables/Franz specifics (vendor sources + third-party reviews; specific memory tier numbers from vendor).
- MEDIUM on competitor coverage — "Project Magus" and "DM-GPT" did not surface in 2026 comparison roundups; may be defunct, niche, or renamed. Worth a phase-specific re-check if/when scope expands toward them.
