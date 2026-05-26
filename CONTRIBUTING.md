<!-- generated-by: gsd-doc-writer -->
# Contributing to EldritchDM

Welcome, and thank you for considering a contribution. EldritchDM is an open-source, Apache 2.0-licensed Discord bot for running D&D 5e games end-to-end with a local AI Dungeon Master. The project exists because we believe a "forever DM" should be possible without API bills, hosted SaaS, or surrendering the rule integrity that makes 5e feel like 5e. Contributions of every size are welcome — bug reports, doc fixes, new MCP wrappers, lint rules, or whole new features.

There is one rule that is not up for negotiation. We'll get to it in a moment.

---

## Project values

- **Local-first.** The bot runs on your machine, talks to your local oMLX, owns its own SQLite. There is no hosted variant and never will be.
- **Mechanically honest.** Narration is the LLM's job. Math is Python's job. The two never mix.
- **Standing on giants.** The 5e engine is [`dm20-protocol`](https://github.com/Polloinfilzato/dm20-protocol). This bot is a Discord adapter plus a small amount of Discord-specific state. We do not reimplement game mechanics.
- **Small, focused, atomic.** Phases are small, plans are smaller, commits are smaller still.

---

## Code of conduct

Please read [`CODE_OF_CONDUCT.md`](./CODE_OF_CONDUCT.md) before contributing. The short version: be kind, be patient, assume good faith. If something feels off — an interaction in an issue, a PR comment, a discussion thread — email **jeremy@shoemoney.com** directly. Don't escalate it in the issue tracker. The maintainer commits to acknowledging your report within 48 hours.

---

## Setting up your environment

Don't duplicate setup instructions here. The canonical paths live in:

- [`README.md`](README.md) — 30-second quickstart for normal use.
- [`INSTALL.md`](INSTALL.md) — operator-grade install with worked examples.
- [`docs/GETTING-STARTED.md`](docs/GETTING-STARTED.md) — checkpointed first-roll walkthrough (and Docker quickstart).
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — how the three-brain split works.
- [`docs/CONFIGURATION.md`](docs/CONFIGURATION.md) — every `.env` variable, every config knob.
- [`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md) — dep groups, console scripts, pre-commit, lint rules, CI matrix.

The TL;DR: clone the repo, run `./install.sh`, copy `.env.example` to `.env`, run `python -m eldritch_dm.bootstrap`, run `python run.py`. You need oMLX running locally on `:8765` with `ShoeGPT` loaded and the dm20 MCP server exposed.

---

## The load-bearing architectural rules

These are quoted directly from `CLAUDE.md` and the project requirements. Every PR is reviewed against them. **A PR that violates any of these will be sent back regardless of how clever the code is.**

1. **The LLM is forbidden from computing math.** All numerical effects originate in Python (or dm20). The LLM is given facts to narrate; it never produces HP, damage, AC checks, saving throws, or turn-order decisions. If your PR has the LLM deciding "the goblin takes 7 damage," that is a rejected PR. Route the mechanical effect through a `dm20__*` MCP call and pass the resulting fact to the narrator. v1.5's cache layer extends this contract — every cache (`mcp/cache.py`, `persistence/character_cache.py`, `observability/narration_cache.py`) is **fail-CLOSED** with an explicit allow-list. Adding a new cache without a fail-CLOSED allow-list breaks the integrity rule.
2. **Persistent Discord views must use `discord.ui.DynamicItem` with a regex `custom_id`** and be registered in `setup_hook`. Buttons must survive a `Ctrl+C` and restart. If a button stops working across restart, that's a bug.
3. **The first line of every interaction callback is `await interaction.response.defer(thinking=True)`.** A custom AST lint rule (`EDM001`, in `src/eldritch_dm/lint/edm001.py`) fails CI if any callback omits this. Discord's 3-second interaction timeout is shorter than any LLM call.
4. **All writes to the main `eldritch.sqlite3` go through the single async writer task using `BEGIN IMMEDIATE`.** Do not open a second writer connection. Do not bypass the writer queue. The WAL + single-writer design is what keeps the 4-channel concurrent stress test (v1.8) green. Cache SQLites (`mcp_cache.sqlite`, `character_cache.sqlite`, `monster_memory.sqlite`) intentionally live outside this queue — they have their own lazy connections.
5. **Player free-text must pass through `sanitize_player_input` before any LLM or MCP call.** No exceptions. Modal text, slash command strings, names, descriptions — anything a player typed. The adversarial corpus in `src/eldritch_dm/safety/corpus/injection_cases.yaml` will catch you if you skip this.

---

## Before you open a PR — the checklist

1. **Discuss design first if it's bigger than a bug fix.** Open an issue and we'll talk about scope before you sink hours into code. The roadmap is intentionally tight; we'd rather hear "I want to build X" before you've built three days of X.
2. **Match the existing tech stack.** No new heavyweight dependencies without discussion. The stack in `CLAUDE.md` is the result of explicit research and pushback against alternatives. Adding `langchain` or `sqlalchemy` or `aiohttp` needs a conversation, not a `pip install`.
3. **Tests pass.** Run `pytest` locally. If your change touches concurrency, load, or perf, also run `RUN_STRESS=1 pytest` (multi-channel stress + perf profiler), `RUN_LOAD=1 pytest` (8-player combat load test), and `RUN_INTEGRATION=1 pytest tests/bot/test_restart_drill.py`. See [`docs/TESTING.md`](docs/TESTING.md) for the full env-gate table.
4. **Lint is clean.** Run `ruff check src/ tests/ run.py` and `ruff format`. Run `python -m eldritch_dm.lint.edm001 src/eldritch_dm/bot/` to confirm the EDM001 defer-first rule is satisfied. Run `pyright` (or `mypy` if you prefer) to catch type regressions.
5. **Import-linter contracts are clean.** Run `lint-imports` to verify module boundaries. `mcp/` must not import `bot/` or `ingest/`. `bot/` and `ingest/` must not import `gameplay/` internals. `safety/` may only import the pure pydantic models from `persistence/`, never the repos. `eval/` (v1.2+) must not import `bot/` or `ingest/`. The contracts in `pyproject.toml` are the source of truth — all 8 must pass.
6. **Coverage holds.** CI runs `pytest --cov=eldritch_dm --cov-report=term --cov-report=xml:coverage.xml` (the Linux runner uploads `coverage.xml` as an artifact). Test contributions are welcome and expected for new feature work; see `.planning/COVERAGE-AUDIT-v1.14.md` for the current state.
7. **Commit messages use the conventional prefix.** Format:
   - `feat(NN-phase-slug): subject` — new feature within a phase
   - `test(NN-NN): subject` — tests for a specific plan within a phase
   - `fix(NN-phase-slug): subject` — bug fix
   - `docs(NN-...): subject` — documentation for a phase or plan
   - `refactor(scope): subject` — non-behavioral cleanup
   - `chore(scope): subject` — tooling, CI, dependencies

   Atomic commits per logical change. Don't smash a refactor + a feature + a doc tweak into one commit.
8. **PR description explains *why*, not just *what*.** Link to the issue, the phase plan in `.planning/phases/`, or the requirement ID (e.g., `COMBAT-04`) the change satisfies. A good PR description saves the reviewer (and future-you) hours.

---

## Adding a feature — the GSD flow

This project uses a phased planning workflow. Look at `.planning/phases/` for the structure — each phase has its own directory with research, plans, and summaries. Milestone-level history is collapsed in [`CHANGELOG.md`](CHANGELOG.md) (Keep-a-Changelog format, one entry per shipped version v1.0 → v1.11+).

The flow is roughly:

1. **RESEARCH.md** — a short investigation: what's the existing surface, what are the open questions, what are the alternatives.
2. **NN-PLAN-<slug>.md** — a concrete plan with a numbered task list, file list, and success criteria. One plan per logically-grouped chunk of work (~30–180 min of execution).
3. **Execute** — write the code one plan at a time, commit atomically as you go.
4. **NN-SUMMARY.md** — what landed, what was deferred, what was learned. Updates `.planning/STATE.md` and `.planning/ROADMAP.md` to mark the phase complete.
5. **Milestone closure** — when a phase set ships as a tagged release, a `v1.N-MILESTONE-AUDIT.md` is added under `.planning/` and a new `[v1.N]` block is prepended to `CHANGELOG.md`.

For a small bug fix or doc tweak, you can skip the plan/summary — just write the patch and use `/gsd-quick`. For anything cross-cutting (new MCP wrapper class, new Discord view kind, new persistence table, new cache layer), the work probably belongs in a **new phase or a new plan within an existing phase**. Open an issue, propose the phase boundary, and we'll figure out where it goes together.

### Filing context

- [`CHANGELOG.md`](CHANGELOG.md) — authoritative rolling release log; the entry above v1.0 is your baseline for "what already shipped."
- [`.planning/UPSTREAM-ISSUES.md`](.planning/UPSTREAM-ISSUES.md) — known dm20-side issues that block our integration work. Reference an `ISSUE-N` row in a PR if your change is gated on an upstream fix.
- [`.planning/SECURITY-BACKLOG.md`](.planning/SECURITY-BACKLOG.md) — v1.11-introduced future-tracking surface for security work; use the filing template if you discover something.
- [`.planning/ROADMAP.md`](.planning/ROADMAP.md) — current phase map and next-milestone signal.

---

## What NOT to contribute

These are explicit non-goals for v1 (see README → "Known Limitations & v1 Non-Goals"). Please don't open PRs for them — they will be politely declined.

- **Voice channel / TTS narration.** Text only. The bot does not join voice channels.
- **Generated battle maps or token grids.** Combat is theater-of-the-mind plus a turn tracker embed.
- **A hosted SaaS variant** (`eldritchdm.com`, multi-tenant deployment, billing). This is local-first by design.
- **Native mobile clients.** Discord is the only client surface.
- **Custom homebrew classes/races/items via slash command UI.** Homebrew belongs in dm20's content-authoring layer, not a modal. (Riposte eligibility is a special case — homebrewable via `database/eligibility.yaml`, see Phase 8.)
- **Difficulty sliders or 5e variant rules** (flanking, gritty realism, lingering injuries). Variant rules are dm20's decision to support; the bot doesn't add a UI for them.
- **"Just let ShoeGPT decide HP for vibes" mode.** This is the load-bearing rule. Don't try.

Many of these are good ideas for v2. Open a `[idea]` issue (see below) and they'll shape what comes after v1.

---

## Reporting bugs

Open a GitHub issue with the `bug` label. Include:

- **What you did** — a minimal reproduction, ideally the exact slash command or interaction sequence.
- **What you expected** — what should have happened?
- **What actually happened** — the error message, the wrong embed, the missing button, etc.
- **Log snippet with `LOG_LEVEL=DEBUG`** — set `LOG_LEVEL=DEBUG` in your `.env`, restart the bot, reproduce, and paste the relevant log lines. JSON logs (`LOG_FORMAT=json`) are easiest for log shippers; `console` is easiest for humans.
- **Your dm20 version** — run `dm20__check_for_updates` via the bot or the MCP gateway directly, paste the version string.
- **Your environment** — macOS or Linux, Apple Silicon or otherwise, Python version, oMLX version, EldritchDM tag (`git describe --tags`).
- **Whether you're using the Docker stack** (v1.10+) or running natively.

Before filing, please check [`docs/TROUBLESHOOTING.md`](docs/TROUBLESHOOTING.md) — 14 entries grounded in real v1.0-v1.9 SUMMARY surface cover the common failures. Reproductions from the test suite are gold.

---

## Feature ideas

Have a wild idea that isn't on the roadmap? Open an issue with `[idea]` as the title prefix. Examples:

- `[idea] surface dm20 token positions as an inline minimap image`
- `[idea] /handoff_dm flag to put ShoeGPT into narration-only and let a human resolve mechanics`
- `[idea] optional ElevenLabs TTS pipe for narration`

`[idea]` issues don't need to land in v1. They shape what v2 looks like, and many of them are already on the post-v1 backlog. Even if the answer is "great idea, but not now," the discussion thread is valuable.

---

## Security

If you've found a security issue — a way to bypass `sanitize_player_input`, a token-leak path, a privilege escalation in turn gatekeeping, a way to make the bot forge MCP tool calls — **please do not open a public issue**.

Email **jeremy@shoemoney.com** directly with the details and a reproduction. You'll get a response within a few days. Once the fix is in, the issue can be discussed publicly and you'll be credited (unless you'd prefer not to be). The v1.11 cross-cutting security audit (`SECURITY-AUDIT-v1.11.md` + `SECURITY-BACKLOG.md`) is the canonical inventory of the project's security surface; new findings get filed into `SECURITY-BACKLOG.md` using its template.

---

## License

EldritchDM is Apache 2.0-licensed. By contributing, you agree that your contributions are licensed under the same Apache 2.0 terms (see [`LICENSE`](LICENSE)). You retain copyright on your contributions; you're granting the project the right to use, modify, and distribute them under Apache 2.0 — including the patent grant in Section 3 of the license.

---

Thanks again for being here. The fact that the bot exists at all is because contributors keep showing up. Roll well. 🎲
