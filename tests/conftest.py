"""
Shared pytest fixtures for EldritchDM tests.
"""

from __future__ import annotations

import logging

import pytest
import structlog

from eldritch_dm.config import get_settings


@pytest.fixture(autouse=True)
def _reset_logging_state_after_each_test():
    """Phase 14 / FLAKE-02 root-cause fix.

    Several entry-point tests (``tests/persistence/test_bootstrap.py``,
    ``tests/test_run_entrypoint.py``) invoke functions that call
    ``eldritch_dm.logging.configure_logging`` — which:

    1. Calls ``logging.basicConfig(..., force=True, handlers=[
       StreamHandler(sys.stderr)])``. ``force=True`` replaces root handlers
       in place, **capturing the current per-test ``sys.stderr``** that
       pytest's ``capsys`` is intercepting at that moment.
    2. Calls ``structlog.configure(cache_logger_on_first_use=True, ...)`` —
       module-level state that persists across tests.

    Without resetting, the next test that uses ``capsys`` to assert on a
    structlog event misses it: the cached logger still writes to the prior
    test's now-defunct capture buffer.

    This autouse fixture runs ``structlog.reset_defaults()`` and clears
    stdlib root handlers after every test, so each test starts from
    structlog's compile-time defaults. Tests that legitimately need a
    persistent log config across their own steps can re-call
    ``configure_logging`` inside the test — the cleanup happens after
    teardown, not before.
    """
    yield
    structlog.reset_defaults()
    root = logging.getLogger()
    for h in list(root.handlers):
        root.removeHandler(h)


@pytest.fixture
def tmp_env(monkeypatch: pytest.MonkeyPatch, tmp_path: pytest.TempPathFactory) -> None:
    """Set minimal required env vars and clear the settings cache.

    Sets:
        DISCORD_TOKEN = "test-token"
        ELDRITCH_DB_PATH = <tmp_path>/eldritch.sqlite3

    Clears get_settings() cache before AND after yielding, so each test
    gets a clean Settings instance and does not pollute later tests.
    """
    get_settings.cache_clear()
    monkeypatch.setenv("DISCORD_TOKEN", "test-token")
    monkeypatch.setenv("ELDRITCH_DB_PATH", str(tmp_path / "eldritch.sqlite3"))
    # Clear any leftover vars that could interfere
    monkeypatch.delenv("DISCORD_APPLICATION_ID", raising=False)
    monkeypatch.delenv("DISCORD_GUILD_IDS", raising=False)
    yield
    get_settings.cache_clear()


@pytest.fixture
def frozen_settings(tmp_env: None) -> object:
    """Return a fresh Settings instance after tmp_env is applied."""
    return get_settings()
