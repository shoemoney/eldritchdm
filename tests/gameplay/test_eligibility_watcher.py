"""Tests for EligibilityFileWatcher (Phase 22 / OPQOL-01).

Covers the hot-reload watcher's 8 behaviors:
  1. initial load captures baseline mtime (no spurious reload on first poll)
  2. no mtime change → no reload
  3. mtime change → reload + on_reload callback fired
  4. bad YAML on reload → keep last-known-good (loader fallback detected)
  5. file vanishes → no crash, last-known-good preserved
  6. start/stop idempotent
  7. no resolvable path → watcher constructs + start/stop work, polls are no-op
  8. on_reload callback errors swallowed

`poll_once()` is the deterministic test seam — keeps most tests synchronous.
"""

from __future__ import annotations

import asyncio
import os
import time
from pathlib import Path

import pytest

from eldritch_dm.config import Settings
from eldritch_dm.gameplay.eligibility_loader import (
    DEFAULT_ELIGIBILITY,
    EligibilityFileWatcher,
)


def _settings_with(path: Path) -> Settings:
    return Settings(eligibility_yaml_path=path)


def _settings_no_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Settings:
    """Build settings with NO discoverable eligibility file.

    Point HOME at an empty tmp dir (so the per-install tier misses) and let
    the in-repo tier be whatever the repo provides — for the no-path test we
    can't easily remove the in-repo file, so this helper is used only when
    the test explicitly constructs a watcher whose `_path` we then patch.
    """
    monkeypatch.setenv("HOME", str(tmp_path))
    return Settings()


def _write_valid_yaml(path: Path, *, subclass: str = "swashbuckler") -> None:
    path.write_text(
        f"version: 1\nmode: extend\neligible:\n  rogue:\n    - {subclass}\n",
        encoding="utf-8",
    )


def _bump_mtime(path: Path) -> None:
    """Force mtime forward by >=1s to defeat coarse-resolution filesystems."""
    future = time.time() + 10.0
    os.utime(path, (future, future))


# ── 1: initial load captures baseline ───────────────────────────────────────


def test_watcher_initial_load_captures_baseline(tmp_path: Path) -> None:
    path = tmp_path / "eligibility.yaml"
    _write_valid_yaml(path)
    initial = frozenset(DEFAULT_ELIGIBILITY | {("rogue", "swashbuckler")})
    w = EligibilityFileWatcher(
        _settings_with(path), initial_set=initial, poll_interval_s=60.0
    )
    # First poll right after construction — mtime unchanged since init.
    assert w.poll_once() is False
    assert w.current == initial


# ── 2: no mtime change → no reload ──────────────────────────────────────────


def test_watcher_no_change_no_reload(tmp_path: Path) -> None:
    path = tmp_path / "eligibility.yaml"
    _write_valid_yaml(path)
    w = EligibilityFileWatcher(_settings_with(path))
    # Multiple polls without touching the file
    assert w.poll_once() is False
    assert w.poll_once() is False
    assert w.poll_once() is False


# ── 3: mtime change triggers reload + on_reload ─────────────────────────────


def test_watcher_mtime_change_triggers_reload(tmp_path: Path) -> None:
    path = tmp_path / "eligibility.yaml"
    _write_valid_yaml(path, subclass="swashbuckler")
    reload_calls: list[frozenset[tuple[str, str]]] = []

    w = EligibilityFileWatcher(
        _settings_with(path),
        on_reload=reload_calls.append,
    )
    # Overwrite with a different subclass + bump mtime
    _write_valid_yaml(path, subclass="thief")
    _bump_mtime(path)

    assert w.poll_once() is True
    assert ("rogue", "thief") in w.current
    assert ("rogue", "swashbuckler") not in w.current
    assert len(reload_calls) == 1
    assert reload_calls[0] == w.current


# ── 4: bad YAML on reload → keep last-known-good ─────────────────────────────


def test_watcher_bad_yaml_preserves_last_known_good(tmp_path: Path) -> None:
    path = tmp_path / "eligibility.yaml"
    _write_valid_yaml(path, subclass="swashbuckler")
    # Seed initial_set to NON-DEFAULT so loader-fallback heuristic fires.
    good_set = frozenset(DEFAULT_ELIGIBILITY | {("rogue", "swashbuckler")})
    reload_calls: list = []
    w = EligibilityFileWatcher(
        _settings_with(path),
        initial_set=good_set,
        on_reload=reload_calls.append,
    )
    # Stomp the file with malformed YAML and bump mtime.
    path.write_text(":\n  - not: [valid: yaml :\n", encoding="utf-8")
    _bump_mtime(path)

    assert w.poll_once() is False  # reload treated as failed (kept LKG)
    assert w.current == good_set
    assert reload_calls == []  # callback NOT invoked


# ── 5: file vanishes → no crash, LKG preserved ──────────────────────────────


def test_watcher_file_vanishes_keeps_last_known_good(tmp_path: Path) -> None:
    path = tmp_path / "eligibility.yaml"
    _write_valid_yaml(path)
    good_set = frozenset(DEFAULT_ELIGIBILITY | {("rogue", "swashbuckler")})
    w = EligibilityFileWatcher(_settings_with(path), initial_set=good_set)
    path.unlink()
    # No crash; logs `watcher_file_missing` once; current preserved.
    assert w.poll_once() is False
    assert w.poll_once() is False  # second time should not re-log nor crash
    assert w.current == good_set


# ── 6: start/stop idempotent ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_watcher_start_stop_idempotent(tmp_path: Path) -> None:
    path = tmp_path / "eligibility.yaml"
    _write_valid_yaml(path)
    w = EligibilityFileWatcher(_settings_with(path), poll_interval_s=0.05)
    await w.start()
    task1 = w._task
    await w.start()  # second start — must not create a new task
    assert w._task is task1
    await w.stop()
    await w.stop()  # second stop — no-op
    assert w._task is None


# ── 7: no resolvable path → watcher no-ops cleanly ──────────────────────────


def test_watcher_no_path_at_init_noops(monkeypatch: pytest.MonkeyPatch) -> None:
    s = Settings(eligibility_yaml_path=Path("/nonexistent/path/eligibility.yaml"))
    w = EligibilityFileWatcher(s)
    # _resolve_path may fall through to the in-repo default which exists in
    # the worktree. Patch _path to None to simulate the no-path tier-miss.
    w._path = None
    assert w.poll_once() is False
    assert w.poll_once() is False  # logged-once flag works
    assert w.current == DEFAULT_ELIGIBILITY


# ── 8: on_reload callback errors are swallowed ──────────────────────────────


def test_watcher_on_reload_callback_errors_swallowed(tmp_path: Path) -> None:
    path = tmp_path / "eligibility.yaml"
    _write_valid_yaml(path, subclass="swashbuckler")

    def _boom(_set: frozenset[tuple[str, str]]) -> None:
        raise ValueError("intentional test failure")

    w = EligibilityFileWatcher(_settings_with(path), on_reload=_boom)
    _write_valid_yaml(path, subclass="thief")
    _bump_mtime(path)

    # poll_once still returns True; no exception escapes.
    assert w.poll_once() is True
    assert ("rogue", "thief") in w.current


# ── 9: background loop actually invokes poll_once ───────────────────────────


@pytest.mark.asyncio
async def test_watcher_background_loop_reloads(tmp_path: Path) -> None:
    """End-to-end sanity check: start the watcher, edit file, wait, see reload."""
    path = tmp_path / "eligibility.yaml"
    _write_valid_yaml(path, subclass="swashbuckler")
    reload_calls: list = []
    w = EligibilityFileWatcher(
        _settings_with(path),
        poll_interval_s=0.05,
        on_reload=reload_calls.append,
    )
    await w.start()
    try:
        _write_valid_yaml(path, subclass="thief")
        _bump_mtime(path)
        # Wait for at least one poll cycle.
        for _ in range(40):
            if reload_calls:
                break
            await asyncio.sleep(0.05)
        assert len(reload_calls) >= 1
        assert ("rogue", "thief") in w.current
    finally:
        await w.stop()
