"""Tests for the AOE addendum loader (Phase 20 / D-152)."""

from __future__ import annotations

from pathlib import Path

import pytest

from eldritch_dm.gameplay.prompts.aoe_addendum import (
    AoeAddendumError,
    load_aoe_addendum,
)


def test_loads_bundled_addendum_with_version() -> None:
    text, version = load_aoe_addendum()
    assert version == "1.0.0"
    assert "EXTENSION: multi-target tactic selection." in text
    # Header must be the literal first line.
    assert text.splitlines()[0] == "# aoe-addendum-version: 1.0.0"


def test_loader_raises_when_file_missing(tmp_path: Path) -> None:
    missing = tmp_path / "nope.txt"
    with pytest.raises(AoeAddendumError, match="not found"):
        load_aoe_addendum(missing)


def test_loader_raises_when_header_malformed(tmp_path: Path) -> None:
    bad = tmp_path / "bad.txt"
    bad.write_text("# wrong-header: 1.0.0\nbody\n", encoding="utf-8")
    with pytest.raises(AoeAddendumError, match="must match"):
        load_aoe_addendum(bad)


def test_loader_raises_when_empty(tmp_path: Path) -> None:
    empty = tmp_path / "empty.txt"
    empty.write_text("", encoding="utf-8")
    with pytest.raises(AoeAddendumError, match="empty"):
        load_aoe_addendum(empty)


def test_loader_raises_on_bad_version_format(tmp_path: Path) -> None:
    bad = tmp_path / "bad_version.txt"
    bad.write_text("# aoe-addendum-version: 1.0\nbody\n", encoding="utf-8")
    with pytest.raises(AoeAddendumError, match="must match"):
        load_aoe_addendum(bad)
