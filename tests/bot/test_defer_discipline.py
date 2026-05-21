"""
tests/bot/test_defer_discipline.py — EDM001 defer-discipline lint rule tests.

Tests the AST-based pre-commit hook in eldritch_dm.lint.edm001.

Corpus-driven:
  Good cases (must NOT trigger EDM001):
    1. App command with defer as first stmt
    2. Button callback with defer as first stmt
    3. App command with send_modal as first stmt + noqa waiver
    4. App command with docstring then defer
    5. App command with # noqa: EDM001 waiver (no defer)
    6. Plain non-callback async function (not subject to rule)

  Bad cases (must trigger EDM001):
    1. App command with DB read before defer
    2. Button callback with print() before defer
    3. App command with helper() await before defer
    4. App command with non-defer/non-send_modal as first stmt
    5. Button callback with conditional defer (not unconditionally first)

Bonus:
  - test_real_codebase_passes_edm001: run against src/eldritch_dm/bot/
"""

from __future__ import annotations

import io
import sys
from pathlib import Path

import pytest

# Corpus directory
CORPUS_DIR = Path(__file__).parent / "_edm001_corpus"
GOOD_DIR = CORPUS_DIR / "good"
BAD_DIR = CORPUS_DIR / "bad"


def run_linter(*paths: str) -> tuple[int, str]:
    """Run the EDM001 linter and capture stdout output.

    Returns:
        (exit_code, stdout_output)
    """
    from eldritch_dm.lint.edm001 import main

    captured = io.StringIO()
    old_stdout = sys.stdout
    sys.stdout = captured
    try:
        exit_code = main(list(paths))
    finally:
        sys.stdout = old_stdout

    return exit_code, captured.getvalue()


# ── Good corpus: must NOT trigger EDM001 ──────────────────────────────────────


@pytest.mark.parametrize(
    "filename,description",
    [
        ("good_01_app_cmd_defer.py", "App command with defer as first stmt"),
        ("good_02_button_defer.py", "Button callback with defer as first stmt"),
        ("good_03_modal_send_modal.py", "send_modal with noqa waiver"),
        ("good_04_docstring_then_defer.py", "App command: docstring then defer"),
        ("good_05_noqa_waiver.py", "App command with # noqa: EDM001 waiver"),
        ("good_06_plain_async_fn.py", "Plain async function — not a callback"),
    ],
)
def test_good_corpus_passes(filename: str, description: str) -> None:
    """Good corpus files must return exit code 0 (no EDM001 violations)."""
    path = str(GOOD_DIR / filename)
    exit_code, output = run_linter(path)
    assert exit_code == 0, (
        f"Expected exit 0 for {description!r}, got exit {exit_code}. Output:\n{output}"
    )


# ── Bad corpus: must trigger EDM001 ──────────────────────────────────────────


@pytest.mark.parametrize(
    "filename,description,expected_fn_name",
    [
        ("bad_01_app_cmd_db_read.py", "App command with DB read first", "broken"),
        ("bad_02_button_print.py", "Button callback with print() first", "callback"),
        ("bad_03_app_cmd_wrong_await.py", "App command with helper() await first", "wrong_order"),
        ("bad_04_modal_non_defer.py", "App command with non-defer first stmt", "modal_bad"),
        ("bad_05_conditional_defer.py", "Button callback with conditional defer", "callback"),
    ],
)
def test_bad_corpus_fails(filename: str, description: str, expected_fn_name: str) -> None:
    """Bad corpus files must return exit code 1 and output the function name."""
    path = str(BAD_DIR / filename)
    exit_code, output = run_linter(path)
    assert exit_code == 1, (
        f"Expected exit 1 for {description!r}, got exit {exit_code}. Output:\n{output}"
    )
    assert "EDM001" in output, (
        f"Expected 'EDM001' in output for {description!r}. Output:\n{output}"
    )
    assert expected_fn_name in output, (
        f"Expected function name {expected_fn_name!r} in output. Output:\n{output}"
    )


# ── Bonus: real codebase must pass ────────────────────────────────────────────


def test_real_codebase_passes_edm001() -> None:
    """The actual bot source code must pass EDM001 (exit 0).

    This is a hard requirement — all callbacks in the codebase must have
    defer as their first statement. If this fails, fix the source before proceeding.
    """
    bot_dir = Path(__file__).parent.parent.parent / "src" / "eldritch_dm" / "bot"
    py_files = list(bot_dir.rglob("*.py"))
    assert py_files, f"No Python files found in {bot_dir}"

    paths = [str(p) for p in py_files]
    exit_code, output = run_linter(*paths)

    assert exit_code == 0, (
        f"EDM001 violations found in live codebase (exit {exit_code}).\n"
        f"Violations:\n{output}\n\n"
        "Fix the source code before proceeding — all callbacks must defer first."
    )
