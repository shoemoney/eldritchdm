"""Cost calculator + daily-spend aggregator (Phase 13 / MON-03 / D-89).

Maps ``(model, tokens_input, tokens_output) → USD`` against
``database/pricing.yaml`` (3-tier loader). Returns ``Decimal`` to keep
cumulative daily totals exact — float arithmetic on currency drifts.

Unknown models log a structured warning and contribute ``Decimal(0)`` to the
total; the cost-report CLI flags any non-zero unknown-model count so
operators can audit.

The ±5% accuracy test in ``tests/observability/test_cost.py`` compares the
calculator against the values in ``database/pricing.yaml`` itself —
operators who refresh pricing don't have to chase down hardcoded constants.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import TYPE_CHECKING, Literal

import yaml
from pydantic import BaseModel, ConfigDict, ValidationError

from eldritch_dm.logging import get_logger
from eldritch_dm.observability.span_buffer import SpanBuffer, init_buffer

if TYPE_CHECKING:
    from eldritch_dm.config import Settings

log = get_logger(__name__)


# ── Schema ──────────────────────────────────────────────────────────────────


class PricingEntry(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    model: str
    input_per_million_usd: Decimal
    output_per_million_usd: Decimal
    currency: Literal["USD"]
    source_url: str
    also_verified_at: str
    as_of: date


class PricingFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int = 1
    entries: list[PricingEntry]


# ── Lookup table ────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class PricingTable:
    """Frozen dict-of-entries keyed by lowercase model name."""

    entries: dict[str, PricingEntry]

    def lookup(self, model: str) -> PricingEntry | None:
        if not model:
            return None
        return self.entries.get(model.lower())


# Built-in default — ShoeGPT only ($0.00) so degraded operation never raises.
DEFAULT_PRICING_TABLE = PricingTable(
    entries={
        "shoegpt": PricingEntry(
            model="ShoeGPT",
            input_per_million_usd=Decimal("0.00"),
            output_per_million_usd=Decimal("0.00"),
            currency="USD",
            source_url="local-inference-on-operator-hardware",
            also_verified_at="local-inference-on-operator-hardware",
            as_of=date(2026, 5, 24),
        )
    }
)


# ── Loader ──────────────────────────────────────────────────────────────────


def _resolve_path(settings: Settings | None) -> Path | None:
    if settings is not None:
        env_path = getattr(settings, "pricing_yaml_path", None)
        if env_path is not None:
            p = Path(env_path)
            if p.is_file():
                return p

    per_install = Path.home() / ".eldritch" / "pricing.yaml"
    if per_install.is_file():
        return per_install

    in_repo = Path(__file__).resolve().parents[3] / "database" / "pricing.yaml"
    if in_repo.is_file():
        return in_repo

    return None


def load_pricing(settings: Settings | None = None) -> PricingTable:
    """Resolve the pricing table. Fail-soft to DEFAULT_PRICING_TABLE."""
    try:
        path = _resolve_path(settings)
        if path is None:
            log.warning("pricing.fallback", reason="no_pricing_yaml_found")
            return DEFAULT_PRICING_TABLE

        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8"))  # noqa: S506
        except yaml.YAMLError as e:
            log.warning(
                "pricing.fallback",
                reason="yaml_parse_error",
                error=str(e),
                source=str(path),
            )
            return DEFAULT_PRICING_TABLE

        if raw is None:
            log.warning("pricing.fallback", reason="empty_yaml_file", source=str(path))
            return DEFAULT_PRICING_TABLE

        try:
            parsed = PricingFile.model_validate(raw)
        except ValidationError as e:
            log.warning(
                "pricing.fallback",
                reason="schema_validation_error",
                error=str(e),
                source=str(path),
            )
            return DEFAULT_PRICING_TABLE

        if parsed.version != 1:
            log.warning(
                "pricing.fallback",
                reason="unsupported_schema_version",
                version=parsed.version,
                source=str(path),
            )
            return DEFAULT_PRICING_TABLE

        table = PricingTable(
            entries={e.model.lower(): e for e in parsed.entries}
        )
        log.info(
            "pricing.resolved",
            source=str(path),
            count=len(table.entries),
            models=sorted(table.entries.keys()),
        )
        return table

    except Exception as e:  # noqa: BLE001
        log.warning("pricing.fallback", reason=e.__class__.__name__, error=str(e))
        return DEFAULT_PRICING_TABLE


# ── Calculator ──────────────────────────────────────────────────────────────


_PER_MILLION = Decimal("1000000")
_SIX_DECIMALS = Decimal("0.000001")


def calculate_cost(
    model: str,
    tokens_input: int,
    tokens_output: int,
    table: PricingTable,
) -> Decimal:
    """Return the USD cost for one LLM call. Unknown model → Decimal(0)."""
    entry = table.lookup(model)
    if entry is None:
        log.warning("eldritch.cost.unknown_model", model=model)
        return Decimal(0)
    cost = (
        Decimal(tokens_input) * entry.input_per_million_usd
        + Decimal(tokens_output) * entry.output_per_million_usd
    ) / _PER_MILLION
    return cost.quantize(_SIX_DECIMALS, rounding=ROUND_HALF_UP)


# ── Daily-spend aggregator ──────────────────────────────────────────────────


@dataclass(frozen=True)
class DailySpendBreakdown:
    """Per-day spend summary returned by ``sum_daily_spend``."""

    on_date: date
    total_usd: Decimal
    by_model: dict[str, Decimal]
    by_channel: dict[str, Decimal]
    unknown_model_count: int
    sample_size: int


def sum_daily_spend(
    buffer: SpanBuffer | None = None,
    *,
    on_date: date,
    table: PricingTable,
) -> DailySpendBreakdown:
    """Aggregate USD spend over the UTC day ``[on_date 00:00, on_date+1 00:00)``."""
    buf = buffer or init_buffer()
    buf.flush(timeout_s=1.0)
    start = datetime.combine(on_date, time.min, tzinfo=UTC)
    end = start + timedelta(days=1)

    # Pull spans across all kinds — decision, translate, eval all contribute
    # token spend.
    rows = buf.query(since=start, until=end)
    by_model: dict[str, Decimal] = {}
    by_channel: dict[str, Decimal] = {}
    total = Decimal(0)
    unknown = 0
    sample = 0

    for r in rows:
        # Only rows with token counts contribute spend; skip cache/random rows
        # (where tokens are 0 or None).
        if (r.tokens_input or 0) == 0 and (r.tokens_output or 0) == 0:
            continue
        sample += 1
        model = r.model or _model_for_decision_row(r)
        if model is None:
            unknown += 1
            continue
        entry = table.lookup(model)
        if entry is None:
            unknown += 1
            continue
        cost = calculate_cost(
            model,
            r.tokens_input or 0,
            r.tokens_output or 0,
            table,
        )
        total += cost
        by_model[model] = by_model.get(model, Decimal(0)) + cost
        if r.channel_id is not None:
            by_channel[r.channel_id] = by_channel.get(
                r.channel_id, Decimal(0)
            ) + cost

    return DailySpendBreakdown(
        on_date=on_date,
        total_usd=total.quantize(_SIX_DECIMALS, rounding=ROUND_HALF_UP),
        by_model=by_model,
        by_channel=by_channel,
        unknown_model_count=unknown,
        sample_size=sample,
    )


def _model_for_decision_row(row) -> str | None:
    """Decision rows don't carry an explicit model column.

    The bot uses a single LLM for monster decisions (the SmartMonsterDriver's
    configured model). For v1.2 we default decision-row spans to "ShoeGPT"
    (the canonical local model from CLAUDE.md). Operators using a cloud
    backend will see decision spans miss the per-model breakdown until a
    follow-up phase adds an explicit `model` attribute to the span schema
    (deferred — flagged for v1.3).
    """
    if row.span_name == "eldritch.monster.decision":
        return "ShoeGPT"
    return None
