"""
Static guard test: verify every mutating method in each repo goes through
writer_queue.submit and does not use BEGIN directly.
"""

from __future__ import annotations

import re
from pathlib import Path


REPO_FILES = [
    "src/eldritch_dm/persistence/channel_sessions_repo.py",
    "src/eldritch_dm/persistence/persistent_views_repo.py",
    "src/eldritch_dm/persistence/riposte_timers_repo.py",
    "src/eldritch_dm/persistence/sanitizer_audit_repo.py",
]

# Methods that are expected to be reads (no writer_queue.submit requirement)
READ_METHOD_PREFIXES = ("get", "list", "count")


def _extract_method_bodies(source: str) -> dict[str, str]:
    """Extract method names and their approximate body text."""
    # Split on 'async def ' or 'def ' at class level indentation
    pattern = re.compile(r"^\s{4}async def (\w+)\s*\(", re.MULTILINE)
    matches = list(pattern.finditer(source))

    result: dict[str, str] = {}
    for i, m in enumerate(matches):
        name = m.group(1)
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(source)
        result[name] = source[start:end]
    return result


class TestWriteMethodsUseQueue:
    def test_no_direct_begin_in_repos(self):
        """Repositories must not issue BEGIN directly — that's WriterQueue's job."""
        direct_begin_re = re.compile(r'\bBEGIN\b(?!\s+IMMEDIATE)', re.IGNORECASE)

        for rel_path in REPO_FILES:
            path = Path(rel_path)
            source = path.read_text()
            # Filter out comment lines
            non_comment_lines = [
                line for line in source.splitlines()
                if not line.lstrip().startswith("#")
            ]
            for line in non_comment_lines:
                assert not direct_begin_re.search(line), (
                    f"{path}: found direct BEGIN (non-IMMEDIATE) in: {line!r}"
                )

    def test_mutating_methods_reference_writer_queue(self):
        """Every method that mutates state should call writer_queue.submit."""
        for rel_path in REPO_FILES:
            path = Path(rel_path)
            source = path.read_text()
            methods = _extract_method_bodies(source)

            for name, body in methods.items():
                if name.startswith(READ_METHOD_PREFIXES):
                    continue
                if name.startswith("_") or name == "__init__":
                    continue
                # Mutating method — must reference writer_queue.submit
                assert "writer_queue.submit" in body or "_writer_queue.submit" in body, (
                    f"{path}: mutating method '{name}' does not use writer_queue.submit"
                )
