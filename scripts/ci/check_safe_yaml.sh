#!/usr/bin/env bash
# EldritchDM — CI gate: enforce yaml.safe_load only.
#
# PITFALLS.md YAML-1 + T-08-01: yaml.load() without a SafeLoader allows
# arbitrary Python execution via `!!python/object/apply:...`. This gate
# fails the build if ANY src/ file calls yaml.load(...) without the
# `safe_` prefix.
#
# Exit codes:
#   0  no unsafe yaml.load calls found (good)
#   1  unsafe yaml.load call detected (fail the build)
#
# Run locally: bash scripts/ci/check_safe_yaml.sh

set -euo pipefail

cd "$(dirname "$0")/../.."

# Match `yaml.load(` but NOT `yaml.safe_load(`. We also strip comment-only
# lines (anything where `yaml.load(` appears AFTER a `#`) since those are
# documentation, not real calls.
HITS=$(git grep -nE 'yaml\.load\(' -- 'src/' \
       | grep -v 'safe_load' \
       | grep -v '^[^:]*:[0-9]*:[[:space:]]*#' \
       || true)

if [ -n "$HITS" ]; then
    echo "UNSAFE yaml.load() detected -- use yaml.safe_load() instead" >&2
    echo "  (PITFALLS.md YAML-1 / T-08-01: arbitrary code execution risk)" >&2
    echo >&2
    echo "$HITS" >&2
    exit 1
fi

echo "safe_load-only check passed"
