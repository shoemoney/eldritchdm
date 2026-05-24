"""Lazy-import canary (Phase 11 / OBS-01 / D-65d).

Verifies that importing the full bot tree with ``OBSERVABILITY_ENABLED`` unset
does NOT pull ``opentelemetry`` into ``sys.modules``.

Uses ``subprocess`` so any OTel imports made by tracer.init_tracing() in a
previous test cannot pollute the current process and cause this test to
spuriously pass.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap


def test_no_otel_in_sys_modules_when_disabled() -> None:
    """Full-bot-tree import with observability disabled leaves OTel unloaded."""
    script = textwrap.dedent(
        """
        import os
        os.environ.pop("OBSERVABILITY_ENABLED", None)
        # Import the full instrumentation surface — catches transitive OTel
        # pulls from ANY subsystem touched by smart driver or ingest.
        import eldritch_dm.observability  # noqa: F401
        import eldritch_dm.gameplay.smart_monster_driver  # noqa: F401
        import eldritch_dm.ingest.translate  # noqa: F401
        # Plus a real call into the no-op context managers to ensure the
        # disabled path executes without triggering imports.
        from eldritch_dm.observability import traced_decision, traced_translate
        with traced_decision(
            monster_id="m", channel_id="c", combat_round=1, driver_path="smart"
        ) as s:
            s.set_attribute("eldritch.latency_ms", 1)
        with traced_translate(channel_id="c", model="ShoeGPT") as s:
            s.set_attribute("eldritch.latency_ms", 1)
        import sys as _sys
        leaks = sorted(k for k in _sys.modules if "opentelemetry" in k)
        assert not leaks, f"OTel import leaked when disabled: {leaks}"
        print("LAZY_IMPORT_OK")
        """
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert (
        result.returncode == 0
    ), f"subprocess failed:\nSTDOUT: {result.stdout}\nSTDERR: {result.stderr}"
    assert "LAZY_IMPORT_OK" in result.stdout
