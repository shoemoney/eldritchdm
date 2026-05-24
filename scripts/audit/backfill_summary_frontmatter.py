#!/usr/bin/env python3
"""Backfill ``requirements_completed:`` YAML frontmatter into v1.1 + v1.2
plan SUMMARY.md files (Phase 14 / FLAKE-03).

The mapping below is the authoritative REQ-ID → SUMMARY assignment derived
from ``.planning/ROADMAP.md`` Traceability table. Embedded in the script for
reproducibility — re-running the script with the same mapping is a no-op.

Usage:
    python scripts/audit/backfill_summary_frontmatter.py [--dry-run|--apply]

--dry-run (default) prints a unified diff per file without modifying anything.
--apply rewrites each SUMMARY in place.

Behavior:
- Parses the YAML frontmatter block (between the first two ``---`` lines).
- If a ``requirements_completed:`` key exists, replaces its value.
- If a legacy ``requirements-completed:`` (hyphen) key exists, removes it
  and inserts the underscore form.
- If neither exists, inserts ``requirements_completed:`` immediately after
  the ``plan:`` line (or as the second-to-last frontmatter line if ``plan``
  is absent).
- Emits IDs as a JSON-style flow sequence sorted alphabetically:
  ``requirements_completed: [DEBT-01]``
"""

from __future__ import annotations

import argparse
import difflib
import sys
from pathlib import Path

# Repo root is two directories up from this script (scripts/audit/).
REPO_ROOT = Path(__file__).resolve().parents[2]
PHASES_DIR = REPO_ROOT / ".planning" / "phases"

# Authoritative mapping: SUMMARY relative path → list of REQ-IDs.
# Derived from .planning/ROADMAP.md Traceability table.
MAPPING: dict[str, list[str]] = {
    "06-debt-paydown-and-cold-start/06-01-SUMMARY.md": ["DEBT-01"],
    "06-debt-paydown-and-cold-start/06-02-SUMMARY.md": ["DEBT-02"],
    "07-safety-gap-closure/07-01-SUMMARY.md": ["SAFETY-01", "SAFETY-02", "SAFETY-03"],
    "08-yaml-riposte-eligibility/08-01-SUMMARY.md": ["HOMEBREW-01", "HOMEBREW-02"],
    "09-pc-classes-backfill/09-01-SUMMARY.md": ["UPGRADE-01"],
    "10-smart-monsterdriver/10-01-SUMMARY.md": ["COMBAT-13"],
    "10-smart-monsterdriver/10-02-SUMMARY.md": ["COMBAT-14"],
    "11-phoenix-observability/11-01-SUMMARY.md": ["OBS-01"],
    "11-phoenix-observability/11-02-SUMMARY.md": ["OBS-02"],
    "12-llm-judge-tactical/12-01-SUMMARY.md": ["EVAL-01"],
    "12-llm-judge-tactical/12-02-SUMMARY.md": ["EVAL-02", "EVAL-03"],
    "13-production-monitoring/13-01-SUMMARY.md": ["MON-01"],
    "13-production-monitoring/13-02-SUMMARY.md": ["MON-02"],
    "13-production-monitoring/13-03-SUMMARY.md": ["MON-03"],
}


def _format_value(req_ids: list[str]) -> str:
    """Format the REQ-ID list as a YAML flow sequence."""
    sorted_ids = sorted(req_ids)
    return "[" + ", ".join(sorted_ids) + "]"


def _split_frontmatter(text: str) -> tuple[list[str] | None, list[str], str]:
    """Return (frontmatter_lines, body_lines, end_delim) or (None, all_lines, '').

    frontmatter_lines does NOT include the opening/closing ``---`` delimiters.
    end_delim is the closing delimiter line (e.g. ``---\n``) so we can
    re-emit it verbatim.
    """
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].rstrip() != "---":
        return None, lines, ""

    # Find closing ``---``
    for i in range(1, len(lines)):
        if lines[i].rstrip() == "---":
            return lines[1:i], lines[i + 1 :], lines[i]
    # No closing delimiter — malformed; treat as no frontmatter.
    return None, lines, ""


def _backfill_frontmatter(fm_lines: list[str], req_ids: list[str]) -> list[str]:
    """Return new frontmatter lines with ``requirements_completed:`` set.

    - Strips any existing ``requirements_completed:`` or
      ``requirements-completed:`` lines (only the single-line scalar form;
      this script does not understand multi-line block sequences for that key
      and the spec uses the flow form).
    - Inserts the new line immediately after the ``plan:`` line if present,
      otherwise as the last line of the block.
    """
    out: list[str] = []
    new_value = f"requirements_completed: {_format_value(req_ids)}\n"
    inserted = False
    plan_index = -1

    # First pass: drop existing requirements_completed / requirements-completed
    # lines; capture the position of ``plan:`` for insertion.
    filtered: list[str] = []
    for line in fm_lines:
        stripped = line.lstrip()
        if stripped.startswith("requirements_completed:") or stripped.startswith(
            "requirements-completed:"
        ):
            continue
        filtered.append(line)
    for i, line in enumerate(filtered):
        if line.lstrip().startswith("plan:"):
            plan_index = i

    # Second pass: insert at correct location.
    if plan_index >= 0:
        out = filtered[: plan_index + 1] + [new_value] + filtered[plan_index + 1 :]
        inserted = True
    else:
        out = filtered + [new_value]
        inserted = True

    assert inserted
    return out


def _process_file(path: Path, req_ids: list[str], *, apply: bool) -> tuple[bool, str]:
    """Process one SUMMARY file. Returns (changed, diff_text)."""
    original = path.read_text(encoding="utf-8")
    fm_lines, body_lines, end_delim = _split_frontmatter(original)
    if fm_lines is None:
        return False, f"SKIP {path}: no YAML frontmatter found\n"

    new_fm = _backfill_frontmatter(fm_lines, req_ids)
    new_text = "---\n" + "".join(new_fm) + (end_delim or "---\n") + "".join(body_lines)

    if new_text == original:
        return False, f"NOOP {path}: requirements_completed already up-to-date\n"

    diff = difflib.unified_diff(
        original.splitlines(keepends=True),
        new_text.splitlines(keepends=True),
        fromfile=str(path),
        tofile=str(path) + " (new)",
        n=2,
    )
    diff_text = "".join(diff)

    if apply:
        path.write_text(new_text, encoding="utf-8")
    return True, diff_text


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Print planned changes without writing (default).",
    )
    mode.add_argument(
        "--apply",
        action="store_true",
        help="Rewrite files in place.",
    )
    args = parser.parse_args()
    apply = bool(args.apply)

    changed_count = 0
    total = 0
    for rel_path, req_ids in MAPPING.items():
        path = PHASES_DIR / rel_path
        total += 1
        if not path.exists():
            print(f"MISSING {path}", file=sys.stderr)
            continue
        changed, message = _process_file(path, req_ids, apply=apply)
        if changed:
            changed_count += 1
            print(message)
        else:
            print(message.rstrip())

    summary = (
        f"\n{'APPLIED' if apply else 'WOULD CHANGE'} "
        f"{changed_count}/{total} SUMMARY files"
    )
    print(summary)
    return 0


if __name__ == "__main__":
    sys.exit(main())
