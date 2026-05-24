"""Casing + whitespace normalizer shared by pc_classes_repo and eligibility_loader.

Extracted from persistence.pc_classes_repo at Phase 08 per D-36 so the YAML loader
and the repo agree on key shape — frozenset[tuple[str, str]] lookups need stable
hashes regardless of YAML author casing or DDB ingest casing.

Pure stdlib (`re`); no upward imports. Safe for any layer to import.
"""

from __future__ import annotations

import re

_WHITESPACE_RE: re.Pattern[str] = re.compile(r"\s+")


def normalize(value: str) -> str:
    """Lowercase + collapse runs of whitespace to a single space, strip ends.

    Examples:
        >>> normalize("Battle Master")
        'battle master'
        >>> normalize("  BATTLE   MASTER  ")
        'battle master'
        >>> normalize("battle\\tmaster")
        'battle master'
    """
    return _WHITESPACE_RE.sub(" ", value.strip().lower())
