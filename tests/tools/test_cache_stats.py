"""CLI tests for eldritch-dm-cache-stats (Phase 18 / NARRCACHE-03)."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path

import pytest

from eldritch_dm.observability.span_buffer import BufferRow, init_buffer, reset_for_tests
from eldritch_dm.tools.cache_stats import (
    EXIT_OK,
    EXIT_USER_ERROR,
    _aggregate,
    main,
)


@pytest.fixture
def buffer_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    reset_for_tests()
    p = tmp_path / "spans.sqlite"
    monkeypatch.setenv("ELDRITCH_SPAN_BUFFER_PATH", str(p))
    yield p
    reset_for_tests()


def _extract_json_object(stdout: str) -> str:
    """Pull the JSON object out of stdout that may also contain structlog lines.

    The CLI emits JSON via ``print(...)``; structlog console output from
    ``span_buffer.initialized`` etc. ends up here too in test contexts.
    Find the first ``{`` and match braces forward.
    """
    match = re.search(r"\{[\s\S]*\}\s*$", stdout)
    if match is None:
        raise AssertionError(f"no JSON object found in stdout: {stdout!r}")
    return match.group(0)


def _row(layer: str, *, savings: float | None = None) -> BufferRow:
    return BufferRow(
        timestamp_utc=datetime.now(UTC),
        span_name="eldritch.narrcache.call",
        model="ShoeGPT",
        driver_path=layer,
        latency_ms=5,
        tokens_input=0 if layer == "hit" else 120,
        tokens_output=0 if layer == "hit" else 80,
        overall_score=savings,
    )


def _seed(path: Path, rows: list[BufferRow]) -> None:
    buf = init_buffer(path=path)
    for r in rows:
        buf.record(r)
    buf.flush(timeout_s=1.0)


def test_aggregate_empty() -> None:
    stats = _aggregate([])
    assert stats["total_calls"] == 0
    assert stats["hit_rate"] == 0.0
    assert stats["total_savings_usd"] == 0.0


def test_aggregate_typical_mix() -> None:
    rows = [
        _row("hit", savings=0.0001),
        _row("hit", savings=0.0002),
        _row("miss"),
        _row("miss"),
        _row("bypass"),
        _row("gate_reject_store"),
        _row("gate_reject_serve"),
    ]
    stats = _aggregate(rows)
    assert stats["total_calls"] == 7
    assert stats["hits"] == 2
    assert stats["misses"] == 2
    assert stats["bypass"] == 1
    assert stats["rejected_by_gate"] == 2
    assert stats["rejected_by_gate_store"] == 1
    assert stats["rejected_by_gate_serve"] == 1
    # hit_rate = 2 / (2+2) = 0.5
    assert stats["hit_rate"] == 0.5
    assert stats["total_savings_usd"] == pytest.approx(0.0003)


def test_missing_scope_returns_user_error(
    capsys: pytest.CaptureFixture[str], buffer_path: Path
) -> None:
    code = main([])
    assert code == EXIT_USER_ERROR
    assert "scope" in capsys.readouterr().err.lower()


def test_bad_since_returns_user_error(
    capsys: pytest.CaptureFixture[str], buffer_path: Path
) -> None:
    code = main(["--narration", "--since", "not-a-date"])
    assert code == EXIT_USER_ERROR
    assert "invalid date" in capsys.readouterr().err.lower()


def test_markdown_output_smoke(capsys: pytest.CaptureFixture[str], buffer_path: Path) -> None:
    _seed(buffer_path, [_row("hit", savings=0.0005), _row("miss"), _row("bypass")])
    code = main(["--narration", "--buffer-path", str(buffer_path)])
    assert code == EXIT_OK
    out = capsys.readouterr().out
    assert "Narration cache statistics" in out
    assert "hit_rate" in out
    assert "total_savings_usd" in out


def test_json_output_is_valid_json(capsys: pytest.CaptureFixture[str], buffer_path: Path) -> None:
    _seed(buffer_path, [_row("hit", savings=0.0007), _row("miss"), _row("miss")])
    code = main(["--narration", "--format", "json", "--buffer-path", str(buffer_path)])
    assert code == EXIT_OK
    out = capsys.readouterr().out
    payload = json.loads(_extract_json_object(out))
    assert payload["scope"] == "narration"
    assert payload["hits"] == 1
    assert payload["misses"] == 2
    assert payload["hit_rate"] == pytest.approx(1 / 3, abs=1e-6)
    assert payload["total_savings_usd"] == pytest.approx(0.0007)


def test_since_until_clamps_window(capsys: pytest.CaptureFixture[str], buffer_path: Path) -> None:
    _seed(buffer_path, [_row("hit", savings=0.001)])
    # since = far future → window contains no rows
    code = main(
        [
            "--narration",
            "--since",
            "2099-01-01",
            "--until",
            "2099-01-02",
            "--format",
            "json",
            "--buffer-path",
            str(buffer_path),
        ]
    )
    assert code == EXIT_OK
    payload = json.loads(_extract_json_object(capsys.readouterr().out))
    assert payload["total_calls"] == 0
