"""
Tests for eldritch_dm.config — Settings class and get_settings().
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from eldritch_dm.config import Settings, get_settings


class TestDefaultsLoad:
    """When only DISCORD_TOKEN is set, all defaults are as expected."""

    def test_defaults_load(self, tmp_env: None) -> None:
        settings = get_settings()
        assert settings.discord_token == "test-token"
        assert settings.omlx_health_interval == 60
        assert settings.omlx_circuit_breaker_threshold == 3
        assert settings.max_modal_input_chars == 500
        assert settings.eldritch_db_path.endswith("eldritch.sqlite3")
        assert settings.log_format == "console"
        assert settings.log_level == "INFO"
        assert settings.riposte_ttl_seconds == 8

    def test_guild_ids_list_empty(self, tmp_env: None) -> None:
        settings = get_settings()
        assert settings.guild_ids_list == []


class TestMissingToken:
    """Missing DISCORD_TOKEN does NOT raise (D-26).

    discord_token is Optional[str] = None in Settings so preflight
    (`python -m eldritch_dm.bootstrap`, `run.py --check-only`) can validate
    oMLX / dm20 / SQLite without a token. Token enforcement lives at the
    bot-launch boundary in `run.py` and `eldritch_dm.bot.__main__`.
    """

    def test_missing_discord_token_yields_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        get_settings.cache_clear()
        monkeypatch.delenv("DISCORD_TOKEN", raising=False)
        # Ensure no .env file with a token is picked up — override env_file
        settings = Settings(_env_file=None)  # type: ignore[call-arg]
        assert settings.discord_token is None
        # Other defaults still load — preflight needs them.
        assert settings.eldritch_db_path.endswith("eldritch.sqlite3")
        assert str(settings.omlx_endpoint).startswith("http://localhost:8765")
        get_settings.cache_clear()

    def test_blank_discord_token_yields_blank(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Empty-string DISCORD_TOKEN (operator pasted nothing) still
        validates at the Settings layer; bot-launch boundary handles it.
        """
        get_settings.cache_clear()
        monkeypatch.setenv("DISCORD_TOKEN", "")
        settings = Settings(_env_file=None)  # type: ignore[call-arg]
        # Empty string is preserved as-is; run.py's strip-then-truthy check
        # treats it as missing.
        assert settings.discord_token == ""
        get_settings.cache_clear()

    def test_malformed_other_field_still_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Removing token-required-ness does not weaken validation on
        OTHER fields. A bogus DISCORD_APPLICATION_ID still raises.
        """
        get_settings.cache_clear()
        monkeypatch.delenv("DISCORD_TOKEN", raising=False)
        monkeypatch.setenv("DISCORD_APPLICATION_ID", "not-an-int")
        with pytest.raises(ValidationError, match="discord_application_id"):
            Settings(_env_file=None)  # type: ignore[call-arg]
        get_settings.cache_clear()


class TestShellEnvWins:
    """Shell environment variable wins over .env file content."""

    def test_shell_env_wins_over_dotenv(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: pytest.TempPathFactory
    ) -> None:
        """Write a .env file with one value; set a different value in shell env."""
        get_settings.cache_clear()

        env_file = tmp_path / ".env"
        env_file.write_text("DISCORD_TOKEN=from-dotenv-file\n")

        # Shell env takes priority (pydantic-settings default)
        monkeypatch.setenv("DISCORD_TOKEN", "from-shell-env")

        settings = Settings(_env_file=str(env_file))  # type: ignore[call-arg]
        assert settings.discord_token == "from-shell-env"
        get_settings.cache_clear()


class TestGuildIdsParsing:
    """guild_ids_list parses CSV correctly."""

    def test_guild_ids_csv(self, monkeypatch: pytest.MonkeyPatch) -> None:
        get_settings.cache_clear()
        monkeypatch.setenv("DISCORD_TOKEN", "t")
        monkeypatch.setenv("DISCORD_GUILD_IDS", "111,222,333")
        settings = get_settings()
        assert settings.guild_ids_list == [111, 222, 333]
        get_settings.cache_clear()

    def test_guild_ids_single(self, monkeypatch: pytest.MonkeyPatch) -> None:
        get_settings.cache_clear()
        monkeypatch.setenv("DISCORD_TOKEN", "t")
        monkeypatch.setenv("DISCORD_GUILD_IDS", "  999  ")
        settings = get_settings()
        assert settings.guild_ids_list == [999]
        get_settings.cache_clear()


class TestFrozen:
    """Settings instance is frozen — attribute assignment raises."""

    def test_frozen_raises(self, tmp_env: None) -> None:
        settings = get_settings()
        with pytest.raises((ValidationError, TypeError)):
            settings.log_level = "DEBUG"  # type: ignore[misc]


class TestMcpCacheDefaults:
    """Phase 16 MCPCACHE_* settings — defaults and overrides."""

    def test_mcpcache_defaults(self, tmp_env: None) -> None:
        settings = get_settings()
        assert settings.mcpcache_enabled is True
        assert settings.mcpcache_l1_size == 512
        assert settings.mcpcache_l1_ttl_s == 300
        assert settings.mcpcache_l2_enabled is False
        assert settings.mcpcache_l2_ttl_s == 86400
        assert settings.mcpcache_l2_path == "~/.eldritch/mcp_cache.sqlite"

    def test_mcpcache_env_overrides(self, monkeypatch: pytest.MonkeyPatch) -> None:
        get_settings.cache_clear()
        monkeypatch.setenv("DISCORD_TOKEN", "t")
        monkeypatch.setenv("MCPCACHE_ENABLED", "false")
        monkeypatch.setenv("MCPCACHE_L1_SIZE", "16")
        monkeypatch.setenv("MCPCACHE_L1_TTL_S", "5")
        monkeypatch.setenv("MCPCACHE_L2_ENABLED", "true")
        monkeypatch.setenv("MCPCACHE_L2_TTL_S", "7")
        monkeypatch.setenv("MCPCACHE_L2_PATH", "/tmp/cache.sqlite")
        settings = Settings(_env_file=None)  # type: ignore[call-arg]
        assert settings.mcpcache_enabled is False
        assert settings.mcpcache_l1_size == 16
        assert settings.mcpcache_l1_ttl_s == 5
        assert settings.mcpcache_l2_enabled is True
        assert settings.mcpcache_l2_ttl_s == 7
        assert settings.mcpcache_l2_path == "/tmp/cache.sqlite"
        get_settings.cache_clear()
