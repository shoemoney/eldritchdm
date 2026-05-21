"""
Tests for eldritch_dm.logging — configure_logging and get_logger.
"""

from __future__ import annotations

import importlib
import io
import json
import subprocess
import sys

import pytest
import structlog

from eldritch_dm.logging import configure_logging, get_logger


def _reset_structlog() -> None:
    """Reset structlog configuration between tests."""
    structlog.reset_defaults()


class TestJsonFormat:
    """configure_logging(fmt='json') emits JSON events."""

    def test_json_output_contains_event_and_keys(self, capsys: pytest.CaptureFixture) -> None:
        _reset_structlog()
        configure_logging(level="DEBUG", fmt="json")
        log = get_logger("test.json")
        log.info("my_event", k="v", num=42)

        captured = capsys.readouterr()
        output = captured.err

        # Find a line that parses as JSON
        json_line = None
        for line in output.strip().splitlines():
            try:
                json_line = json.loads(line)
                break
            except json.JSONDecodeError:
                continue

        assert json_line is not None, f"No JSON line found in stderr:\n{output}"
        assert json_line.get("event") == "my_event"
        assert json_line.get("k") == "v"
        assert json_line.get("num") == 42
        _reset_structlog()


class TestConsoleFormat:
    """configure_logging(fmt='console') emits human-readable output."""

    def test_console_output_is_not_json(self, capsys: pytest.CaptureFixture) -> None:
        _reset_structlog()
        configure_logging(level="DEBUG", fmt="console")
        log = get_logger("test.console")
        log.info("console_event", detail="something")

        captured = capsys.readouterr()
        output = captured.err

        # Console output should contain the event name but NOT be valid JSON
        assert "console_event" in output
        # Try to parse as JSON — should fail for console output
        is_all_json = all(
            _is_json(line) for line in output.strip().splitlines() if line.strip()
        )
        assert not is_all_json, "Console format should not be all-JSON lines"
        _reset_structlog()


def _is_json(s: str) -> bool:
    try:
        json.loads(s)
        return True
    except (json.JSONDecodeError, ValueError):
        return False


class TestBoundContext:
    """Bound context variables appear in log events."""

    def test_bound_context_appears_in_event(self, capsys: pytest.CaptureFixture) -> None:
        _reset_structlog()
        configure_logging(level="DEBUG", fmt="json")

        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(channel_id="chan-test-456")

        log = get_logger("test.bound")
        log.info("context_event")

        captured = capsys.readouterr()
        output = captured.err

        json_line = None
        for line in output.strip().splitlines():
            try:
                parsed = json.loads(line)
                if parsed.get("event") == "context_event":
                    json_line = parsed
                    break
            except json.JSONDecodeError:
                continue

        assert json_line is not None
        assert json_line.get("channel_id") == "chan-test-456"

        structlog.contextvars.clear_contextvars()
        _reset_structlog()


class TestSecretScrubbing:
    """Secrets are redacted from log events."""

    def test_token_is_redacted(self, capsys: pytest.CaptureFixture) -> None:
        _reset_structlog()
        configure_logging(level="DEBUG", fmt="json")
        log = get_logger("test.secrets")
        log.info("auth_event", discord_token="super-secret-value", user="bob")

        captured = capsys.readouterr()
        output = captured.err

        assert "super-secret-value" not in output
        assert "***REDACTED***" in output
        _reset_structlog()


@pytest.mark.skipif(
    importlib.util.find_spec("importlinter") is None,
    reason="import-linter not installed",
)
class TestImportLinter:
    """import-linter contract passes on the skeleton."""

    def test_importlinter_passes(self) -> None:
        """Run lint-imports in a subprocess — exit 0 required.

        import-linter is invoked via its CLI (lint-imports), not -m importlinter,
        which does not have a __main__ entry point.
        """
        import shutil

        lint_imports_bin = shutil.which("lint-imports")
        if lint_imports_bin is None:
            # Fall back to finding it in the venv
            import pathlib

            venv_bin = pathlib.Path(sys.executable).parent / "lint-imports"
            lint_imports_bin = str(venv_bin) if venv_bin.exists() else "lint-imports"

        result = subprocess.run(
            [lint_imports_bin, "--config", "pyproject.toml"],
            capture_output=True,
            text=True,
            cwd="/Users/shoemoney/Services/DiscordDM",
        )
        assert result.returncode == 0, (
            f"import-linter failed:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
        )
