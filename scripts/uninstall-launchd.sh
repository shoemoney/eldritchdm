#!/usr/bin/env bash
#
# uninstall-launchd.sh — remove the EldritchDM LaunchAgent.
#
# Phase 5 Plan 03 / HOST-08. Idempotent: exits 0 even if already uninstalled.
#
# Usage:
#   bash scripts/uninstall-launchd.sh

set -euo pipefail

readonly PLIST_LABEL="com.shoemoney.eldritch-dm"
readonly TARGET="$HOME/Library/LaunchAgents/${PLIST_LABEL}.plist"

# Bootout (safe if not loaded)
launchctl bootout "gui/$UID/$PLIST_LABEL" 2>/dev/null || true

if [[ -f "$TARGET" ]]; then
  rm "$TARGET"
  echo "✅ Uninstalled $PLIST_LABEL ($TARGET removed)"
else
  echo "ℹ️  $PLIST_LABEL not installed (no plist at $TARGET)"
fi
