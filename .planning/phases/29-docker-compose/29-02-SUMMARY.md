---
phase: 29-docker-compose
plan: 29-02
subsystem: deploy
tags: [docker, smoke-test, ops]
requirements: [DEPLOY-03]
key-files:
  created:
    - scripts/ops/test_docker_smoke.sh
  modified: []
decisions:
  - D-226 (smoke is operator-opt-in; NOT in default CI)
metrics:
  duration: ~10 min
  completed: 2026-05-26
---

# Phase 29 Plan 02: docker compose smoke test Summary

## One-liner
`scripts/ops/test_docker_smoke.sh` runs the build → up → exec(`import eldritch_dm`) → down cycle behind a Docker preflight, with image-size budget warn and friendly exit codes (2 = no Docker, 1 = test fail, 0 = pass).

## What Shipped

### `scripts/ops/test_docker_smoke.sh` (chmod +x)

POSIX-friendly bash script (`set -euo pipefail`) that:

1. **Resolves repo root from its own location** — works regardless of cwd.
2. **Preflights**: checks `docker` is on PATH and `docker compose version` works (compose v2 plugin). Exits **2** with a friendly message if either is missing — distinguishable from a generic test failure (exit 1).
3. **Creates a throwaway `.env`** with a placeholder `DISCORD_TOKEN` if no real `.env` exists at repo root. The probe runs `import eldritch_dm` and exits before `bot.run`, so the placeholder never reaches Discord's auth endpoint. Marked for cleanup in the trap.
4. **Build**: `docker compose build eldritch-bot`.
5. **Up**: `docker compose up -d eldritch-bot`, then polls `docker inspect` for container status with a 60s deadline.
6. **Probe**: `docker compose exec -T eldritch-bot python -c "import eldritch_dm; print('OK:', ...)"` — asserts stdout starts with `OK:`.
7. **Size check**: `docker image inspect eldritch-dm:local --format '{{.Size}}'` — **WARN-only** if >500 MiB (per D-223 budget). Doesn't fail the smoke; size regressions are flagged for the operator to investigate before tagging a release.
8. **Cleanup trap (EXIT/INT/TERM)** always runs:
   - Dumps `docker compose logs eldritch-bot` to stderr on failure.
   - `docker compose down -v --remove-orphans`.
   - Removes the throwaway `.env` if we created it.

### Exit-code contract

| Exit | Meaning                                                     |
| ---- | ----------------------------------------------------------- |
| 0    | Smoke pass                                                  |
| 1    | Smoke fail (build, up, probe, or down)                      |
| 2    | Docker / compose v2 not installed (preflight, distinct)     |

NOT wired into default CI per **D-226** — no `.github/workflows/*` edits. Operators run it manually after Dockerfile or compose changes.

## Verification

- `bash -n scripts/ops/test_docker_smoke.sh` → syntax OK
- `head -1 scripts/ops/test_docker_smoke.sh` → `#!/usr/bin/env bash`
- `chmod +x` applied (committed mode 100755)
- **Preflight verified in this environment**: `docker` is installed (29.5.2) but the compose **v2** plugin is NOT (only legacy `docker-compose` v1). Running the script produced:
  ```
  [smoke FAIL] 'docker compose' (v2 plugin) not available. This script requires
              the compose v2 CLI plugin — 'docker-compose' v1 is not supported.
  exit=2
  ```
  Confirms the friendly-exit-2 preflight path works as designed.
- **Full build → up → probe → down cycle was NOT exercised** in this execution environment because the host lacks the compose v2 plugin. Per D-226 this is operator-opt-in tooling, so shipping the artifact + preflight verification satisfies DEPLOY-03. To run the full smoke on a Docker Desktop or Docker Engine + compose-v2 host:
  ```
  bash scripts/ops/test_docker_smoke.sh
  ```

## Deviations from Plan

None. The script implements the planned behavior exactly; the env-stub bookkeeping was simplified (single `CREATED_DOT_ENV` flag) during implementation but the contract is unchanged.

## Auth/Environment Gates

The host lacks `docker compose` v2. This is not an auth gate — it's an environment limitation that the script itself reports cleanly via exit 2. Full end-to-end smoke verification is deferred to an operator with a Docker Desktop or Docker Engine + compose-v2 install. **DEPLOY-03 is "shipped, requires Docker daemon + compose v2 plugin to verify end-to-end."**

## Commits

| Commit  | Type | Description                                  |
| ------- | ---- | -------------------------------------------- |
| 30f58be | feat | `scripts/ops/test_docker_smoke.sh` (DEPLOY-03) |

## Self-Check: PASSED
- `scripts/ops/test_docker_smoke.sh`: FOUND, mode 100755
- Commit 30f58be: FOUND in git log
- Preflight exit-2 path: VERIFIED by direct invocation
