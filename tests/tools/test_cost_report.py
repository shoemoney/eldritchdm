"""Tests for the eldritch-dm-cost-report CLI (Phase 13 / MON-03)."""

from __future__ import annotations

import io
import json
from contextlib import redirect_stdout
from datetime import UTC, datetime, timedelta

import pytest

from eldritch_dm.observability.span_buffer import (
    BufferRow,
    init_buffer,
    reset_for_tests,
)
from eldritch_dm.tools.cost_report import main


@pytest.fixture(autouse=True)
def _isolate(monkeypatch, tmp_path):
    monkeypatch.setenv("ELDRITCH_SPAN_BUFFER_PATH", str(tmp_path / "spans.sqlite"))
    monkeypatch.delenv("ELDRITCH_DAILY_LLM_BUDGET_USD", raising=False)
    reset_for_tests()
    yield
    reset_for_tests()


def _seed_translate_row(model: str, tin: int, tout: int):
    buf = init_buffer()
    buf.record(
        BufferRow(
            span_name="eldritch.ingest.translate",
            channel_id="c1",
            model=model,
            latency_ms=100,
            tokens_input=tin,
            tokens_output=tout,
            timestamp_utc=datetime.now(UTC),
        )
    )
    buf.flush(timeout_s=3.0)


def _run(argv: list[str]) -> tuple[int, str]:
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = main(argv)
    return rc, buf.getvalue()


def _extract_json(blob: str) -> dict:
    """Parse the JSON object from a stdout blob that may contain log lines."""
    # The CLI's JSON output is a single multi-line JSON object — find the
    # opening '{' that starts a fresh line, then parse from there.
    lines = blob.splitlines()
    json_start = None
    for i, line in enumerate(lines):
        if line.strip().startswith("{"):
            json_start = i
            break
    if json_start is None:
        raise ValueError(f"no JSON object found in stdout:\n{blob}")
    return json.loads("\n".join(lines[json_start:]))


def test_help_lists_all_flags(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--help"])
    assert exc.value.code == 0
    out = capsys.readouterr().out
    for flag in (
        "--since",
        "--until",
        "--by-model",
        "--by-channel",
        "--format",
        "--budget",
        "--buffer-path",
        "--pricing-path",
    ):
        assert flag in out


def test_empty_buffer_markdown_format():
    rc, out = _run(["--format", "markdown"])
    assert rc == 0
    assert "# EldritchDM Cost Report" in out
    assert "Total spend:" in out
    assert "Over budget:" in out
    assert "no" in out  # under budget


def test_empty_buffer_json_format():
    rc, out = _run(["--format", "json"])
    assert rc == 0
    data = _extract_json(out)
    # Total is a Decimal-stringified zero; could be "0" or "0.000000" depending
    # on whether any rows were aggregated. Accept any zero spelling.
    from decimal import Decimal as _D
    assert _D(data["total_usd"]) == _D(0)
    assert data["over_budget"] is False
    assert data["sample_size"] == 0


def test_spending_appears_in_markdown_by_model():
    _seed_translate_row("gpt-4o", 1_000_000, 0)  # = $2.50
    rc, out = _run(["--format", "markdown"])
    assert rc == 0
    assert "## By model" in out
    assert "gpt-4o" in out


def test_over_budget_flagged():
    _seed_translate_row("gpt-4o", 10_000_000, 0)  # $25
    rc, out = _run(["--format", "json", "--budget", "5.00"])
    # Exit code 0 because no unknown models (only EXIT_PARTIAL on unknowns)
    assert rc == 0
    data = _extract_json(out)
    assert data["over_budget"] is True


def test_unknown_model_returns_exit_2():
    _seed_translate_row("model-not-in-pricing", 1000, 500)
    rc, out = _run(["--format", "json"])
    # Unknown model present → EXIT_PARTIAL
    assert rc == 2
    data = _extract_json(out)
    assert data["unknown_model_count"] == 1


def test_by_channel_flag_includes_section():
    _seed_translate_row("gpt-4o", 100, 0)
    rc, out = _run(["--format", "markdown", "--by-channel"])
    assert rc == 0
    assert "## By channel" in out
    assert "c1" in out


def test_invalid_since_returns_user_error():
    with pytest.raises(SystemExit) as exc:
        main(["--since", "not-a-date"])
    assert exc.value.code == 1


def test_invalid_budget_returns_user_error():
    with pytest.raises(SystemExit) as exc:
        main(["--budget", "not-a-number"])
    assert exc.value.code == 1


def test_budget_env_var_picked_up(monkeypatch):
    monkeypatch.setenv("ELDRITCH_DAILY_LLM_BUDGET_USD", "0.10")
    _seed_translate_row("gpt-4o", 1_000_000, 0)  # $2.50 vs $0.10 cap
    rc, out = _run(["--format", "json"])
    assert rc == 0
    data = _extract_json(out)
    assert data["budget_usd"] == "0.10"
    assert data["over_budget"] is True


def test_since_until_window(monkeypatch):
    """The CLI scans all UTC dates in the [since, until) window."""
    rc, out = _run(
        [
            "--since",
            (datetime.now(UTC) - timedelta(hours=1)).isoformat(),
            "--until",
            datetime.now(UTC).isoformat(),
            "--format",
            "json",
        ]
    )
    assert rc == 0
    data = _extract_json(out)
    assert "since" in data and "until" in data
