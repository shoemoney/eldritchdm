"""Phase 28 / TUNE-02 — perf-baseline smoke test.

Verifies the CLI exits 0 when the profiler "happens to" reproduce the
committed v1.9.0 baseline. The real profiler isn't run — it's
monkeypatched to write a copy of the committed JSON. This guards against
schema/CLI regressions without flake risk.
"""

from __future__ import annotations

import json
from pathlib import Path

from eldritch_dm.tools import perf_baseline

_REPO_ROOT = Path(__file__).resolve().parents[2]
_COMMITTED_BASELINE = _REPO_ROOT / ".planning" / "perf-baseline-v1.9.0.json"


def test_smoke_against_committed_baseline_exit_0(tmp_path, monkeypatch):
    """CLI vs committed baseline with profiler returning identical numbers → exit 0."""
    assert _COMMITTED_BASELINE.is_file(), "committed v1.9.0 baseline missing"
    committed_payload = json.loads(_COMMITTED_BASELINE.read_text())

    def _fake_profiler(*, output: Path, iterations: int, skip_cprofile: bool, paths: str) -> int:
        # Write a byte-equivalent copy of the committed baseline.
        output.write_text(json.dumps(committed_payload))
        return 0

    monkeypatch.setattr(perf_baseline, "_invoke_profiler", _fake_profiler)

    output_dir = tmp_path / "perf-runs"
    rc = perf_baseline.main(
        [
            "--baseline",
            str(_COMMITTED_BASELINE),
            "--output",
            str(output_dir),
            "--skip-cprofile",
        ]
    )
    assert rc == 0, "smoke run against identical baseline should exit 0"

    # Output artifacts written.
    assert list(output_dir.glob("perf-*.json")), "expected JSON artifact written"
    assert list(output_dir.glob("perf-*.md")), "expected Markdown artifact written"


def test_committed_baseline_validates_against_schema():
    """Defensive: the v1.9.0 baseline must round-trip BaselineSchema."""
    from scripts.perf._schema import BaselineSchema

    text = _COMMITTED_BASELINE.read_text()
    schema = BaselineSchema.model_validate_json(text)
    assert len(schema.operations) >= 6, "expected ≥6 operations in v1.9.0 baseline"
