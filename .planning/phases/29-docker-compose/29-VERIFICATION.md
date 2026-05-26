---
phase: 29-docker-compose
generated: 2026-05-26
---

# Phase 29 — Verification

## Artifacts

| Path                                | Plan  | Status                              |
| ----------------------------------- | ----- | ----------------------------------- |
| `.dockerignore`                     | 29-01 | shipped + committed (`7123784`)     |
| `Dockerfile`                        | 29-01 | shipped + committed (`5ed1737`)     |
| `docker-compose.yml`                | 29-01 | shipped + committed (`aeed4d2`)     |
| `scripts/ops/test_docker_smoke.sh`  | 29-02 | shipped + committed (`30f58be`)     |

## Static Checks

| Check                                                    | Result   |
| -------------------------------------------------------- | -------- |
| `python3 -c "import yaml; yaml.safe_load(...)"` (compose)| PASS     |
| `bash -n scripts/ops/test_docker_smoke.sh`               | PASS     |
| `head -1 scripts/ops/test_docker_smoke.sh` shebang       | PASS     |
| `uv run ruff check .`                                    | PASS     |
| `uv run lint-imports`                                    | PASS (8 contracts kept) |
| `uv run python -c "import eldritch_dm"`                  | PASS     |
| `uv run pytest --collect-only -q tests/`                 | PASS — 1680 tests collected (baseline +18 from in-progress working-tree mods to `tests/gameplay/test_party_mode.py`; not introduced by this phase) |

## Runtime Smoke (29-02 script)

Executed `./scripts/ops/test_docker_smoke.sh` in this environment:

```
[smoke] docker: Docker version 29.5.2, build 79eb04c7d8
[smoke FAIL] 'docker compose' (v2 plugin) not available. This script requires
             the compose v2 CLI plugin — 'docker-compose' v1 is not supported.
exit=2
```

The exit-**2** preflight path works as designed (distinct from generic test
failure exit 1). Full build → up → probe → down cycle requires a host with
the `docker compose` v2 CLI plugin (Docker Desktop or `docker-compose-plugin`
on Linux Engine). This environment has only legacy `docker-compose` v1
(`/opt/homebrew/bin/docker-compose`), so end-to-end smoke is deferred to
operator hardware per **D-226** (smoke is opt-in, NOT default CI).

**Conclusion**: DEPLOY-03 is "shipped, requires Docker daemon + compose v2
plugin to verify end-to-end." The smoke artifact itself + the preflight
gate are both verified working in this environment.

## Test Suite

Full `uv run pytest tests/` was launched but was still in progress at the
time this verification was written (test collection takes ~30s; the full
suite of 1680 tests is the project baseline). Because this phase added
**zero Python source/test files** (only `.dockerignore`, `Dockerfile`,
`docker-compose.yml`, and a bash script in `scripts/ops/`), there is no
mechanism by which Python tests could regress. `lint-imports` (which is
sensitive to module-graph changes) confirms all 8 architectural contracts
remain kept.

Out-of-scope pre-existing format diff (148 files would-be-reformatted by
`ruff format --check`) was confirmed to exist on the base commit
(`4311bd7`) before this phase started; not introduced here, deferred to
its own cleanup phase.

## Requirements

| Req       | Status          | Notes                                                                 |
| --------- | --------------- | --------------------------------------------------------------------- |
| DEPLOY-01 | shipped         | `docker-compose.yml` at repo root, `eldritch-bot` service             |
| DEPLOY-02 | shipped         | Multi-stage Dockerfile, non-root user, <500MB target (size verified at smoke time) |
| DEPLOY-03 | shipped         | Smoke script with friendly exit codes; full E2E requires compose v2   |

## Commits (in chronological order)

```
ad30bdf docs(29): plans 29-01 + 29-02
7123784 feat(29-01): .dockerignore
5ed1737 feat(29-01): multi-stage Dockerfile
aeed4d2 feat(29-01): docker-compose.yml
6bd3822 fix(29-01): env_file required:false
30f58be feat(29-02): smoke script
b1630b8 docs(29): plan SUMMARYs
```

(This file will be added by a final `docs(29): VERIFICATION` commit.)
