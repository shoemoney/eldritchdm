---
phase: 01-mcp-client-local-state
plan: 03
subsystem: safety, tests
tags: [sanitizer, adversarial-corpus, injection-prevention, stress-test, integration-test, pre-commit, ruff]
dependency_graph:
  requires:
    - eldritch_dm.persistence.SanitizerAuditRepo
    - eldritch_dm.persistence.models.SanitizerAuditRow
    - eldritch_dm.mcp.MCPClient
    - eldritch_dm.mcp.errors
    - eldritch_dm.mcp.health
  provides:
    - eldritch_dm.safety.sanitize_player_input
    - eldritch_dm.safety.SanitizedInput
    - eldritch_dm.safety.DEFAULT_BLACKLIST
    - eldritch_dm.safety.make_async_audit_callback
    - tests/integration/test_phase1_smoke (vertical slice coverage)
  affects: []
tech_stack:
  added:
    - pyyaml (corpus loading in tests)
    - pre-commit ruff v0.9.10 (lint+format hooks)
  patterns:
    - Sync sanitizer with bounded 64-pass strip loop (no async)
    - Truncate-first order: cap at max_chars BEFORE stripping (prevents cap-evading attacks)
    - XML-escape output body before wrapping in player_action sentinel
    - asyncio.run_coroutine_threadsafe bridges sync callback to async repo
    - Parametrized pytest corpus: raw_repeat expander for generated adversarial strings
    - RUN_STRESS=1 environment gate for slow concurrent-write stress tests
key_files:
  created:
    - src/eldritch_dm/safety/sanitizer.py
    - src/eldritch_dm/safety/corpus/__init__.py
    - src/eldritch_dm/safety/corpus/injection_cases.yaml
    - tests/safety/__init__.py
    - tests/safety/conftest.py
    - tests/safety/test_sanitizer.py
    - tests/persistence/test_concurrent_writes.py
    - tests/integration/__init__.py
    - tests/integration/test_phase1_smoke.py
    - .pre-commit-config.yaml
  modified:
    - src/eldritch_dm/safety/__init__.py
    - pyproject.toml (per-file-ignores for E402/E501 in test files)
decisions:
  - "sanitize_player_input is sync — Discord event handler calls it synchronously before any async work"
  - "Truncate BEFORE strip: prevents attackers from padding to cap then smuggling tokens after truncation"
  - "64 max strip passes: bounded to prevent pathological overlapping-injection infinite loops"
  - "XML-escape uses html.escape() on the cleaned body before wrapping in XML sentinel"
  - "make_async_audit_callback uses asyncio.run_coroutine_threadsafe — bridges sync sanitizer to async repo in same event loop"
  - "DEFAULT_BLACKLIST has exactly 13 tokens: verified by test_default_blacklist_count assertion"
  - "Stress test gated behind RUN_STRESS=1: excluded from default pytest run (fast suite)"
  - "Per-file ruff ignores: E402 for stress test (imports after pytestmark), E501 for test assertion messages"
metrics:
  duration_minutes: 40
  completed_date: "2026-05-21"
  tasks_completed: 4
  tests_passing: 177
  files_created: 10
---

# Phase 1 Plan 03: Sanitizer and Stress Test Summary

Sync player-input sanitizer with 13-token blacklist, 34-case adversarial YAML corpus, 4-channel concurrent-write stress test, and full vertical-slice integration smoke suite.

## What Was Built

**safety/sanitizer.py** — `sanitize_player_input(raw, *, speaker, user_id, channel_id, max_chars=500, blacklist, audit_callback)`. Four-step pipeline:
1. Truncate to max_chars (attack-prevention: cap before strip)
2. Blacklist strip: 64-pass bounded loop, case-insensitive, records stripped tokens
3. Broad ChatML regex `<\|.*?\|>` sweep (catches unicode lookalikes with pipes)
4. XML-escape body + wrap in `<player_action speaker="..." user_id="...">` sentinel

`make_async_audit_callback(repo, loop)` — returns sync callback using `asyncio.run_coroutine_threadsafe` for fire-and-forget audit writes from sync context.

**DEFAULT_BLACKLIST** — 13 tokens: `<tool_call>`, `</tool_call>`, `<|im_start|>`, `<|im_end|>`, `<|system|>`, `<|user|>`, `<|assistant|>`, `<player_action>`, `</player_action>`, `SYSTEM:`, `ASSISTANT:`, `USER:`, `<|endoftext|>`.

**safety/corpus/injection_cases.yaml** — 34 adversarial cases covering:
- ChatML escape attempts (im_start, im_end, system tag, endoftext)
- Tool-call forgery (basic, mixed-case, incomplete, nested)
- Sentinel breakout (system, assistant, user, fake open)
- Truncation boundary attacks (padding+sentinel after cap, exactly-at-cap, 501, 1000 chars)
- Mixed casing (SYSTEM:, IM_START, ASSISTANT:)
- Unicode lookalikes (Cyrillic А in sentinel pipes)
- Empty/whitespace input
- Multi-injection (all tokens at once)
- HTML escape (& and < > preserved as &amp; &lt; &gt;)
- Newlines preserved in inner body
- Speaker XSS (`<script>` in speaker name escaped in attribute)
- False-positive guard (system/user/assistant as ordinary words)
- Adjacent tokens with no space

**tests/persistence/test_concurrent_writes.py** — 4-channel stress test:
- `_producer` coroutine: 60% writes (upsert, view_insert, audit_insert), 40% reads
- Gated by `RUN_STRESS=1` environment variable
- `test_stress_5sec_sanity`: 5-second quick smoke (default 5s, configurable via STRESS_DURATION_SEC)
- `test_concurrent_writes_60sec`: 60-second full test
- Asserts: zero errors, p99 write latency < 250ms, >= 4 active sessions after run

**tests/integration/test_phase1_smoke.py** — 9 integration tests:
- Channel session full lifecycle (create, upsert-idempotent, get, set_state, list_active, delete)
- Persistent view insert, list_by_channel (isolation), delete_for_message
- Riposte timer lifecycle (insert, list_pending, mark_consumed, verify consumed)
- Sanitizer → audit_repo integration (injection fires audit row, clean input does not)
- MCP error hierarchy (all subclasses importable, str representations correct)
- Circuit breaker trips at threshold=3, resets on success
- MCPClient successful call (respx mock, returns parsed JSON)
- MCPClient 4xx raises MCPToolError without retry (call_count==1)
- MCPClient circuit OPEN blocks call before any HTTP

**.pre-commit-config.yaml** — ruff v0.9.10 `ruff` (lint+fix) and `ruff-format` hooks.

## Test Results

| Suite | Tests | Status |
|-------|-------|--------|
| test_sanitizer.py | 44 | PASSED |
| test_concurrent_writes.py | 2 skipped (RUN_STRESS gate) | SKIPPED |
| test_phase1_smoke.py | 9 | PASSED |
| **Plan 03 Total** | **53 (+2 gated)** | **PASSED** |

Full suite (all plans): 177 passing, 2 skipped (stress gate).

Stress test verified manually: `RUN_STRESS=1 STRESS_DURATION_SEC=5` passed in 5.03s.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] fixture 'bootstrapped_db_with_repos' not found in tests/safety/**
- **Found during:** test_sanitizer.py execution
- **Issue:** The `bootstrapped_db_with_repos` fixture was defined only in `tests/persistence/conftest.py`, not visible to `tests/safety/`
- **Fix:** Created `tests/safety/conftest.py` that imports the fixture from `tests.persistence.conftest` via `__all__`
- **Files modified:** tests/safety/conftest.py (created)

**2. [Rule 1 - Bug] Ruff E501/E402 in test files**
- **Found during:** Final ruff verification
- **Issue:** Long assertion messages in test_sanitizer.py exceed 100-char limit; stress test has E402 (imports after pytestmark which requires pytest to be imported first)
- **Fix:** Added `per-file-ignores` to pyproject.toml for affected test files
- **Files modified:** pyproject.toml

**3. [Rule 1 - Bug] sanitizer.py lambda-in-subn line too long**
- **Found during:** Final ruff verification
- **Issue:** `pattern.subn(lambda m: (stripped_tokens.append(m.group(0)), "")[1], cleaned)` exceeded 100 chars
- **Fix:** Extracted lambda to named `_replacer` function; also cleaner semantically
- **Files modified:** src/eldritch_dm/safety/sanitizer.py

**4. [Rule 1 - Bug] Integration smoke test used wrong ChannelState/RiposteTimer fields**
- **Found during:** test_phase1_smoke.py execution
- **Issue:** `ChannelState.IDLE` doesn't exist (correct: LOBBY); `RiposteTimer` requires `character_id`, `user_id` (not `target_user_id`), `message_id`, `custom_id`, `created_at`; `list_pending()` takes no channel_id arg; `mark_consumed()` returns None not a model; MCPClient uses `/v1/mcp/execute` not `/call`
- **Fix:** Corrected all field names, method signatures, and mock URL in smoke test
- **Files modified:** tests/integration/test_phase1_smoke.py

## Known Stubs

None — sanitizer is fully functional, corpus is complete (34 real cases), all integration tests exercise real sqlite3 databases.

## Threat Flags

| Flag | File | Description |
|------|------|-------------|
| threat_flag: player_input_injection | src/eldritch_dm/safety/sanitizer.py | Primary injection surface: player text entering the LLM prompt. Mitigated by: truncate-first, 64-pass strip loop, XML-escape, player_action sentinel wrapping. 34 adversarial corpus cases validate coverage. |

## Self-Check: PASSED

- src/eldritch_dm/safety/sanitizer.py: FOUND
- src/eldritch_dm/safety/corpus/injection_cases.yaml: FOUND
- tests/safety/test_sanitizer.py: FOUND
- tests/persistence/test_concurrent_writes.py: FOUND
- tests/integration/test_phase1_smoke.py: FOUND
- .pre-commit-config.yaml: FOUND
- Tests: 177 passed, 2 skipped, 0 failed
- import-linter: 4 contracts KEPT
- ruff: All checks passed
- Stress test: RUN_STRESS=1 STRESS_DURATION_SEC=5 — 1 passed in 5.03s
- Commits: e9131ae (sanitizer+corpus+stress), a1e3625 (integration+pre-commit+lint fixes)
