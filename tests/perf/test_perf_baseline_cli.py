"""Phase 28 / TUNE-02 — perf-baseline CLI tests.

These exercise ``main()`` end-to-end but monkeypatch the inner profiler
invocation so the test stays deterministic (the real profiler has 50%+
single-iter variance on riposte-click-handler — flaky for a smoke test).
"""

from __future__ import annotations

import json
from pathlib import Path

from eldritch_dm.tools import perf_baseline


def _fake_profiler_factory(out_p99s: dict[str, float]):
    """Return a fake ``_invoke_profiler`` that writes a baseline-shaped JSON."""

    def _fake(*, output: Path, iterations: int, skip_cprofile: bool, paths: str) -> int:
        payload = {
            "version": "test",
            "git_sha": "f" * 40,
            "generated_at": "2026-05-26T00:00:00+00:00",
            "operations": {
                name: {
                    "p50_ms": p99 * 0.5,
                    "p95_ms": p99 * 0.9,
                    "p99_ms": p99,
                    "iterations": iterations,
                    "cprofile_top_10": [],
                }
                for name, p99 in out_p99s.items()
            },
        }
        output.write_text(json.dumps(payload))
        return 0

    return _fake


def _write_baseline(path: Path, p99s: dict[str, float]) -> None:
    payload = {
        "version": "test",
        "git_sha": "0" * 40,
        "generated_at": "2026-05-26T00:00:00+00:00",
        "operations": {
            name: {
                "p50_ms": p99 * 0.5,
                "p95_ms": p99 * 0.9,
                "p99_ms": p99,
                "iterations": 100,
                "cprofile_top_10": [],
            }
            for name, p99 in p99s.items()
        },
    }
    path.write_text(json.dumps(payload))


def test_parser_accepts_all_documented_flags():
    parser = perf_baseline.build_parser()
    args = parser.parse_args(
        [
            "--baseline",
            "/tmp/x.json",
            "--output",
            "/tmp/out",
            "--limit-iterations",
            "5",
            "--skip-cprofile",
            "--paths",
            "smart-driver-oracle",
        ]
    )
    assert args.baseline == Path("/tmp/x.json")
    assert args.output == Path("/tmp/out")
    assert args.limit_iterations == 5
    assert args.skip_cprofile is True
    assert args.paths == "smart-driver-oracle"


def test_main_baseline_identical_returns_0(tmp_path, monkeypatch):
    baseline_path = tmp_path / "baseline.json"
    output_dir = tmp_path / "out"
    p99s = {"op-a": 1.0, "op-b": 2.0}
    _write_baseline(baseline_path, p99s)
    monkeypatch.setattr(
        perf_baseline, "_invoke_profiler", _fake_profiler_factory(p99s)
    )

    rc = perf_baseline.main(
        [
            "--baseline",
            str(baseline_path),
            "--output",
            str(output_dir),
            "--limit-iterations",
            "5",
            "--skip-cprofile",
        ]
    )
    assert rc == 0
    written = list(output_dir.glob("perf-*.json"))
    assert len(written) == 1
    written_md = list(output_dir.glob("perf-*.md"))
    assert len(written_md) == 1


def test_main_30pct_regression_returns_2(tmp_path, monkeypatch):
    baseline_path = tmp_path / "baseline.json"
    output_dir = tmp_path / "out"
    _write_baseline(baseline_path, {"op-a": 1.0})
    monkeypatch.setattr(
        perf_baseline,
        "_invoke_profiler",
        _fake_profiler_factory({"op-a": 1.30}),  # +30%
    )

    rc = perf_baseline.main(
        [
            "--baseline",
            str(baseline_path),
            "--output",
            str(output_dir),
            "--skip-cprofile",
        ]
    )
    assert rc == 2


def test_main_15pct_regression_returns_1(tmp_path, monkeypatch):
    baseline_path = tmp_path / "baseline.json"
    output_dir = tmp_path / "out"
    _write_baseline(baseline_path, {"op-a": 1.0})
    monkeypatch.setattr(
        perf_baseline,
        "_invoke_profiler",
        _fake_profiler_factory({"op-a": 1.15}),  # +15%
    )

    rc = perf_baseline.main(
        [
            "--baseline",
            str(baseline_path),
            "--output",
            str(output_dir),
            "--skip-cprofile",
        ]
    )
    assert rc == 1


def test_main_missing_baseline_returns_warn(tmp_path, monkeypatch):
    output_dir = tmp_path / "out"
    # Profiler should never be invoked when baseline doesn't exist.
    called = []
    monkeypatch.setattr(
        perf_baseline,
        "_invoke_profiler",
        lambda **_: called.append(1) or 0,
    )
    rc = perf_baseline.main(
        [
            "--baseline",
            str(tmp_path / "does-not-exist.json"),
            "--output",
            str(output_dir),
        ]
    )
    assert rc == 1
    assert called == []  # short-circuited before profiler invocation


def test_main_output_filenames_have_timestamp_and_sha(tmp_path, monkeypatch):
    baseline_path = tmp_path / "baseline.json"
    output_dir = tmp_path / "out"
    p99s = {"op-a": 1.0}
    _write_baseline(baseline_path, p99s)
    monkeypatch.setattr(
        perf_baseline, "_invoke_profiler", _fake_profiler_factory(p99s)
    )

    perf_baseline.main(
        [
            "--baseline",
            str(baseline_path),
            "--output",
            str(output_dir),
            "--skip-cprofile",
        ]
    )
    jsons = list(output_dir.glob("perf-*.json"))
    assert len(jsons) == 1
    name = jsons[0].name
    # Format: perf-{YYYYMMDDThhmmssZ}-{sha-or-unknown}.json
    assert name.startswith("perf-")
    assert name.endswith(".json")
    # 4 dashes total: "perf-" + "20260526T..." + "-" + "<sha>" + ".json"
    assert name.count("-") >= 2
