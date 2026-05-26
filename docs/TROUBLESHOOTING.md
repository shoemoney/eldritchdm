<!-- generated-by: gsd Phase 30 plan 30-02 (DOCS-02) -->
# 🩺 EldritchDM — TROUBLESHOOTING

> Operator FAQ for the most common symptoms surfaced across v1.0 - v1.10. Each entry is grounded in a real milestone change — no invented questions. If a symptom isn't here, check [`INSTALL.md`](../INSTALL.md), [`docs/dm20-troubleshooting.md`](dm20-troubleshooting.md) (preflight exit codes 1/2), or [`docs/UPGRADE.md`](UPGRADE.md) for version-to-version pitfalls.

> 🔗 **Companion docs:**
> - [`INSTALL.md`](../INSTALL.md) — fresh-install walkthrough
> - [`docs/UPGRADE.md`](UPGRADE.md) — version-to-version notes (v1.0 → v1.10)

---

## Bot says DM is offline

**Symptom:** Every interaction replies with an ephemeral `🔌 DM is offline` warning instead of acting on your command.

**Cause:** The MCP circuit breaker has opened. After `OMLX_CIRCUIT_BREAKER_THRESHOLD` consecutive ping failures (default 3, every `OMLX_HEALTH_INTERVAL=60s`), the `@catch_circuit_open` decorator wired in Phase 7 OPS-02 short-circuits every callback with the warning. The warning is per-channel debounced to 1 per 30s.

**Diagnose:**

```bash
curl -s http://localhost:8765/v1/models | jq .       # should return JSON, not hang
curl -s http://localhost:8765/v1/mcp/tools | jq '. | length'   # should be ≥ 116 (dm20 tools)
```

**Fix:**

1. Bounce oMLX (macOS): `launchctl kickstart -k gui/$(id -u)/com.user.omlx`
2. Tail logs: `tail ~/Library/Logs/omlx.log`
3. The breaker auto-closes on the next successful ping (every 60s by default).

**Citations:** `Settings.omlx_circuit_breaker_threshold` ([`src/eldritch_dm/config/__init__.py`](../src/eldritch_dm/config/__init__.py)); Phase 7 audit-close note in [`.planning/milestones/v1.1-ROADMAP.md`](../.planning/milestones/v1.1-ROADMAP.md).

---

## OCR tests are skipping

**Symptom:** `pytest` reports a swath of OCR-related tests as `skipped`.

**Cause:** Phase 14 FLAKE-01 added an auto-skip gate that fires when neither `ocrmac` nor `easyocr` is importable. This was the v1.3 hygiene sweep's response to platform-fragile test runs.

**Fix:**

```bash
# macOS — primary OCR
pip install -e ".[mac-ocr]"

# Linux / cross-platform fallback
pip install -e ".[linux-ocr]"
```

**Citations:** [`.planning/milestones/v1.3-ROADMAP.md`](../.planning/milestones/v1.3-ROADMAP.md) (Phase 14 / FLAKE-01); `pyproject.toml` `[project.optional-dependencies]`.

---

## Cache hit rate is zero

**Symptom:** `eldritch-dm-cache-stats` (or your Phoenix dashboard) shows a 0% hit rate.

**Cause:** Each of the three caches has its own gating switch and its own definition of "cacheable". The most common reason for 0% is the cache being disabled, *not* a logic bug.

- **dm20 MCP cache** (`MCPCACHE_ENABLED`, default `true`): only an allow-listed subset of read-only tools are cacheable. Mutations and mutable-state reads are NEVER cached (Phase 16 / D-117). L2 only fires if `MCPCACHE_L2_ENABLED=true` (default `false`).
- **Narration cache** (`NARRCACHE_ENABLED`, default **false**): opt-in due to the v1.0 mechanical-honesty contract (Phase 18 / D-129). NarrCacheGate fail-CLOSED classifier gates both store and serve — most attempts are deliberately rejected.
- **Character snapshot cache** (`CHARCACHE_ENABLED`, default `true`): static-fields-only (Phase 17 / D-125); combat-mutable state is never cached.

**Fix:** Verify the relevant env var. To see hit-rate spans in Phoenix, also set `OBSERVABILITY_ENABLED=true`.

**Citations:** `Settings.mcpcache_enabled` / `narrcache_enabled` / `charcache_enabled` ([`src/eldritch_dm/config/__init__.py`](../src/eldritch_dm/config/__init__.py)); Phase 16, 17, 18 in [`.planning/milestones/v1.5-ROADMAP.md`](../.planning/milestones/v1.5-ROADMAP.md).

---

## Bot exits with code 4 (DISCORD_TOKEN missing)

**Symptom:**

```text
❌ DISCORD_TOKEN is not set.
   Copy .env.example to .env and paste your bot token …
```

…and the process exits 4.

**Cause:** Phase 7 SAFETY-03 / TD-1 — the shared `config.token_guard` helper validates `DISCORD_TOKEN` at the moment the bot is about to call `bot.run(...)`. Both `run.py` and `python -m eldritch_dm.bot` now exit with the same friendly message and the same exit code (parity was the Phase 7 audit-close goal).

**Fix:**

```bash
cp .env.example .env && $EDITOR .env
# paste the token from https://discord.com/developers/applications, save
```

**Important:** `python -m eldritch_dm.bootstrap` and `python run.py --check-only` do **not** require a token (Phase 5 / D-26). Use those to verify oMLX + dm20 before pasting any real secret.

**Citations:** Phase 7 entry in [`.planning/milestones/v1.1-ROADMAP.md`](../.planning/milestones/v1.1-ROADMAP.md); `Settings.discord_token`.

---

## Pytest hangs in the full suite

**Symptom:** `pytest` collects 1680+ tests, runs a few, then appears to stall indefinitely.

**Cause:** Known orchestrator-session-specific behavior — not a code bug. The v1.3 hygiene sweep accepted this as user-accepted tech debt (FLAKE-02 partial, v1.3 audit status: `tech_debt`).

**Fix:**

1. Cancel the run (`Ctrl-C`).
2. Start a fresh shell session (closes any lingering pytest fixtures or background tasks from a prior partial run).
3. Re-invoke `pytest` from the new shell.

**Citations:** [`.planning/milestones/v1.3-ROADMAP.md`](../.planning/milestones/v1.3-ROADMAP.md) (FLAKE-02 partial).

---

## Monster driver always picks random targets

**Symptom:** Smart targeting never fires — every monster acts as if INT ≤ 4 (pure random).

**Cause:** Two possibilities.

1. **Explicit override.** `MONSTER_DRIVER=random` in your `.env` is the v1.0 escape hatch (Phase 10 / D-52). Unset it (defaults to `smart`).
2. **Degraded mode tripped.** When sustained P99 latency exceeds the budget, SmartMonsterDriver falls back to random for safety. Phase 22 OPQOL-02 (D-170) added owner DMs on degraded-mode transitions — check your DMs from the bot if `DISCORD_OWNER_ID` is set.

**Diagnose:**

```bash
eldritch-dm-perf-baseline --baseline .planning/perf-baseline-v1.9.0.json
```

Exit 0 = healthy, 1 = regression, 2 = profile run failed (Phase 28 / D-218).

**Fix:** unset `MONSTER_DRIVER`; investigate latency; if you genuinely want random, leave the override in place.

**Citations:** `Settings.monster_driver` ([`src/eldritch_dm/config/__init__.py`](../src/eldritch_dm/config/__init__.py)); Phase 10 / D-52 in [`.planning/milestones/v1.1-ROADMAP.md`](../.planning/milestones/v1.1-ROADMAP.md); Phase 22 / D-170 in [`.planning/milestones/v1.6-ROADMAP.md`](../.planning/milestones/v1.6-ROADMAP.md).

---

## Riposte button doesn't fire

**Symptom:** A Battle Master Fighter never gets the Riposte interrupt button when an enemy attacks.

**Cause:** The `pc_classes` table is missing or empty for that character — the standard v1.0 → v1.1 upgrade gap (Phase 9 / TD-3 / UPGRADE-01).

**Diagnose:**

```bash
sqlite3 eldritch.sqlite3 'SELECT * FROM pc_classes LIMIT 5;'
```

If empty or missing your character, run the backfill.

**Fix:**

```bash
# Stop the bot first
eldritch-dm-backfill-pc-classes --dry-run    # verify what would change
eldritch-dm-backfill-pc-classes              # for real
# Restart the bot
```

**Caveat:** dm20's schema doesn't expose `subclass`. For Battle Master Riposte specifically, hand-edit:

```bash
sqlite3 eldritch.sqlite3 \
  "UPDATE pc_classes SET subclass='battle master' \
   WHERE channel_id='123…' AND character_id='abc…'"
```

The full upgrade procedure (flags, exit codes, idempotency) lives in [`docs/UPGRADE.md#v10--v11`](UPGRADE.md#v10--v11).

**Citations:** Phase 9 in [`.planning/milestones/v1.1-ROADMAP.md`](../.planning/milestones/v1.1-ROADMAP.md); `eldritch-dm-backfill-pc-classes` in `pyproject.toml` `[project.scripts]`.

---

## Phoenix dashboards empty

**Symptom:** Phoenix UI loads but every panel is blank.

**Cause:** Observability is off by default. Two env vars + the optional dep group must all be present.

**Fix:**

```bash
# 1) Install the optional dep group
pip install -e ".[observability]"

# 2) Enable tracing + metrics
echo 'OBSERVABILITY_ENABLED=true' >> .env
echo 'OBSERVABILITY_METRICS_ENDPOINT=true' >> .env   # for Prometheus /metrics on :9090

# 3) Bring up Phoenix
docker compose -f docker-compose.observability.yml up -d

# 4) Restart the bot
```

**Citations:** [`src/eldritch_dm/observability/tracer.py:39`](../src/eldritch_dm/observability/tracer.py) (env read for `OBSERVABILITY_ENABLED`); [`src/eldritch_dm/observability/metrics_endpoint.py:51`](../src/eldritch_dm/observability/metrics_endpoint.py) (env read for `OBSERVABILITY_METRICS_ENDPOINT`); Phase 11 OBS-01 + Phase 13 MON-01 in [`.planning/milestones/v1.2-ROADMAP.md`](../.planning/milestones/v1.2-ROADMAP.md).

---

## Cost calculator is off

**Symptom:** `eldritch-dm-cost-report` prints dollar amounts that don't match what your provider invoiced.

**Cause:** `database/pricing.yaml` is stale — provider pricing drifted. This is the same problem the v1.2.1 hotfix addressed by refreshing the file.

**Fix:**

1. Refresh `database/pricing.yaml` with your provider's current `$/1M tokens` figures.
2. Set your real ceiling: `ELDRITCH_DAILY_LLM_BUDGET_USD=10.00` (default `5.00`).
3. Re-run `eldritch-dm-cost-report`.

**Citations:** [`src/eldritch_dm/tools/cost_report.py:84`](../src/eldritch_dm/tools/cost_report.py) (env read for `ELDRITCH_DAILY_LLM_BUDGET_USD`); Phase 13 MON-03 in [`.planning/milestones/v1.2-ROADMAP.md`](../.planning/milestones/v1.2-ROADMAP.md).

---

## perf-baseline regression alert

**Symptom:** CI or a local run of `eldritch-dm-perf-baseline` exits with code 1 or 2.

**Cause:** Phase 28 TUNE-02 / D-218 regression-detection contract. Exit codes:

- **0** — healthy (within baseline tolerance)
- **1** — regression detected vs. committed baseline
- **2** — profile run itself failed (not a regression — investigate the runner)

**Diagnose:**

```bash
eldritch-dm-perf-baseline --baseline .planning/perf-baseline-v1.9.0.json --verbose
```

**Fix:**

- If exit 1 from an unintentional regression: identify the hot path, fix it, re-run.
- If exit 1 from an intentional change (new feature deliberately moves the baseline): regenerate with `--write-baseline .planning/perf-baseline-v1.X.0.json` and commit the new file.

**Citations:** `eldritch-dm-perf-baseline` in `pyproject.toml` `[project.scripts]`; Phase 28 in [`.planning/milestones/v1.9-ROADMAP.md`](../.planning/milestones/v1.9-ROADMAP.md); existing reference doc [`docs/PERFORMANCE.md`](PERFORMANCE.md).

---

## Restart loses character state

**Symptom:** After restarting the bot, character HP / conditions / cache state appears reset.

**Cause:** Two paths to investigate.

1. **Combat state (HP, conditions, turn order):** Phase 4 OPS-04 restart-resume persists this to SQLite. If you lost it, you're not pointing at the same `eldritch.sqlite3` (check `ELDRITCH_DB_PATH`) or WAL is disabled (`PRAGMA journal_mode` should return `wal`).
2. **Character snapshot cache:** auto-enabled from v1.5 (Phase 17 / D-119, `CHARCACHE_ENABLED=true` by default). If the bot is reading a stale snapshot after an out-of-band character edit, purge it: `eldritch-dm-cache-clear`.

**Diagnose:**

```bash
sqlite3 "$ELDRITCH_DB_PATH" 'PRAGMA journal_mode;'   # expect wal
sqlite3 "$ELDRITCH_DB_PATH" 'SELECT COUNT(*) FROM combat_state;'
```

**Citations:** Phase 17 in [`.planning/milestones/v1.5-ROADMAP.md`](../.planning/milestones/v1.5-ROADMAP.md); `Settings.charcache_enabled` ([`src/eldritch_dm/config/__init__.py`](../src/eldritch_dm/config/__init__.py)).

---

## Eligibility YAML edits don't take effect

**Symptom:** You edited `~/.eldritch/eligibility.yaml` (or `database/eligibility.yaml`), but the bot still uses the old eligibility table.

**Cause:** The Phase 22 OPQOL hot-reload watcher is mtime-polled. If your editor wrote in place without bumping mtime (rare but possible on some sync filesystems), the poll misses the change.

**Fix:**

```bash
touch ~/.eldritch/eligibility.yaml      # force mtime bump
```

Watch logs for `eligibility.yaml.reloaded` — that's the confirmation event.

**Citations:** Phase 22 OPQOL bundle in [`.planning/milestones/v1.6-ROADMAP.md`](../.planning/milestones/v1.6-ROADMAP.md); `Settings.eligibility_yaml_path` ([`src/eldritch_dm/config/__init__.py`](../src/eldritch_dm/config/__init__.py)).

---

## sqlite3.OperationalError database is locked

**Symptom:** The bot raises `sqlite3.OperationalError: database is locked` mid-session.

**Cause:** Phase 15 (v1.4 writer-queue) made the writer serial through a single connection. This error means a *different* process holds the lock — almost never the bot itself.

**Diagnose:**

```bash
lsof "$ELDRITCH_DB_PATH"                                    # who else has it open?
sqlite3 "$ELDRITCH_DB_PATH" 'PRAGMA journal_mode;'          # expect wal
```

**Fix:**

1. Close any REPL with an open transaction, second `python run.py`, or SQLite browser GUI.
2. If `PRAGMA journal_mode` prints `delete`, re-run `python -m eldritch_dm.bootstrap` — it re-applies the WAL setting.

**Citations:** [`.planning/milestones/v1.4-ROADMAP.md`](../.planning/milestones/v1.4-ROADMAP.md) (writer-queue reliability).

---

## Bot disconnected mid-combat — buttons inert after restart

**Symptom:** Combat buttons posted before the bot disconnect look normal but never respond to clicks.

**Cause:** `discord.ui.DynamicItem` registers regex `custom_id` templates (e.g. `endturn:(?P<channel_id>\d+):(?P<actor>\d+)`) in `setup_hook`. Buttons posted by an older code version may carry a `custom_id` that no longer matches the current regex — they remain in Discord's UI but never route to a callback.

**Diagnose:**

```bash
sqlite3 "$ELDRITCH_DB_PATH" 'SELECT custom_id, view_class FROM persistent_views;'
```

If `custom_id` shapes don't match the current templates, the buttons are stale.

**Fix:** either let those messages age out (the sweeper cleans them) or `DELETE FROM persistent_views WHERE …` for the affected channel and `/start_game` again. See the persistent-view discipline section of [`docs/ARCHITECTURE.md`](ARCHITECTURE.md).

**Citations:** [`docs/ARCHITECTURE.md`](ARCHITECTURE.md) (persistent Views); Phase 4 OPS-04.

---

> 🔗 **See also:**
> - [`INSTALL.md`](../INSTALL.md) — fresh-install walkthrough + bootstrap exit-code diagnostics
> - [`docs/UPGRADE.md`](UPGRADE.md) — version-to-version upgrade notes (v1.0 → v1.10)
> - [`docs/dm20-troubleshooting.md`](dm20-troubleshooting.md) — preflight exit codes 1/2 (oMLX / dm20 unreachable)
