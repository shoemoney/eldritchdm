"""
Tests for eldritch_dm.safety.sanitizer.

Loads injection_cases.yaml adversarial corpus and runs each case.
Also tests audit callback, bounded iterations, and sync guarantees.
"""

from __future__ import annotations

import inspect
import re
from pathlib import Path

import pytest
import yaml

from eldritch_dm.persistence.models import SanitizerAuditRow
from eldritch_dm.safety.sanitizer import (
    DEFAULT_BLACKLIST,
    SanitizedInput,
    make_async_audit_callback,
    sanitize_player_input,
)

# ── Corpus helpers ─────────────────────────────────────────────────────────────

CORPUS_PATH = Path("src/eldritch_dm/safety/corpus/injection_cases.yaml")


def _expand_raw(case: dict) -> str:
    """Expand raw_repeat entries into a literal string."""
    if "raw" in case:
        return case["raw"]
    rr = case["raw_repeat"]
    char = rr.get("char", "")
    count = rr.get("count", 0)
    prefix = rr.get("prefix", "")
    suffix = rr.get("suffix", "")
    return prefix + (char * count) + suffix


def load_corpus() -> list[dict]:
    data = yaml.safe_load(CORPUS_PATH.read_text(encoding="utf-8"))
    cases = data["cases"]
    # Expand raw_repeat entries
    for case in cases:
        if "raw_repeat" in case:
            case["raw"] = _expand_raw(case)
    return cases


_CORPUS = load_corpus()


def _extract_inner(wrapped: str) -> str:
    """Extract the text between <player_action ...> and </player_action>."""
    m = re.search(r"<player_action[^>]*>(.*)</player_action>", wrapped, re.DOTALL)
    return m.group(1) if m else ""


# ── Corpus count ──────────────────────────────────────────────────────────────


def test_corpus_has_at_least_30():
    assert len(_CORPUS) >= 30, f"Expected >= 30 corpus cases, got {len(_CORPUS)}"


# ── Parametrized corpus tests ─────────────────────────────────────────────────


@pytest.mark.parametrize("case", _CORPUS, ids=lambda c: c["id"])
def test_sanitizer_case(case: dict) -> None:
    raw = case["raw"]
    speaker = case.get("speaker", "Thorin")
    user_id = case.get("user_id", "111")
    expect = case["expect"]

    result = sanitize_player_input(
        raw,
        speaker=speaker,
        user_id=user_id,
        channel_id="999",
        max_chars=500,
    )

    assert isinstance(result, SanitizedInput)

    # truncated
    assert result.truncated == expect["truncated"], (
        f"[{case['id']}] truncated: got {result.truncated}, expected {expect['truncated']}"
    )

    # min_stripped
    min_s = expect.get("min_stripped", 0)
    assert len(result.stripped_tokens) >= min_s, (
        f"[{case['id']}] stripped_tokens: got {len(result.stripped_tokens)}, "
        f"expected >= {min_s}. tokens={result.stripped_tokens!r}"
    )

    # wrapped_contains
    if "wrapped_contains" in expect:
        assert expect["wrapped_contains"] in result.wrapped, (
            f"[{case['id']}] wrapped_contains: {expect['wrapped_contains']!r} not in:\n{result.wrapped!r}"
        )

    # wrapped_not_contains (literal)
    if "wrapped_not_contains" in expect:
        inner = _extract_inner(result.wrapped)
        assert expect["wrapped_not_contains"] not in inner, (
            f"[{case['id']}] wrapped_not_contains: {expect['wrapped_not_contains']!r} still in inner body:\n{inner!r}"
        )

    # wrapped_not_contains_ci (case-insensitive, applied to inner body)
    if "wrapped_not_contains_ci" in expect:
        inner = _extract_inner(result.wrapped)
        assert expect["wrapped_not_contains_ci"].lower() not in inner.lower(), (
            f"[{case['id']}] wrapped_not_contains_ci: {expect['wrapped_not_contains_ci']!r} still in inner body (ci):\n{inner!r}"
        )

    # wrapped_contains_inner (exact substring in inner body)
    if "wrapped_contains_inner" in expect:
        inner = _extract_inner(result.wrapped)
        assert expect["wrapped_contains_inner"] in inner, (
            f"[{case['id']}] wrapped_contains_inner: {expect['wrapped_contains_inner']!r} not in inner:\n{inner!r}"
        )

    # wrapped_contains_body (exact equality of inner body)
    if "wrapped_contains_body" in expect:
        inner = _extract_inner(result.wrapped)
        assert inner == expect["wrapped_contains_body"], (
            f"[{case['id']}] wrapped_contains_body: got {inner!r}, expected {expect['wrapped_contains_body']!r}"
        )


# ── Audit callback ─────────────────────────────────────────────────────────────


def test_audit_callback_fires_on_strip():
    rows: list[SanitizerAuditRow] = []

    def cb(row: SanitizerAuditRow) -> None:
        rows.append(row)

    sanitize_player_input(
        "I attack <tool_call>x</tool_call>",
        speaker="Thorin",
        user_id="42",
        channel_id="chan-1",
        audit_callback=cb,
    )

    assert len(rows) == 1
    assert rows[0].channel_id == "chan-1"
    assert len(rows[0].stripped_tokens) >= 1


def test_audit_callback_fires_on_truncate():
    rows: list[SanitizerAuditRow] = []

    def cb(row: SanitizerAuditRow) -> None:
        rows.append(row)

    sanitize_player_input(
        "A" * 600,
        speaker="Thorin",
        user_id="42",
        channel_id="chan-1",
        audit_callback=cb,
    )

    assert len(rows) == 1
    assert rows[0].truncated is True


def test_no_audit_for_clean_input():
    rows: list[SanitizerAuditRow] = []

    def cb(row: SanitizerAuditRow) -> None:
        rows.append(row)

    sanitize_player_input(
        "I simply swing my sword",
        speaker="Thorin",
        user_id="42",
        channel_id="chan-1",
        audit_callback=cb,
    )

    assert len(rows) == 0, "Callback should NOT fire for clean input"


# ── make_async_audit_callback ─────────────────────────────────────────────────


async def test_make_async_audit_callback_routes_to_repo(bootstrapped_db_with_repos):
    """make_async_audit_callback wires correctly; audit row count increments."""

    db_path, wq, _, _, _, audit_repo, _ = bootstrapped_db_with_repos

    loop = __import__("asyncio").get_event_loop()
    cb = make_async_audit_callback(audit_repo, loop=loop)

    before = await audit_repo.count()

    sanitize_player_input(
        "I attack <tool_call>{}</tool_call>",
        speaker="Thorin",
        user_id="42",
        channel_id="chan-1",
        audit_callback=cb,
    )

    # Give the fire-and-forget time to flush
    import asyncio
    await asyncio.sleep(0.1)

    after = await audit_repo.count()
    assert after == before + 1


# ── Bounded iterations ─────────────────────────────────────────────────────────


def test_bounded_iterations():
    """Pathological overlapping input terminates in <= 64 passes."""
    # Nested tool calls that reveal new tokens after each strip
    evil = "<tool_call>" * 64 + "x" + "</tool_call>" * 64
    result = sanitize_player_input(
        evil,
        speaker="Thorin",
        user_id="42",
        channel_id="chan-1",
    )
    # Function must return (not hang); all tokens should be stripped
    assert isinstance(result, SanitizedInput)
    assert "<tool_call>" not in result.cleaned
    assert "</tool_call>" not in result.cleaned


def test_bounded_iterations_deterministic():
    """Same input produces same output on two runs."""
    evil = "<tool_call>" * 10 + "text" + "</tool_call>" * 10
    r1 = sanitize_player_input(evil, speaker="A", user_id="1", channel_id="c")
    r2 = sanitize_player_input(evil, speaker="A", user_id="1", channel_id="c")
    assert r1.cleaned == r2.cleaned
    assert len(r1.stripped_tokens) == len(r2.stripped_tokens)


# ── Sync guarantee ────────────────────────────────────────────────────────────


def test_sanitizer_is_sync():
    assert not inspect.iscoroutinefunction(sanitize_player_input), (
        "sanitize_player_input must be a sync function (no async)"
    )


# ── DEFAULT_BLACKLIST count ────────────────────────────────────────────────────


def test_default_blacklist_count():
    assert len(DEFAULT_BLACKLIST) == 13
