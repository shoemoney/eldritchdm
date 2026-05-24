"""
Tests for the enriched combat_embed (Phase 4 Plan 02, Task 1).

New behaviors tested:
  Test 6: combat_embed accepts 6-tuples (name, init, hp_cur, hp_max, ac, conditions).
  Test 7: Turn marker ▶️ for current actor, ▫️ for others (D-14).
  Test 8: 8-row case renders cleanly (≤25 embed field limit).
  Test 9: Empty conditions list shows "—".
  Test 10: Backward-compat: old 5-tuple calls (name, init, hp_cur, hp_max, conditions)
           still work — ac defaults to 10 via thin shim.

Phase 4 Plan 02.
"""

from __future__ import annotations


from eldritch_dm.bot.embeds import combat_embed

# ── Helpers ───────────────────────────────────────────────────────────────────


def _field_titles(embed) -> list[str]:
    return [f.name for f in embed.fields]


def _field_values(embed) -> list[str]:
    return [f.value for f in embed.fields]


# ── Sample data ───────────────────────────────────────────────────────────────

# 6-tuple format: (name, initiative_roll, hp_cur, hp_max, ac, conditions)
INITIATIVE_8_V2 = [
    ("Thorin",      20, 55, 55, 18, []),
    ("Goblin King", 18, 40, 60, 14, ["stunned"]),
    ("Aria",        15, 42, 50, 15, []),
    ("Brog",        12, 30, 30, 16, ["poisoned"]),
    ("Cave Troll",   5, 80, 120, 11, ["frightened"]),
    ("Orc Shaman",  17, 20, 40, 13, []),
    ("Skeleton",     9, 12, 13, 13, []),
    ("Dire Wolf",    3, 25, 30, 14, []),
]

# 5-tuple (legacy) format: (name, initiative_roll, hp_cur, hp_max, conditions)
INITIATIVE_5_LEGACY = [
    ("Thorin",      20, 55, 55, []),
    ("Goblin King", 18, 40, 60, ["stunned"]),
    ("Aria",        15, 42, 50, []),
]


# ── Test 6: 6-tuple signature ─────────────────────────────────────────────────


class TestCombatEmbedV2Signature:
    def test_accepts_6_tuples(self) -> None:
        """combat_embed accepts 6-tuple (name, init, hp_cur, hp_max, ac, conditions)."""
        embed = combat_embed(
            round_n=1,
            current_actor="Thorin",
            initiative=INITIATIVE_8_V2[:3],
        )
        assert embed is not None
        assert len(embed.fields) == 3

    def test_ac_appears_in_field_title(self) -> None:
        """AC is included in the field title format: 'name (hp/max HP, AC ac)'."""
        embed = combat_embed(
            round_n=1,
            current_actor="Thorin",
            initiative=[("Thorin", 20, 55, 55, 18, [])],
        )
        title = embed.fields[0].name
        assert "AC 18" in title

    def test_hp_appears_in_field_title(self) -> None:
        """HP is included in field title: 'name (55/55 HP, AC 18)'."""
        embed = combat_embed(
            round_n=1,
            current_actor="Thorin",
            initiative=[("Thorin", 20, 45, 55, 18, [])],
        )
        title = embed.fields[0].name
        assert "45/55 HP" in title


# ── Test 7: Turn markers ──────────────────────────────────────────────────────


class TestTurnMarkers:
    def test_current_actor_has_play_marker(self) -> None:
        """Current actor field title starts with ▶️."""
        embed = combat_embed(
            round_n=2,
            current_actor="Thorin",
            initiative=INITIATIVE_8_V2[:3],
        )
        titles = _field_titles(embed)
        thorin_title = next(t for t in titles if "Thorin" in t)
        assert thorin_title.startswith("▶️")

    def test_non_current_actors_have_empty_marker(self) -> None:
        """Non-current actors use ▫️ marker."""
        embed = combat_embed(
            round_n=2,
            current_actor="Thorin",
            initiative=INITIATIVE_8_V2[:3],
        )
        titles = _field_titles(embed)
        for title in titles:
            if "Thorin" in title:
                assert title.startswith("▶️")
            else:
                assert title.startswith("▫️")

    def test_only_one_play_marker(self) -> None:
        """Exactly one ▶️ marker per embed (the current actor's turn)."""
        embed = combat_embed(
            round_n=1,
            current_actor="Aria",
            initiative=INITIATIVE_8_V2[:5],
        )
        play_markers = [t for t in _field_titles(embed) if t.startswith("▶️")]
        assert len(play_markers) == 1

    def test_current_actor_not_in_initiative_still_renders(self) -> None:
        """If current_actor name has no match in initiative, all actors get ▫️."""
        embed = combat_embed(
            round_n=1,
            current_actor="UnknownActor",
            initiative=INITIATIVE_8_V2[:2],
        )
        titles = _field_titles(embed)
        for title in titles:
            assert title.startswith("▫️")


# ── Test 8: 8-row render ─────────────────────────────────────────────────────


class TestEightRowRender:
    def test_8_row_renders_8_fields(self) -> None:
        """8-actor initiative list produces exactly 8 embed fields."""
        embed = combat_embed(
            round_n=3,
            current_actor="Thorin",
            initiative=INITIATIVE_8_V2,
        )
        assert len(embed.fields) == 8

    def test_8_row_within_discord_25_field_limit(self) -> None:
        """8 fields is well within Discord's 25-field embed limit."""
        embed = combat_embed(
            round_n=3,
            current_actor="Thorin",
            initiative=INITIATIVE_8_V2,
        )
        assert len(embed.fields) <= 25

    def test_title_shows_round_number(self) -> None:
        """Embed title includes 'Round 3' for round_n=3."""
        embed = combat_embed(
            round_n=3,
            current_actor="Thorin",
            initiative=INITIATIVE_8_V2,
        )
        assert "Round 3" in embed.title


# ── Test 9: Empty conditions renders "—" ─────────────────────────────────────


class TestConditionsRendering:
    def test_empty_conditions_renders_dash(self) -> None:
        """An actor with no conditions shows '—' (not empty string) in field value."""
        embed = combat_embed(
            round_n=1,
            current_actor="Thorin",
            initiative=[("Thorin", 20, 55, 55, 18, [])],
        )
        field_val = embed.fields[0].value
        assert "—" in field_val

    def test_conditions_list_rendered_in_value(self) -> None:
        """Conditions present in the list appear in the field value."""
        embed = combat_embed(
            round_n=1,
            current_actor="Goblin King",
            initiative=[("Goblin King", 18, 40, 60, 14, ["stunned", "blinded"])],
        )
        field_val = embed.fields[0].value
        assert "stunned" in field_val
        assert "blinded" in field_val


# ── Test 10: Backward-compat with 5-tuple callers ────────────────────────────


class TestBackwardCompat5Tuple:
    def test_5_tuple_does_not_crash(self) -> None:
        """Old-style 5-tuple (name, init, hp_cur, hp_max, conditions) still works."""
        embed = combat_embed(
            round_n=1,
            current_actor="Thorin",
            initiative=INITIATIVE_5_LEGACY,  # type: ignore[arg-type]  # intentional 5-tuple
        )
        assert embed is not None
        assert len(embed.fields) == 3

    def test_5_tuple_defaults_ac_to_10(self) -> None:
        """5-tuple callers get AC=10 as default (documented shim behavior)."""
        embed = combat_embed(
            round_n=1,
            current_actor="Thorin",
            initiative=[("Thorin", 20, 55, 55, [])],  # type: ignore[arg-type]  # legacy 5-tuple
        )
        title = embed.fields[0].name
        assert "AC 10" in title

    def test_5_tuple_still_renders_turn_markers(self) -> None:
        """5-tuple callers still get ▶️/▫️ markers."""
        embed = combat_embed(
            round_n=1,
            current_actor="Thorin",
            initiative=INITIATIVE_5_LEGACY,  # type: ignore[arg-type]
        )
        titles = _field_titles(embed)
        thorin_title = next(t for t in titles if "Thorin" in t)
        assert thorin_title.startswith("▶️")
        for title in titles:
            if "Thorin" not in title:
                assert title.startswith("▫️")
