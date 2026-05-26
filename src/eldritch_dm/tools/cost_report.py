"""eldritch-dm-cost-report — offline daily-spend CLI (Phase 13 / MON-03 / D-90).

Reads spans from the local SQLite span buffer (NOT Phoenix — must work
without observability stack) and emits a daily spend report.

Flags:
  --since DATE         start of report range (default 24h ago UTC)
  --until DATE         end of report range (default now UTC)
  --by-model           include per-model breakdown (default on)
  --by-channel         include per-channel breakdown (default off)
  --format json|markdown   output format (default markdown)
  --budget USD         override $ELDRITCH_DAILY_LLM_BUDGET_USD
  --buffer-path PATH   override $ELDRITCH_SPAN_BUFFER_PATH
  --pricing-path PATH  override pricing.yaml location

Exit codes (R-13-03-e):
  0 — ok
  1 — user error (bad date format, etc.)
  2 — partial (unknown_model_count > 0)
  3 — fatal (buffer corrupt — sqlite3.DatabaseError)
"""
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path

from eldritch_dm.logging import get_logger

log = get_logger(__name__)

EXIT_OK = 0
EXIT_USER_ERROR = 1
EXIT_PARTIAL = 2
EXIT_FATAL = 3


@dataclass
class _Args:
    since: datetime
    until: datetime
    by_model: bool
    by_channel: bool
    fmt: str
    budget: Decimal
    buffer_path: Path | None
    pricing_path: Path | None


def _parse_args(argv: list[str]) -> _Args:
    parser = argparse.ArgumentParser(
        prog="eldritch-dm-cost-report",
        description="Daily LLM-spend report from the local span buffer.",
    )
    parser.add_argument("--since", default=None, help="ISO-8601 start (default 24h ago UTC)")
    parser.add_argument("--until", default=None, help="ISO-8601 end (default now UTC)")
    parser.add_argument(
        "--by-model",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Include per-model breakdown (default on)",
    )
    parser.add_argument(
        "--by-channel",
        action="store_true",
        help="Include per-channel breakdown",
    )
    parser.add_argument(
        "--format",
        choices=("json", "markdown"),
        default="markdown",
        dest="fmt",
    )
    parser.add_argument(
        "--budget",
        type=str,
        default=os.environ.get("ELDRITCH_DAILY_LLM_BUDGET_USD", "5.00"),
        help="Override daily budget cap in USD (default $ELDRITCH_DAILY_LLM_BUDGET_USD or 5.00)",
    )
    parser.add_argument("--buffer-path", default=None, type=Path)
    parser.add_argument("--pricing-path", default=None, type=Path)
    ns = parser.parse_args(argv)

    now = datetime.now(UTC)
    if ns.since:
        try:
            since = datetime.fromisoformat(ns.since)
            if since.tzinfo is None:
                since = since.replace(tzinfo=UTC)
        except ValueError as e:
            print(f"error: invalid --since: {e}", file=sys.stderr)
            sys.exit(EXIT_USER_ERROR)
    else:
        since = now - timedelta(hours=24)

    if ns.until:
        try:
            until = datetime.fromisoformat(ns.until)
            if until.tzinfo is None:
                until = until.replace(tzinfo=UTC)
        except ValueError as e:
            print(f"error: invalid --until: {e}", file=sys.stderr)
            sys.exit(EXIT_USER_ERROR)
    else:
        until = now

    try:
        budget = Decimal(ns.budget)
    except Exception:
        print(f"error: invalid --budget: {ns.budget!r}", file=sys.stderr)
        sys.exit(EXIT_USER_ERROR)

    return _Args(
        since=since,
        until=until,
        by_model=ns.by_model,
        by_channel=ns.by_channel,
        fmt=ns.fmt,
        budget=budget,
        buffer_path=ns.buffer_path,
        pricing_path=ns.pricing_path,
    )


def _date_range(start: datetime, end: datetime) -> list[date]:
    """Yield each UTC date in [start, end), inclusive of start day."""
    out: list[date] = []
    cursor = start.date()
    end_date = end.date()
    while cursor <= end_date:
        out.append(cursor)
        cursor = cursor + timedelta(days=1)
    return out


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])

    # Set up env BEFORE importing observability modules — buffer path is read
    # at init_buffer() time.
    if args.buffer_path is not None:
        os.environ["ELDRITCH_SPAN_BUFFER_PATH"] = str(args.buffer_path)
    if args.pricing_path is not None:
        os.environ["ELDRITCH_PRICING_YAML"] = str(args.pricing_path)

    try:
        from eldritch_dm.observability.cost import load_pricing, sum_daily_spend
        from eldritch_dm.observability.span_buffer import init_buffer
    except Exception as e:  # noqa: BLE001
        print(f"error: failed to import observability: {e}", file=sys.stderr)
        return EXIT_FATAL

    # Settings shim — we only need pricing_yaml_path if --pricing-path was set.
    class _Shim:
        pricing_yaml_path = args.pricing_path

    try:
        table = load_pricing(_Shim())
    except Exception as e:  # noqa: BLE001
        print(f"error: failed to load pricing: {e}", file=sys.stderr)
        return EXIT_FATAL

    try:
        buf = init_buffer()
    except sqlite3.DatabaseError as e:
        print(f"error: span buffer is corrupt: {e}", file=sys.stderr)
        return EXIT_FATAL

    # Iterate over UTC days in the range; aggregate.
    days = _date_range(args.since, args.until)
    per_day = []
    total_usd = Decimal(0)
    total_unknown = 0
    total_sample = 0
    grand_by_model: dict[str, Decimal] = {}
    grand_by_channel: dict[str, Decimal] = {}

    for d in days:
        # Only aggregate the slice of the day that overlaps [since, until).
        day_start = datetime.combine(d, time.min, tzinfo=UTC)
        day_end = day_start + timedelta(days=1)
        effective_start = max(day_start, args.since)
        effective_end = min(day_end, args.until)
        if effective_start >= effective_end:
            continue
        # For simplicity v1.2 always reports full UTC days; partial-day
        # filtering would need a finer sum_daily_spend variant (deferred to v1.3).
        try:
            breakdown = sum_daily_spend(buf, on_date=d, table=table)
        except sqlite3.DatabaseError as e:
            print(f"error: span buffer query failed: {e}", file=sys.stderr)
            return EXIT_FATAL
        per_day.append(breakdown)
        total_usd += breakdown.total_usd
        total_unknown += breakdown.unknown_model_count
        total_sample += breakdown.sample_size
        for m, c in breakdown.by_model.items():
            grand_by_model[m] = grand_by_model.get(m, Decimal(0)) + c
        for ch, c in breakdown.by_channel.items():
            grand_by_channel[ch] = grand_by_channel.get(ch, Decimal(0)) + c

    over_budget = total_usd > args.budget

    if args.fmt == "json":
        out = {
            "since": args.since.isoformat(),
            "until": args.until.isoformat(),
            "total_usd": str(total_usd),
            "by_model": (
                {k: str(v) for k, v in grand_by_model.items()} if args.by_model else None
            ),
            "by_channel": (
                {k: str(v) for k, v in grand_by_channel.items()}
                if args.by_channel
                else None
            ),
            "unknown_model_count": total_unknown,
            "sample_size": total_sample,
            "budget_usd": str(args.budget),
            "over_budget": over_budget,
            "generated_at_utc": datetime.now(UTC).isoformat(),
        }
        print(json.dumps(out, indent=2))
    else:
        lines = [
            "# EldritchDM Cost Report",
            "",
            f"- **Range:** `{args.since.isoformat()}` → `{args.until.isoformat()}`",
            f"- **Total spend:** ${total_usd}",
            f"- **Daily budget cap:** ${args.budget}",
            f"- **Over budget:** {'⚠ YES' if over_budget else 'no'}",
            f"- **Span sample size:** {total_sample}",
        ]
        if total_unknown > 0:
            lines.append(
                f"- **Unknown-model spans:** {total_unknown} (excluded from totals)"
            )
        if args.by_model and grand_by_model:
            lines.append("")
            lines.append("## By model")
            lines.append("| Model | USD |")
            lines.append("|-------|-----|")
            for m, c in sorted(
                grand_by_model.items(), key=lambda kv: kv[1], reverse=True
            ):
                lines.append(f"| `{m}` | ${c} |")
        if args.by_channel and grand_by_channel:
            lines.append("")
            lines.append("## By channel")
            lines.append("| Channel | USD |")
            lines.append("|---------|-----|")
            for ch, c in sorted(
                grand_by_channel.items(), key=lambda kv: kv[1], reverse=True
            ):
                lines.append(f"| `{ch}` | ${c} |")
        print("\n".join(lines))

    if total_unknown > 0:
        return EXIT_PARTIAL
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
