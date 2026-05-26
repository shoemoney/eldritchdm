---
phase: 34-os-hygiene
milestone: v1.13
generated: 2026-05-26
mode: inline (no agent dispatch — mechanical changes only)
---

# Phase 34 — Open-source hygiene

Inline-executed by orchestrator. No agent overhead — scope is two
mechanical changes (one new file, one batch SPDX header add).

## Outcome
- CODE_OF_CONDUCT.md created (project-specific, lightweight, ~40 lines)
- 105/105 src/eldritch_dm/**/*.py files now have SPDX-License-Identifier: Apache-2.0 headers
- ruff clean post-patch
