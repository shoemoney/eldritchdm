"""eldritch-dm-cache-stats — narration cache aggregation CLI (Phase 18 / NARRCACHE-03).

Reads ``eldritch.narrcache.call`` spans from the Phase 13 SQLite span
buffer and reports hit_rate, total_calls, cached_calls (hits),
rejected_by_gate (store + serve combined), bypass_count, and
total_savings_usd.

v1.5 scope: ``--narration`` only.

Exit codes:
  0 = ok
  1 = user error (bad / missing scope, malformed --since)
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

from eldritch_dm.logging import get_logger
from eldritch_dm.observability.span_buffer import BufferRow, init_buffer

log = get_logger(__name__)

EXIT_OK = 0
EXIT_USER_ERROR = 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="eldritch-dm-cache-stats",
        description=(
            "Aggregate cache statistics from the Phase 13 span buffer. v1.5 "
            "supports the narration cache (Phase 18 NARRCACHE-03)."
        ),
    )
    scope = parser.add_argument_group("scope (exactly one required)")
    scope.add_argument(
        "--narration",
        action="store_true",
        help="Report on the Phase 18 narration cache.",
    )
    parser.add_argument(
        "--since",
        default=None,
        help="Lower bound (UTC). Format: YYYY-MM-DD. Default: 24h ago.",
    )
    parser.add_argument(
        "--until",
        default=None,
        help="Upper bound (UTC). Format: YYYY-MM-DD. Default: now.",
    )
    parser.add_argument(
        "--format",
        choices=("markdown", "json"),
        default="markdown",
        help="Output format. Default: markdown.",
    )
    parser.add_argument(
        "--buffer-path",
        default=None,
        help=(
            "Override the span buffer SQLite path. Default = "
            "$ELDRITCH_SPAN_BUFFER_PATH or ~/.eldritch/spans.sqlite."
        ),
    )
    return parser


def _parse_date(value: str | None, *, default: datetime) -> datetime | None:
    if value is None:
        return default
    try:
        d = datetime.strptime(value, "%Y-%m-%d")
        return d.replace(tzinfo=UTC)
    except ValueError as exc:
        raise ValueError(f"invalid date {value!r}; use YYYY-MM-DD") from exc


def _aggregate(rows: list[BufferRow]) -> dict[str, object]:
    total = len(rows)
    hits = sum(1 for r in rows if r.driver_path == "hit")
    misses = sum(1 for r in rows if r.driver_path == "miss")
    bypass = sum(1 for r in rows if r.driver_path == "bypass")
    rejected_store = sum(1 for r in rows if r.driver_path == "gate_reject_store")
    rejected_serve = sum(1 for r in rows if r.driver_path == "gate_reject_serve")
    rejected = rejected_store + rejected_serve
    denom = hits + misses
    hit_rate = (hits / denom) if denom > 0 else 0.0
    # overall_score column reuses for savings_usd on HIT rows
    total_savings = sum(
        float(r.overall_score)
        for r in rows
        if r.driver_path == "hit" and r.overall_score is not None
    )
    return {
        "total_calls": total,
        "hits": hits,
        "misses": misses,
        "bypass": bypass,
        "rejected_by_gate": rejected,
        "rejected_by_gate_store": rejected_store,
        "rejected_by_gate_serve": rejected_serve,
        "hit_rate": round(hit_rate, 6),
        "total_savings_usd": round(total_savings, 6),
    }


def _format_markdown(stats: dict[str, object], *, since: datetime, until: datetime) -> str:
    return (
        "# Narration cache statistics\n"
        f"\nWindow: {since.isoformat()} → {until.isoformat()}\n\n"
        "| metric                  | value          |\n"
        "|-------------------------|----------------|\n"
        f"| total_calls             | {stats['total_calls']} |\n"
        f"| hits                    | {stats['hits']} |\n"
        f"| misses                  | {stats['misses']} |\n"
        f"| bypass                  | {stats['bypass']} |\n"
        f"| rejected_by_gate (store)| {stats['rejected_by_gate_store']} |\n"
        f"| rejected_by_gate (serve)| {stats['rejected_by_gate_serve']} |\n"
        f"| hit_rate                | {stats['hit_rate']:.4f} |\n"
        f"| total_savings_usd       | ${stats['total_savings_usd']:.6f} |\n"
        "\n"
        "Note: hit_rate is hits / (hits + misses). With temperature ≥ 0.5 in "
        "real narration prompts, deterministic-cache-key collisions are rare; "
        "see Plan 18-01 SUMMARY 'Known limitations' for context.\n"
    )


def _format_json(stats: dict[str, object], *, since: datetime, until: datetime) -> str:
    payload = {
        "window": {"since": since.isoformat(), "until": until.isoformat()},
        "scope": "narration",
        **stats,
    }
    return json.dumps(payload, indent=2)


def _run(args: argparse.Namespace) -> int:
    if not args.narration:
        print(
            "ERROR: must specify a scope. Use --narration.",
            file=sys.stderr,
        )
        return EXIT_USER_ERROR

    now = datetime.now(UTC)
    try:
        since = _parse_date(args.since, default=now - timedelta(days=1))
        until = _parse_date(args.until, default=now)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return EXIT_USER_ERROR

    buffer_path = Path(args.buffer_path) if args.buffer_path else None
    buf = init_buffer(path=buffer_path)
    buf.flush(timeout_s=1.0)
    rows = buf.query(
        since=since,
        until=until,
        span_name="eldritch.narrcache.call",
    )
    stats = _aggregate(rows)

    if args.format == "json":
        print(_format_json(stats, since=since, until=until))
    else:
        print(_format_markdown(stats, since=since, until=until))
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return _run(args)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
