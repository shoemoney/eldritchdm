---
phase: 30-install-troubleshooting
milestone: v1.10
generated: 2026-05-26
mode: auto-generated (autonomous-flow)
source_requirements:
  - DOCS-01 (INSTALL.md refresh)
  - DOCS-02 (TROUBLESHOOTING.md FAQ)
  - DOCS-03 (UPGRADE.md version-to-version)
---

# Phase 30 — INSTALL refresh + troubleshooting runbook (CONTEXT)

## Mission

Final v1.10 phase. Refresh INSTALL.md to reflect v1.0-v1.9 changes. Write TROUBLESHOOTING.md FAQ from real operator gotchas. Write UPGRADE.md with version-to-version notes operators can follow step-by-step.

## Locked Decisions

| ID | Decision | Rationale |
|----|----------|-----------|
| **D-229** | **INSTALL.md sections to add/refresh**:<br>- Docker quickstart (Phase 29's `docker compose up -d`)<br>- macOS native setup (existing path with [mac-ocr])<br>- Linux native setup (`[linux-ocr]` extras instead)<br>- Env var reference (12 documented: DISCORD_TOKEN, DISCORD_GUILD_IDS, DISCORD_OWNER_ID, ELDRITCH_DB_PATH, DM20_MCP_URL, OBSERVABILITY_ENABLED, MONSTER_DRIVER, NARRCACHE_ENABLED, MCPCACHE_L2_ENABLED, MONSTER_MEMORY_PERSIST, ELDRITCH_DAILY_LLM_BUDGET_USD, STREAM_ENABLED)<br>- CLIs reference (7: backfill-pc-classes, eval, cost-report, cache-clear, cache-disable, cache-stats, perf-baseline)<br>- Optional dep groups (`[dev]`, `[mac-ocr]`, `[linux-ocr]`, `[observability]`) | Reflects EXISTING surface |
| **D-230** | **TROUBLESHOOTING.md FAQ entries** (≥10, grounded in real v1.0-v1.9 SUMMARY surface):<br>1. "Bot says DM is offline" → Phase 7 OPS-02 DM_OFFLINE warning; circuit-breaker open<br>2. "OCR tests skipping" → Phase 14 FLAKE-01 skip-gate; install `[mac-ocr]` or `[linux-ocr]`<br>3. "Cache hit rate is 0" → check OBSERVABILITY_ENABLED + MCPCACHE_ENABLED<br>4. "DISCORD_TOKEN missing exits with code 4" → Phase 7 SAFETY-03 token_guard<br>5. "Pytest hangs in full suite" → likely orchestrator-session-specific; restart shell<br>6. "Monster driver always picks random" → MONSTER_DRIVER=random override OR degraded mode tripped (P99>1500ms)<br>7. "Riposte button doesn't fire" → check pc_classes table (Phase 9 `eldritch-dm-backfill-pc-classes`)<br>8. "Phoenix dashboards empty" → OBSERVABILITY_ENABLED=true + OBSERVABILITY_METRICS_ENDPOINT=true<br>9. "Cost calculator off" → refresh `database/pricing.yaml` (v1.2.1 hotfix pattern)<br>10. "perf baseline regression alert" → check `eldritch-dm-perf-baseline --baseline .planning/perf-baseline-v1.9.0.json`<br>11. "Restart loses character state" → enable CHARCACHE persistence (auto in v1.5+)<br>12. "Eligibility YAML doesn't reload" → Phase 22 hot-reload watcher; check mtime poll | Real questions from real phase surface |
| **D-231** | **UPGRADE.md v1.0 → v1.9 step-by-step**:<br>- **v1.0→v1.1**: run `eldritch-dm-backfill-pc-classes` for existing characters (UPGRADE-01); pricing.yaml is placeholder if cost-guard enabled<br>- **v1.1→v1.2**: opt in to `[observability]` extras + `OBSERVABILITY_ENABLED=true` + docker compose -f docker-compose.observability.yml up -d<br>- **v1.2→v1.2.1** (hotfix): refresh pricing.yaml if you've manually customized it<br>- **v1.2→v1.3**: OCR skip-gate now auto-skips on Linux without `[mac-ocr]`; no action needed<br>- **v1.3→v1.4**: writer-queue fix is internal; no operator action<br>- **v1.4→v1.5**: MCP cache opt-in via `MCPCACHE_L2_ENABLED=true` (L1 already on); character cache auto-enabled<br>- **v1.5→v1.6**: streaming embed on by default; can disable via `STREAM_ENABLED=false`; monster memory opt-in persistence via `MONSTER_MEMORY_PERSIST=true`<br>- **v1.6→v1.7**: nothing; cog-wiring + AOE addendum auto-active<br>- **v1.7→v1.8**: schema-poller auto-invalidates BOTH caches (was just MCP)<br>- **v1.8→v1.9**: docs/PERFORMANCE.md establishes budgets; `eldritch-dm-perf-baseline` CLI available<br>- **v1.9→v1.10**: docker-compose.yml available for single-command setup | Real upgrade trail |
| **D-232** | **NO speculative content** — every claim cross-references either: pyproject.toml, Settings class fields, [project.scripts] entries, or a milestone archive. If a section can't be traced to existing source, omit it. | Honest docs |
| **D-233** | **Cross-link the 3 files**: INSTALL.md links to TROUBLESHOOTING.md for "having issues?" + to UPGRADE.md for "moving from older version?". TROUBLESHOOTING entries link back to relevant INSTALL section. | Operator can navigate |
| **D-234** | **2 plans**: 30-01 = INSTALL.md refresh. 30-02 = TROUBLESHOOTING.md + UPGRADE.md. | ROADMAP plans section |

## Success Criteria
1. INSTALL.md updated with Docker quickstart + 12 env vars + 7 CLIs + 4 optional dep groups
2. TROUBLESHOOTING.md with ≥12 FAQ entries (more than the 10 minimum)
3. UPGRADE.md covers v1.0→v1.1→v1.2→v1.2.1→v1.3→v1.4→v1.5→v1.6→v1.7→v1.8→v1.9→v1.10
4. Every claim cross-referenced to existing source (pyproject.toml / Settings / scripts / milestone archives)
5. Cross-links between INSTALL/TROUBLESHOOTING/UPGRADE
6. ruff (no code change expected) + lint-imports clean
7. No regression in 1680-test suite
