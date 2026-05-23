"""Tests for D-27 multi-backend ingest LLM support.

Covers:
  - The default ingest backend is omlx.
  - resolve_ingest_config returns the right (endpoint, model, api_key)
    for each backend (omlx, ollama, openrouter).
  - INGEST_ENDPOINT overrides win over the backend default.
  - INGEST_MODEL_OVERRIDE wins over OMLX_INGEST_MODEL and OMLX_MODEL.
  - openrouter without OPENROUTER_API_KEY raises ValueError.
  - __repr__ redacts OPENROUTER_API_KEY.
  - IngestCog._get_openai_client() end-to-end wiring against each backend.

Test environment isolation follows the same monkeypatch pattern used in
tests/test_config.py — each test clears the get_settings cache and unsets
any leftover env vars so backend selection cannot leak between cases.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest

from eldritch_dm.config import IngestConfig, Settings, get_settings

if TYPE_CHECKING:
    pass


# ── Shared helper ──────────────────────────────────────────────────────────────


def _make_settings(monkeypatch: pytest.MonkeyPatch, **env: str) -> Settings:
    """Build a fresh Settings instance with only the supplied env overrides.

    Clears get_settings cache and forces ``_env_file=None`` so a developer's
    real .env file cannot bleed into the test (D-27).
    """
    get_settings.cache_clear()
    # Clear anything that might already be set in the runner's env.
    for key in (
        "INGEST_BACKEND",
        "INGEST_ENDPOINT",
        "INGEST_MODEL_OVERRIDE",
        "OPENROUTER_API_KEY",
        "OMLX_INGEST_MODEL",
        "OMLX_MODEL",
        "OMLX_ENDPOINT",
        "DISCORD_TOKEN",
    ):
        monkeypatch.delenv(key, raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    return Settings(_env_file=None)  # type: ignore[call-arg]


# ── Default backend (D-27) ─────────────────────────────────────────────────────


def test_default_backend_is_omlx(monkeypatch: pytest.MonkeyPatch) -> None:
    """D-27 — INGEST_BACKEND defaults to ``omlx`` so existing self-hosters
    are not silently repointed when they upgrade.
    """
    settings = _make_settings(monkeypatch)
    assert settings.ingest_backend == "omlx"
    cfg = settings.resolve_ingest_config()
    assert isinstance(cfg, IngestConfig)


# ── Per-backend resolution (D-27) ──────────────────────────────────────────────


def test_resolve_omlx_uses_omlx_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    """D-27 — omlx backend pulls endpoint from OMLX_ENDPOINT and uses
    the local-backend sentinel api_key.
    """
    settings = _make_settings(
        monkeypatch,
        INGEST_BACKEND="omlx",
        OMLX_ENDPOINT="http://localhost:8765/v1",
        OMLX_MODEL="ShoeGPT",
    )
    cfg = settings.resolve_ingest_config()
    assert cfg.endpoint == "http://localhost:8765/v1"
    assert cfg.model == "ShoeGPT"
    assert cfg.api_key == "not-needed"


def test_resolve_ollama_uses_ollama_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """D-27 — ollama backend uses ``http://localhost:11434/v1`` by default
    and keeps the local-backend sentinel api_key. OMLX_MODEL still flows
    through as the model fallback (operator can override via INGEST_MODEL_OVERRIDE).
    """
    settings = _make_settings(
        monkeypatch,
        INGEST_BACKEND="ollama",
        OMLX_MODEL="ShoeGPT",
    )
    cfg = settings.resolve_ingest_config()
    assert cfg.endpoint == "http://localhost:11434/v1"
    assert cfg.api_key == "not-needed"
    assert cfg.model == "ShoeGPT"


def test_resolve_openrouter_uses_openrouter_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """D-27 — openrouter backend uses ``https://openrouter.ai/api/v1`` by
    default and passes through ``OPENROUTER_API_KEY`` verbatim.
    """
    settings = _make_settings(
        monkeypatch,
        INGEST_BACKEND="openrouter",
        OPENROUTER_API_KEY="sk-or-v1-test-key-12345",
        OMLX_MODEL="ShoeGPT",
    )
    cfg = settings.resolve_ingest_config()
    assert cfg.endpoint == "https://openrouter.ai/api/v1"
    assert cfg.api_key == "sk-or-v1-test-key-12345"
    # OMLX_MODEL flows through as the fallback when no INGEST_MODEL_OVERRIDE set.
    assert cfg.model == "ShoeGPT"


# ── API key enforcement (D-27) ─────────────────────────────────────────────────


def test_openrouter_without_api_key_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """D-27 — picking openrouter without OPENROUTER_API_KEY is an operator
    config error, not a silent fallback. resolve_ingest_config raises
    ValueError pointing at .env.example and the openrouter.ai/keys page.
    """
    settings = _make_settings(
        monkeypatch,
        INGEST_BACKEND="openrouter",
    )
    with pytest.raises(ValueError, match="OPENROUTER_API_KEY"):
        settings.resolve_ingest_config()


def test_openrouter_with_empty_api_key_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """D-27 — empty-string OPENROUTER_API_KEY is treated as missing.
    Self-hosters who paste a blank key get a clear error, not a 401 mid-ingest.
    """
    settings = _make_settings(
        monkeypatch,
        INGEST_BACKEND="openrouter",
        OPENROUTER_API_KEY="",
    )
    with pytest.raises(ValueError, match="OPENROUTER_API_KEY"):
        settings.resolve_ingest_config()


# ── Override precedence (D-27) ────────────────────────────────────────────────


def test_ingest_endpoint_override_wins_over_backend_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """D-27 — INGEST_ENDPOINT overrides the per-backend default URL.
    Useful for: Ollama on a non-default port, or a third-party
    OpenAI-compatible proxy.
    """
    settings = _make_settings(
        monkeypatch,
        INGEST_BACKEND="ollama",
        INGEST_ENDPOINT="http://localhost:12345/v1",
        OMLX_MODEL="ShoeGPT",
    )
    cfg = settings.resolve_ingest_config()
    # Override wins over ollama's 11434 default.
    assert cfg.endpoint == "http://localhost:12345/v1"


def test_ingest_endpoint_override_also_wins_for_openrouter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """D-27 — same override semantics for openrouter (e.g. when fronting it
    through a CDN or reverse proxy).
    """
    settings = _make_settings(
        monkeypatch,
        INGEST_BACKEND="openrouter",
        INGEST_ENDPOINT="https://openrouter.example.com/v1",
        OPENROUTER_API_KEY="sk-or-v1-test",
    )
    cfg = settings.resolve_ingest_config()
    assert cfg.endpoint == "https://openrouter.example.com/v1"
    assert cfg.api_key == "sk-or-v1-test"


def test_ingest_model_override_wins_over_omlx_model(monkeypatch: pytest.MonkeyPatch) -> None:
    """D-27 — INGEST_MODEL_OVERRIDE wins over OMLX_INGEST_MODEL, which
    wins over OMLX_MODEL. Verifies the full three-tier precedence chain.
    """
    # All three set — INGEST_MODEL_OVERRIDE must win.
    settings = _make_settings(
        monkeypatch,
        INGEST_BACKEND="openrouter",
        OPENROUTER_API_KEY="sk-or-v1-test",
        INGEST_MODEL_OVERRIDE="anthropic/claude-3.5-sonnet",
        OMLX_INGEST_MODEL="ShoeGPT-ingest",
        OMLX_MODEL="ShoeGPT",
    )
    cfg = settings.resolve_ingest_config()
    assert cfg.model == "anthropic/claude-3.5-sonnet"

    # No override, but OMLX_INGEST_MODEL set — that wins over OMLX_MODEL.
    settings = _make_settings(
        monkeypatch,
        INGEST_BACKEND="omlx",
        OMLX_INGEST_MODEL="ShoeGPT-ingest",
        OMLX_MODEL="ShoeGPT",
    )
    cfg = settings.resolve_ingest_config()
    assert cfg.model == "ShoeGPT-ingest"

    # Neither override set — OMLX_MODEL is the final fallback.
    settings = _make_settings(
        monkeypatch,
        INGEST_BACKEND="omlx",
        OMLX_MODEL="ShoeGPT",
    )
    cfg = settings.resolve_ingest_config()
    assert cfg.model == "ShoeGPT"


# ── Secret redaction (D-27) ────────────────────────────────────────────────────


def test_repr_redacts_openrouter_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """D-27 — ``Settings.__repr__`` must never leak OPENROUTER_API_KEY into
    logs, tracebacks, or debug dumps. Same redaction rule as DISCORD_TOKEN.
    """
    settings = _make_settings(
        monkeypatch,
        INGEST_BACKEND="openrouter",
        OPENROUTER_API_KEY="sk-or-v1-SECRETSHOULDNOTAPPEAR",
    )
    text = repr(settings)
    assert "sk-or-v1-SECRETSHOULDNOTAPPEAR" not in text
    assert "REDACTED" in text
    # Backend name is fine to surface — that's not a secret.
    assert "openrouter" in text


def test_repr_shows_none_when_no_openrouter_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """D-27 — when OPENROUTER_API_KEY is unset, ``__repr__`` shows ``None``
    rather than ``***REDACTED***`` (so operators can tell at a glance that
    the key is missing vs hidden).
    """
    settings = _make_settings(
        monkeypatch,
        INGEST_BACKEND="omlx",
    )
    text = repr(settings)
    assert "openrouter_api_key=None" in text


# ── End-to-end IngestCog wiring (D-27) ─────────────────────────────────────────


def _make_cog_with_settings(settings: Settings) -> object:
    """Build a minimal IngestCog with a real Settings instance plugged in.

    Bypasses Discord — we only want to exercise _get_openai_client and
    _get_ingest_model. Returns the cog instance (typed as object since
    the IngestCog import is deferred to avoid pulling discord.py into
    test_ingest_backend's import path needlessly).
    """
    from eldritch_dm.bot.cogs.ingest import IngestCog

    bot = MagicMock()
    # The cog short-circuits if bot.openai_client is set — make sure it isn't,
    # so resolve_ingest_config is what drives the construction.
    bot.openai_client = None
    bot.settings = settings
    return IngestCog(bot)


def test_get_openai_client_wires_omlx_endpoint_and_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """D-27 end-to-end — INGEST_BACKEND=omlx produces an AsyncOpenAI client
    whose base_url is the oMLX endpoint and api_key is the local sentinel.
    """
    settings = _make_settings(
        monkeypatch,
        INGEST_BACKEND="omlx",
        OMLX_ENDPOINT="http://localhost:8765/v1",
        OMLX_MODEL="ShoeGPT",
    )
    cog = _make_cog_with_settings(settings)
    client = cog._get_openai_client()  # type: ignore[attr-defined]
    assert str(client.base_url).rstrip("/") == "http://localhost:8765/v1"
    # AsyncOpenAI exposes the api_key as .api_key
    assert client.api_key == "not-needed"
    # Model resolution
    assert cog._get_ingest_model() == "ShoeGPT"  # type: ignore[attr-defined]


def test_get_openai_client_wires_ollama_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    """D-27 end-to-end — INGEST_BACKEND=ollama produces a client pointed at
    Ollama's default 11434 port with the local sentinel api_key.
    """
    settings = _make_settings(
        monkeypatch,
        INGEST_BACKEND="ollama",
        OMLX_MODEL="ShoeGPT",
        INGEST_MODEL_OVERRIDE="llama3.1:8b-instruct",
    )
    cog = _make_cog_with_settings(settings)
    client = cog._get_openai_client()  # type: ignore[attr-defined]
    assert str(client.base_url).rstrip("/") == "http://localhost:11434/v1"
    assert client.api_key == "not-needed"
    assert cog._get_ingest_model() == "llama3.1:8b-instruct"  # type: ignore[attr-defined]


def test_get_openai_client_wires_openrouter(monkeypatch: pytest.MonkeyPatch) -> None:
    """D-27 end-to-end — INGEST_BACKEND=openrouter produces a client with
    the cloud base_url and the real api_key in the Authorization header.
    """
    settings = _make_settings(
        monkeypatch,
        INGEST_BACKEND="openrouter",
        OPENROUTER_API_KEY="sk-or-v1-test-12345",
        OMLX_MODEL="ShoeGPT",
        INGEST_MODEL_OVERRIDE="anthropic/claude-3.5-sonnet",
    )
    cog = _make_cog_with_settings(settings)
    client = cog._get_openai_client()  # type: ignore[attr-defined]
    assert str(client.base_url).rstrip("/") == "https://openrouter.ai/api/v1"
    assert client.api_key == "sk-or-v1-test-12345"
    assert cog._get_ingest_model() == "anthropic/claude-3.5-sonnet"  # type: ignore[attr-defined]


def test_get_openai_client_openrouter_without_key_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """D-27 end-to-end — operator picks openrouter but forgot the api_key.
    The cog surfaces the ValueError from resolve_ingest_config rather than
    silently constructing a client that would later 401.
    """
    settings = _make_settings(
        monkeypatch,
        INGEST_BACKEND="openrouter",
    )
    cog = _make_cog_with_settings(settings)
    with pytest.raises(ValueError, match="OPENROUTER_API_KEY"):
        cog._get_openai_client()  # type: ignore[attr-defined]


def test_preset_openai_client_short_circuits_resolution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """D-27 — if a test (or some future runtime path) pre-sets
    ``bot.openai_client``, the cog must return it verbatim without
    going through Settings. This preserves the existing test injection
    pattern used in tests/bot/cogs/test_ingest.py.
    """
    settings = _make_settings(
        monkeypatch,
        INGEST_BACKEND="openrouter",  # would normally need an api_key
    )
    from eldritch_dm.bot.cogs.ingest import IngestCog

    sentinel = object()
    bot = MagicMock()
    bot.openai_client = sentinel
    bot.settings = settings
    cog = IngestCog(bot)
    # No ValueError despite the missing api_key — bot.openai_client wins.
    assert cog._get_openai_client() is sentinel  # type: ignore[comparison-overlap]
