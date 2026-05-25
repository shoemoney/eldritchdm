"""
MonsterDriver factory (Phase 10 Plan 02 — D-52, D-60).

Centralizes driver construction so the orchestrator never instantiates
`MonsterDriver` or `SmartMonsterDriver` directly. Resolution order:

  1. Explicit `env_override` argument (highest — used by tests)
  2. `Settings().monster_driver` (i.e. the `MONSTER_DRIVER` env var)
  3. Default: ``"smart"``

Values:

  - ``"smart"``  → `SmartMonsterDriver` (LLM-routed targeting)
  - ``"random"`` → `MonsterDriver` (v1.0 escape hatch — pure random)
  - ``"mixed"``  → `SmartMonsterDriver`; the INT-gating inside
    `_route_path` already implements per-monster mixing. The factory-level
    "mixed" label is a no-op alias for "smart" with mixed semantics — it
    exists so operators can express intent in their `.env` without changing
    behaviour.

Unknown values log a structured warning and fall back to "smart".

Import-linter discipline: this module lives in `gameplay/` and imports only
from `gameplay/`, `logging`. No upward imports.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal

from eldritch_dm.gameplay.monster_driver import MonsterDriver
from eldritch_dm.gameplay.smart_monster_driver import SmartMonsterDriver
from eldritch_dm.logging import get_logger

if TYPE_CHECKING:
    pass

log = get_logger(__name__)

DriverMode = Literal["smart", "random", "mixed"]
_VALID_MODES: frozenset[str] = frozenset({"smart", "random", "mixed"})


def _resolve_mode(env_override: str | None) -> DriverMode:
    """Resolve the final driver mode.

    Priority (Phase 13 / MON-02 / R-13-02-a — degraded mode wins over EVERY
    other signal):
      0. observability.degraded_mode.is_active() → "random" (safety override)
      1. env_override argument (tests + explicit overrides)
      2. Settings.monster_driver
      3. "smart" default
    Unknown values fall back to "smart" and emit a structured warning.
    """
    # ── Phase 13 safety override — degraded mode forces random ──
    # Lazy import (in-function) so this module stays import-linter-safe and
    # observability is not pulled in when gameplay is imported in unrelated
    # contexts (e.g. eval/runner.py reuses the factory).
    try:
        from eldritch_dm.observability.degraded_mode import get_degraded_mode

        if get_degraded_mode().is_active():
            log.info("monster_driver_factory_degraded_override", to="random")
            return "random"
    except Exception as exc:  # noqa: BLE001 — fail-soft
        # Observability error must NEVER prevent gameplay from running. If
        # the degraded-mode module misbehaves, fall through to the normal
        # mode-resolution chain.
        log.warning(
            "monster_driver_factory_degraded_check_failed",
            error_type=type(exc).__name__,
            error=str(exc)[:120],
        )

    raw: str | None = env_override

    if raw is None:
        # Lazy import to keep gameplay/ off the config import path during tests
        try:
            from eldritch_dm.config import get_settings

            settings = get_settings()
            raw = getattr(settings, "monster_driver", None)
        except Exception as exc:  # noqa: BLE001 — fail-soft
            log.warning(
                "monster_driver_factory_settings_error",
                error_type=type(exc).__name__,
                error=str(exc)[:120],
            )
            raw = None

    if raw is None or raw == "":
        return "smart"

    raw = raw.strip().lower()
    if raw not in _VALID_MODES:
        log.warning(
            "monster_driver_factory_unknown_mode",
            requested=raw,
            fallback="smart",
        )
        return "smart"

    return raw  # type: ignore[return-value]


def make_monster_driver(
    *,
    env_override: str | None = None,
    **driver_kwargs: Any,
) -> MonsterDriver:
    """Construct the configured MonsterDriver.

    Args:
        env_override: Optional explicit mode ("smart"|"random"|"mixed"). When
            None, falls back to `Settings().monster_driver` then to "smart".
        **driver_kwargs: Forwarded to the concrete driver constructor. The
            "random" mode does NOT need `openai_client` and will pop it from
            the kwargs if provided (so the same call site can stay generic).

    Returns:
        Either `MonsterDriver` (random) or `SmartMonsterDriver`
        (smart/mixed).
    """
    mode = _resolve_mode(env_override)
    log.info("monster_driver_factory_resolved", mode=mode)

    if mode == "random":
        # Strip kwargs that only the smart driver consumes.
        # Phase 19 / STREAM-03: ``embed_update_callback`` is smart-driver-only;
        # pop it here so callers can pass the same kwargs to either mode.
        for k in (
            "openai_client",
            "llm_model",
            "llm_timeout_seconds",
            "cache_max_size",
            "embed_update_callback",
            "aoe_addendum_loader",
            "monster_memory",  # Phase 21 / MEM-02: smart-driver-only
        ):
            driver_kwargs.pop(k, None)
        return MonsterDriver(**driver_kwargs)

    # "smart" or "mixed" — same class, internal routing handles the mix.
    return SmartMonsterDriver(**driver_kwargs)
