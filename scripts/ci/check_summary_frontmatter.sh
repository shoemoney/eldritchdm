#!/usr/bin/env bash
# CI gate: every plan SUMMARY.md must have a top-level
# ``requirements_completed:`` key in its YAML frontmatter. Phase 14 / FLAKE-03.
#
# Exits 0 if all SUMMARY files comply.
# Exits 1 and lists offenders otherwise.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PHASES_DIR="$REPO_ROOT/.planning/phases"

if [ ! -d "$PHASES_DIR" ]; then
    echo "ERROR: .planning/phases not found under $REPO_ROOT" >&2
    exit 1
fi

offenders=()
checked=0

# Use find -print0 + a while-read loop for safe traversal (avoids globbing
# issues when no SUMMARYs match).
while IFS= read -r -d '' summary; do
    checked=$((checked + 1))

    # Must start with --- (frontmatter delimiter).
    first_line="$(head -n 1 "$summary")"
    if [ "$first_line" != "---" ]; then
        offenders+=("$summary :: missing YAML frontmatter (first line is not '---')")
        continue
    fi

    # Extract frontmatter block (between first two '---' lines).
    # awk: turn on flag on first '---', off on second.
    fm_block=$(awk '
        /^---$/ {
            n++;
            if (n == 1) { inside=1; next }
            if (n == 2) { inside=0; exit }
        }
        inside { print }
    ' "$summary")

    if ! echo "$fm_block" | grep -qE '^requirements_completed:'; then
        offenders+=("$summary :: no 'requirements_completed:' key in frontmatter")
        continue
    fi

    # Forbid the legacy hyphen form (it must have been normalised).
    if echo "$fm_block" | grep -qE '^requirements-completed:'; then
        offenders+=("$summary :: legacy 'requirements-completed:' (hyphen) key present — normalise to underscore")
        continue
    fi
done < <(find "$PHASES_DIR" -type f -name '*-SUMMARY.md' -print0)

if [ ${#offenders[@]} -gt 0 ]; then
    echo "FAIL: SUMMARY frontmatter check failed (${#offenders[@]} offenders, $checked checked):" >&2
    for o in "${offenders[@]}"; do
        echo "  - $o" >&2
    done
    echo "" >&2
    echo "Fix: run scripts/audit/backfill_summary_frontmatter.py --apply" >&2
    exit 1
fi

echo "OK: $checked SUMMARY files have requirements_completed: frontmatter"
