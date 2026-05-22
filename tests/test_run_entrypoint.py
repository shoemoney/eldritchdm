"""
Tests for run.py, launchd plist, systemd unit, install/uninstall scripts,
and the two troubleshooting docs.

Phase 5 Plan 03 Task 2.

Covers the 15 behaviors from the plan.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RUN_PY = PROJECT_ROOT / "run.py"
PLIST = PROJECT_ROOT / "docs" / "launchd.plist.example"
SYSTEMD = PROJECT_ROOT / "docs" / "eldritch-dm.service.example"
INSTALL_SH = PROJECT_ROOT / "scripts" / "install-launchd.sh"
UNINSTALL_SH = PROJECT_ROOT / "scripts" / "uninstall-launchd.sh"
DM20_DOC = PROJECT_ROOT / "docs" / "dm20-troubleshooting.md"
INGEST_DOC = PROJECT_ROOT / "docs" / "character-ingest-formats.md"


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────
def _load_run_module() -> object:
    """Import run.py freshly and return the module. Robust to repeated calls."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("run_entry", RUN_PY)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ──────────────────────────────────────────────────────────────────────────────
# Test 1: --check-only runs preflight and exits with preflight's code (0 on green)
# ──────────────────────────────────────────────────────────────────────────────
def test_run_check_only_returns_preflight_exit_code(
    tmp_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = _load_run_module()

    # Patch preflight on the imported eldritch_dm.bootstrap module *and* on
    # the alias used by run.py (which imports as `preflight_mod`).
    from eldritch_dm import bootstrap as bootstrap_mod

    async def _fake_preflight() -> int:
        return 0

    monkeypatch.setattr(bootstrap_mod, "preflight", _fake_preflight)

    code = run.main(["--check-only"])
    assert code == 0

    # Now make preflight return non-zero — main should bubble it up.
    async def _failing_preflight() -> int:
        return bootstrap_mod.EXIT_DM20_NOT_LOADED

    monkeypatch.setattr(bootstrap_mod, "preflight", _failing_preflight)
    code = run.main(["--check-only"])
    assert code == bootstrap_mod.EXIT_DM20_NOT_LOADED


# ──────────────────────────────────────────────────────────────────────────────
# Test 2: ELDRITCH_ALLOW_OFFLINE_START=1 skips preflight
# ──────────────────────────────────────────────────────────────────────────────
def test_run_offline_start_skips_preflight(
    tmp_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = _load_run_module()
    from eldritch_dm import bootstrap as bootstrap_mod
    from eldritch_dm.bot import bot as bot_mod

    preflight_calls: list[int] = []

    async def _spy_preflight() -> int:
        preflight_calls.append(1)
        return 0

    monkeypatch.setattr(bootstrap_mod, "preflight", _spy_preflight)
    monkeypatch.setenv("ELDRITCH_ALLOW_OFFLINE_START", "1")

    # Stub EldritchBot.run so we don't actually connect to Discord.
    bot_runs: list[str] = []

    class _FakeBot:
        def __init__(self, settings: object) -> None:
            self.settings = settings

        def run(self, token: str, **kwargs: object) -> None:
            bot_runs.append(token)

    monkeypatch.setattr(bot_mod, "EldritchBot", _FakeBot)

    # Prevent SIGTERM handler installation from leaking into the rest of
    # the pytest session — main() would otherwise override pytest's own
    # signal handling and cause downstream tests to hang on shutdown.
    monkeypatch.setattr(run, "_install_sigterm_handler", lambda: None)

    code = run.main([])
    assert code == 0
    assert preflight_calls == [], "preflight must be skipped when ELDRITCH_ALLOW_OFFLINE_START=1"
    assert bot_runs == ["test-token"], "bot.run should still be invoked"


# ──────────────────────────────────────────────────────────────────────────────
# Test 3: Missing DISCORD_TOKEN raises ValidationError; exit non-zero,
#         stderr names the missing field.
# ──────────────────────────────────────────────────────────────────────────────
def test_run_missing_discord_token_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Run in a subprocess so we get a real `Settings()` failure.
    env = os.environ.copy()
    env.pop("DISCORD_TOKEN", None)
    env["ELDRITCH_DB_PATH"] = str(tmp_path / "eldritch.sqlite3")
    # Run from an empty CWD so the project's .env file isn't auto-loaded
    # by pydantic-settings.
    workdir = tmp_path / "empty_cwd"
    workdir.mkdir(exist_ok=True)

    result = subprocess.run(
        [sys.executable, str(RUN_PY)],
        env=env,
        cwd=workdir,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode != 0
    # pydantic v2 ValidationError stringifies with "discord_token" in the message
    combined = result.stdout + result.stderr
    assert "discord_token" in combined.lower() or "DISCORD_TOKEN" in combined


# ──────────────────────────────────────────────────────────────────────────────
# Test 4: SIGTERM handler installed and raises KeyboardInterrupt
# ──────────────────────────────────────────────────────────────────────────────
def test_sigterm_handler_raises_keyboard_interrupt() -> None:
    run = _load_run_module()
    import signal as _signal

    # Capture the pre-test handler so we can restore it. This matters because
    # pytest runs in a single process; leaking our SIGTERM handler into the
    # rest of the test session would override pytest's own signal handling.
    previous_handler = _signal.getsignal(_signal.SIGTERM)
    try:
        # Install the handler manually (normally main() does this).
        run._install_sigterm_handler()

        handler = _signal.getsignal(_signal.SIGTERM)
        assert callable(handler), "SIGTERM must have a callable handler installed"
        assert handler is not previous_handler, "handler should have been replaced"

        with pytest.raises(KeyboardInterrupt):
            # Invoke the handler directly (cannot easily send SIGTERM to self
            # inside pytest without disrupting the runner).
            handler(_signal.SIGTERM, None)
    finally:
        # Restore the pre-test handler so subsequent tests / pytest hooks
        # are not affected by our installation.
        _signal.signal(_signal.SIGTERM, previous_handler)


# ──────────────────────────────────────────────────────────────────────────────
# Test 5: `import run` does not start the bot (no side effects)
# ──────────────────────────────────────────────────────────────────────────────
def test_importing_run_module_has_no_side_effects() -> None:
    # Run in a subprocess so we don't pollute test interpreter state.
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; sys.path.insert(0, '.'); import run; print('ok')",
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, (
        f"`import run` failed: stdout={result.stdout!r}, stderr={result.stderr!r}"
    )
    assert "ok" in result.stdout


# ──────────────────────────────────────────────────────────────────────────────
# Test 6: plutil -lint passes on docs/launchd.plist.example
# ──────────────────────────────────────────────────────────────────────────────
def test_plist_validates_with_plutil() -> None:
    if shutil.which("plutil") is None:
        pytest.skip("plutil not available (not macOS)")
    result = subprocess.run(
        ["plutil", "-lint", str(PLIST)],
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert result.returncode == 0, (
        f"plutil -lint failed: {result.stdout} {result.stderr}"
    )


# ──────────────────────────────────────────────────────────────────────────────
# Test 7: plist structure — label, ProgramArguments, KeepAlive dict, ThrottleInterval, RunAtLoad
# ──────────────────────────────────────────────────────────────────────────────
def test_plist_structure() -> None:
    # Parse as XML and pull the top-level <dict>
    tree = ET.parse(str(PLIST))
    root = tree.getroot()
    top = root.find("dict")
    assert top is not None

    # Helper: parse <key>k</key><value/> pairs into a dict (value can be
    # <string>, <true/>, <integer>, <dict>, <array>)
    def _to_dict(elem: ET.Element) -> dict[str, object]:
        out: dict[str, object] = {}
        children = list(elem)
        i = 0
        while i < len(children):
            child = children[i]
            if child.tag == "key" and i + 1 < len(children):
                key = child.text or ""
                value_elem = children[i + 1]
                if value_elem.tag == "string":
                    out[key] = value_elem.text or ""
                elif value_elem.tag == "true":
                    out[key] = True
                elif value_elem.tag == "false":
                    out[key] = False
                elif value_elem.tag == "integer":
                    out[key] = int(value_elem.text or 0)
                elif value_elem.tag == "dict":
                    out[key] = _to_dict(value_elem)
                elif value_elem.tag == "array":
                    out[key] = [
                        c.text for c in list(value_elem) if c.tag == "string"
                    ]
                i += 2
            else:
                i += 1
        return out

    d = _to_dict(top)
    assert d.get("Label") == "com.shoemoney.eldritch-dm"
    args = d.get("ProgramArguments")
    assert isinstance(args, list)
    assert any("run.py" in (s or "") for s in args)
    assert d.get("RunAtLoad") is True
    assert isinstance(d.get("KeepAlive"), dict)
    keep_alive = d["KeepAlive"]
    assert isinstance(keep_alive, dict)
    assert keep_alive.get("SuccessfulExit") is False
    assert d.get("ThrottleInterval") == 10


# ──────────────────────────────────────────────────────────────────────────────
# Test 8: EnvironmentVariables sets LOG_FORMAT=json AND DISCORD_TOKEN warning comment
# ──────────────────────────────────────────────────────────────────────────────
def test_plist_environment_and_comment() -> None:
    src = PLIST.read_text(encoding="utf-8")
    assert "<key>LOG_FORMAT</key>" in src
    assert "<string>json</string>" in src
    # Anti-pattern comment must be present — DISCORD_TOKEN warning.
    assert "DISCORD_TOKEN" in src, (
        "plist must include a comment warning about DISCORD_TOKEN secrets"
    )
    # Comment must be inside an XML comment block, not a key (i.e. never
    # as a real <key>DISCORD_TOKEN</key> — that would be the anti-pattern).
    assert "<key>DISCORD_TOKEN</key>" not in src, (
        "DISCORD_TOKEN must NOT be a real plist key — it's a comment-only warning"
    )
    # And the literal token must appear inside a comment block somewhere.
    comments = re.findall(r"<!--(.*?)-->", src, re.DOTALL)
    assert any("DISCORD_TOKEN" in c for c in comments), (
        "DISCORD_TOKEN warning text must appear inside an XML comment block"
    )


# ──────────────────────────────────────────────────────────────────────────────
# Test 9: ELDRITCH_ALLOW_OFFLINE_START with explanatory comment
# ──────────────────────────────────────────────────────────────────────────────
def test_plist_offline_start_documented() -> None:
    src = PLIST.read_text(encoding="utf-8")
    assert "ELDRITCH_ALLOW_OFFLINE_START" in src
    # A comment near it must mention the tradeoff.
    assert "circuit breaker" in src.lower() or "preflight" in src.lower()


# ──────────────────────────────────────────────────────────────────────────────
# Test 10: systemd unit exists and validates (where systemd-analyze is available)
# ──────────────────────────────────────────────────────────────────────────────
def test_systemd_unit_exists() -> None:
    assert SYSTEMD.exists()
    # Light syntactic check: contains the required sections.
    content = SYSTEMD.read_text(encoding="utf-8")
    assert "[Unit]" in content
    assert "[Service]" in content
    assert "[Install]" in content


# ──────────────────────────────────────────────────────────────────────────────
# Test 11: systemd unit fields — ExecStart, Restart=on-failure, etc.
# ──────────────────────────────────────────────────────────────────────────────
def test_systemd_unit_fields() -> None:
    content = SYSTEMD.read_text(encoding="utf-8")
    assert "ExecStart=/usr/bin/env python3" in content
    assert "Restart=on-failure" in content
    assert "RestartSec=10" in content
    assert 'Environment="LOG_FORMAT=json"' in content


# ──────────────────────────────────────────────────────────────────────────────
# Test 12: install-launchd.sh — shebang, set -euo pipefail, idempotent, DRY_RUN
# ──────────────────────────────────────────────────────────────────────────────
def test_install_launchd_script() -> None:
    assert INSTALL_SH.exists()
    assert os.access(INSTALL_SH, os.X_OK), "install-launchd.sh must be executable"
    content = INSTALL_SH.read_text(encoding="utf-8")
    assert content.startswith("#!/usr/bin/env bash")
    assert "set -euo pipefail" in content
    assert "launchctl bootout" in content  # idempotency
    assert "{PROJECT_DIR}" in content  # placeholder substitution
    assert "DRY_RUN" in content

    # DRY_RUN smoke test
    result = subprocess.run(
        ["bash", str(INSTALL_SH)],
        cwd=PROJECT_ROOT,
        env={**os.environ, "DRY_RUN": "1"},
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 0, (
        f"DRY_RUN install-launchd.sh failed: {result.stderr}"
    )
    assert "[DRY_RUN]" in result.stdout


# ──────────────────────────────────────────────────────────────────────────────
# Test 13: uninstall-launchd.sh — shebang, exit-clean on already-uninstalled
# ──────────────────────────────────────────────────────────────────────────────
def test_uninstall_launchd_script() -> None:
    assert UNINSTALL_SH.exists()
    assert os.access(UNINSTALL_SH, os.X_OK)
    content = UNINSTALL_SH.read_text(encoding="utf-8")
    assert content.startswith("#!/usr/bin/env bash")
    assert "launchctl bootout" in content
    # Syntax-only check (not actually running, since it would touch real launchd):
    result = subprocess.run(
        ["bash", "-n", str(UNINSTALL_SH)], capture_output=True, text=True
    )
    assert result.returncode == 0


# ──────────────────────────────────────────────────────────────────────────────
# Test 14: Troubleshooting docs exist and are substantive
# ──────────────────────────────────────────────────────────────────────────────
def test_troubleshooting_docs_substantive() -> None:
    assert DM20_DOC.exists()
    assert INGEST_DOC.exists()
    # Both files must be > 500 bytes
    assert DM20_DOC.stat().st_size > 500
    assert INGEST_DOC.stat().st_size > 500

    dm20_content = DM20_DOC.read_text(encoding="utf-8")
    # Covers the four common failures
    assert "oMLX" in dm20_content
    assert "dm20" in dm20_content.lower()
    assert "curl" in dm20_content  # diagnostic commands
    assert "/v1/mcp/tools" in dm20_content

    ingest_content = INGEST_DOC.read_text(encoding="utf-8")
    assert "D&D Beyond" in ingest_content or "dndbeyond" in ingest_content.lower()
    assert "PDF" in ingest_content
    assert "PNG" in ingest_content or "JPG" in ingest_content


# ──────────────────────────────────────────────────────────────────────────────
# Test 15: Both .md files have YAML frontmatter with title + audience
# ──────────────────────────────────────────────────────────────────────────────
def test_troubleshooting_docs_frontmatter() -> None:
    for doc in (DM20_DOC, INGEST_DOC):
        content = doc.read_text(encoding="utf-8")
        assert content.startswith("---\n"), (
            f"{doc.name} must start with YAML frontmatter delimiter"
        )
        # Extract the frontmatter block
        match = re.match(r"^---\n(.*?)\n---\n", content, re.DOTALL)
        assert match is not None, f"{doc.name} frontmatter not parseable"
        frontmatter = match.group(1)
        assert "title:" in frontmatter
        assert "audience: self-host" in frontmatter
