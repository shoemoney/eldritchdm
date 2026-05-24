"""Judge prompt loader with SemVer header (Phase 12 / D-72).

The judge prompt's first line MUST be exactly
``# judge-prompt-version: <MAJOR>.<MINOR>.<PATCH>``. The version string
flows into the eval run's JSON output so prior runs remain comparable to
new ones across prompt iterations.
"""

from __future__ import annotations

import re
from pathlib import Path

_VERSION_HEADER_RE = re.compile(r"^# judge-prompt-version: (\d+\.\d+\.\d+)\s*$")

_DEFAULT_PROMPT_PATH = Path(__file__).parent / "prompts" / "judge.txt"


class JudgePromptError(Exception):
    """Raised when the judge prompt file is missing or has a malformed header."""


def load_judge_prompt(path: Path | None = None) -> tuple[str, str]:
    """Load the judge prompt, return ``(full_text, version)``.

    Args:
        path: Optional override for testing. Defaults to the bundled
            ``src/eldritch_dm/eval/prompts/judge.txt``.

    Raises:
        JudgePromptError: file missing OR line 1 doesn't match the
            ``# judge-prompt-version: X.Y.Z`` format.
    """
    target = path if path is not None else _DEFAULT_PROMPT_PATH
    if not target.is_file():
        raise JudgePromptError(f"judge prompt not found: {target}")

    try:
        text = target.read_text(encoding="utf-8")
    except OSError as exc:
        raise JudgePromptError(f"cannot read judge prompt {target}: {exc}") from exc

    if not text:
        raise JudgePromptError(f"judge prompt is empty: {target}")

    first_line = text.splitlines()[0]
    match = _VERSION_HEADER_RE.match(first_line)
    if match is None:
        raise JudgePromptError(
            f"judge prompt {target} line 1 must match "
            f"'# judge-prompt-version: X.Y.Z'; got: {first_line!r}"
        )

    return text, match.group(1)
