"""
Tests for gameplay/combat_outcome_parser.py (Phase 5 Plan 01 Task 2).

dm20's combat_action returns formatted markdown text. The parser maps the
known headers to an AttackOutcome enum value. Unknown headers return None.
"""

from __future__ import annotations

from eldritch_dm.gameplay.combat_outcome_parser import (
    AttackOutcome,
    parse_combat_outcome,
)


class TestParseCombatOutcomeHappyPath:
    def test_critical_hit_header(self) -> None:
        assert (
            parse_combat_outcome("**CRITICAL HIT!** Goblin Scout strikes Thorin!")
            == AttackOutcome.CRITICAL
        )

    def test_hit_header(self) -> None:
        assert (
            parse_combat_outcome("**Hit!** Goblin Scout hits Thorin.")
            == AttackOutcome.HIT
        )

    def test_natural_one_header(self) -> None:
        assert (
            parse_combat_outcome("**Natural 1!** Goblin Scout misses Thorin.")
            == AttackOutcome.NATURAL_ONE
        )

    def test_miss_header(self) -> None:
        assert (
            parse_combat_outcome("**Miss.** Goblin Scout misses Thorin.")
            == AttackOutcome.MISS
        )


class TestParseCombatOutcomeUnknownReturnsNone:
    def test_no_recognized_header(self) -> None:
        assert parse_combat_outcome("Goblin Scout takes 5 damage.") is None

    def test_empty_string(self) -> None:
        assert parse_combat_outcome("") is None

    def test_only_bold_markdown_no_match(self) -> None:
        assert parse_combat_outcome("**Wow!** something happened.") is None


class TestParseCombatOutcomeMultiline:
    def test_header_on_second_line_via_multiline(self) -> None:
        body = (
            "The goblin lunges forward...\n"
            "**Miss.** Goblin Scout misses Thorin.\n"
            "The party watches.\n"
        )
        assert parse_combat_outcome(body) == AttackOutcome.MISS

    def test_first_matching_header_wins(self) -> None:
        body = "**Hit!** A.\n**Miss.** B.\n"
        # Search returns the first match in document order
        assert parse_combat_outcome(body) == AttackOutcome.HIT
