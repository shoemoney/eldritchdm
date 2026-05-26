"""Shared DISCORD_TOKEN validation helper (SAFETY-03 / TD-1 / D-33).

Before Phase 7, ``run.py`` had an inline 15-line block that printed a friendly
stderr message + emitted a structured-log line + returned EXIT_MISSING_TOKEN
when ``DISCORD_TOKEN`` was unset or blank. ``python -m eldritch_dm.bot`` had
no equivalent — it let ``discord.errors.LoginFailure`` traceback through to
stderr.

This module is the single source of truth for that friendly-error text + log
key. Both entrypoints (``run.py`` and ``bot/__main__.py``) import and call
``require_token_or_exit(settings, log)``; on a ``None`` return they propagate
``EXIT_MISSING_TOKEN`` (the helper does NOT call ``sys.exit`` — keeps it
testable).

Per D-33 the helper lives under the ``eldritch_dm.config`` package alongside
``Settings`` so there are no circular imports.
"""
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import sys
from typing import Any

# NOTE: we deliberately do NOT `from eldritch_dm.bootstrap import EXIT_MISSING_TOKEN`
# here — that would pull `eldritch_dm.persistence` (via bootstrap's re-export)
# into the config layer and break the import-linter contract "config and
# logging must not import subsystems". The exit-code namespace lives in
# eldritch_dm.bootstrap as the single source of truth; we mirror only this
# one constant locally. Tests assert the two values stay equal.
EXIT_MISSING_TOKEN = 4

_STDERR_HINT = (
    "❌ DISCORD_TOKEN is not set.\n"
    "   Copy .env.example to .env and paste your bot token, e.g.:\n"
    "     cp .env.example .env && $EDITOR .env\n"
    "   (Or run `python run.py --check-only` to verify oMLX / dm20 "
    "without a token first.)"
)


def require_token_or_exit(settings: Any, log: Any) -> str | None:
    """Return the stripped DISCORD_TOKEN, or None to signal exit-4.

    On the failure branch emits:
      * A structured-log line keyed ``missing_discord_token`` with
        ``exit_code=EXIT_MISSING_TOKEN`` and the ``.env.example`` hint.
      * A friendly stderr message identical to run.py's pre-refactor
        inline block — self-hosters see ``❌ DISCORD_TOKEN is not set`` plus
        the ``cp .env.example .env`` hint regardless of which entrypoint
        they invoked.

    Returns the stripped token on success; ``None`` on missing/blank so the
    caller can ``return EXIT_MISSING_TOKEN`` itself (no implicit sys.exit
    keeps the function testable without subprocess gymnastics).
    """
    token = (getattr(settings, "discord_token", None) or "").strip()
    if not token:
        log.error(
            "missing_discord_token",
            hint="Copy .env.example to .env and paste your DISCORD_TOKEN.",
            exit_code=EXIT_MISSING_TOKEN,
        )
        print(_STDERR_HINT, file=sys.stderr)
        return None
    return token
