"""JudgeVerdict dimension-mean validator tests (T-12-01-03)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from eldritch_dm.eval.judge import JudgeVerdict


def _dims(t=0.75, m=0.75, n=0.75, e=0.75) -> dict[str, float]:
    return {
        "tactical_intent": t,
        "meta_knowledge": m,
        "narrative_fairness": n,
        "edge_case": e,
    }


def test_happy_path() -> None:
    v = JudgeVerdict.model_validate(
        {
            "overall_score": 0.75,
            "per_dimension": _dims(),
            "reasoning": "All dimensions equal.",
            "would_a_veteran_dm_approve": True,
        }
    )
    assert v.overall_score == 0.75
    assert len(v.per_dimension) == 4


def test_mean_mismatch_beyond_tolerance() -> None:
    with pytest.raises(ValidationError, match="disagrees with"):
        JudgeVerdict.model_validate(
            {
                "overall_score": 0.5,
                "per_dimension": _dims(0.9, 0.9, 0.9, 0.9),
                "reasoning": "x",
                "would_a_veteran_dm_approve": False,
            }
        )


def test_tolerance_edge_inside() -> None:
    # mean = 0.79, overall = 0.75 → diff 0.04, within 0.05
    JudgeVerdict.model_validate(
        {
            "overall_score": 0.75,
            "per_dimension": _dims(0.8, 0.8, 0.8, 0.76),
            "reasoning": "x",
            "would_a_veteran_dm_approve": True,
        }
    )


def test_tolerance_edge_outside() -> None:
    # mean = 0.81, overall = 0.75 → diff 0.06, outside
    with pytest.raises(ValidationError, match="disagrees with"):
        JudgeVerdict.model_validate(
            {
                "overall_score": 0.75,
                "per_dimension": _dims(0.8, 0.8, 0.8, 0.84),
                "reasoning": "x",
                "would_a_veteran_dm_approve": True,
            }
        )


def test_missing_dimension_key() -> None:
    with pytest.raises(ValidationError):
        JudgeVerdict.model_validate(
            {
                "overall_score": 0.75,
                "per_dimension": {
                    "tactical_intent": 0.75,
                    "meta_knowledge": 0.75,
                    "narrative_fairness": 0.75,
                },
                "reasoning": "x",
                "would_a_veteran_dm_approve": True,
            }
        )


def test_unknown_dimension_key() -> None:
    with pytest.raises(ValidationError):
        JudgeVerdict.model_validate(
            {
                "overall_score": 0.75,
                "per_dimension": {
                    "tactical_intent": 0.75,
                    "meta_knowledge": 0.75,
                    "narrative_fairness": 0.75,
                    "wisdom_check": 0.75,
                },
                "reasoning": "x",
                "would_a_veteran_dm_approve": True,
            }
        )


def test_score_out_of_range_high() -> None:
    with pytest.raises(ValidationError):
        JudgeVerdict.model_validate(
            {
                "overall_score": 1.5,
                "per_dimension": _dims(),
                "reasoning": "x",
                "would_a_veteran_dm_approve": True,
            }
        )


def test_score_out_of_range_low() -> None:
    with pytest.raises(ValidationError):
        JudgeVerdict.model_validate(
            {
                "overall_score": -0.1,
                "per_dimension": _dims(),
                "reasoning": "x",
                "would_a_veteran_dm_approve": True,
            }
        )


def test_per_dimension_value_out_of_range() -> None:
    with pytest.raises(ValidationError):
        JudgeVerdict.model_validate(
            {
                "overall_score": 0.75,
                "per_dimension": _dims(1.5, 0.5, 0.5, 0.5),
                "reasoning": "x",
                "would_a_veteran_dm_approve": True,
            }
        )


def test_reasoning_too_long() -> None:
    with pytest.raises(ValidationError):
        JudgeVerdict.model_validate(
            {
                "overall_score": 0.75,
                "per_dimension": _dims(),
                "reasoning": "x" * 501,
                "would_a_veteran_dm_approve": True,
            }
        )


def test_extra_top_level_field_ignored() -> None:
    # model_config extra="ignore" → silently drops extras
    v = JudgeVerdict.model_validate(
        {
            "overall_score": 0.75,
            "per_dimension": _dims(),
            "reasoning": "x",
            "would_a_veteran_dm_approve": True,
            "confidence": 0.99,  # extra
        }
    )
    assert v.overall_score == 0.75
