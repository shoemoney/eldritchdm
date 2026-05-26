"""Phase 27 / PROFILE-01 / D-209 — Baseline JSON schema.

Pydantic v2 model that validates the JSON emitted by
``scripts/perf/profile_hot_paths.py`` and the committed baselines at
``.planning/perf-baseline-v{version}.json``.

Schema (D-209):

    {
      "version": "1.9.0",
      "git_sha": "...",
      "generated_at": "ISO 8601",
      "operations": {
        "<operation-name>": {
          "p50_ms": float,
          "p95_ms": float,
          "p99_ms": float,
          "iterations": int,
          "cprofile_top_10": ["module.func:lineno (cumtime_pct)", ...]
        },
        ...
      }
    }

Sub-paths are recorded as dotted operation keys (e.g.,
``"mcp-cache-roundtrip.l1-hit"``).
"""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class OperationStats(BaseModel):
    """Per-operation latency + profile snapshot."""

    p50_ms: float = Field(ge=0.0)
    p95_ms: float = Field(ge=0.0)
    p99_ms: float = Field(ge=0.0)
    iterations: int = Field(ge=1)
    cprofile_top_10: list[str] = Field(default_factory=list)

    @field_validator("cprofile_top_10")
    @classmethod
    def _top_10_size(cls, v: list[str]) -> list[str]:
        if len(v) > 10:
            raise ValueError(f"cprofile_top_10 must contain ≤10 entries (got {len(v)})")
        return v


class BaselineSchema(BaseModel):
    """The full baseline JSON document. Matches D-209 exactly."""

    version: str
    git_sha: str
    generated_at: str
    operations: dict[str, OperationStats]

    @field_validator("operations")
    @classmethod
    def _at_least_one_op(cls, v: dict[str, OperationStats]) -> dict[str, OperationStats]:
        if not v:
            raise ValueError("operations must contain at least one entry")
        return v
