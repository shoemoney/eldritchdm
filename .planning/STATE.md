# State: EldritchDM

**Initialized:** 2026-05-21

## Project Reference

- **Project:** EldritchDM (ShoeGPT)
- **Core Value:** Mechanically honest AI DM — narration is evocative, but every die roll, HP change, AC check, and turn boundary is enforced by deterministic Python code; the LLM never touches the math.
- **Current Focus:** Phase 1 — Persistence Foundation

## Current Position

- **Milestone:** v1
- **Phase:** 1 — Persistence Foundation
- **Plan:** (none yet — awaiting `/gsd:plan-phase 1`)
- **Status:** Roadmap complete; planning not yet started
- **Progress:** [░░░░░░░░░░░░░░░░░░░░] 0% (0/11 phases complete)

## Phase Pointer

Phase 1: Persistence Foundation
Goal: A correct, single-writer SQLite persistence layer that supports concurrent multi-channel sessions with zero writer contention
Requirements: DB-01..DB-08
Success Criteria:
  1. The four tables exist with PRD-correct columns and constraints
  2. Every connection sets `journal_mode=WAL` and `busy_timeout=5000`; a single asyncio writer task drains all writes
  3. Every write uses `BEGIN IMMEDIATE`; no transaction spans an `await` to an external service
  4. Multi-channel concurrent stress test passes with zero `database is locked` errors
  5. Repository classes exist per aggregate; pure reads take no per-session lock

## Performance Metrics

- **Phases planned:** 0/11
- **Phases complete:** 0/11
- **Requirements mapped:** 87/87 ✓
- **Requirements complete:** 0/87

## Accumulated Context

### Key Decisions

- Inference backend is **oMLX (`omlx serve`)** at `http://localhost:8765/v1` with model id `ShoeGPT` (Gemma 4 4-bit under the hood). NOT mlx-lm.server. NOT port 8080.
- Native `response.tool_calls` is the primary dispatch path; structured `<tool_call>{json}</tool_call>` parser is a defensive fallback, disabled for turns containing user free-text.
- Three-brain architecture is a **logical** boundary inside one async Python process — not multiple processes.
- `ocrmac` (Apple Vision) is primary OCR on macOS; `easyocr` lives behind a `linux-ocr` extra.
- `PyMuPDF` is primary PDF parser; `pypdf` retained as MIT fallback.
- Single-writer asyncio queue + `BEGIN IMMEDIATE` + `busy_timeout=5000` is the SQLite concurrency model (WAL alone is insufficient).
- Self-hostable from day one — README + bootstrap + `.env.example` are first-class deliverables (Phase 11).

### Active Todos

- Run `/gsd:plan-phase 1` to plan the Persistence Foundation phase

### Blockers

(none)

### Risk Watch (CRITICAL v1 pitfalls)

- LLM math leakage → mitigated in Phase 3 (no-math validator + adversarial corpus)
- Persistent Views vanishing on restart → mitigated in Phase 5 (DynamicItem in `setup_hook`)
- Discord 3s ack cliff → mitigated in Phase 5 (lint-enforced `defer(thinking=True)`)
- SQLite writer contention → mitigated in Phase 1 (single-writer queue)
- Prompt injection via player modal → mitigated in Phase 3 (`<player_action>` sentinels, 500-char cap, fallback disabled with user text)

## Session Continuity

- **Last session:** 2026-05-21 — roadmap created with 11 phases, 87/87 requirements mapped
- **Next session:** Begin `/gsd:plan-phase 1` for Persistence Foundation

---
*State initialized: 2026-05-21*
