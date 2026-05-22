#!/usr/bin/env bash
#
# install-launchd.sh — register EldritchDM as a user-scope LaunchAgent on macOS.
#
# Phase 5 Plan 03 / HOST-08. Mirrors the user's existing com.user.omlx model
# but uses dict-form KeepAlive (see docs/launchd.plist.example).
#
# Idempotent: bootouts any existing instance before re-installing.
# Honors DRY_RUN=1 (prints intent without touching launchctl).
#
# Usage:
#   bash scripts/install-launchd.sh              # install + start
#   DRY_RUN=1 bash scripts/install-launchd.sh    # validate plist only
#
# Run from the project root (substitutes {PROJECT_DIR} with $PWD).

set -euo pipefail

readonly PLIST_LABEL="com.shoemoney.eldritch-dm"
readonly TARGET="$HOME/Library/LaunchAgents/${PLIST_LABEL}.plist"
readonly SOURCE="docs/launchd.plist.example"

if [[ ! -f "$SOURCE" ]]; then
  echo "❌ ${SOURCE} not found. Run this script from the project root." >&2
  exit 1
fi

if [[ "${DRY_RUN:-0}" == "1" ]]; then
  # DRY_RUN: render to a tempfile, validate, do NOT touch ~/Library/LaunchAgents
  TMP_PLIST=$(mktemp -t "${PLIST_LABEL}.plist.XXXXXX")
  trap 'rm -f "$TMP_PLIST"' EXIT
  sed "s|{PROJECT_DIR}|$PWD|g" "$SOURCE" > "$TMP_PLIST"
  plutil -lint "$TMP_PLIST"
  echo "[DRY_RUN] Would bootstrap $TARGET"
  echo "[DRY_RUN] Plist rendered to $TMP_PLIST and validated; no launchctl call made."
  exit 0
fi

# Ensure LaunchAgents dir exists
mkdir -p "$(dirname "$TARGET")"

# Bootout any pre-existing instance (idempotent — safe if not loaded)
launchctl bootout "gui/$UID/$PLIST_LABEL" 2>/dev/null || true

# Substitute {PROJECT_DIR} placeholders with the current working directory.
# IMPORTANT: $PWD must be the absolute project root.
sed "s|{PROJECT_DIR}|$PWD|g" "$SOURCE" > "$TARGET"

# Validate plist syntax before activating it
plutil -lint "$TARGET"

# Activate the agent
launchctl bootstrap "gui/$UID" "$TARGET"
launchctl kickstart -k "gui/$UID/$PLIST_LABEL"

echo "✅ Installed and started $PLIST_LABEL"
echo "   Logs: $PWD/eldritch-dm.log"
echo "   Errors: $PWD/eldritch-dm.err"
echo "   Inspect: launchctl list | grep eldritch"
echo "   Uninstall: bash scripts/uninstall-launchd.sh"
