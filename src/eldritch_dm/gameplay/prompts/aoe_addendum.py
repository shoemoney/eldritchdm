"""AOE-addendum prompt loader with SemVer header (Phase 20 / D-152).

Mirrors the ``eval/judge_prompt.py`` pattern: the first line of the
addendum MUST match ``# aoe-addendum-version: <MAJOR>.<MINOR>.<PATCH>``.
The version string flows into structured logs so prior runs remain
comparable across prompt iterations.
"""

from __future__ import annotations

import re
from pathlib import Path

_VERSION_HEADER_RE = re.compile(r"^# aoe-addendum-version: (\d+\.\d+\.\d+)\s*$")

_DEFAULT_PROMPT_PATH = Path(__file__).parent / "aoe_addendum.txt"


class AoeAddendumError(Exception):
    """Raised when the AOE addendum file is missing or has a malformed header."""


def load_aoe_addendum(path: Path | None = None) -> tuple[str, str]:
    """Load the AOE addendum, return ``(full_text, version)``.

    Args:
        path: Optional override for testing. Defaults to the bundled
            ``src/eldritch_dm/gameplay/prompts/aoe_addendum.txt``.

    Raises:
        AoeAddendumError: file missing OR line 1 doesn't match the
            ``# aoe-addendum-version: X.Y.Z`` format.
    """
    target = path if path is not None else _DEFAULT_PROMPT_PATH
    if not target.is_file():
        raise AoeAddendumError(f"AOE addendum not found: {target}")

    try:
        text = target.read_text(encoding="utf-8")
    except OSError as exc:
        raise AoeAddendumError(f"cannot read AOE addendum {target}: {exc}") from exc

    if not text:
        raise AoeAddendumError(f"AOE addendum is empty: {target}")

    first_line = text.splitlines()[0]
    match = _VERSION_HEADER_RE.match(first_line)
    if match is None:
        raise AoeAddendumError(
            f"AOE addendum {target} line 1 must match "
            f"'# aoe-addendum-version: X.Y.Z'; got: {first_line!r}"
        )

    return text, match.group(1)
