---
title: dm20 Troubleshooting Guide
audience: self-host
last_updated: 2026-05-22
---

# dm20 / oMLX Troubleshooting

This guide covers the four most common self-host failure modes when
EldritchDM cannot talk to the dm20 MCP toolbox or to oMLX. If `python
run.py --check-only` returns a non-zero exit code, find your error
below and follow the recipe.

| Preflight exit code | Symptom | Section |
| ------------------- | ------- | ------- |
| `1` (`EXIT_OMLX_UNREACHABLE`) | "oMLX unreachable at …" | [oMLX is down](#1-omlx-is-down) |
| `2` (`EXIT_DM20_NOT_LOADED`)  | "dm20 MCP tools are not loaded …" | [dm20 not loaded](#2-dm20-mcp-tools-not-loaded) |
| `3` (`EXIT_SCHEMA_FAIL`)      | "Schema bootstrap failed at …" | [Schema bootstrap fails](#4-local-sqlite-schema-fails-to-bootstrap) |
| (any) preflight OK, runtime errors | bot says "DM is offline" or `dm20__*` tool calls 500 | [Wrong model loaded / runtime errors](#3-wrong-model-loaded-or-runtime-errors) |

---

## 1. oMLX is down

**Symptom:** `python run.py --check-only` exits `1` with stderr:

```
❌ oMLX unreachable at http://localhost:8765/v1/models: …
   Is oMLX running? Try: `curl -s http://localhost:8765/v1/models | jq .`
```

**Diagnose:**

```bash
# Direct probe — should return JSON with at least one model
curl -s http://localhost:8765/v1/models | jq .

# launchd-supervised? Check status:
launchctl list | grep omlx

# Is anything listening on port 8765 at all?
lsof -i :8765
```

**Fix:**

- **If oMLX has crashed:** `launchctl kickstart -k gui/$(id -u)/com.user.omlx`
  (or whatever your launchd label is — the user's reference rig uses
  `com.user.omlx`). Tail `~/Library/Logs/omlx.log` for the crash reason.

- **If oMLX is not installed/configured:** see
  [github.com/macabdul9/omlx](https://github.com/macabdul9/omlx) and the
  user's notes at `~/.claude/memory/omlx_mcp_setup.md`.

- **If you want to start the bot anyway** (e.g. you're debugging the bot
  half without oMLX up): `ELDRITCH_ALLOW_OFFLINE_START=1 python run.py`.
  The OPS-02 circuit breaker handles oMLX coming back online at runtime
  — you'll just see "DM is offline" embeds until oMLX is reachable.

---

## 2. dm20 MCP tools not loaded

**Symptom:** `python run.py --check-only` exits `2` with stderr:

```
❌ dm20 MCP tools are not loaded in oMLX
   (http://localhost:8765/v1/mcp/tools returned N tools, 0 dm20__*).
```

**Diagnose:**

```bash
# Total tool count — should be ≥ 116 with dm20 + dice + dnd + fetch loaded
curl -s http://localhost:8765/v1/mcp/tools | jq '. | length'

# Just the dm20__* tools — should be ≥ 97
curl -s http://localhost:8765/v1/mcp/tools \
  | jq '[.[] | select(.name | startswith("dm20__"))] | length'
```

**Fix:** oMLX needs the `mcp` SDK installed into its virtualenv AND its
`--mcp-config` JSON file must point at the dm20 server's stdio
entrypoint. The user has a known-good recipe at
`~/.claude/memory/omlx_mcp_setup.md` — the key trap is that
`pip install mcp` against the wrong interpreter silently fails with
"0/N MCP servers connected" on the next launch.

After fixing the install, bounce oMLX:

```bash
launchctl kickstart -k gui/$(id -u)/com.user.omlx
# wait ~5s for warmup
curl -s http://localhost:8765/v1/mcp/tools | jq '. | length'
```

---

## 3. Wrong model loaded or runtime errors

**Symptom:** Preflight passes, but the bot's `/ping` command says
"DM is offline" or specific `dm20__*` tool calls return 500.

### 3a. Wrong model loaded

Preflight will emit a `WARN` line — not a hard error per RESEARCH A5 —
if `OMLX_MODEL` is set to a model id that isn't currently loaded in
oMLX. The bot will start, but narration calls will 500. Stderr:

```
⚠️  Configured OMLX_MODEL 'ShoeGPT' is not currently loaded in oMLX.
    Loaded: ['SomeOtherModel']. (Continuing — flip OMLX_MODEL or
    `omlx serve --model ShoeGPT` to silence this.)
```

**Fix:** either change `OMLX_MODEL=` in `.env` to match what's loaded,
or restart oMLX with `--model ShoeGPT` (or whatever your narration
model is named).

### 3b. dm20 tool returns a 500 or a structured error

If a specific `dm20__*` call fails (e.g. `dm20__create_character`
returns `{"error": "..."}`), the bot logs it at ERROR with
`tool_name`, `arg_snapshot`, and the dm20 error string bound to the
structlog event. Use `LOG_LEVEL=DEBUG` to see the full request/response.

Common dm20 errors and fixes are in the dm20-protocol README
([github.com/Polloinfilzato/dm20-protocol](https://github.com/Polloinfilzato/dm20-protocol)).

---

## 4. Local SQLite schema fails to bootstrap

**Symptom:** `python run.py --check-only` exits `3` with stderr:

```
❌ Schema bootstrap failed at ./eldritch.sqlite3: …
```

**Diagnose:**

```bash
# Is the file path actually writable?
ls -la ./eldritch.sqlite3 2>/dev/null || echo "Not yet created — check parent dir"
test -w "$(dirname "$(python -c 'from eldritch_dm.config import Settings; print(Settings().eldritch_db_path)')")" \
  && echo "Parent dir writable" || echo "Parent dir NOT writable"

# Schema file present?
ls -la database/schema.sql
```

**Fix:**

- **Permission denied on the DB file or its parent dir:** `chmod` or
  `chown` to fix. The bot runs as your user; the DB file must be writable
  by that user.

- **`schema.sql not found`:** you're running from a directory that
  doesn't contain `database/schema.sql`. Always run from the project
  root (the `WorkingDirectory` in your launchd plist controls this for
  supervised runs).

- **`database is locked` on first run:** another process (a forgotten
  REPL, a SQLite GUI, a previous bot instance) is holding the file.
  Close it and retry.

---

## Last-ditch debugging

Capture a full debug trace:

```bash
LOG_LEVEL=DEBUG python run.py --check-only 2>&1 | tee preflight-debug.log
```

Attach `preflight-debug.log` (with `DISCORD_TOKEN` redacted!) to your
bug report. See also `docs/CONFIGURATION.md` for the full env-var
reference and `docs/DEVELOPMENT.md` for the architecture-level overview.
