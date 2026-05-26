# EldritchDM v1.11 — Security Audit

**Phase:** 31 (read-only investigation)
**Date:** 2026-05-26
**Auditor:** GSD execute-phase agent (autonomous)
**Scope:** 8 attack surfaces enumerated in SECAUDIT-01, covering 11 milestones of accumulated surface (v1.0 → v1.10).
**Mode:** READ-ONLY. No code modified. Verification: `git diff --stat src/ tests/` == 0 at completion.
**Honesty clause:** Active per SECAUDIT-03 / D-239. Findings are not manufactured; absence of finding is a valid result when the methodology is auditable.

---

## Executive Summary

| Severity   | Count |
|------------|-------|
| CRITICAL   | 0     |
| HIGH       | 0     |
| MEDIUM     | 0     |
| LOW        | 0     |
| **Total**  | **0** |

**Outcome:** Branch B closure (0 findings). The codebase has accumulated multiple layers of defense over 11 milestones — sanitizer with audit, fail-CLOSED gates, parameterized SQL, allow-list projections, strict Pydantic validation of LLM output, hardcoded subprocess argv, `yaml.safe_load` only, intents minimized, paths sourced from env/config not user messages — and the audit found no exploitable weakness in any of the 8 surfaces. Methodology is documented per-surface below so the closure is itself audit-grade.

---

## Methodology

Investigation toolkit per D-241:

```text
# Dangerous-pattern grep (run from repo root):
grep -rn "eval(\|exec(\|os.system\|shell=True" src/ tests/
grep -rn "pickle\.\(load\|loads\)" src/ tests/
grep -rn "yaml\.load(" src/ tests/                # without _safe
grep -rn "subprocess" src/
grep -rn "Path(\|open(" src/

# Secret / log scrubbing:
grep -rn "DISCORD_TOKEN\|api_key\|API_KEY\|SECRET" src/
grep -rin "log.*token\|log.*secret\|log.*password\|log.*api[_-]key" src/

# Discord intents:
grep -rn "Intents\|message_content" src/

# LLM output paths:
grep -rn "completions\.create\|chat\.completions" src/

# Allow-lists:
grep -rn "ALLOWED\|allowlist\|WHITELIST\|CACHEABLE" src/
```

Files inspected (primary):
- `src/eldritch_dm/safety/sanitizer.py`
- `src/eldritch_dm/persistence/sanitizer_audit_repo.py`
- `src/eldritch_dm/logging.py`
- `src/eldritch_dm/config/__init__.py`, `config/token_guard.py`
- `src/eldritch_dm/mcp/cache.py`, `mcp/tools.py`, `mcp/client.py`
- `src/eldritch_dm/persistence/character_cache.py`
- `src/eldritch_dm/observability/narration_cache.py`, `budget_dm.py`, `budget_guard.py`, `alert_evaluator.py`, `alerts_loader.py`, `cost.py`, `span_buffer.py`
- `src/eldritch_dm/gameplay/smart_monster_driver.py`, `eligibility_loader.py`
- `src/eldritch_dm/eval/judge.py`, `eval/cli.py`
- `src/eldritch_dm/bot/bot.py`, `bot/modals.py`, `bot/cogs/exploration.py`, `bot/cogs/ingest.py`, `bot/cogs/lobby.py`, `bot/party_mode_parser.py`, `bot/qr.py`
- `src/eldritch_dm/ingest/translate.py`, `ingest/pdf.py`
- `src/eldritch_dm/tools/perf_baseline.py`, `tools/cache_clear.py`
- `pyproject.toml`

Cross-references to prior security work (D-240): v1.0 SAN-01..06, v1.1 SAFETY-01/02/03, v1.4 isolation, v1.5 MCPCache/CharacterSnapshot/NarrCache allow-lists, v1.6 OPQOL-02.

---

## Surface 1 — Secret / Token Leak Vectors

**Scope:** Does any code path log `DISCORD_TOKEN`, `OPENROUTER_API_KEY`, or other secret material? Does `sanitizer_audit` (which stores `raw_input`) constitute a leak vector? Do error responses or structured-log fields ever surface secrets?

**Methodology grep evidence:**

```bash
grep -rn "DISCORD_TOKEN\|api_key\|API_KEY\|SECRET" src/
grep -rin "log.*token\|log.*secret\|log.*password\|log.*api[_-]key" src/
```

**Findings inspected:**

- `src/eldritch_dm/logging.py:25-37` — `_SCRUB_KEYS = frozenset({"token","secret","key","password","passwd","auth"})`. A `_scrub_secrets` structlog processor runs in the shared processor chain (line 75) BEFORE the renderer, redacting any event-dict key whose name contains any sensitive substring. This catches *any* future logger that binds `token=...` or `api_key=...` regardless of call site.
- `src/eldritch_dm/config/__init__.py:316-323` — `Settings.__repr__` explicitly redacts `discord_token` and `openrouter_api_key` to `***REDACTED***`.
- `src/eldritch_dm/config/token_guard.py:33-60` — `DISCORD_TOKEN` unset → stderr message + structured-log event `missing_discord_token` (no value logged) + exit-4. Never echoes the token.
- `src/eldritch_dm/persistence/sanitizer_audit_repo.py:58-73` — writes `raw_input` to the `sanitizer_audit` table. This IS the player's free-text input. Status: **intentional, documented**. v1.0-REQUIREMENTS.md line 34 defines this column as part of SAN-05; v1.1-REQUIREMENTS.md line 54 explicitly defers retention policy. The table is local SQLite (self-hosted threat model: only the bot operator can read it). The player typed the content themselves; storing it for audit replay is the documented behavior. Not a finding under the project threat model.

**Result:** No findings. Secret scrubbing is enforced at the structlog processor level (defense in depth) AND at the `Settings.__repr__` level. `sanitizer_audit.raw_input` is a documented column, not a regression.

---

## Surface 2 — Allow-list Bypass Paths

**Scope:** `MCPCache` 6-tool CACHEABLE_TOOLS, `CharacterSnapshot` 14-field ALLOWED_SNAPSHOT_FIELDS, `NarrCacheGate` regex set. Can any path slip past?

**Methodology grep evidence:**

```bash
grep -n "CACHEABLE_TOOLS\|allow_list\|ALLOWED\|allowlist\|WHITELIST" src/
grep -n "PATTERNS\|_GATE_PATTERNS\|fail-CLOSED" src/eldritch_dm/observability/narration_cache.py
```

**Findings inspected:**

- `src/eldritch_dm/mcp/cache.py:74-88` — `CACHEABLE_TOOLS` is a module-level `frozenset[str]` of exactly 6 names: `dm20__get_class_info`, `dm20__get_race_info`, `dm20__list_campaigns`, `dm20__get_campaign_info`, `dnd__search_all_categories`, `dnd__verify_with_api`. Line 197 enforces: `if not self._settings.mcpcache_enabled or tool_name not in CACHEABLE_TOOLS: ... pass-through`. The gate is single-keyed (`in` test on frozenset) — no substring, no regex, no globbing. Bypass would require modifying `CACHEABLE_TOOLS` itself.
- `src/eldritch_dm/persistence/character_cache.py:120-141` — `ALLOWED_SNAPSHOT_FIELDS = frozenset(CharacterSnapshot.model_fields.keys())` pinned at import. `FORBIDDEN_SNAPSHOT_FIELDS` (lines 127-141) lists the 11 combat-mutable fields. `_project_to_snapshot` (line 159) first drops FORBIDDEN, then re-restricts to ALLOWED. Pydantic `extra="forbid"` on the model is a third belt. Triple-defense.
- `src/eldritch_dm/observability/narration_cache.py:62-95` — `_GATE_PATTERNS` is a compiled tuple of case-insensitive regexes covering HP/AC/damage/saves/conditions/dice/sentinel tokens. `is_pure_narration` is fail-CLOSED: returns `False` on FIRST match. Re-gated on serve as well as on store (lines 104-108, "pre-store" + "pre-serve" double gate).

**Result:** No findings. All three allow-lists are frozenset/compiled-regex constants enforced at the single entry point, with no dynamic membership computation. The triple-defense pattern in `_project_to_snapshot` is exemplary.

---

## Surface 3 — Cache-Poisoning Vectors

**Scope:** L2 SQLite cache holds attacker-controllable JSON (if dm20 MCP server is malicious). Can the cache write or read introduce code execution or state mutation?

**Methodology grep evidence:**

```bash
grep -n "pickle\|loads\|response_json\|INSERT\|EXECUTE" src/eldritch_dm/mcp/cache.py
grep -n "_l2_put\|_l2_get\|json.loads" src/eldritch_dm/mcp/cache.py
```

**Findings inspected:**

- `src/eldritch_dm/mcp/cache.py:697-704` — `_l2_put` serializes with `json.dumps(value, default=str)`. INSERT uses parameterized SQL (`?` placeholders, line 699-704). No string interpolation; SQL injection impossible.
- `src/eldritch_dm/mcp/cache.py:677-678` — `_l2_get` deserializes via `json.loads`. JSON only — no `pickle`, no `eval`. A malicious dm20 response can only deserialize back to standard JSON primitives (dict/list/str/int/float/bool/None). On JSONDecodeError (line 679) the row is dropped.
- Cacheable tools are all *reference data* (class info, race info, campaign metadata, SRD search) — they don't drive game-state mutations. The consumers of the cached dict are the cogs that *display* this reference data; they do not execute it.
- Per `src/eldritch_dm/mcp/cache.py:65-72` comment block: "Adding mutable-state reads here in the future REQUIRES per-mutation invalidation wiring at every dm20__update_* / dm20__apply_* / dm20__set_* call site. Do not relax without that wiring." — explicit design constraint preserved.

**Result:** No findings. The L2 cache is JSON-only (no pickle), uses parameterized SQL, and the cacheable surface is reference data with no execution semantics in consumers.

---

## Surface 4 — Sanitizer Regression Across 3 Modals

**Scope:** Phase 7 SAFETY-01 wired `sanitize_player_input` into 3 ingest modals. Did any later phase introduce a new modal/free-text path that bypasses the sanitizer?

**Methodology grep evidence:**

```bash
grep -rn "class.*Modal\b" src/eldritch_dm/bot/
grep -rn "sanitize_player_input\|_sanitize_modal_field" src/eldritch_dm/
```

**Modal census (all Modal subclasses in src/eldritch_dm/bot/):**

| Class                  | Location                                | Free-prose? | Sanitizer |
|------------------------|-----------------------------------------|-------------|-----------|
| `CharacterReviewModal` | `bot/modals.py:161`                     | Yes         | ✓ `_sanitize_modal_field` (lines 260-265) |
| `CharacterEntryModal`  | `bot/modals.py:284`                     | Yes         | ✓ `_sanitize_modal_field` (lines 372-377) |
| `OptionalFieldsModal`  | `bot/modals.py:396`                     | Yes         | ✓ `_sanitize_modal_field` per-field (line 487) |
| `WeaponSelectModal`    | `bot/modals.py:513`                     | No (structured) | ✓ Strict regex allow-list `^[a-zA-Z0-9 '+]+$` for weapon + `^[a-z0-9-]+$` for target_id (lines 510-511, 575-596). Rejects rather than strips. **More restrictive than sanitizer.** Sanitizer redundancy explicitly waived per v1.1-REQUIREMENTS SAFETY-01 note. |
| `DeclareActionModal`   | `bot/cogs/exploration.py:58`            | Yes         | ✓ `sanitize_player_input` (lines 109-122) |

OCR ingest path (`src/eldritch_dm/ingest/translate.py:227`) also calls `sanitize_player_input` on raw OCR text with `max_chars=4000` before forwarding to oMLX. Coverage includes the non-modal player-input vector.

**Result:** No findings. All 4 free-prose modals + the OCR ingest path are sanitized; the one structured modal uses tighter regex validation. No new modal/free-text path has been added since v1.1 Phase 7 without sanitizer wiring.

---

## Surface 5 — Mechanical-Honesty Contract Verification

**Scope:** Per project core value, the LLM never mutates game state. Verify that `SmartMonsterDriver`, `TacticalJudge`, and `NarrCache` outputs cannot inject HP/AC/damage values into the state machine.

**Methodology grep evidence:**

```bash
grep -rn "completions\.create\|chat\.completions" src/
grep -n "model_validate\|MonsterTacticChoice\|candidate_ids" src/eldritch_dm/gameplay/smart_monster_driver.py
```

**Findings inspected:**

- `src/eldritch_dm/gameplay/smart_monster_driver.py:622-633` — LLM call uses `response_format={"type":"json_object"}`. Output content is parsed at line 707 via `MonsterTacticChoice.model_validate_json(content)`. The Pydantic model contains ONLY `target_pc_ids: list[str]` and `tactic_kind: Literal["single","aoe"]` — no numeric fields. Lines 757-768 enforce `chosen_ids.issubset(candidate_ids)` and a defensive cap on AOE size. A hallucinated target ID → fail-soft return `None` (line 770). The LLM literally cannot supply an HP or damage value to the game engine; the model schema rejects them.
- `src/eldritch_dm/eval/judge.py:181, 235` — `TacticalJudge` is offline evaluation only. Returns `JudgeVerdict` (scores) via `model_validate_json`. It is not invoked from the gameplay event loop and cannot mutate combat state. (Cross-reference: `judge.py:96-102` docstring explicitly states fail-soft eval semantics.)
- `src/eldritch_dm/observability/narration_cache.py:62-128` — `NarrCacheGate.is_pure_narration` REJECTS any cached LLM output containing HP/AC/damage/dice/save/condition tokens. Both store-time (pre-store) and serve-time (pre-serve) re-gating per lines 104-108. A poisoned cache entry that somehow slipped in would be invalidated on serve.

**Result:** No findings. Three layers (Pydantic schema, candidate-ID set membership, NarrCacheGate regex) keep LLM output from touching numerics. The mechanical-honesty contract is structurally enforced.

---

## Surface 6 — Discord Permission Scope

**Scope:** Did any phase escalate the bot's intents beyond the v1.0 D-04 minimum (`message_content = False`)?

**Methodology grep evidence:**

```bash
grep -rn "Intents\|message_content\|members\|presences" src/
```

**Findings inspected:**

- `src/eldritch_dm/bot/bot.py:59-60` —
  ```python
  intents = discord.Intents.default()
  intents.message_content = False  # D-04: security choice — bot never reads raw messages
  ```
- No other `intents.X = True` assignment exists in `src/`. Bot relies entirely on slash commands, modals, and interaction events — none of which require message content.

**Result:** No findings. Phase 2 D-04 minimum is preserved across all 11 milestones.

---

## Surface 7 — File-system Path Traversal

**Scope:** YAML loaders (eligibility / alerts / pricing), `character_cache.sqlite`, `pc_classes --db-path`, QR PNG paths from dm20.

**Methodology grep evidence:**

```bash
grep -rn "Path(\|open(" src/ | grep -v "with open"
grep -rn "yaml\.load\|yaml\.safe_load" src/
grep -rn "add_argument.*path\|--.*path" src/
```

**Findings inspected:**

- `src/eldritch_dm/gameplay/eligibility_loader.py:69-98` — 3-tier path resolution: `Settings.eligibility_yaml_path` (env override, never user-supplied at runtime) → `~/.eldritch/eligibility.yaml` (per-install) → in-repo default. All `Path(...)` constructions are env-or-config-derived; not derived from Discord messages.
- `src/eldritch_dm/observability/alerts_loader.py:152` — `yaml.safe_load` only. CI grep gate in `tests/observability/test_alerts_loader.py:163-165` enforces bare `yaml.load(` is never introduced.
- `src/eldritch_dm/observability/cost.py:96-104` — same 3-tier pattern for `pricing.yaml`.
- `src/eldritch_dm/persistence/character_cache.py:267-271` — DB path: explicit constructor `path=` (test injection) OR `os.path.expanduser(settings.charcache_path)`. Both env/config-sourced, never Discord-input-derived.
- `src/eldritch_dm/tools/cache_clear.py:74-78` — `--cache-path` is a CLI argument for the operator's tool; never reachable from Discord.
- `src/eldritch_dm/bot/party_mode_parser.py:155-158` — parses `qr_path` out of dm20 markdown (untrusted source). The path IS checked with `.exists()` and stored on `PartyMember.qr_path`. **However:** `src/eldritch_dm/bot/cogs/lobby.py:252, 265` force `qr_path: None` when repacking the parsed result for downstream consumers, and `bot/qr.py:33-52` re-renders the QR locally from the server URL via `segno`. The dm20-supplied `qr_path` is NOT actually read or sent as an attachment; it is structurally orphaned at the cog boundary.
- `src/eldritch_dm/tools/perf_baseline.py:236-244` and `src/eldritch_dm/eval/cli.py:124-132` — both subprocess calls are `["git","rev-parse","--short","HEAD"]` (hardcoded argv, `shell=False`). No injection vector.
- `src/eldritch_dm/ingest/pdf.py:43` — `fitz.open(stream=pdf_bytes, filetype="pdf")` — reads from bytes (Discord attachment), not from a filesystem path. No traversal.

**Result:** No findings. Every `Path(...)` construction is either env-derived, in-repo-relative, or constructor-injected (tests). The one untrusted-source path (`qr_path` from dm20) is orphaned at the cog boundary and never consumed.

---

## Surface 8 — Discord DM-to-Owner Content

**Scope:** Phase 22 OPQOL-02 added an owner-DM notifier for budget / degraded-mode events. Verify the DM body cannot contain secrets or attacker-controlled content.

**Methodology grep evidence:**

```bash
grep -n "_MESSAGES\|notify_async\|user.send" src/eldritch_dm/observability/budget_dm.py
grep -rn "\.trip(\|notify_async(\|reason=" src/eldritch_dm/observability/
```

**Findings inspected:**

- `src/eldritch_dm/observability/budget_dm.py:70-74` — `_MESSAGES` template dict has 3 fixed templates with `{reason}` interpolation only.
- `src/eldritch_dm/observability/budget_dm.py:177-181` — `notify_async` formats `template.format(reason=reason)` and sends via `user.send(msg)`.
- `reason` origin trace:
  - `observability/budget_guard.py:146` — `reason = f"budget_exceeded:${spent} over ${self._cap}"` (numeric KPI values from internal float math).
  - `observability/alert_evaluator.py:186, 259` — `reason = f"{rule.name}:{rule.kpi}={value}>{rule.threshold}"` / `f"cold_start_replay:{rule.name}"` (config-defined rule names + numeric KPI values).
- Every `reason` source is internal: either a number formatted with `f"${spent}"` or a config-file rule name from `alerts.yaml`. None of these strings include Discord user input, secret material, file paths, or attacker-controlled content. The owner DM has a fixed structure: `"⚠️ EldritchDM: daily LLM budget breached. Reason: budget_exceeded:$X over $Y"` or similar.
- Send failures are caught at `Forbidden`/`HTTPException`/`NotFound` (lines 184-208) and routed to `log.warning`; the structured logger has the secret-scrubbing processor enabled (Surface 1).

**Result:** No findings. The DM body templates are static; the `{reason}` field is internal-only and never sources from Discord input or environment secrets.

---

## Aggregate Result — Branch B Closure

**0 findings across 8 surfaces.** Per SECAUDIT-03 / D-239, this is a legitimate closure outcome: the codebase has been built with structural defenses (allow-lists, fail-CLOSED gates, sanitizer + audit, parameterized SQL, intents minimized, secret-scrubbing logger processor, hardcoded subprocess argv, `yaml.safe_load` only, strict Pydantic schemas on LLM output) and 11 milestones of consistent application of these patterns. The audit methodology is documented above so the absence of findings can itself be audited.

**Not in scope (already covered by prior security work, no regression detected):**
- v1.0 SAN-01..06 — sanitizer + audit table (Surface 4 confirms no regression)
- v1.1 SAFETY-01/02/03 — modal wiring + token guard (Surfaces 1, 4)
- v1.4 isolation work — single-writer queue (Surface 3 confirms parameterized SQL preserved)
- v1.5 MCPCache / CharacterSnapshot / NarrCacheGate allow-lists (Surfaces 2, 5)
- v1.6 OPQOL-02 owner DM (Surface 8)

**Recommendations for Phase 32 (remediation phase) — none mandated by this audit.** If Phase 32 proceeds, it would be opportunistic hardening rather than vulnerability response.

**Recommendations as observations (not findings, not actionable in Phase 32):**
- `sanitizer_audit` retention policy remains deferred (v1.1-REQUIREMENTS line 54). The table grows unbounded. This is documented; no action required for security, but operators should be aware.
- The `qr_path` orphaning (Surface 7) is correct but relies on every future consumer of `PartyMember` to continue forcing `None`. A defensive note in `bot/party_mode_parser.py` already exists (T-03-05); consumers should retain that pattern.

---

## Verification of Read-only Constraint

```bash
$ git diff --stat src/ tests/
# (empty — 0 files changed)
```

No `.py` files in `src/` or `tests/` were modified during this phase. All changes are in `.planning/`.

---

*End of audit.*
