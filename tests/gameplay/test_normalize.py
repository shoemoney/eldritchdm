"""Tests for the shared casing/whitespace normalizer (Phase 8 / D-36).

The normalizer is the only thing standing between YAML author casing and the
repo's frozenset key shape. If these tests fail, eligibility lookups silently
miss for any non-lowercased input.
"""

from __future__ import annotations

import pytest

from eldritch_dm.gameplay.normalize import normalize


def test_basic_casing() -> None:
    assert normalize("Battle Master") == "battle master"


def test_whitespace_collapse_and_strip() -> None:
    assert normalize("  Battle   Master  ") == "battle master"


def test_full_uppercase() -> None:
    assert normalize("BATTLE MASTER") == "battle master"


def test_empty_string_roundtrip() -> None:
    assert normalize("") == ""


def test_tab_is_whitespace() -> None:
    assert normalize("battle\tmaster") == "battle master"


def test_all_casing_variants_share_hash() -> None:
    variants = [
        "Battle Master",
        "battle master",
        "BATTLE MASTER",
        "  battle   master  ",
    ]
    normalized = [normalize(v) for v in variants]
    # All four normalize to the same string, therefore the same hash.
    assert len(set(normalized)) == 1
    for a in variants:
        for b in variants:
            assert hash(normalize(a)) == hash(normalize(b))


def test_legacy_underscore_normalize_removed_from_pc_classes_repo() -> None:
    """Proves the symbol was MOVED, not duplicated (D-36)."""
    from eldritch_dm.persistence import pc_classes_repo

    assert not hasattr(pc_classes_repo, "_normalize"), (
        "pc_classes_repo._normalize should have been moved to gameplay.normalize"
    )
    assert not hasattr(pc_classes_repo, "_WHITESPACE_RE"), (
        "pc_classes_repo._WHITESPACE_RE should have been moved to gameplay.normalize"
    )


def test_pc_class_info_uses_shared_normalize() -> None:
    """PCClassInfo.field_validator goes through gameplay.normalize.normalize now."""
    from eldritch_dm.persistence.pc_classes_repo import PCClassInfo

    info = PCClassInfo(class_name="Battle Master", subclass="Battle Master")
    assert info.class_name == "battle master"
    assert info.subclass == "battle master"


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("  ", ""),
        ("\n\tFighter\t\n", "fighter"),
        ("Echo Knight", "echo knight"),  # nbsp is NOT \s in Python re
    ],
)
def test_edge_cases(raw: str, expected: str) -> None:
    assert normalize(raw) == expected
