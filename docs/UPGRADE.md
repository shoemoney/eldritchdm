<!-- generated-by: gsd Phase 30 plan 30-02 (DOCS-03) -->
# 🧭 EldritchDM — UPGRADE.md

> Version-to-version upgrade notes for operators. Each transition lists the **concrete actions you must take** (if any) and cites the milestone archive it came from. Internal refactors with no operator surface are explicitly called out as "no action".

> 🔗 **Companion docs:**
> - [`INSTALL.md`](../INSTALL.md) — fresh-install walkthrough
> - [`docs/TROUBLESHOOTING.md`](TROUBLESHOOTING.md) — operator FAQ

---

## At-a-glance — which upgrades need action?

| Transition | Operator action required? | What changed |
|---|---|---|
| [v1.0 → v1.1](#v10--v11) | ✅ **Yes** — run `eldritch-dm-backfill-pc-classes` | Riposte eligibility, smart MonsterDriver, YAML eligibility |
| [v1.1 → v1.2](#v11--v12) | 🟡 Opt-in only | Phoenix observability + LLM-judge eval + cost reports |
| [v1.2 → v1.2.1](#v12--v121) | 🟡 If you customized pricing | Hotfix: refresh `database/pricing.yaml` |
| [v1.2 → v1.3](#v12--v13) | ❌ No action | OCR skip-gate is automatic |
| [v1.3 → v1.4](#v13--v14) | ❌ No action | Writer-queue fix is internal |
| [v1.4 → v1.5](#v14--v15) | 🟡 Opt-in only | MCP L2, character cache, narration cache |
| [v1.5 → v1.6](#v15--v16) | 🟡 Opt-in only | Streaming embed, monster memory persistence, owner DMs |
| [v1.6 → v1.7](#v16--v17) | ❌ No action | Cog-wiring + AOE addendum |
| [v1.7 → v1.8](#v17--v18) | ❌ No action | Schema-poller invalidates both caches |
| [v1.8 → v1.9](#v18--v19) | ❌ No action | New CLI: `eldritch-dm-perf-baseline` |
| [v1.9 → v1.10](#v19--v110) | 🟡 Optional | `docker compose up -d` available |

---

## v1.0 → v1.1

**Audit status:** ✅ passed ([`.planning/v1.1-MILESTONE-AUDIT.md`](../.planning/v1.1-MILESTONE-AUDIT.md)).

**Headline change:** Phase 9 adds the `pc_classes` table; Phase 10 ships the Smart MonsterDriver; Phase 8 adds homebrew-friendly YAML eligibility. **Required action:** populate `pc_classes` for any characters that existed before the upgrade, otherwise Riposte silently never fires.

### Required: run the backfill once

If you ran v1.0, your `eldritch.sqlite3` does not have a populated `pc_classes` table. Without it, the Phase 5 Riposte eligibility check sees no class data for legacy PCs and **Riposte never fires** — silently. This is the v1.0 audit's TD-3 gap, closed by the `eldritch-dm-backfill-pc-classes` CLI (Phase 9 / UPGRADE-01).

### When to run

- Right after upgrading from v1.0 to v1.1.
- Whenever you import characters into a campaign without going through the Phase 3 character-ingest flow (which already writes `pc_classes`).

It's idempotent — safe to re-run any time.

### Install

`pip install -e .` already exposes the console script:

```bash
eldritch-dm-backfill-pc-classes --help
```

### Recommended flow

```bash
# 1) Stop the bot first (the tool will fail with EXIT_FATAL=3 if a write lock is detected;
#    safer to halt cleanly than retry into a partial state)
launchctl unload ~/Library/LaunchAgents/com.user.eldritch-dm.plist
#    or:  systemctl --user stop eldritch-dm

# 2) Dry-run — opens SQLite read-only (mode=ro URI; driver-impossible to write) and
#    reports what WOULD change
eldritch-dm-backfill-pc-classes --dry-run

# 3) Real run — populates pc_classes from dm20
eldritch-dm-backfill-pc-classes

# 4) Restart the bot
launchctl load ~/Library/LaunchAgents/com.user.eldritch-dm.plist
```

### Flags

| Flag | Default | Effect |
|------|---------|--------|
| `--dry-run` | off | Open SQLite read-only; report counts; never writes |
| `--force` | off | Re-process rows already in `pc_classes` (default skips them) |
| `--db-path PATH` | from `Settings().eldritch_db_path` | Override database location |
| `--dm20-url URL` | `$DM20_MCP_URL` → `$OMLX_ENDPOINT` minus `/v1` → `http://localhost:8765` | dm20 MCP base URL |
| `--verbose` / `-v` | off | Emit per-character DEBUG events |

### Exit codes

| Code | Meaning |
|------|---------|
| 0 | Success — all sessions populated |
| 1 | dm20 unreachable / bad args / DB open failure |
| 2 | Partial — some channels populated, some failed (check stderr for which) |
| 3 | Fatal — database is locked (stop the bot and retry) |

### Caveat — `subclass` is left empty

dm20's character schema does not expose a `subclass` field. The tool populates `class_name` (normalized lowercase) and writes `subclass=""` for every row. **For subclass-gated features like Battle Master Riposte**, hand-edit `pc_classes`:

```bash
sqlite3 eldritch.sqlite3 \
  "UPDATE pc_classes SET subclass='battle master' \
   WHERE channel_id='123…' AND character_id='abc…'"
```

The tool emits a `backfill.subclass_unknown` WARNING per row — grep stderr for the character_ids needing manual annotation.

### Re-running safely

Default behavior is idempotent — re-running with no flags will report `skipped: N` for every row already populated and exit 0. Use `--force` only when dm20's class data has drifted from what was last backfilled (rare).

**Citation:** [`.planning/milestones/v1.1-ROADMAP.md`](../.planning/milestones/v1.1-ROADMAP.md) (Phases 6-10).

---

## v1.1 → v1.2

**Audit status:** ✅ passed ([`.planning/v1.2-MILESTONE-AUDIT.md`](../.planning/v1.2-MILESTONE-AUDIT.md)).

**Headline change:** Phoenix observability (Phase 11), LLM-as-judge tactical scoring (Phase 12), and production monitoring + alerting (Phase 13). All opt-in.

**Required action:** none.

### Optional: turn on observability

```bash
# 1) Install the optional dep group
pip install -e ".[observability]"

# 2) Enable in .env
echo 'OBSERVABILITY_ENABLED=true' >> .env
echo 'OBSERVABILITY_METRICS_ENDPOINT=true' >> .env   # Prometheus /metrics on :9090

# 3) Bring up the Phoenix stack
docker compose -f docker-compose.observability.yml up -d
```

When `OBSERVABILITY_ENABLED` is unset or `false`, the entire observability tree is a lazy no-op — zero overhead.

### Optional: cost reports

```bash
echo 'ELDRITCH_DAILY_LLM_BUDGET_USD=5.00' >> .env
eldritch-dm-cost-report           # daily LLM-spend report
```

**Citation:** [`.planning/milestones/v1.2-ROADMAP.md`](../.planning/milestones/v1.2-ROADMAP.md) (Phases 11-13).

---

## v1.2 → v1.2.1

**Audit status:** hotfix (Phase 13 follow-up).

**Required action:** none, unless you have manually customized `database/pricing.yaml`.

**If you customized it:** the v1.2.1 hotfix refreshes the file with current provider pricing. If you had local edits, re-apply them on top of the new file (or skip the refresh if your local numbers are still accurate).

**Citation:** v1.2.1 hotfix pattern, Phase 13 MON-03 in [`.planning/milestones/v1.2-ROADMAP.md`](../.planning/milestones/v1.2-ROADMAP.md).

---

## v1.2 → v1.3

**Audit status:** ⚠️ complete-with-tech-debt — FLAKE-02 user-accepted partial ([`.planning/v1.3-MILESTONE-AUDIT.md`](../.planning/v1.3-MILESTONE-AUDIT.md)).

**Headline change:** Phase 14 hygiene sweep — OCR skip-gate (FLAKE-01) and orchestrator quirks (FLAKE-02, partial).

**Required action:** none. The OCR test skip-gate is automatic — Linux operators without `easyocr` and macOS operators without `ocrmac` will see those tests as `skipped` rather than failing the suite (Phase 14 / FLAKE-01).

**Citation:** [`.planning/milestones/v1.3-ROADMAP.md`](../.planning/milestones/v1.3-ROADMAP.md).

---

## v1.3 → v1.4

**Audit status:** ✅ passed ([`.planning/v1.4-MILESTONE-AUDIT.md`](../.planning/v1.4-MILESTONE-AUDIT.md)).

**Headline change:** Phase 15 writer-queue reliability — single asyncio.Queue drained by one connection, with structured backoff. Pure internal refactor.

**Required action:** none.

**Citation:** [`.planning/milestones/v1.4-ROADMAP.md`](../.planning/milestones/v1.4-ROADMAP.md).

---

## v1.4 → v1.5

**Audit status:** ✅ passed ([`.planning/v1.5-MILESTONE-AUDIT.md`](../.planning/v1.5-MILESTONE-AUDIT.md)).

**Headline change:** Three caches landed across Phases 16, 17, 18 — dm20 MCP cache, character snapshot cache, narration cache. Each has its own opt-in / opt-out semantics.

**Required action:** none. All three caches ship with safe defaults.

### Default cache state out of the box

| Cache | Default | Source field |
|---|---|---|
| MCP L1 (in-process LRU) | **on** | `Settings.mcpcache_enabled = True` |
| MCP L2 (SQLite WAL) | off | `Settings.mcpcache_l2_enabled = False` |
| Character snapshot | **on** | `Settings.charcache_enabled = True` |
| Narration | **off** | `Settings.narrcache_enabled = False` |

The narration cache is opt-in because of the v1.0 mechanical-honesty contract (Phase 18 / D-129) — a wrongly cached narration could leak HP, AC, or damage as if it were live. The NarrCacheGate fail-CLOSED classifier gates both store and serve, but operators must still opt in explicitly.

### Optional: enable L2 for the MCP cache

```bash
echo 'MCPCACHE_L2_ENABLED=true' >> .env
# Default L2 path: ~/.eldritch/mcp_cache.sqlite (24h TTL)
```

### Optional: enable narration cache

```bash
echo 'NARRCACHE_ENABLED=true' >> .env
```

**Citation:** [`.planning/milestones/v1.5-ROADMAP.md`](../.planning/milestones/v1.5-ROADMAP.md) (Phases 16-18); D-117, D-119, D-125, D-129 in the corresponding phase CONTEXT files.

---

## v1.5 → v1.6

**Audit status:** ✅ passed ([`.planning/v1.6-MILESTONE-AUDIT.md`](../.planning/v1.6-MILESTONE-AUDIT.md)).

**Headline change:** UX + feature expansion across Phases 19-22 — streaming "monster is thinking" embed, AOE / multi-target tactic selection, cross-round monster memory, and the operator quality-of-life bundle.

**Required action:** none.

### Optional: disable the streaming indicator (revert to v1.5 silent behavior)

```bash
echo 'STREAM_ENABLED=false' >> .env
```

When `STREAM_ENABLED=true` (default), SmartMonsterDriver emits a `🤔 {name} is sizing up the party...` indicator via the per-channel embed coalescer before invoking the LLM oracle (Phase 19 / STREAM-03). The 1500ms oracle deadline (D-54) and 2s embed-stall budget (Phase 4) are unchanged.

### Optional: persist monster memory across restarts

```bash
echo 'MONSTER_MEMORY_PERSIST=true' >> .env
# Default path: ~/.eldritch/monster_memory.sqlite
```

Off by default keeps the bot self-contained for users who don't want cross-restart memory (Phase 21 / D-160).

### Optional: opt in to owner DMs for budget and degraded-mode events

```bash
echo 'DISCORD_OWNER_ID=<your_discord_user_id>' >> .env
```

When set, EldritchDM DMs this user on budget breach + degraded-mode transitions, rate-limited 1 DM per event-type per hour (Phase 22 / OPQOL-02 / D-170). Unset = log-only behavior.

**Citation:** [`.planning/milestones/v1.6-ROADMAP.md`](../.planning/milestones/v1.6-ROADMAP.md) (Phases 19-22).

---

## v1.6 → v1.7

**Audit status:** ✅ passed with 1 documented deferral — WIRE-01 blocked on dm20 event surface ([`.planning/v1.7-MILESTONE-AUDIT.md`](../.planning/v1.7-MILESTONE-AUDIT.md)).

**Headline change:** Phase 23 cog-wiring polish and Phase 24 CI + dashboards integration. Mostly internal; the AOE addendum from Phase 20 is auto-active.

**Required action:** none.

**Citation:** [`.planning/milestones/v1.7-ROADMAP.md`](../.planning/milestones/v1.7-ROADMAP.md).

---

## v1.7 → v1.8

**Audit status:** ✅ passed ([`.planning/v1.8-MILESTONE-AUDIT.md`](../.planning/v1.8-MILESTONE-AUDIT.md)).

**Headline change:** Phase 25 multi-channel concurrency stress tests (proved the architecture) and Phase 26 ops-dashboard tooling. Schema-poller now auto-invalidates **both** MCP and character caches (it was just MCP before).

**Required action:** none.

**Citation:** [`.planning/milestones/v1.8-ROADMAP.md`](../.planning/milestones/v1.8-ROADMAP.md).

---

## v1.8 → v1.9

**Audit status:** ✅ passed ([`.planning/v1.9-MILESTONE-AUDIT.md`](../.planning/v1.9-MILESTONE-AUDIT.md)).

**Headline change:** Phase 27 profiling + [`docs/PERFORMANCE.md`](PERFORMANCE.md) latency budgets; Phase 28 targeted optimizations + the new `eldritch-dm-perf-baseline` regression-detection CLI (D-218).

**Required action:** none. The new CLI is opt-in but recommended for CI:

```bash
eldritch-dm-perf-baseline --baseline .planning/perf-baseline-v1.9.0.json
# Exit codes: 0 = healthy, 1 = regression, 2 = profile-run failure
```

To regenerate a baseline after intentional changes:

```bash
eldritch-dm-perf-baseline --write-baseline .planning/perf-baseline-v1.X.0.json
```

**Citation:** [`.planning/milestones/v1.9-ROADMAP.md`](../.planning/milestones/v1.9-ROADMAP.md) (Phases 27-28).

---

## v1.9 → v1.10

**Audit status:** in progress — v1.10 is shipping with this document.

**Headline change:**

- **Phase 29 (DEPLOY-01/02):** `docker-compose.yml` + multi-stage `Dockerfile` + `.dockerignore` for single-command container setup.
- **Phase 30 (DOCS-01/02/03):** `INSTALL.md` refresh, this `docs/UPGRADE.md`, and `docs/TROUBLESHOOTING.md`.

**Required action:** none.

### Optional: containerized bot

```bash
cp .env.example .env       # edit DISCORD_TOKEN, set MLX_BASE_URL if oMLX is on host
docker compose up -d
docker compose logs -f eldritch-bot
```

The compose file brings up only the bot — oMLX, dm20 MCP, and Phoenix run on the host (by design, D-221). On Linux the `extra_hosts: host-gateway` mapping ([`docker-compose.yml`](../docker-compose.yml) lines 49-52) provides Docker-Desktop parity for `host.docker.internal`.

**Citation:** Phase 29 SUMMARYs in [`.planning/phases/29-docker-compose/`](../.planning/phases/29-docker-compose/); Phase 30 CONTEXT in [`.planning/phases/30-install-troubleshooting/30-CONTEXT.md`](../.planning/phases/30-install-troubleshooting/30-CONTEXT.md).

---

> 🔗 **See also:**
> - [`INSTALL.md`](../INSTALL.md) — fresh-install walkthrough
> - [`docs/TROUBLESHOOTING.md`](TROUBLESHOOTING.md) — operator FAQ
