"""End-to-end CLI smoke (mocked LLM) — T-12-02-06.

Patches eldritch_dm.eval.cli._build_openai_client to return a MagicMock
whose chat.completions.create dispatches by system-message content
(oracle = driver, critic = judge).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from openai import AsyncOpenAI

from eldritch_dm.eval import cli as eval_cli


FIXTURE_PATH = Path(__file__).parent / "dataset" / "_fixture_one_scenario.jsonl"


def _mock_completion(content: str) -> Any:
    c = MagicMock()
    c.choices = [MagicMock()]
    c.choices[0].message = MagicMock()
    c.choices[0].message.content = content
    c.usage = MagicMock(prompt_tokens=50, completion_tokens=25)
    return c


def _dispatched_client(*, target: str, overall: float) -> Any:
    async def create(**kwargs):  # type: ignore[no-untyped-def]
        msgs = kwargs.get("messages", [])
        system = msgs[0].get("content", "") if msgs else ""
        if "oracle" in system:
            return _mock_completion(
                json.dumps({"target_pc_id": target, "rationale": "x"})
            )
        if "critic" in system:
            return _mock_completion(
                json.dumps(
                    {
                        "overall_score": overall,
                        "per_dimension": {
                            "tactical_intent": overall,
                            "meta_knowledge": overall,
                            "narrative_fairness": overall,
                            "edge_case": overall,
                        },
                        "reasoning": "smoke",
                        "would_a_veteran_dm_approve": overall >= 0.7,
                    }
                )
            )
        raise AssertionError(f"unknown system: {system[:80]!r}")

    client = MagicMock(spec=AsyncOpenAI)
    client.chat = MagicMock()
    client.chat.completions = MagicMock()
    client.chat.completions.create = AsyncMock(side_effect=create)
    return client


def test_smoke_passes_with_high_scores(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Mocked LLM returns 0.85 across the board → exit 0."""
    output = tmp_path / "runs"

    # Patch BOTH the AsyncOpenAI factory AND _git_short_sha (no .git in tmp).
    monkeypatch.setattr(
        eval_cli, "_build_openai_client",
        lambda **_: _dispatched_client(target="pc-2", overall=0.85),
    )

    argv = [
        "--dataset", str(FIXTURE_PATH),
        "--output", str(output),
        "--driver-model", "ShoeGPT",
        "--judge-model", "ShoeGPT",
    ]
    monkeypatch.setattr("sys.argv", ["eldritch-dm-eval"] + argv)

    exit_code = eval_cli.main()
    assert exit_code == 0

    json_files = sorted(output.glob("eval-*.json"))
    md_files = sorted(output.glob("eval-*.md"))
    assert len(json_files) == 1
    assert len(md_files) == 1

    payload = json.loads(json_files[0].read_text())
    assert payload["judge_prompt_version"] == "1.0.0"
    assert payload["driver_model"] == "ShoeGPT"
    assert payload["judge_model"] == "ShoeGPT"
    assert payload["exit_code"] == 0
    assert len(payload["scenarios"]) == 1
    assert payload["aggregate"]["n"] == 1
    assert payload["aggregate"]["overall_mean"] == 0.85
    assert payload["scenarios"][0]["scenario_id"] == "fixture-001"
    assert payload["scenarios"][0]["driver_target_pc_id"] == "pc-2"

    md = md_files[0].read_text()
    assert "EldritchDM Tactical Eval Report" in md
    assert "fixture-001" in md


def test_smoke_critical_exit_code_2(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Judge returns 0.3 → per-dimension mean < 0.5 → exit 2."""
    output = tmp_path / "runs"
    monkeypatch.setattr(
        eval_cli, "_build_openai_client",
        lambda **_: _dispatched_client(target="pc-1", overall=0.3),
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "eldritch-dm-eval",
            "--dataset", str(FIXTURE_PATH),
            "--output", str(output),
        ],
    )
    exit_code = eval_cli.main()
    assert exit_code == 2


def test_smoke_with_baseline_regression(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Current=0.65 vs baseline=0.85 → regression → exit 1."""
    output = tmp_path / "runs"
    baseline = tmp_path / "baseline.json"
    baseline.write_text(json.dumps({"aggregate": {"overall_mean": 0.85}}))

    monkeypatch.setattr(
        eval_cli, "_build_openai_client",
        lambda **_: _dispatched_client(target="pc-1", overall=0.65),
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "eldritch-dm-eval",
            "--dataset", str(FIXTURE_PATH),
            "--output", str(output),
            "--baseline", str(baseline),
        ],
    )
    exit_code = eval_cli.main()
    assert exit_code == 1

    payload = json.loads(next(output.glob("eval-*.json")).read_text())
    assert payload["baseline_diff"] is not None
    assert payload["baseline_diff"]["regressed"] is True
