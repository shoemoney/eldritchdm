#!/usr/bin/env python3
"""Backfill ``requirements_completed:`` YAML frontmatter into every plan
SUMMARY.md file under ``.planning/phases/``.

**OPSDASH-02 rewrite (Phase 26):** the legacy version of this script
hardcoded a {SUMMARY → req-list} mapping, which silently drifted as new
phases shipped (Phase 24 audit caught 14 SUMMARYs whose
``requirements_completed:`` ended up empty because the hardcoded table
was never extended past Phase 13).

This rewrite:

1. **Auto-discovers** every ``*-SUMMARY.md`` under ``.planning/phases/``
   via ``pathlib.Path(...).rglob(...)`` — no hardcoded path list.
2. **Infers** each SUMMARY's REQ-ID list by reading the sibling PLAN
   file (same directory, ``*-SUMMARY.md`` → ``*-PLAN.md``) and parsing
   its YAML frontmatter ``requirements:`` flow-style sequence. The PLAN
   frontmatter is the canonical source — it is exactly what the executor
   used at plan time to call ``gsd-sdk query requirements.mark-complete``.

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
  the ``plan:`` line (or as the last frontmatter line if ``plan`` is absent).
- Emits IDs as a JSON-style flow sequence sorted alphabetically:
  ``requirements_completed: [DEBT-01]``
- A plan with no ``requirements:`` field, or an empty list, still gets
  ``requirements_completed: []`` written — the CI gate
  (``check_summary_frontmatter.sh``) requires the key to be present.
"""

from __future__ import annotations

import argparse
import difflib
import re
import sys
from pathlib import Path

# Repo root is two directories up from this script (scripts/audit/).
REPO_ROOT = Path(__file__).resolve().parents[2]
PHASES_DIR = REPO_ROOT / ".planning" / "phases"

# Match a flow-style YAML sequence on a single frontmatter line.
# Accepts either:
#   requirements: [FOO-01, BAR-02]
#   requirements: []
_REQUIREMENTS_LINE_RE = re.compile(
    r"^\s*requirements\s*:\s*\[(?P<inner>[^\]]*)\]\s*$"
)


def _format_value(req_ids: list[str]) -> str:
    """Format the REQ-ID list as a YAML flow sequence (alphabetically sorted)."""
    sorted_ids = sorted(req_ids)
    return "[" + ", ".join(sorted_ids) + "]"


def _split_frontmatter(text: str) -> tuple[list[str] | None, list[str], str]:
    """Return (frontmatter_lines, body_lines, end_delim) or (None, all_lines, '').

    frontmatter_lines does NOT include the opening/closing ``---`` delimiters.
    end_delim is the closing delimiter line (e.g. ``---\\n``) so we can
    re-emit it verbatim.
    """
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].rstrip() != "---":
        return None, lines, ""

    for i in range(1, len(lines)):
        if lines[i].rstrip() == "---":
            return lines[1:i], lines[i + 1 :], lines[i]
    # No closing delimiter — malformed; treat as no frontmatter.
    return None, lines, ""


def _extract_plan_requirements(plan_path: Path) -> list[str] | None:
    """Read a PLAN.md, extract the flow-style ``requirements:`` list.

    Returns:
        list[str] of REQ-IDs (possibly empty) if the field exists and parses.
        None if the file has no frontmatter, no ``requirements:`` line, or
        the value isn't a flow-style ``[...]`` sequence we can parse.
    """
    try:
        text = plan_path.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"ERROR: cannot read {plan_path}: {exc}", file=sys.stderr)
        return None

    fm_lines, _body, _end = _split_frontmatter(text)
    if fm_lines is None:
        return None

    for line in fm_lines:
        m = _REQUIREMENTS_LINE_RE.match(line)
        if m:
            inner = m.group("inner").strip()
            if not inner:
                return []
            return [tok.strip() for tok in inner.split(",") if tok.strip()]
    return None


def _backfill_frontmatter(fm_lines: list[str], req_ids: list[str]) -> list[str]:
    """Return new frontmatter lines with ``requirements_completed:`` set.

    - Strips any existing ``requirements_completed:`` or
      ``requirements-completed:`` lines (only the single-line scalar form).
    - Inserts the new line immediately after the ``plan:`` line if present,
      otherwise as the last line of the block.
    """
    new_value = f"requirements_completed: {_format_value(req_ids)}\n"
    plan_index = -1

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

    if plan_index >= 0:
        return filtered[: plan_index + 1] + [new_value] + filtered[plan_index + 1 :]
    return filtered + [new_value]


def _process_file(
    summary_path: Path, req_ids: list[str], *, apply: bool
) -> tuple[bool, str]:
    """Process one SUMMARY file. Returns (changed, message)."""
    original = summary_path.read_text(encoding="utf-8")
    fm_lines, body_lines, end_delim = _split_frontmatter(original)
    if fm_lines is None:
        return False, f"SKIP {summary_path}: no YAML frontmatter found"

    new_fm = _backfill_frontmatter(fm_lines, req_ids)
    new_text = "---\n" + "".join(new_fm) + (end_delim or "---\n") + "".join(body_lines)

    if new_text == original:
        return False, f"NOOP {summary_path}: requirements_completed already up-to-date"

    diff = difflib.unified_diff(
        original.splitlines(keepends=True),
        new_text.splitlines(keepends=True),
        fromfile=str(summary_path),
        tofile=str(summary_path) + " (new)",
        n=2,
    )
    diff_text = "".join(diff)

    if apply:
        summary_path.write_text(new_text, encoding="utf-8")
    return True, diff_text


def _sibling_plan_path(summary_path: Path) -> Path:
    """Given .../XX-YY-SUMMARY.md return .../XX-YY-PLAN.md."""
    return summary_path.with_name(summary_path.name.replace("-SUMMARY.md", "-PLAN.md"))


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

    if not PHASES_DIR.is_dir():
        print(f"ERROR: {PHASES_DIR} not found", file=sys.stderr)
        return 1

    summaries = sorted(PHASES_DIR.rglob("*-SUMMARY.md"))
    if not summaries:
        print(f"WARN: no SUMMARY files found under {PHASES_DIR}", file=sys.stderr)
        return 0

    changed_count = 0
    skipped_count = 0
    total = len(summaries)

    for summary in summaries:
        plan = _sibling_plan_path(summary)
        if not plan.exists():
            print(f"WARN {summary}: no sibling PLAN at {plan} — skipping")
            skipped_count += 1
            continue

        req_ids = _extract_plan_requirements(plan)
        if req_ids is None:
            print(
                f"WARN {summary}: sibling PLAN has no parseable 'requirements:' "
                f"flow-list ({plan}) — skipping"
            )
            skipped_count += 1
            continue

        changed, message = _process_file(summary, req_ids, apply=apply)
        if changed:
            changed_count += 1
        print(message)

    print(
        f"\n{'APPLIED' if apply else 'WOULD CHANGE'} {changed_count}/{total} "
        f"SUMMARY files (skipped {skipped_count})"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
