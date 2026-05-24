"""SAFETY-03 subprocess E2E test (Phase 7 / TD-1 closure).

Asserts ``python -m eldritch_dm.bot`` with no DISCORD_TOKEN exits with
code 4 (EXIT_MISSING_TOKEN) and emits the same friendly stderr message
that ``run.py`` emits — no discord.errors.LoginFailure traceback, no
pydantic ValidationError. Mirrors the run.py-side test at
``tests/test_run_entrypoint.py::test_run_missing_discord_token_fails``.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_main_missing_discord_token_exits_4(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """python -m eldritch_dm.bot with DISCORD_TOKEN unset must exit 4."""
    from eldritch_dm.bootstrap import EXIT_MISSING_TOKEN

    env = os.environ.copy()
    env.pop("DISCORD_TOKEN", None)
    env["ELDRITCH_DB_PATH"] = str(tmp_path / "eldritch.sqlite3")
    # PYTHONPATH so `python -m eldritch_dm.bot` finds the source tree even
    # when CWD is outside the project.
    src = str(PROJECT_ROOT / "src")
    existing_pp = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = src + (os.pathsep + existing_pp if existing_pp else "")
    # Run from an empty CWD so the project's .env file isn't auto-loaded by
    # pydantic-settings (otherwise the operator's real DISCORD_TOKEN leaks in).
    workdir = tmp_path / "empty_cwd"
    workdir.mkdir(exist_ok=True)

    result = subprocess.run(
        [sys.executable, "-m", "eldritch_dm.bot"],
        env=env,
        cwd=workdir,
        capture_output=True,
        text=True,
        timeout=20,
    )
    combined = result.stdout + result.stderr

    assert result.returncode == EXIT_MISSING_TOKEN, (
        f"expected exit code {EXIT_MISSING_TOKEN} (EXIT_MISSING_TOKEN), "
        f"got {result.returncode}. Combined output:\n{combined}"
    )
    # Friendly stderr must mention DISCORD_TOKEN and point at .env.example —
    # parity with run.py's behavior.
    assert "DISCORD_TOKEN" in combined, (
        f"stderr must mention DISCORD_TOKEN. Got:\n{combined}"
    )
    assert ".env" in combined, (
        f"stderr must point self-hosters at .env / .env.example. Got:\n{combined}"
    )
    # No discord.py login traceback (the WHOLE POINT of SAFETY-03).
    assert "Traceback" not in combined, (
        f"a Python traceback leaked to the operator. SAFETY-03 demands a "
        f"friendly error instead. Combined output:\n{combined}"
    )
    assert "LoginFailure" not in combined, (
        f"discord.errors.LoginFailure must not appear; SAFETY-03 short-circuits "
        f"BEFORE bot.run is called. Got:\n{combined}"
    )
    assert "pydantic" not in combined.lower(), (
        f"pydantic internals must not appear in operator-facing output. Got:\n{combined}"
    )


def test_imports_still_work_after_config_package_migration() -> None:
    """Smoke: config.py → config/ package migration kept import-compat."""
    # Both import paths must continue to work — pre-Phase-7 callers used these.
    from eldritch_dm.config import Settings, get_settings  # noqa: F401
    from eldritch_dm.config.token_guard import require_token_or_exit  # noqa: F401
