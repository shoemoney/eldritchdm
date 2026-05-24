"""Tests for the cost calculator (Phase 13 / MON-03 / Task 02).

The ±5% accuracy corpus compares ``calculate_cost(...)`` against expected
USD values **computed from the values in pricing.yaml itself** — operators
who refresh pricing don't have to chase down hardcoded constants. The
assertions are internally consistent: if pricing.yaml drifts vs reality,
that's an operator-doc problem, not a calculator-correctness problem.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from eldritch_dm.observability.cost import (
    DEFAULT_PRICING_TABLE,
    PricingEntry,
    calculate_cost,
    load_pricing,
    sum_daily_spend,
)
from eldritch_dm.observability.span_buffer import BufferRow, init_buffer, reset_for_tests


@pytest.fixture(autouse=True)
def _isolate(monkeypatch, tmp_path):
    monkeypatch.setenv("ELDRITCH_SPAN_BUFFER_PATH", str(tmp_path / "spans.sqlite"))
    reset_for_tests()
    yield
    reset_for_tests()


# ── Loader ──────────────────────────────────────────────────────────────────


def test_load_pricing_parses_repo_default():
    table = load_pricing(MagicMock(pricing_yaml_path=None))
    # All 6 expected models present (5 cloud + ShoeGPT).
    expected_models = {
        "gpt-4o",
        "gpt-4o-mini",
        "claude-haiku-4-5-20251001",
        "claude-sonnet-4-6",
        "claude-opus-4-7",
        "shoegpt",
    }
    assert set(table.entries.keys()) == expected_models


def test_loader_env_override(tmp_path):
    override = tmp_path / "custom_pricing.yaml"
    override.write_text(
        """\
version: 1
entries:
  - model: my-test-model
    input_per_million_usd: "1.23"
    output_per_million_usd: "4.56"
    currency: USD
    source_url: test-url
    also_verified_at: test-url-2
    as_of: 2026-05-24
""",
        encoding="utf-8",
    )
    table = load_pricing(MagicMock(pricing_yaml_path=override))
    entry = table.lookup("my-test-model")
    assert entry is not None
    assert entry.input_per_million_usd == Decimal("1.23")


def test_loader_fails_soft_on_parse_error(tmp_path):
    bad = tmp_path / "p.yaml"
    bad.write_text("version: 1\nentries: [unclosed\n", encoding="utf-8")
    table = load_pricing(MagicMock(pricing_yaml_path=bad))
    # Falls back to DEFAULT_PRICING_TABLE (ShoeGPT only).
    assert "shoegpt" in table.entries
    assert "gpt-4o" not in table.entries


# ── Calculator ──────────────────────────────────────────────────────────────


def test_calculate_cost_shoegpt_is_zero():
    table = load_pricing(MagicMock(pricing_yaml_path=None))
    cost = calculate_cost("ShoeGPT", 1000, 500, table)
    assert cost == Decimal("0.000000")


def test_calculate_cost_unknown_model_returns_zero():
    table = DEFAULT_PRICING_TABLE
    cost = calculate_cost("model-from-typo", 1000, 500, table)
    assert cost == Decimal(0)


def test_calculate_cost_case_insensitive():
    table = load_pricing(MagicMock(pricing_yaml_path=None))
    a = calculate_cost("GPT-4o", 1000, 500, table)
    b = calculate_cost("gpt-4o", 1000, 500, table)
    assert a == b
    assert a > 0


def test_calculate_cost_matches_yaml_rates_within_5pct():
    """5-workload corpus (R-13-03-f) — expected USD computed from YAML rates."""
    table = load_pricing(MagicMock(pricing_yaml_path=None))

    workloads = [
        # (name, model, tin, tout) — expected_usd computed from YAML rates
        ("small_chat_gpt4o_mini", "gpt-4o-mini", 100, 200),
        ("large_chat_gpt4o", "gpt-4o", 4000, 800),
        ("judge_eval_sonnet", "claude-sonnet-4-6", 1500, 400),
        ("cheap_judge_haiku", "claude-haiku-4-5-20251001", 1500, 400),
        ("local_shoegpt", "ShoeGPT", 1000, 500),
    ]

    for name, model, tin, tout in workloads:
        entry = table.lookup(model)
        assert entry is not None, f"missing pricing for {model}"
        expected = (
            Decimal(tin) * entry.input_per_million_usd
            + Decimal(tout) * entry.output_per_million_usd
        ) / Decimal(1_000_000)
        actual = calculate_cost(model, tin, tout, table)
        # ±5% tolerance — for ShoeGPT (expected=0) we just assert exact match.
        if expected == 0:
            assert actual == Decimal(0), f"{name}: ShoeGPT should be $0"
        else:
            ratio = abs(actual - expected) / expected
            assert ratio <= Decimal("0.05"), (
                f"{name}: actual=${actual} expected=${expected} drift={ratio*100:.2f}%"
            )


def test_pricing_entry_extra_field_forbidden():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        PricingEntry(
            model="x",
            input_per_million_usd=Decimal("1"),
            output_per_million_usd=Decimal("2"),
            currency="USD",
            source_url="u",
            also_verified_at="v",
            as_of="2026-05-24",  # type: ignore[arg-type]
            extra_field="boom",  # type: ignore[call-arg]
        )


# ── Daily-spend aggregator ──────────────────────────────────────────────────


def test_sum_daily_spend_aggregates_by_model_and_channel():
    table = load_pricing(MagicMock(pricing_yaml_path=None))
    buf = init_buffer()
    today = datetime(2026, 5, 24, 10, 0, 0, tzinfo=UTC).date()
    # 2 translate spans on gpt-4o-mini, 1 on ShoeGPT, 1 unknown model
    buf.record(
        BufferRow(
            span_name="eldritch.ingest.translate",
            channel_id="c1",
            model="gpt-4o-mini",
            latency_ms=100,
            tokens_input=1000,
            tokens_output=500,
            timestamp_utc=datetime(2026, 5, 24, 10, 0, 0, tzinfo=UTC),
        )
    )
    buf.record(
        BufferRow(
            span_name="eldritch.ingest.translate",
            channel_id="c2",
            model="gpt-4o-mini",
            latency_ms=100,
            tokens_input=500,
            tokens_output=200,
            timestamp_utc=datetime(2026, 5, 24, 10, 5, 0, tzinfo=UTC),
        )
    )
    buf.record(
        BufferRow(
            span_name="eldritch.ingest.translate",
            channel_id="c1",
            model="ShoeGPT",
            latency_ms=100,
            tokens_input=2000,
            tokens_output=1000,
            timestamp_utc=datetime(2026, 5, 24, 11, 0, 0, tzinfo=UTC),
        )
    )
    buf.record(
        BufferRow(
            span_name="eldritch.ingest.translate",
            channel_id="c3",
            model="some-unknown-model",
            latency_ms=100,
            tokens_input=500,
            tokens_output=100,
            timestamp_utc=datetime(2026, 5, 24, 12, 0, 0, tzinfo=UTC),
        )
    )
    # And an old row from yesterday — must be excluded.
    buf.record(
        BufferRow(
            span_name="eldritch.ingest.translate",
            channel_id="c1",
            model="gpt-4o-mini",
            latency_ms=100,
            tokens_input=9999,
            tokens_output=9999,
            timestamp_utc=datetime(2026, 5, 23, 23, 0, 0, tzinfo=UTC),
        )
    )
    buf.flush(timeout_s=3.0)

    breakdown = sum_daily_spend(buf, on_date=today, table=table)
    assert breakdown.unknown_model_count == 1
    assert breakdown.sample_size == 4
    # ShoeGPT contributes $0 — total = 2 gpt-4o-mini calls.
    assert breakdown.total_usd > 0
    assert "gpt-4o-mini" in breakdown.by_model
    assert breakdown.by_model.get("ShoeGPT", Decimal(0)) == Decimal(0)
    assert "c1" in breakdown.by_channel


def test_sum_daily_spend_empty_buffer():
    buf = init_buffer()
    table = load_pricing(MagicMock(pricing_yaml_path=None))
    today = datetime.now(UTC).date()
    breakdown = sum_daily_spend(buf, on_date=today, table=table)
    assert breakdown.total_usd == Decimal(0)
    assert breakdown.sample_size == 0
    assert breakdown.unknown_model_count == 0


def test_sum_daily_spend_excludes_zero_token_rows():
    """Rows with 0 in + 0 out (cache hits, random driver) don't count."""
    buf = init_buffer()
    table = DEFAULT_PRICING_TABLE
    today = datetime.now(UTC).date()
    buf.record(
        BufferRow(
            span_name="eldritch.monster.decision",
            monster_id="m",
            channel_id="c",
            combat_round=1,
            driver_path="cache",
            latency_ms=0,
            tokens_input=0,
            tokens_output=0,
        )
    )
    buf.flush(timeout_s=3.0)
    breakdown = sum_daily_spend(buf, on_date=today, table=table)
    assert breakdown.sample_size == 0
    assert breakdown.total_usd == Decimal(0)


def test_pricing_table_lookup_returns_none_for_empty_string():
    table = load_pricing(MagicMock(pricing_yaml_path=None))
    assert table.lookup("") is None
