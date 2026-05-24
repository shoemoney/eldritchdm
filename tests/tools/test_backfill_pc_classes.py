"""Tests for eldritch_dm.tools.backfill_pc_classes (Phase 9 / TD-3).

Test categories (D-49):
  - argparse + module-shape smoke (T-09-01-01)
  - dm20 fetch loop with respx-mocked MCP (T-09-01-02)
  - dry-run no-write, --force re-process, idempotency (T-09-01-03)
"""

from __future__ import annotations

import pytest

from eldritch_dm.tools import backfill_pc_classes as backfill

# ── T-09-01-01: scaffold smoke tests ─────────────────────────────────────────


def test_module_importable() -> None:
    """Plain import should work; no side-effects allowed."""
    assert hasattr(backfill, "main")
    assert hasattr(backfill, "build_parser")
    assert backfill.EXIT_OK == 0
    assert backfill.EXIT_USER_ERROR == 1
    assert backfill.EXIT_PARTIAL == 2
    assert backfill.EXIT_FATAL == 3


def test_help_exits_zero(capsys: pytest.CaptureFixture[str]) -> None:
    """argparse --help should exit cleanly with code 0."""
    with pytest.raises(SystemExit) as exc_info:
        backfill.main(["--help"])
    assert exc_info.value.code == 0
    out = capsys.readouterr().out
    assert "eldritch-dm-backfill-pc-classes" in out
    assert "--dry-run" in out
    assert "--force" in out


def test_dry_run_and_force_flags_parse() -> None:
    parser = backfill.build_parser()
    args = parser.parse_args([])
    assert args.dry_run is False
    assert args.force is False

    args = parser.parse_args(["--dry-run", "--force"])
    assert args.dry_run is True
    assert args.force is True


def test_dm20_url_resolution_cli_wins(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DM20_MCP_URL", "http://from-env:9999")
    monkeypatch.setenv("OMLX_ENDPOINT", "http://from-omlx:8765/v1")
    assert (
        backfill.resolve_dm20_url("http://from-cli:1234")
        == "http://from-cli:1234"
    )


def test_dm20_url_resolution_env_dm20(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DM20_MCP_URL", "http://from-env:9999/")
    monkeypatch.delenv("OMLX_ENDPOINT", raising=False)
    assert backfill.resolve_dm20_url(None) == "http://from-env:9999"


def test_dm20_url_resolution_omlx_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DM20_MCP_URL", raising=False)
    monkeypatch.setenv("OMLX_ENDPOINT", "http://omlx-host:8765/v1")
    assert backfill.resolve_dm20_url(None) == "http://omlx-host:8765"


def test_dm20_url_resolution_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DM20_MCP_URL", raising=False)
    monkeypatch.delenv("OMLX_ENDPOINT", raising=False)
    assert backfill.resolve_dm20_url(None) == "http://localhost:8765"
