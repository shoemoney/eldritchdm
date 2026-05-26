"""
EDM001 — defer-discipline AST lint rule.

Every Discord interaction callback's first non-docstring statement MUST be:
    await <interaction_arg>.response.defer(...)

Or for modal-submit handlers that respond with a new modal immediately:
    await <interaction_arg>.response.send_modal(...)

Exceptions are marked with:
    # noqa: EDM001 — <reason>

on the function `def` line.

Usage::

    python -m eldritch_dm.lint.edm001 src/eldritch_dm/bot/
    # or with explicit files:
    python -m eldritch_dm.lint.edm001 src/eldritch_dm/bot/cogs/diagnostics.py

Exit code:
    0 — no violations
    1 — one or more violations found

Heuristic: false positives are acceptable (silence with noqa).
False negatives (missing real violations) are NOT acceptable — when in doubt, flag.
"""
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import ast
import sys
from pathlib import Path

EXIT_OK = 0
EXIT_VIOLATION = 1

# Decorator names that identify interaction callbacks
CALLBACK_DECORATOR_NAMES = frozenset(
    {
        "command",  # @app_commands.command, @bot.tree.command
        "button",  # @discord.ui.button
        "select",  # @discord.ui.select
        "context_menu",  # @app_commands.context_menu
        "error",  # @<cmd>.error (app command error handlers also need defer)
    }
)

# Base class names that identify UI subclasses (string-match, no symbol resolution)
UI_BASE_CLASS_NAMES = frozenset(
    {
        "DynamicItem",
        "View",
        "Modal",
        "Button",
        "Item",
    }
)

# noqa tag to silence EDM001 on a specific function
NOQA_TAG = "# noqa: EDM001"


def _has_noqa(line: str) -> bool:
    """Check whether a source line has a noqa: EDM001 suppression."""
    return NOQA_TAG in line


def _decorator_attr(node: ast.expr) -> str | None:
    """Extract the final attribute name from a decorator expression.

    Handles:
      - @name → "name"
      - @module.name → "name"
      - @a.b.name → "name"
      - @name(...) → "name" (Call wrapping)

    Returns None if the structure is unrecognized.
    """
    if isinstance(node, ast.Call):
        return _decorator_attr(node.func)
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Name):
        return node.id
    return None


def _is_ui_subclass(class_node: ast.ClassDef) -> bool:
    """Return True if the class appears to subclass a discord UI type."""
    for base in class_node.bases:
        # Handle DynamicItem[Button] which is ast.Subscript
        if isinstance(base, ast.Subscript):
            value = base.value
            attr = _decorator_attr(value)
            if attr in UI_BASE_CLASS_NAMES:
                return True
        else:
            attr = _decorator_attr(base)
            if attr in UI_BASE_CLASS_NAMES:
                return True
    return False


def _is_target_callback(
    func_node: ast.AsyncFunctionDef,
    class_stack: list[ast.ClassDef],
) -> bool:
    """Return True if this async function is an interaction callback subject to EDM001.

    Detection heuristics (conservative — flags generously):
      1. Decorated with one of CALLBACK_DECORATOR_NAMES
      2. Named 'callback' AND enclosed in a class that subclasses a UI type
    """
    # Heuristic 1: decorator-based detection
    for dec in func_node.decorator_list:
        attr = _decorator_attr(dec)
        if attr in CALLBACK_DECORATOR_NAMES:
            return True

    # Heuristic 2: 'callback' method in a discord UI subclass
    if func_node.name == "callback" and class_stack:
        enclosing_class = class_stack[-1]
        if _is_ui_subclass(enclosing_class):
            return True

    return False


def _first_real_statement(body: list[ast.stmt]) -> ast.stmt | None:
    """Return the first non-docstring statement in a function body.

    A leading docstring is a bare string Expr node (Constant with str value).
    """
    if not body:
        return None

    first = body[0]
    if (
        isinstance(first, ast.Expr)
        and isinstance(first.value, ast.Constant)
        and isinstance(first.value.value, str)
    ):
        # It's a docstring — skip to the next statement
        return body[1] if len(body) > 1 else None

    return first


def _is_defer_or_send_modal(stmt: ast.stmt) -> bool:
    """Check whether a statement is an acceptable first-statement.

    Accepted forms:
      - ``await <name>.response.defer(...)``      (any args/kwargs)
      - ``await <name>.response.send_modal(...)`` (D-12 modal exception)

    Where <name> is any identifier (typically 'interaction', but may differ).
    """
    if not isinstance(stmt, ast.Expr):
        return False
    if not isinstance(stmt.value, ast.Await):
        return False
    call = stmt.value.value
    if not isinstance(call, ast.Call):
        return False
    func = call.func
    if not isinstance(func, ast.Attribute):
        return False

    # Must end in .defer or .send_modal
    if func.attr not in ("defer", "send_modal"):
        return False

    # Middle part must be .response
    middle = func.value
    if isinstance(middle, ast.Attribute) and middle.attr == "response":
        return True

    return False


def check_file(path: Path, source_lines: list[str] | None = None) -> list[tuple[int, int, str]]:
    """Check a single Python file for EDM001 violations.

    Args:
        path: Path to the Python file.
        source_lines: Pre-split lines (avoids re-reading; pass None to read from disk).

    Returns:
        List of (line, col, message) tuples. Empty list means no violations.
    """
    try:
        source = path.read_text(encoding="utf-8")
    except OSError as e:
        return [(0, 0, f"IOError: {e}")]

    if source_lines is None:
        source_lines = source.splitlines()

    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError as e:
        return [(e.lineno or 0, e.offset or 0, f"SyntaxError: {e.msg}")]

    violations: list[tuple[int, int, str]] = []
    class_stack: list[ast.ClassDef] = []

    class Visitor(ast.NodeVisitor):
        def visit_ClassDef(self, node: ast.ClassDef) -> None:
            class_stack.append(node)
            self.generic_visit(node)
            class_stack.pop()

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
            if _is_target_callback(node, class_stack):
                # Check for noqa suppression on the function def line
                def_line_idx = node.lineno - 1
                def_line = source_lines[def_line_idx] if def_line_idx < len(source_lines) else ""
                if _has_noqa(def_line):
                    # Waived — skip check but still visit children
                    self.generic_visit(node)
                    return

                first_stmt = _first_real_statement(node.body)

                if first_stmt is None or not _is_defer_or_send_modal(first_stmt):
                    violations.append(
                        (
                            node.lineno,
                            node.col_offset,
                            f"EDM001 callback '{node.name}' first statement is not "
                            f"`await <interaction>.response.defer(...)`; "
                            f"use `# noqa: EDM001 — <reason>` for exceptions",
                        )
                    )

            # Always recurse to catch nested classes (e.g. Modal inside a Cog method)
            self.generic_visit(node)

    Visitor().visit(tree)
    return violations


def main(argv: list[str] | None = None) -> int:
    """Entry point for EDM001 lint rule.

    Args:
        argv: List of file paths or directory paths. If None, defaults to
              ["src/eldritch_dm/bot"] relative to cwd.

    Returns:
        0 if no violations; 1 if any violations found.
    """
    if argv is None:
        argv = sys.argv[1:]

    if not argv:
        argv = ["src/eldritch_dm/bot"]

    files: list[Path] = []
    for arg in argv:
        p = Path(arg)
        if p.is_dir():
            files.extend(sorted(p.rglob("*.py")))
        elif p.is_file() and p.suffix == ".py":
            files.append(p)
        # Non-.py files are silently ignored (pre-commit passes all files;
        # we only care about Python source)

    exit_code = EXIT_OK
    for file_path in files:
        for line, col, msg in check_file(file_path):
            print(f"{file_path}:{line}:{col}: {msg}")
            exit_code = EXIT_VIOLATION

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
