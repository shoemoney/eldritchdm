# Phase 28 Plan 02 — Verification

## Success Criteria

- [x] `eldritch-dm-perf-baseline` registered + on PATH
- [x] CLI accepts `--baseline`, `--output`, `--limit-iterations`
- [x] Exit codes 0/1/2 implemented per D-218 (verified by diff tests 2,3,8)
- [x] CLI smoke test (mocked profiler) against committed baseline → exit 0
- [x] ≥5 new tests across `tests/perf/test_perf_baseline_*.py` (18 new tests)
- [x] `.github/workflows/perf.yml` valid YAML with weekly + `[perf]`-push triggers
- [x] ruff + lint-imports clean
- [x] Existing 1655-test suite still passes (1662 total now passing)
- [x] TUNE-02 + TUNE-03 ticked `[x]` in REQUIREMENTS.md

## Evidence

```
$ uv run eldritch-dm-perf-baseline --help
usage: eldritch-dm-perf-baseline [-h] [--baseline BASELINE] [--output OUTPUT]
                                 [--limit-iterations LIMIT_ITERATIONS]
                                 [--skip-cprofile] [--paths PATHS]
... (Exit codes 0/1/2 documented in epilog)

$ uv run python -c "import yaml; yaml.safe_load(open('.github/workflows/perf.yml'))"
(no output — valid)

$ uv run pytest tests/perf/test_perf_baseline_diff.py \
                tests/perf/test_perf_baseline_cli.py \
                tests/perf/test_perf_baseline_smoke.py -q
..................                                                       [100%]
18 passed in 0.07s

$ uv run pytest tests/ -q --ignore=tests/perf/test_profiler_self_check.py
1662 passed, 18 skipped, 83 warnings in 121.58s

$ uv run ruff check src/eldritch_dm/tools/perf_baseline.py tests/perf/test_perf_baseline_*.py
All checks passed!

$ uv run lint-imports
Contracts: 8 kept, 0 broken.

$ grep -q "eldritch-dm-perf-baseline" pyproject.toml && echo OK
OK

$ grep -q "\[x\] \*\*TUNE-02\*\*" .planning/REQUIREMENTS.md && \
  grep -q "\[x\] \*\*TUNE-03\*\*" .planning/REQUIREMENTS.md && echo OK
OK
```

## Commits

```
7dfd26e docs(28-02): tick TUNE-02 + TUNE-03
22a7ac5 feat(28-02): add .github/workflows/perf.yml — weekly + [perf]-push CI
7b1e9a1 feat(28-02): register eldritch-dm-perf-baseline console script + smoke test
51a62bd test(28-02): perf-baseline CLI end-to-end tests with mocked profiler
365842d feat(28-02): implement perf-baseline diff + CLI scaffold
8b310ed test(28-02): add failing tests for perf-baseline diff module
```

## Test Coverage

| Test file | Tests | Purpose |
|---|---:|---|
| `test_perf_baseline_diff.py` | 10 | pure-function diff + exit-code rules |
| `test_perf_baseline_cli.py`  |  6 | CLI end-to-end with mocked profiler |
| `test_perf_baseline_smoke.py`|  2 | committed baseline regression guard |
| **Total new** | **18** | |

## Outcome

**PASS — TUNE-02 CLI + TUNE-03 CI workflow shipped per D-217/D-218/D-219.**
