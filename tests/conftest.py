"""
Shared pytest fixtures for EldritchDM tests.
"""

from __future__ import annotations

import pytest

from eldritch_dm.config import get_settings


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
