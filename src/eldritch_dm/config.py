"""
EldritchDM configuration.

Loads every environment variable the bot needs via pydantic-settings.
Shell environment wins over .env file content (standard convention).
Single Settings instance per process — obtain via get_settings().

IMPORTANT: This module must NOT import eldritch_dm.persistence,
           eldritch_dm.mcp, or eldritch_dm.safety (import-linter enforced).
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import AnyHttpUrl, NonNegativeInt, PositiveFloat, PositiveInt
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All configuration for EldritchDM, loaded from env / .env file.

    Shell environment takes precedence over .env file (pydantic-settings default).
    See .env.example for documentation of each field.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
    )

    # ── Discord ──────────────────────────────────────────────────────────────
    discord_token: str
    discord_application_id: int | None = None
    # CSV of guild IDs; use `guild_ids_list` property to parse
    discord_guild_ids: str = ""

    # ── oMLX / MCP ───────────────────────────────────────────────────────────
    omlx_endpoint: AnyHttpUrl = AnyHttpUrl("http://localhost:8765/v1")
    omlx_model: str = "ShoeGPT"
    mcp_execute_url: AnyHttpUrl = AnyHttpUrl("http://localhost:8765/v1/mcp/execute")
    mcp_tools_url: AnyHttpUrl = AnyHttpUrl("http://localhost:8765/v1/mcp/tools")
    omlx_health_interval: PositiveInt = 60
    omlx_circuit_breaker_threshold: PositiveInt = 3
    omlx_ingest_model: str | None = None

    # ── SQLite persistence ────────────────────────────────────────────────────
    eldritch_db_path: str = "./eldritch.sqlite3"
    eldritch_db_busy_timeout_ms: PositiveInt = 5000
    eldritch_db_checkpoint_interval: NonNegativeInt = 600

    # ── Logging ───────────────────────────────────────────────────────────────
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    log_format: Literal["json", "console"] = "console"
    log_file: str | None = None

    # ── Gameplay knobs ────────────────────────────────────────────────────────
    riposte_ttl_seconds: PositiveInt = 8
    embed_edit_rate_limit: PositiveFloat = 1.0
    max_modal_input_chars: PositiveInt = 500
    explore_batch_window_seconds: PositiveInt = 30

    # ── dm20 Party Mode ───────────────────────────────────────────────────────
    party_mode_port: PositiveInt = 8080
    party_poll_interval_ms: PositiveInt = 250
    # MCP rate limit: minimum ms between mutating MCP calls per channel (OPS-03)
    mcp_rate_limit_ms: PositiveInt = 200

    # ── Dev / test ────────────────────────────────────────────────────────────
    run_stress: bool = False
    sanitizer_verbose_audit: bool = False

    # ── Properties ────────────────────────────────────────────────────────────
    @property
    def guild_ids_list(self) -> list[int]:
        """Parse DISCORD_GUILD_IDS CSV into a list of ints. Empty string → []."""
        if not self.discord_guild_ids.strip():
            return []
        return [int(gid.strip()) for gid in self.discord_guild_ids.split(",") if gid.strip()]

    def __repr__(self) -> str:
        """Redact discord_token and other secrets from repr."""
        return (
            f"Settings("
            f"discord_token=***REDACTED***, "
            f"omlx_endpoint={self.omlx_endpoint!r}, "
            f"eldritch_db_path={self.eldritch_db_path!r}, "
            f"log_format={self.log_format!r}"
            f")"
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the singleton Settings instance. Thread-safe due to GIL + lru_cache."""
    return Settings()
