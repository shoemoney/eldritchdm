# EldritchDM — Requirements (v1.13 Open-Source Hygiene)

**Milestone:** v1.13 Open-Source Hygiene
**Goal:** Close real open-source repo gaps. CODE_OF_CONDUCT.md (separated from inline CONTRIBUTING.md). SPDX-License-Identifier headers on all src/ Python files (was 0/105). Apache-2.0 license is in LICENSE but headers identify provenance per-file.
**Total v1.13 requirements:** 2.

---

## v1.13 Requirements

- [x] **HYGIENE-01**: `CODE_OF_CONDUCT.md` at repo root. Project-specific lightweight version (not full Contributor Covenant adoption — clarity over ceremony). Cross-link from CONTRIBUTING.md. Maintainer email + 4-step enforcement process documented.
- [x] **HYGIENE-02**: `SPDX-License-Identifier: Apache-2.0` headers on all 105 `src/eldritch_dm/**/*.py` files. Comment-only change; placement is AFTER any module docstring (Python convention). 0% → 100% coverage.

## Traceability

| REQ-ID | Phase | Source |
|---|---|---|
| HYGIENE-01 | 34 | Open-source repo gap — Apache-2.0 repos conventionally ship CODE_OF_CONDUCT.md as a separate file |
| HYGIENE-02 | 34 | SPDX best practice — per-file provenance even with a LICENSE file in repo root |

## Mode Constraints
- Documentation-only milestone. SPDX headers are comment lines; ruff verified clean post-patch.
- No new dependencies, no code-behavior change.
- Single phase (34), single plan (34-01).
