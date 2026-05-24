"""Observability bootstrap is wired into bot startup (Phase 13 / MON-01 / Task 06).

Phase 11 discovery: ``init_tracing()`` was defined but never called from any
production startup path. Phase 13 wires it into ``eldritch_dm.bot.__main__``
alongside ``start_metrics_endpoint()``. Both honor their env gates and are
no-ops when off.

This test inspects the source of ``bot.__main__`` to assert the boot wiring
exists without spinning up Discord. A full integration test would require
mocking the entire Discord client + the bootstrap path — disproportionate
for a "the call is present and gated correctly" assertion.
"""

from __future__ import annotations

import inspect

from eldritch_dm.bot import __main__ as bot_main


def test_main_imports_observability_init_tracing():
    src = inspect.getsource(bot_main.main)
    assert "init_tracing" in src, (
        "bot.__main__.main must call init_tracing() during startup"
    )


def test_main_imports_metrics_endpoint_start():
    src = inspect.getsource(bot_main.main)
    assert "start_metrics_endpoint" in src, (
        "bot.__main__.main must call start_metrics_endpoint() during startup"
    )


def test_main_observability_init_is_wrapped_in_try():
    """Observability failures must NEVER block bot boot (Rule-3 fail-soft)."""
    src = inspect.getsource(bot_main.main)
    # The init_tracing/start_metrics_endpoint block has its own try/except
    # so an OTel exporter misconfig or port collision doesn't kill the bot.
    # We assert the block exists by looking for the comment marker that
    # documents the deviation.
    assert "observability_init_failed" in src, (
        "Observability init must be wrapped in try/except logging "
        "observability_init_failed — bot boot must not depend on observability"
    )
