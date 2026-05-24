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

    Priority: env_override > Settings.monster_driver > "smart" default.
    Unknown values fall back to "smart" and emit a structured warning.
    """
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
        for k in ("openai_client", "llm_model", "llm_timeout_seconds", "cache_max_size"):
            driver_kwargs.pop(k, None)
        return MonsterDriver(**driver_kwargs)

    # "smart" or "mixed" — same class, internal routing handles the mix.
    return SmartMonsterDriver(**driver_kwargs)
