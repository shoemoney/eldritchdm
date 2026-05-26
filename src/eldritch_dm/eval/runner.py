"""Eval runner — driver/judge invocation bypassing Discord (Phase 12 / D-80).

Builds a stripped-down ``SmartMonsterDriver`` whose non-``_choose_target``
dependencies are sentinel objects that raise on access. This guarantees
the eval path NEVER accidentally executes the production combat
orchestration — if it tries to, the sentinel surfaces the bug loudly.

``run_scenario`` orchestrates one scenario: build candidate dicts, call
``driver._choose_target``, time both halves, ask the judge to score.
"""
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from eldritch_dm.eval.aggregator import ScenarioResult
from eldritch_dm.eval.judge import TacticalJudge
from eldritch_dm.eval.scenarios import ScenarioEntry
from eldritch_dm.gameplay.smart_monster_driver import SmartMonsterDriver
from eldritch_dm.logging import get_logger

if TYPE_CHECKING:
    from openai import AsyncOpenAI

log = get_logger(__name__)


class _NoopSentinel:
    """Raises on any attribute access — guards eval against accidentally
    hitting the production orchestration path.
    """

    def __init__(self, name: str) -> None:
        self._name = name

    def __getattr__(self, attr: str) -> Any:
        raise RuntimeError(
            f"Eval driver sentinel '{self._name}' was unexpectedly accessed "
            f"(attr={attr!r}). The eval path should call only "
            f"_choose_target / _pick_target_llm — never the full drive()."
        )

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        raise RuntimeError(
            f"Eval driver sentinel '{self._name}' was unexpectedly called."
        )


def build_eval_driver(
    *,
    openai_client: AsyncOpenAI,
    model: str = "ShoeGPT",
    llm_timeout_seconds: float = 1.5,
) -> SmartMonsterDriver:
    """Construct a SmartMonsterDriver for ``_choose_target``-only use.

    All non-LLM dependencies are sentinels that raise on access. Returns
    a fully-instantiated SmartMonsterDriver — eval callers MUST use only
    ``_choose_target`` (and inherited target-selection helpers); calling
    ``drive()`` will raise immediately on first access to the orchestrator
    dependencies.
    """
    driver = SmartMonsterDriver(
        mcp=_NoopSentinel("mcp"),
        rate_limiter=_NoopSentinel("rate_limiter"),
        pc_classes_repo=_NoopSentinel("pc_classes_repo"),  # type: ignore[arg-type]
        riposte_timers_repo=_NoopSentinel("riposte_timers_repo"),  # type: ignore[arg-type]
        button_factory=_NoopSentinel("button_factory"),  # type: ignore[arg-type]
        state_provider=_NoopSentinel("state_provider"),  # type: ignore[arg-type]
        channel_resolver=_NoopSentinel("channel_resolver"),
        openai_client=openai_client,
        llm_model=model,
        llm_timeout_seconds=llm_timeout_seconds,
    )
    return driver


def _pc_to_target_dict(pc) -> dict[str, Any]:  # type: ignore[no-untyped-def]
    """Convert a PCEntry into the dict shape SmartMonsterDriver expects."""
    return {
        "character_id": pc.character_id,
        "name": pc.name,
        "hp_current": pc.hp_current,
        "hp_max": pc.hp_max,
        "ac": pc.ac,
        "active_conditions": list(pc.active_conditions),
    }


def _monster_to_actor_dict(monster, monster_id: str) -> dict[str, Any]:  # type: ignore[no-untyped-def]
    return {
        "character_id": monster_id,
        "player_id": None,  # ensures monster turn semantics
        "name": monster.name,
        "intelligence": monster.intelligence,
        "stats": {"intelligence": monster.intelligence},
    }


async def run_scenario(
    *,
    driver: SmartMonsterDriver,
    judge: TacticalJudge,
    scenario: ScenarioEntry,
    driver_model: str,
    judge_model: str,
) -> ScenarioResult:
    """Run one scenario end-to-end. NEVER raises (errors are recorded).

    Driver failure → ``driver_target_pc_id=None``, judge gets called with
    ``"<no-choice>"`` so we still get a verdict (the judge can rate
    "no choice" appropriately).
    """
    targets = [_pc_to_target_dict(pc) for pc in scenario.pc_list]
    monster_id = f"monster-{scenario.scenario_id}"
    current_actor = _monster_to_actor_dict(scenario.monster_stats, monster_id)
    channel_id = f"eval-{scenario.scenario_id}"

    # ── Driver ──────────────────────────────────────────────────────────
    driver_target_pc_id: str | None = None
    t0 = time.monotonic()
    try:
        chosen = await driver._choose_target(
            targets,
            channel_id=channel_id,
            round_number=1,
            current_actor=current_actor,
        )
        driver_target_pc_id = chosen.get("character_id")
    except Exception as exc:  # noqa: BLE001 — runner is fail-soft
        log.warning(
            "eval.driver_error",
            scenario_id=scenario.scenario_id,
            error_type=type(exc).__name__,
            error=str(exc)[:200],
        )
    latency_ms_driver = int((time.monotonic() - t0) * 1000)

    # ── Judge ───────────────────────────────────────────────────────────
    t0 = time.monotonic()
    verdict = await judge.score(
        scenario,
        driver_choice_pc_id=driver_target_pc_id or "<no-choice>",
        driver_rationale=None,  # SmartMonsterDriver doesn't surface rationale up
        driver_model=driver_model,
    )
    latency_ms_judge = int((time.monotonic() - t0) * 1000)

    judge_error = None if verdict is not None else "judge_returned_none"

    return ScenarioResult(
        scenario_id=scenario.scenario_id,
        archetype=scenario.archetype,
        driver_target_pc_id=driver_target_pc_id,
        driver_rationale=None,
        verdict=verdict,
        judge_error=judge_error,
        latency_ms_driver=latency_ms_driver,
        latency_ms_judge=latency_ms_judge,
    )


__all__ = ["build_eval_driver", "run_scenario"]
