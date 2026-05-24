"""Judge prompt loader tests (T-12-01-02)."""

from __future__ import annotations

from pathlib import Path

import pytest

from eldritch_dm.eval.judge_prompt import JudgePromptError, load_judge_prompt


def test_load_bundled_prompt() -> None:
    text, version = load_judge_prompt()
    assert version == "1.0.0"
    assert "tactical_intent" in text
    assert "meta_knowledge" in text
    assert "narrative_fairness" in text
    assert "edge_case" in text
    assert text.startswith("# judge-prompt-version: 1.0.0")


def test_load_explicit_path(tmp_path: Path) -> None:
    p = tmp_path / "prompt.txt"
    p.write_text("# judge-prompt-version: 2.3.4\nBody text.\n")
    text, version = load_judge_prompt(p)
    assert version == "2.3.4"
    assert "Body text." in text


def test_missing_file(tmp_path: Path) -> None:
    with pytest.raises(JudgePromptError, match="not found"):
        load_judge_prompt(tmp_path / "no.txt")


def test_empty_file(tmp_path: Path) -> None:
    p = tmp_path / "prompt.txt"
    p.write_text("")
    with pytest.raises(JudgePromptError, match="empty"):
        load_judge_prompt(p)


def test_missing_header(tmp_path: Path) -> None:
    p = tmp_path / "prompt.txt"
    p.write_text("No header here\nbody\n")
    with pytest.raises(JudgePromptError, match="line 1"):
        load_judge_prompt(p)


def test_malformed_version(tmp_path: Path) -> None:
    p = tmp_path / "prompt.txt"
    p.write_text("# judge-prompt-version: foo\nbody\n")
    with pytest.raises(JudgePromptError, match="line 1"):
        load_judge_prompt(p)


def test_wrong_header_format(tmp_path: Path) -> None:
    p = tmp_path / "prompt.txt"
    # Missing the leading "# "
    p.write_text("judge-prompt-version: 1.0.0\nbody\n")
    with pytest.raises(JudgePromptError, match="line 1"):
        load_judge_prompt(p)
