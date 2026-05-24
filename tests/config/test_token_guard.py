"""SAFETY-03 unit tests for require_token_or_exit (Phase 7 / TD-1 / D-33).

The helper is the single source of truth for the friendly missing-token
behavior. Both run.py and bot/__main__.py call it, so the unit-level
contract must be locked tight before either subprocess test runs.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from eldritch_dm.bootstrap import EXIT_MISSING_TOKEN as BOOTSTRAP_EXIT_MISSING_TOKEN
from eldritch_dm.config.token_guard import (
    EXIT_MISSING_TOKEN,
    require_token_or_exit,
)


def test_exit_code_constant_matches_bootstrap_namespace() -> None:
    """Local EXIT_MISSING_TOKEN must match the bootstrap-namespace value.

    The config layer cannot import from eldritch_dm.bootstrap (which would
    pull persistence into config and break the import-linter contract), so
    we mirror the constant locally. This test is the contract that keeps
    the two values in sync — bump both together or bump neither.
    """
    assert EXIT_MISSING_TOKEN == BOOTSTRAP_EXIT_MISSING_TOKEN


def _settings(token: str | None) -> SimpleNamespace:
    return SimpleNamespace(discord_token=token)


def test_returns_stripped_token_when_present() -> None:
    log = MagicMock()
    result = require_token_or_exit(_settings("  abc123  "), log)
    assert result == "abc123"
    log.error.assert_not_called()


def test_returns_token_unchanged_when_already_stripped() -> None:
    log = MagicMock()
    assert require_token_or_exit(_settings("plain"), log) == "plain"
    log.error.assert_not_called()


def test_none_token_returns_none_and_logs_error(
    capsys: pytest.CaptureFixture[str],
) -> None:
    log = MagicMock()
    result = require_token_or_exit(_settings(None), log)
    assert result is None
    # structured-log assertion
    log.error.assert_called_once()
    call_args = log.error.call_args
    assert call_args.args[0] == "missing_discord_token"
    assert call_args.kwargs["exit_code"] == EXIT_MISSING_TOKEN
    assert "Copy .env.example" in call_args.kwargs["hint"]
    # stderr message assertion
    captured = capsys.readouterr()
    assert "DISCORD_TOKEN is not set" in captured.err
    assert ".env.example" in captured.err


def test_empty_token_returns_none_and_logs_error(
    capsys: pytest.CaptureFixture[str],
) -> None:
    log = MagicMock()
    assert require_token_or_exit(_settings(""), log) is None
    log.error.assert_called_once()
    assert "DISCORD_TOKEN is not set" in capsys.readouterr().err


def test_whitespace_only_token_returns_none_and_logs_error(
    capsys: pytest.CaptureFixture[str],
) -> None:
    log = MagicMock()
    assert require_token_or_exit(_settings("   \t  "), log) is None
    log.error.assert_called_once()
    assert "DISCORD_TOKEN is not set" in capsys.readouterr().err


def test_helper_does_not_call_sys_exit() -> None:
    """Contract: helper returns None (caller chooses what to do) — no sys.exit."""
    log = MagicMock()
    # If the helper called sys.exit, this assertion would not run because the
    # SystemExit would propagate out of the test. Reaching the assertion is
    # itself the contract check.
    result = require_token_or_exit(_settings(None), log)
    assert result is None


def test_friendly_stderr_no_traceback_substring(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """SAFETY-03: stderr must not leak pydantic/discord internals."""
    log = MagicMock()
    require_token_or_exit(_settings(""), log)
    err = capsys.readouterr().err
    assert "Traceback" not in err
    assert "pydantic" not in err.lower()
    assert "LoginFailure" not in err
