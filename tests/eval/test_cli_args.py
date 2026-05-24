"""eldritch-dm-eval CLI argparse tests (T-12-02-05)."""

from __future__ import annotations

from pathlib import Path

import pytest

from eldritch_dm.eval.cli import build_parser


def test_parser_accepts_all_flags() -> None:
    parser = build_parser()
    args = parser.parse_args(
        [
            "--dataset", "/tmp/x.jsonl",
            "--judge-model", "gpt-4o",
            "--driver-model", "ShoeGPT",
            "--limit", "5",
            "--baseline", "/tmp/prior.json",
            "--output", "/tmp/runs",
            "--verbose",
        ]
    )
    assert args.dataset == Path("/tmp/x.jsonl")
    assert args.judge_model == "gpt-4o"
    assert args.driver_model == "ShoeGPT"
    assert args.limit == 5
    assert args.baseline == Path("/tmp/prior.json")
    assert args.output == Path("/tmp/runs")
    assert args.verbose is True


def test_parser_defaults() -> None:
    parser = build_parser()
    args = parser.parse_args([])
    assert args.judge_model == "ShoeGPT"
    assert args.driver_model == "ShoeGPT"
    assert args.limit == 0
    assert args.baseline is None
    assert args.output == Path("./eval-runs")
    assert args.verbose is False
    assert args.dataset.name == "tactical_corpus.jsonl"


def test_help_mentions_exit_codes(capsys: pytest.CaptureFixture) -> None:
    parser = build_parser()
    with pytest.raises(SystemExit) as excinfo:
        parser.parse_args(["--help"])
    assert excinfo.value.code == 0
    out = capsys.readouterr().out
    assert "Exit codes" in out
    assert "0 = passed" in out
    assert "1 = regression" in out
    assert "2 = critical" in out
