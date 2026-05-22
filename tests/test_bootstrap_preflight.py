"""
Tests for src/eldritch_dm/bootstrap.py — preflight + .env.example audit + pyproject.

Phase 5 Plan 03 Task 1.

Covers the 14 behaviors from the plan:
  Tests 1-8: preflight() exit codes and short-circuit ordering
  Tests 9-10: .env.example audit (MCP_RATE_LIMIT_MS added, OMLX_CACHE_STRATEGY resolved)
  Test 11: Settings default preservation
  Tests 12-14: pyproject.toml [project.scripts] + [project.urls] + pinned deps
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import tomllib
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
import pytest
import respx

PROJECT_ROOT = Path(__file__).resolve().parents[1]


# ──────────────────────────────────────────────────────────────────────────────
# Test 1: Re-export — `from eldritch_dm.bootstrap import bootstrap as ensure_schema`
# ──────────────────────────────────────────────────────────────────────────────
def test_bootstrap_reexport_works() -> None:
    """Legacy `from eldritch_dm.bootstrap import bootstrap` must still work."""
    from eldritch_dm.bootstrap import bootstrap as ensure_schema
    from eldritch_dm.persistence.bootstrap import bootstrap as persistence_bootstrap

    # Same callable object (re-export, not a copy)
    assert ensure_schema is persistence_bootstrap


# ──────────────────────────────────────────────────────────────────────────────
# Test 2: Named exit-code constants exist with correct values
# ──────────────────────────────────────────────────────────────────────────────
def test_exit_code_constants() -> None:
    from eldritch_dm.bootstrap import (
        EXIT_DM20_NOT_LOADED,
        EXIT_OK,
        EXIT_OMLX_UNREACHABLE,
        EXIT_SCHEMA_FAIL,
    )

    assert EXIT_OK == 0
    assert EXIT_OMLX_UNREACHABLE == 1
    assert EXIT_DM20_NOT_LOADED == 2
    assert EXIT_SCHEMA_FAIL == 3


# ──────────────────────────────────────────────────────────────────────────────
# Test 3: preflight() — all mocks green returns EXIT_OK
# ──────────────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_preflight_all_green(tmp_env: None) -> None:
    from eldritch_dm import bootstrap as bootstrap_mod
    from eldritch_dm.config import get_settings

    settings = get_settings()
    omlx_models_url = f"{str(settings.omlx_endpoint).rstrip('/')}/models"

    with respx.mock(assert_all_called=False) as respx_mock:
        respx_mock.get(omlx_models_url).mock(
            return_value=httpx.Response(
                200,
                json={"data": [{"id": "ShoeGPT"}]},
            )
        )
        respx_mock.get(str(settings.mcp_tools_url)).mock(
            return_value=httpx.Response(
                200,
                json=[{"name": "dm20__create_campaign"}],
            )
        )
        code = await bootstrap_mod.preflight()

    assert code == bootstrap_mod.EXIT_OK


# ──────────────────────────────────────────────────────────────────────────────
# Test 4: oMLX unreachable -> EXIT_OMLX_UNREACHABLE + stderr message with URL
# ──────────────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_preflight_omlx_unreachable(
    tmp_env: None, capsys: pytest.CaptureFixture[str]
) -> None:
    from eldritch_dm import bootstrap as bootstrap_mod
    from eldritch_dm.config import get_settings

    settings = get_settings()
    omlx_models_url = f"{str(settings.omlx_endpoint).rstrip('/')}/models"

    with respx.mock(assert_all_called=False) as respx_mock:
        respx_mock.get(omlx_models_url).mock(
            side_effect=httpx.ConnectError("connection refused")
        )
        code = await bootstrap_mod.preflight()

    captured = capsys.readouterr()
    assert code == bootstrap_mod.EXIT_OMLX_UNREACHABLE
    # Stderr message names the endpoint URL so operators can act on it.
    assert "oMLX" in captured.err
    assert str(settings.omlx_endpoint) in captured.err or omlx_models_url in captured.err


# ──────────────────────────────────────────────────────────────────────────────
# Test 5: oMLX up, but configured model missing -> WARN, still EXIT_OK
# ──────────────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_preflight_model_missing_is_soft_warning(tmp_env: None) -> None:
    from eldritch_dm import bootstrap as bootstrap_mod
    from eldritch_dm.config import get_settings

    settings = get_settings()
    omlx_models_url = f"{str(settings.omlx_endpoint).rstrip('/')}/models"

    with respx.mock(assert_all_called=False) as respx_mock:
        # Configured model is ShoeGPT; oMLX reports a different model loaded
        respx_mock.get(omlx_models_url).mock(
            return_value=httpx.Response(
                200,
                json={"data": [{"id": "SomeOtherModel"}]},
            )
        )
        respx_mock.get(str(settings.mcp_tools_url)).mock(
            return_value=httpx.Response(
                200,
                json=[{"name": "dm20__create_campaign"}],
            )
        )
        code = await bootstrap_mod.preflight()

    # Soft warning, not a fatal error (RESEARCH A5).
    assert code == bootstrap_mod.EXIT_OK


# ──────────────────────────────────────────────────────────────────────────────
# Test 6: MCP tools returns zero dm20__* -> EXIT_DM20_NOT_LOADED
# ──────────────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_preflight_dm20_not_loaded(tmp_env: None) -> None:
    from eldritch_dm import bootstrap as bootstrap_mod
    from eldritch_dm.config import get_settings

    settings = get_settings()
    omlx_models_url = f"{str(settings.omlx_endpoint).rstrip('/')}/models"

    with respx.mock(assert_all_called=False) as respx_mock:
        respx_mock.get(omlx_models_url).mock(
            return_value=httpx.Response(
                200,
                json={"data": [{"id": "ShoeGPT"}]},
            )
        )
        respx_mock.get(str(settings.mcp_tools_url)).mock(
            return_value=httpx.Response(
                200,
                # Tools list with no dm20__* entries (e.g. only fetch/dice loaded)
                json=[
                    {"name": "fetch__fetch"},
                    {"name": "dice__d20"},
                ],
            )
        )
        code = await bootstrap_mod.preflight()

    assert code == bootstrap_mod.EXIT_DM20_NOT_LOADED


# ──────────────────────────────────────────────────────────────────────────────
# Test 7: Schema bootstrap raises -> EXIT_SCHEMA_FAIL, short-circuits oMLX
# ──────────────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_preflight_schema_fail_short_circuits(tmp_env: None) -> None:
    from eldritch_dm import bootstrap as bootstrap_mod

    fake_bootstrap = AsyncMock(side_effect=RuntimeError("schema apply failed"))
    with patch("eldritch_dm.bootstrap.bootstrap", fake_bootstrap):
        # The httpx mock SHOULD NOT be called at all — schema fails first.
        with respx.mock(assert_all_called=False) as respx_mock:
            omlx_route = respx_mock.get("http://localhost:8765/v1/models").mock(
                return_value=httpx.Response(200, json={"data": []})
            )
            code = await bootstrap_mod.preflight()
            assert omlx_route.call_count == 0, "oMLX must not be queried when schema fails"

    assert code == bootstrap_mod.EXIT_SCHEMA_FAIL


# ──────────────────────────────────────────────────────────────────────────────
# Test 8: main() invokes asyncio.run(preflight()) and sys.exit(code)
# ──────────────────────────────────────────────────────────────────────────────
def test_main_calls_sys_exit_with_preflight_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from eldritch_dm import bootstrap as bootstrap_mod

    exit_codes_seen: list[int] = []

    def _fake_exit(code: int = 0) -> None:
        exit_codes_seen.append(code)

    async def _fake_preflight() -> int:
        return 42  # arbitrary distinct sentinel

    monkeypatch.setattr(bootstrap_mod.sys, "exit", _fake_exit)
    monkeypatch.setattr(bootstrap_mod, "preflight", _fake_preflight)

    # Avoid configure_logging side effects in CI
    monkeypatch.setattr(
        "eldritch_dm.logging.configure_logging", lambda **kwargs: None
    )

    bootstrap_mod.main()

    assert exit_codes_seen == [42]


# ──────────────────────────────────────────────────────────────────────────────
# Test 9: .env.example contains MCP_RATE_LIMIT_MS=200
# ──────────────────────────────────────────────────────────────────────────────
def test_env_example_has_mcp_rate_limit_ms() -> None:
    env_example = (PROJECT_ROOT / ".env.example").read_text(encoding="utf-8")

    # The setting line must exist with the documented default
    assert "MCP_RATE_LIMIT_MS=200" in env_example, (
        ".env.example must include MCP_RATE_LIMIT_MS=200 (was missing per RESEARCH Q9)"
    )
    # Must be tagged 🧪 (developer/advanced) per the .env.example legend
    # Find context around the line
    lines = env_example.splitlines()
    idx = next(
        i for i, line in enumerate(lines) if line.startswith("MCP_RATE_LIMIT_MS")
    )
    # Look at the 5 lines immediately preceding for the 🧪 tag
    preceding = "\n".join(lines[max(0, idx - 8) : idx])
    assert "🧪" in preceding, (
        "MCP_RATE_LIMIT_MS should be tagged 🧪 in its comment block"
    )
    # Must mention OPS-03 or rate-limit context
    assert ("OPS-03" in preceding) or ("rate" in preceding.lower()), (
        "MCP_RATE_LIMIT_MS comment must reference OPS-03 or rate-limit context"
    )


# ──────────────────────────────────────────────────────────────────────────────
# Test 10: .env.example resolves OMLX_CACHE_STRATEGY orphan
# Option (a) chosen: line REMOVED with explanatory comment.
# ──────────────────────────────────────────────────────────────────────────────
def test_env_example_resolves_omlx_cache_strategy_orphan() -> None:
    env_example = (PROJECT_ROOT / ".env.example").read_text(encoding="utf-8")

    # Option (a) was chosen: the OMLX_CACHE_STRATEGY assignment line must
    # NOT be present, OR (if present) a Settings field MUST back it.
    # We verify by checking that no assignment line exists.
    lines = [
        line for line in env_example.splitlines() if line.startswith("OMLX_CACHE_STRATEGY=")
    ]
    # The pre-Phase-5 .env.example had `# OMLX_CACHE_STRATEGY=` (commented out).
    # Removal means there are no live or commented OMLX_CACHE_STRATEGY assignments.
    commented_lines = [
        line for line in env_example.splitlines() if "OMLX_CACHE_STRATEGY=" in line
    ]
    assert len(lines) == 0, (
        "OMLX_CACHE_STRATEGY= active assignment must be removed (orphan; not in Settings)"
    )
    assert len(commented_lines) == 0, (
        "OMLX_CACHE_STRATEGY= even commented-out form must be removed to avoid resurrection"
    )
    # An explanatory comment block must exist for self-hosters who go looking.
    assert "oMLX cache strategy" in env_example or "cache strategy" in env_example.lower(), (
        ".env.example must include a short comment explaining oMLX cache "
        "strategy is server-side, not via this .env"
    )


# ──────────────────────────────────────────────────────────────────────────────
# Test 11: Settings default for mcp_rate_limit_ms is preserved (200)
# ──────────────────────────────────────────────────────────────────────────────
def test_settings_default_mcp_rate_limit_ms(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from eldritch_dm.config import Settings, get_settings

    # Strip env var if set in current shell, so we test pydantic-settings default
    monkeypatch.delenv("MCP_RATE_LIMIT_MS", raising=False)
    monkeypatch.setenv("DISCORD_TOKEN", "test-token")
    get_settings.cache_clear()

    s = Settings()
    assert s.mcp_rate_limit_ms == 200

    get_settings.cache_clear()


# ──────────────────────────────────────────────────────────────────────────────
# Test 12: pyproject.toml has [project.scripts] with eldritch-dm entry
# ──────────────────────────────────────────────────────────────────────────────
def test_pyproject_scripts_entry() -> None:
    pyproject = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text("utf-8"))

    scripts = pyproject["project"].get("scripts", {})
    assert "eldritch-dm" in scripts, (
        "pyproject.toml must declare [project.scripts] eldritch-dm = ... (D-23)"
    )
    assert scripts["eldritch-dm"] == "eldritch_dm.bot.__main__:main", (
        f"Expected eldritch-dm -> eldritch_dm.bot.__main__:main, got {scripts['eldritch-dm']!r}"
    )


# ──────────────────────────────────────────────────────────────────────────────
# Test 13: pyproject.toml has [project.urls] with Homepage/Repository/Issues
# ──────────────────────────────────────────────────────────────────────────────
def test_pyproject_urls() -> None:
    pyproject = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text("utf-8"))

    urls = pyproject["project"].get("urls", {})
    # Required keys per D-25; values may be placeholders with a TODO comment.
    for required_key in ("Homepage", "Repository", "Issues"):
        assert required_key in urls, (
            f"pyproject.toml [project.urls] must define {required_key} (D-25)"
        )
        assert urls[required_key].startswith("http"), (
            f"{required_key} URL must be a real URL placeholder, got {urls[required_key]!r}"
        )


# ──────────────────────────────────────────────────────────────────────────────
# Test 14: All deps in pyproject.toml are pinned (HOST-05)
# ──────────────────────────────────────────────────────────────────────────────
def test_pyproject_dependencies_pinned() -> None:
    pyproject = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text("utf-8"))
    deps: list[str] = pyproject["project"]["dependencies"]

    pin_operators = ("==", ">=", "~=", "<=", "<", ">")
    unpinned = [d for d in deps if not any(op in d for op in pin_operators)]
    assert not unpinned, f"Unpinned dependencies (HOST-05): {unpinned!r}"
