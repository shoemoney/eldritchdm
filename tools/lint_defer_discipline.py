#!/usr/bin/env python3
"""
tools/lint_defer_discipline.py — thin wrapper for the EDM001 defer-discipline rule.

Delegates entirely to eldritch_dm.lint.edm001.main(). Can be invoked:
  - As a script: `python tools/lint_defer_discipline.py [files...]`
  - As a module: `python -m eldritch_dm.lint.edm001 [files...]`

Both forms are equivalent. The pre-commit hook uses the module form.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure src/ is importable when running as a standalone script
_src = Path(__file__).parent.parent / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from eldritch_dm.lint.edm001 import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
