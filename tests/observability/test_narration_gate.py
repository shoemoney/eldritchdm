"""Unit tests for NarrCacheGate (Phase 18 / NARRCACHE-02).

Per-pattern positive (gate rejects the canonical example) + negative
(similar-looking text that should pass) coverage. The corpus-level 0%
false-negative bar lives in ``tests/eval/test_narration_gate_corpus.py``;
these tests pin individual regex behavior so a regex tweak fails the most
specific test first.
"""

from __future__ import annotations

import pytest

from eldritch_dm.observability.narration_cache import (
    _GATE_PATTERNS,
    NarrCacheGate,
)

# ── Positive (gate MUST reject) ─────────────────────────────────────────────


@pytest.mark.parametrize(
    "text",
    [
        # HP / hit points
        "Your HP drops",
        "Your hit points are low",
        "Your hit point pool is exhausted",
        "remaining hp50 score",  # hpNN literal
        # AC / armor class
        "Their AC is 17",
        "Their armor class is high",
        "Their armour class is high",
        # damage / dmg / takes-N / deals-N
        "She deals damage",
        "Roll 1d8 dmg",
        "He takes 5 wounds",
        "She deals 12 with the axe",
        "She was reduced to 0",
        "His HP drops to 7",
        "She falls to 0 hit points",
        # crit / natural N
        "A critical hit lands",
        "What a crit",
        "He rolled a natural 20",
        # save / DC
        "Make a saving throw",
        "He saves against fear",
        "DC 15 check",
        "DC15 check",  # no space variant
        # conditions (stems)
        "She is paralyzed by fear",
        "He was stunned for a moment",
        "The fey charmed the bard",
        "The party is frightened",
        "He was grappled and held",
        "She felt incapacitated",
        "He felt the petrifying gaze",
        "A poisoned dart",
        "He was restrained",
        "She fell unconscious",
        # condition complete words
        "He fell prone in the mud",
        "Her status changed",
        "A condition was applied",
        "She became invisible",
        # dice / hp assignment
        "Roll 2d6",
        "He has 4 hit dice left",
        "hp=12 confirmed",
        "hp: 7 noted",
        # sentinels
        "Echoed back <player_action> contents",
        "Echoed back <damage> sentinel",
        "Echoed back <effect> sentinel",
    ],
)
def test_gate_rejects_mechanical(text: str) -> None:
    assert NarrCacheGate.is_pure_narration(text) is False, (
        f"Gate FAILED to reject mechanical text: {text!r}"
    )


# ── Negative (gate MUST accept) ─────────────────────────────────────────────


@pytest.mark.parametrize(
    "text",
    [
        "The tavern smells of woodsmoke and stew.",
        "Old Vahn nods solemnly and pours the cup.",
        "Lanterns sway against a salt-bitter wind.",
        # adversarial near-misses — must NOT match
        "He took 2 steps forward",  # 'took' not 'takes', not 'deals'
        "She fell to one knee",  # 'fell to one knee' has no digit after 'to'
        "The dealer arrived",  # 'deal' substring but not '\bdeals\b' followed by digit
        "She promoted him",  # 'promoted' must not match \bprone\b
        # 'prone' is a complete word — explicit check below:
        "She demoted the captain",
        "The shopkeeper's invitation arrived",
        # 'crit' boundary — 'critique' is allowed if the gate uses \bcrit\b; verify
        # that 'critique' is rejected? Per spec, \bcrit\b matches "crit" but
        # \bcrit\b\w*-style is NOT in our pattern set. Confirm \bcrit\b only.
        "Her critique was sharp but kind.",
        # 'condition' is rejected (whole word). Confirm 'conditioner' is rejected
        # too (\bcondition\b matches the prefix substring of 'conditioner'?
        # actually \bcondition\b requires \b AFTER 'condition' — 'conditioner'
        # has letter 'e' after 'condition' so no \b — must NOT match.
        "The hair conditioner is on the shelf.",
        # 'invisible' rejected; 'invisibly' is NOT a complete word match (\b
        # after 'invisible' fails because 'y' follows).
        "She moved invisibly through the alley.",
        # 'status' rejected; 'statuses' is not a complete-word match.
        "Two statuesque guardians flank the door.",
        # number contexts that should NOT trip
        "The tower has 2 windows facing east.",
        "Old maps showed seven roads, but only three remained.",
        # 'dn' notation must require digit-d-digit; '4d-printed' shouldn't match
        "A 4d-printed brass coin lay on the table.",
        # narration with quoted dialogue
        '"By the gods, the moon is huge tonight," she whispered.',
        # quest-hook style
        "The innkeeper leans close and offers a discreet job.",
    ],
)
def test_gate_accepts_pure_narration(text: str) -> None:
    assert NarrCacheGate.is_pure_narration(text) is True, (
        f"Gate WRONGLY rejected pure narration: {text!r}"
    )


# ── Edge cases ──────────────────────────────────────────────────────────────


def test_gate_accepts_empty_string() -> None:
    assert NarrCacheGate.is_pure_narration("") is True


def test_gate_accepts_whitespace_only() -> None:
    assert NarrCacheGate.is_pure_narration("   \n\t  ") is True


def test_gate_case_insensitive() -> None:
    assert NarrCacheGate.is_pure_narration("Your hp DROPS to 7") is False
    assert NarrCacheGate.is_pure_narration("YOUR HIT POINTS ARE LOW") is False
    assert NarrCacheGate.is_pure_narration("a Critical Hit lands") is False


def test_gate_is_static() -> None:
    # Verify no instance state — confirm it can be called without instantiation.
    assert NarrCacheGate.is_pure_narration("hello") is True


def test_gate_patterns_compiled_once() -> None:
    # Sanity: PATTERNS class attr is the same tuple as the module-level set.
    assert NarrCacheGate.PATTERNS is _GATE_PATTERNS
    assert len(_GATE_PATTERNS) >= 18  # spec requires the full set


def test_gate_short_circuits_on_first_match() -> None:
    # Construct text that matches MANY patterns. Gate should still return False.
    # (We can't directly observe the short-circuit without instrumentation; this
    # is a smoke test that multi-match text still returns False.)
    text = "Your HP drops to 0 — critical hit! DC 15 save, paralyzed, 2d6 damage"
    assert NarrCacheGate.is_pure_narration(text) is False


def test_gate_prone_does_not_match_promote() -> None:
    # Critical regression test: \bprone\b must NOT match 'promote' / 'promoted'.
    assert NarrCacheGate.is_pure_narration("She was promoted last week.") is True
    assert NarrCacheGate.is_pure_narration("The student was prone to error.") is False


def test_gate_invisible_word_boundary() -> None:
    # 'invisible' must reject; 'invisibly' (different word) must pass.
    assert NarrCacheGate.is_pure_narration("It was invisible to the eye.") is False
    assert NarrCacheGate.is_pure_narration("It moved invisibly past.") is True


def test_gate_hp_abbreviation_collision_is_rejected_safely() -> None:
    # 'HP' could be 'Hidden Passage' in some context — gate must STILL reject
    # because fail-CLOSED. This is the headline corpus adversarial case.
    text = "The map shows the dungeon's HP — Hidden Passage on the east wall."
    assert NarrCacheGate.is_pure_narration(text) is False
