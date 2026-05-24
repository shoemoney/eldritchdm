#!/usr/bin/env bash
# Seed Phoenix projects from database/dashboards/*.json (Phase 11 / OBS-02).
#
# Idempotent: skips already-existing project names.
# Best-effort: Phoenix HTTP API drift produces WARN messages, not failures,
# because the worst case is the operator pastes the query_recipe field into
# the UI manually.
#
# Usage:
#   ./scripts/observability/seed-dashboards.sh
#
# Environment overrides:
#   PHOENIX_BASE_URL   default: http://localhost:6006
#   DASHBOARDS_DIR     default: <script_dir>/../../database/dashboards
set -euo pipefail

PHOENIX_BASE_URL="${PHOENIX_BASE_URL:-http://localhost:6006}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DASHBOARDS_DIR="${DASHBOARDS_DIR:-$SCRIPT_DIR/../../database/dashboards}"

if ! command -v curl >/dev/null 2>&1; then
  echo "WARN: curl not found — cannot seed Phoenix dashboards" >&2
  exit 0
fi
if ! command -v jq >/dev/null 2>&1; then
  echo "WARN: jq not found — install jq to parse dashboard JSON" >&2
  exit 0
fi

# Probe Phoenix reachability (warn-only; do NOT fail bot startup or CI).
if ! curl -fsS -m 3 "$PHOENIX_BASE_URL/healthz" >/dev/null 2>&1 \
   && ! curl -fsS -m 3 "$PHOENIX_BASE_URL/" >/dev/null 2>&1; then
  echo "WARN: Phoenix not reachable at $PHOENIX_BASE_URL — skipping dashboard seed" >&2
  exit 0
fi

if [ ! -d "$DASHBOARDS_DIR" ]; then
  echo "WARN: dashboards dir not found: $DASHBOARDS_DIR" >&2
  exit 0
fi

shopt -s nullglob
seeded=0
skipped=0
failed=0
for f in "$DASHBOARDS_DIR"/*.json; do
  name="$(jq -r '.phoenix_project_name' "$f" 2>/dev/null || true)"
  if [ -z "$name" ] || [ "$name" = "null" ]; then
    echo "WARN: $f has no phoenix_project_name — skipping" >&2
    continue
  fi

  # Phoenix /v1/projects GET enumerates projects; check if our name is present.
  existing="$(
    curl -fsS -m 5 "$PHOENIX_BASE_URL/v1/projects" 2>/dev/null \
      | jq -r --arg n "$name" '.data[]?.name? | select(. == $n)' 2>/dev/null \
      || true
  )"
  if [ -n "$existing" ]; then
    echo "skip: project '$name' already exists"
    skipped=$((skipped + 1))
    continue
  fi

  # Create the project. POST body shape: {name, description}.
  body="$(jq -c '{name: .phoenix_project_name, description: .title}' "$f")"
  if curl -fsS -m 5 -X POST "$PHOENIX_BASE_URL/v1/projects" \
       -H "Content-Type: application/json" \
       -d "$body" >/dev/null 2>&1; then
    echo "seeded: $name"
    seeded=$((seeded + 1))
  else
    echo "WARN: failed to seed '$name' — Phoenix API may have changed; paste query_recipe from $f into the UI manually" >&2
    failed=$((failed + 1))
  fi
done

echo "phoenix dashboards: seeded=$seeded skipped=$skipped failed=$failed"
exit 0
