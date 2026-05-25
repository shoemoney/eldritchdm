"""CLI tests for eldritch-dm-cache-disable (Phase 18 / NARRCACHE-03)."""

from __future__ import annotations

import pytest

from eldritch_dm.observability.narrcache_runtime import get_narrcache_override
from eldritch_dm.tools.cache_disable import EXIT_OK, EXIT_USER_ERROR, build_parser, main


@pytest.fixture(autouse=True)
def _reset_override() -> None:
    ov = get_narrcache_override()
    ov.reset_for_tests()
    yield
    ov.reset_for_tests()


def test_disable_narration_flips_override(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["--narration"])
    assert code == EXIT_OK
    assert get_narrcache_override().is_disabled() is True
    out = capsys.readouterr().out
    assert "narration cache: DISABLED" in out


def test_enable_narration_flips_back(capsys: pytest.CaptureFixture[str]) -> None:
    get_narrcache_override().disable(reason="pre-test")
    code = main(["--narration", "--enable"])
    assert code == EXIT_OK
    assert get_narrcache_override().is_disabled() is False
    out = capsys.readouterr().out
    assert "narration cache: ENABLED" in out


def test_missing_scope_returns_user_error(capsys: pytest.CaptureFixture[str]) -> None:
    code = main([])
    assert code == EXIT_USER_ERROR
    err = capsys.readouterr().err
    assert "scope" in err.lower()


def test_reason_is_logged_and_visible_in_output(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["--narration", "--reason", "rolling_canary"])
    assert code == EXIT_OK
    out = capsys.readouterr().out
    assert "rolling_canary" in out
    assert get_narrcache_override().snapshot().reason == "rolling_canary"


def test_parser_help_smoke() -> None:
    parser = build_parser()
    assert parser.prog == "eldritch-dm-cache-disable"
    # argparse exits with SystemExit(0) on --help; we just smoke parse_args.
    args = parser.parse_args(["--narration", "--enable"])
    assert args.narration is True
    assert args.enable is True
