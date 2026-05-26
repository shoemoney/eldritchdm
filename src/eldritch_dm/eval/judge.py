"""TacticalJudge + JudgeVerdict (Phase 12 / D-71, D-73, D-81).

Locked decisions:
  D-71  Judge uses same AsyncOpenAI client pattern as SmartMonsterDriver.
        ``response_format={"type":"json_object"}``. NEVER ``.beta.parse``.
  D-73  JudgeVerdict carries overall_score + per_dimension (4 keys) +
        reasoning (≤500 chars) + would_a_veteran_dm_approve. A post-parse
        model_validator checks ``abs(overall - mean(values)) <= 0.05``.
  D-81  Judge call wrapped in ``traced_eval`` (eldritch.eval.judge span).

Import-linter-safe: lives under ``eval/``; imports stdlib, pydantic,
``openai`` (TYPE_CHECKING only), and ``eldritch_dm`` siblings.
"""
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    model_validator,
)

from eldritch_dm.eval.judge_prompt import load_judge_prompt
from eldritch_dm.eval.scenarios import ScenarioEntry
from eldritch_dm.logging import get_logger
from eldritch_dm.observability import traced_eval

if TYPE_CHECKING:
    from openai import AsyncOpenAI

log = get_logger(__name__)


DimensionKey = Literal[
    "tactical_intent",
    "meta_knowledge",
    "narrative_fairness",
    "edge_case",
]

_DIMENSION_KEYS: frozenset[str] = frozenset(
    {"tactical_intent", "meta_knowledge", "narrative_fairness", "edge_case"}
)

_MEAN_TOLERANCE = 0.05


class JudgeVerdict(BaseModel):
    """One judge verdict for one scenario (D-73)."""

    model_config = ConfigDict(extra="ignore", frozen=True)

    overall_score: float = Field(ge=0.0, le=1.0)
    per_dimension: dict[DimensionKey, float]
    reasoning: str = Field(max_length=500)
    would_a_veteran_dm_approve: bool

    @model_validator(mode="after")
    def _check_dimensions_and_mean(self) -> JudgeVerdict:
        # Pydantic v2 enforces the Literal keys, but missing keys are still
        # legal (any subset). Require all 4 keys present.
        present = set(self.per_dimension.keys())
        if present != _DIMENSION_KEYS:
            missing = _DIMENSION_KEYS - present
            extra = present - _DIMENSION_KEYS
            raise ValueError(
                f"per_dimension must have exactly 4 keys "
                f"{sorted(_DIMENSION_KEYS)}; missing={sorted(missing)}, "
                f"extra={sorted(extra)}"
            )

        for k, v in self.per_dimension.items():
            if not (0.0 <= v <= 1.0):
                raise ValueError(
                    f"per_dimension[{k!r}]={v} out of range [0.0, 1.0]"
                )

        mean = sum(self.per_dimension.values()) / 4
        if abs(self.overall_score - mean) > _MEAN_TOLERANCE:
            raise ValueError(
                f"overall_score={self.overall_score} disagrees with "
                f"mean(per_dimension)={mean:.4f} by more than "
                f"{_MEAN_TOLERANCE}"
            )
        return self


class TacticalJudge:
    """LLM oracle that scores a (scenario, driver_choice) pair.

    Construction loads the prompt at init time so callers can read
    ``prompt_version`` synchronously for output metadata.

    Fail-soft semantics: ``score()`` returns ``None`` on any error
    (timeout, malformed JSON, validation failure, refusal). The
    aggregator records ``judge_error`` for triage. We do NOT fail loud
    inside scoring because a single bad scenario shouldn't abort a
    50-scenario run.
    """

    def __init__(
        self,
        *,
        openai_client: AsyncOpenAI,
        model: str = "ShoeGPT",
        prompt_path: Path | None = None,
        timeout_seconds: float = 30.0,
    ) -> None:
        self._client = openai_client
        self._model = model
        self._timeout_seconds = timeout_seconds
        prompt_text, prompt_version = load_judge_prompt(prompt_path)
        self._prompt_text = prompt_text
        self.prompt_version: str = prompt_version
        self._log = log.bind(component="TacticalJudge", judge_model=model)

    @property
    def model(self) -> str:
        return self._model

    async def score(
        self,
        scenario: ScenarioEntry,
        *,
        driver_choice_pc_id: str,
        driver_rationale: str | None,
        driver_model: str = "unknown",
    ) -> JudgeVerdict | None:
        """Score one scenario+choice. Returns ``None`` on any failure.

        Wraps the LLM call in a ``traced_eval`` span (D-81) so eval runs
        produce a ``eldritch.eval.judge`` trace per scenario.
        """
        bound = self._log.bind(
            scenario_id=scenario.scenario_id,
            archetype=scenario.archetype,
            driver_model=driver_model,
        )

        user_payload = {
            "scenario": {
                "scenario_id": scenario.scenario_id,
                "archetype": scenario.archetype,
                "monster_stats": scenario.monster_stats.model_dump(),
                "pc_list": [pc.model_dump() for pc in scenario.pc_list],
                "environment": scenario.environment,
                "expected_target_pool": list(scenario.expected_target_pool),
                "expected_avoidance": list(scenario.expected_avoidance),
                "author_rationale": scenario.rationale,
            },
            "driver_choice": {
                "target_pc_id": driver_choice_pc_id,
                "rationale": driver_rationale,
            },
        }
        user_message = json.dumps(user_payload, default=str)

        with traced_eval(
            scenario_id=scenario.scenario_id,
            judge_model=self._model,
            driver_model=driver_model,
            archetype=scenario.archetype,
        ) as span:
            t0 = time.monotonic()
            try:
                completion = await asyncio.wait_for(
                    self._client.chat.completions.create(
                        model=self._model,
                        messages=[
                            {"role": "system", "content": self._prompt_text},
                            {"role": "user", "content": user_message},
                        ],
                        response_format={"type": "json_object"},
                        temperature=0.0,
                        max_tokens=600,
                    ),
                    timeout=self._timeout_seconds,
                )
            except TimeoutError:
                latency_ms = int((time.monotonic() - t0) * 1000)
                bound.warning("judge.timeout", latency_ms=latency_ms)
                span.set_attribute("eldritch.eval.latency_ms", latency_ms)
                span.set_attribute("eldritch.eval.error", "timeout")
                return None
            except Exception as exc:  # noqa: BLE001 — fail-soft per S-12-01-C
                latency_ms = int((time.monotonic() - t0) * 1000)
                bound.warning(
                    "judge.error",
                    latency_ms=latency_ms,
                    error_type=type(exc).__name__,
                    error=str(exc)[:200],
                )
                span.set_attribute("eldritch.eval.latency_ms", latency_ms)
                span.set_attribute(
                    "eldritch.eval.error", type(exc).__name__
                )
                return None

            latency_ms = int((time.monotonic() - t0) * 1000)
            usage = getattr(completion, "usage", None)
            tokens_in = (
                getattr(usage, "prompt_tokens", 0) if usage is not None else 0
            ) or 0
            tokens_out = (
                getattr(usage, "completion_tokens", 0)
                if usage is not None
                else 0
            ) or 0
            span.set_attribute("eldritch.eval.latency_ms", latency_ms)
            span.set_attribute("eldritch.eval.tokens.input", tokens_in)
            span.set_attribute("eldritch.eval.tokens.output", tokens_out)

            try:
                message = completion.choices[0].message
                content = (message.content or "") if message is not None else ""
            except (AttributeError, IndexError, TypeError):
                bound.warning("judge.no_content", latency_ms=latency_ms)
                span.set_attribute("eldritch.eval.error", "refusal")
                return None

            if not content.strip():
                bound.warning("judge.empty", latency_ms=latency_ms)
                span.set_attribute("eldritch.eval.error", "refusal")
                return None

            try:
                verdict = JudgeVerdict.model_validate_json(content)
            except (ValidationError, ValueError, json.JSONDecodeError) as exc:
                bound.warning(
                    "judge.parse_error",
                    latency_ms=latency_ms,
                    raw_preview=content[:200],
                    error_type=type(exc).__name__,
                )
                span.set_attribute("eldritch.eval.error", "parse_error")
                return None

            bound.info(
                "judge.ok",
                latency_ms=latency_ms,
                overall_score=verdict.overall_score,
                approve=verdict.would_a_veteran_dm_approve,
            )
            span.set_attribute("eldritch.eval.overall_score", verdict.overall_score)
            return verdict


__all__ = ["JudgeVerdict", "TacticalJudge", "DimensionKey"]


# Convenience: expose constants we reference in tests.
def _dimension_keys() -> frozenset[str]:  # pragma: no cover — used only by tests
    return _DIMENSION_KEYS


def _mean_tolerance() -> float:  # pragma: no cover — used only by tests
    return _MEAN_TOLERANCE


def _make_judge_verdict_for_testing(
    *,
    overall: float,
    dims: dict[str, float],
    reasoning: str = "test",
    approve: bool = True,
) -> JudgeVerdict:
    """Test helper. Constructs (validates) a JudgeVerdict via raw dict."""
    return JudgeVerdict.model_validate(
        {
            "overall_score": overall,
            "per_dimension": dims,
            "reasoning": reasoning,
            "would_a_veteran_dm_approve": approve,
        }
    )
