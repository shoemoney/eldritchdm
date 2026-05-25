"""
EldritchDM configuration.

Loads every environment variable the bot needs via pydantic-settings.
Shell environment wins over .env file content (standard convention).
Single Settings instance per process — obtain via get_settings().

IMPORTANT: This module must NOT import eldritch_dm.persistence,
           eldritch_dm.mcp, or eldritch_dm.safety (import-linter enforced).
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import AnyHttpUrl, Field, NonNegativeInt, PositiveFloat, PositiveInt
from pydantic_settings import BaseSettings, SettingsConfigDict

# ── Backend defaults (D-27) ───────────────────────────────────────────────────
# Centralized so .env.example, Settings, and tests stay in sync.
_OLLAMA_DEFAULT_ENDPOINT: str = "http://localhost:11434/v1"
_OPENROUTER_DEFAULT_ENDPOINT: str = "https://openrouter.ai/api/v1"
# Local backends advertise no auth; the OpenAI client still wants a non-empty
# string, so we send a sentinel that is obviously not a real key.
_LOCAL_BACKEND_API_KEY: str = "not-needed"


@dataclass(frozen=True, slots=True)
class IngestConfig:
    """Resolved endpoint + model + api_key for the ingest LLM (D-27).

    Produced by ``Settings.resolve_ingest_config()``. Centralizes the
    backend-selection logic so cog code, tests, and docs all agree.

    Attributes:
        endpoint: Full OpenAI-compatible base URL (e.g. ``http://localhost:8765/v1``).
        model:    Model id to send in ``chat.completions.create(model=...)``.
                  For OpenRouter, this is a full slug like ``anthropic/claude-3.5-sonnet``.
        api_key:  Auth token. ``"not-needed"`` for local backends (omlx, ollama);
                  the real ``OPENROUTER_API_KEY`` for openrouter.
    """

    endpoint: str
    model: str
    api_key: str


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
        populate_by_name=True,
    )

    # ── Discord ──────────────────────────────────────────────────────────────
    # discord_token is Optional so preflight (`python -m eldritch_dm.bootstrap`,
    # `python run.py --check-only`) can validate oMLX / dm20 / SQLite WITHOUT
    # a token in env. The token is required only by code paths that actually
    # contact Discord — `run.py` main() and `eldritch_dm.bot.__main__` validate
    # it at the moment they're about to call `bot.run(...)`. See Phase 5
    # Plan 03 fix: preflight-requires-token (D-26).
    discord_token: str | None = None
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

    # ── Ingest LLM backend (D-27) ─────────────────────────────────────────────
    # Three backends supported for the character-sheet schema translator
    # (the ONLY direct LLM call site in this codebase — dm20 owns narration
    # internally and is not affected by this choice). All three speak the
    # OpenAI-compatible Chat Completions API.
    #
    # - "omlx"       → http://localhost:8765/v1 (default; same server hosts dm20 MCP)
    # - "ollama"     → http://localhost:11434/v1 (alternative local backend)
    # - "openrouter" → https://openrouter.ai/api/v1 (cloud — requires API key)
    #
    # IMPORTANT: dm20 MCP (the rules engine) is always at the oMLX endpoint
    # (omlx_endpoint + /mcp/execute). Switching the ingest backend to ollama
    # or openrouter does NOT move dm20 — it still needs oMLX running locally.
    ingest_backend: Literal["omlx", "ollama", "openrouter"] = "omlx"

    # Override the ingest endpoint independently of omlx_endpoint. If unset,
    # the default is derived from `ingest_backend`:
    #   omlx       → omlx_endpoint
    #   ollama     → http://localhost:11434/v1
    #   openrouter → https://openrouter.ai/api/v1
    ingest_endpoint: AnyHttpUrl | None = None

    # Model id sent to the ingest backend. If unset, falls back to
    # `omlx_ingest_model`, then `omlx_model`. For OpenRouter, this should be
    # a full route like "anthropic/claude-3.5-sonnet" or
    # "meta-llama/llama-3.1-70b-instruct".
    ingest_model_override: str | None = None

    # Required for openrouter backend. Looks like `sk-or-v1-...`. Get one at
    # https://openrouter.ai/keys.
    openrouter_api_key: str | None = None

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

    # ── Homebrew Riposte Eligibility (Phase 8 / HOMEBREW-01 / D-29 / D-39) ────
    # Override path for the Riposte eligibility YAML. When unset, the loader
    # walks per-install (~/.eldritch/eligibility.yaml) then the in-repo default
    # (database/eligibility.yaml). See gameplay.eligibility_loader.load_eligibility.
    eligibility_yaml_path: Path | None = Field(
        default=None,
        alias="ELDRITCH_ELIGIBILITY_YAML",
        description=(
            "Override path for Riposte eligibility YAML (D-29 tier-1). "
            "When unset, loader walks per-install (~/.eldritch/eligibility.yaml) "
            "then in-repo default (database/eligibility.yaml)."
        ),
    )

    # ── Phase 10 Smart MonsterDriver (D-52) ───────────────────────────────────
    # MONSTER_DRIVER controls which driver the orchestrator constructs:
    #   "smart"  → LLM-routed targeting (default; Phase 10)
    #   "random" → v1.0 escape hatch (pure random)
    #   "mixed"  → SmartMonsterDriver; per-monster INT-gating handles mixing
    # Unknown values fall back to "smart" with a structured warning.
    monster_driver: Literal["smart", "random", "mixed"] = Field(
        default="smart",
        alias="MONSTER_DRIVER",
        description=(
            "Phase 10 driver mode: 'smart' (LLM-routed; default), 'random' "
            "(v1.0 escape hatch), or 'mixed' (smart with internal INT-gating)."
        ),
    )

    # ── Phase 16 MCP cache (MCPCACHE-01/02/03) ────────────────────────────────
    # L1 = in-process OrderedDict LRU. Safe-by-default (TTL clears stale data).
    # L2 = aiosqlite WAL at MCPCACHE_L2_PATH. Opt-in (adds disk write cost).
    # Allow-list of cacheable tools is hard-coded in eldritch_dm.mcp.cache —
    # mutations and mutable-state reads are NEVER cacheable (D-117).
    mcpcache_enabled: bool = Field(default=True, alias="MCPCACHE_ENABLED")
    mcpcache_l1_size: PositiveInt = Field(default=512, alias="MCPCACHE_L1_SIZE")
    mcpcache_l1_ttl_s: PositiveInt = Field(default=300, alias="MCPCACHE_L1_TTL_S")
    mcpcache_l2_enabled: bool = Field(default=False, alias="MCPCACHE_L2_ENABLED")
    mcpcache_l2_ttl_s: PositiveInt = Field(default=86400, alias="MCPCACHE_L2_TTL_S")
    mcpcache_l2_path: str = Field(
        default="~/.eldritch/mcp_cache.sqlite",
        alias="MCPCACHE_L2_PATH",
        description="L2 SQLite cache file path; '~' is expanded at use site.",
    )

    # ── Phase 17 character cache (CHARCACHE-01/02/03) ─────────────────────────
    # Standalone cache (D-119) at ~/.eldritch/character_cache.sqlite.
    # Static-fields-only snapshots (D-125) — combat-mutable state never cached.
    # TTL short-circuit (D-123): inside TTL, get_or_fetch skips the dm20 call.
    charcache_enabled: bool = Field(default=True, alias="CHARCACHE_ENABLED")
    charcache_path: str = Field(
        default="~/.eldritch/character_cache.sqlite",
        alias="CHARCACHE_PATH",
        description="Character snapshot cache SQLite file; '~' expanded at use.",
    )
    charcache_ttl_s: PositiveInt = Field(default=3600, alias="CHARCACHE_TTL_S")

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

    # ── Ingest backend resolution (D-27) ──────────────────────────────────────
    def resolve_ingest_config(self) -> IngestConfig:
        """Return the resolved (endpoint, model, api_key) for the ingest LLM.

        Centralizes the backend-selection logic so all callers agree. The
        ingest pipeline is the ONLY direct LLM call site in this codebase
        (dm20 owns narration internally), so this is the only knob that
        ever needs to change to repoint LLM inference.

        Resolution rules:
          * endpoint = ``ingest_endpoint`` if set, else the backend default:
              - omlx       → ``omlx_endpoint``
              - ollama     → http://localhost:11434/v1
              - openrouter → https://openrouter.ai/api/v1
          * model = ``ingest_model_override`` → ``omlx_ingest_model`` → ``omlx_model``.
          * api_key = ``openrouter_api_key`` for openrouter, ``"not-needed"`` otherwise.

        Returns:
            IngestConfig dataclass with all three fields populated.

        Raises:
            ValueError: ``ingest_backend == "openrouter"`` but ``openrouter_api_key``
                is unset. Self-hosters: set ``OPENROUTER_API_KEY`` in .env (see
                .env.example) — get a key at https://openrouter.ai/keys.
        """
        # ── api_key + endpoint default selection ─────────────────────────────
        if self.ingest_backend == "openrouter":
            if not self.openrouter_api_key:
                raise ValueError(
                    "INGEST_BACKEND=openrouter requires OPENROUTER_API_KEY to be set "
                    "(see .env.example). Get a key at https://openrouter.ai/keys."
                )
            api_key = self.openrouter_api_key
            default_endpoint = _OPENROUTER_DEFAULT_ENDPOINT
        elif self.ingest_backend == "ollama":
            api_key = _LOCAL_BACKEND_API_KEY
            default_endpoint = _OLLAMA_DEFAULT_ENDPOINT
        else:  # omlx
            api_key = _LOCAL_BACKEND_API_KEY
            default_endpoint = str(self.omlx_endpoint)

        # ── endpoint override wins over backend default ──────────────────────
        endpoint = str(self.ingest_endpoint) if self.ingest_endpoint else default_endpoint

        # ── model: explicit override → omlx_ingest_model → omlx_model ────────
        model = self.ingest_model_override or self.omlx_ingest_model or self.omlx_model

        return IngestConfig(endpoint=endpoint, model=model, api_key=api_key)

    def __repr__(self) -> str:
        """Redact discord_token and other secrets (including OPENROUTER_API_KEY) from repr."""
        openrouter_key_repr = "***REDACTED***" if self.openrouter_api_key else "None"
        return (
            f"Settings("
            f"discord_token=***REDACTED***, "
            f"omlx_endpoint={self.omlx_endpoint!r}, "
            f"ingest_backend={self.ingest_backend!r}, "
            f"openrouter_api_key={openrouter_key_repr}, "
            f"eldritch_db_path={self.eldritch_db_path!r}, "
            f"log_format={self.log_format!r}"
            f")"
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the singleton Settings instance. Thread-safe due to GIL + lru_cache."""
    return Settings()
