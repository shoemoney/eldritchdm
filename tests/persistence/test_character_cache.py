"""Tests for eldritch_dm.persistence.character_cache (Phase 17)."""

from __future__ import annotations

import time
from typing import Any

import pytest
from pydantic import ValidationError

from eldritch_dm.config import Settings
from eldritch_dm.persistence.character_cache import (
    ALLOWED_SNAPSHOT_FIELDS,
    FORBIDDEN_SNAPSHOT_FIELDS,
    CharacterCacheMetrics,
    CharacterCacheRepo,
    CharacterSnapshot,
    _project_to_snapshot,
    etag_of,
)

# ── Test helpers ─────────────────────────────────────────────────────────────


def _valid_payload(
    *,
    character_id: str = "char-001",
    level: int = 5,
    max_hp: int = 38,
) -> dict[str, Any]:
    """Return a complete, valid dm20-shaped payload (with extras the projector drops)."""
    return {
        "id": character_id,
        "name": "Aragorn",
        "race": "human",
        "character_class": "fighter",
        "subclass": "battle_master",
        "level": level,
        "proficiency_bonus": 3,
        "alignment": "lawful_good",
        "languages": ["common", "elvish"],
        "max_hp": max_hp,
        "base_stats": {
            "STR": 16,
            "DEX": 14,
            "CON": 14,
            "INT": 12,
            "WIS": 13,
            "CHA": 10,
        },
        "base_ac": 18,
        "base_speed": 30,
        "equipment": ["longsword", "shield", "plate_armor"],
        # Extras the projector should drop silently.
        "xp_total": 6500,
        "background": "soldier",
        # Combat-mutable fields the projector MUST strip (D-125).
        "current_hp": 12,
        "current_temp_hp": 0,
        "current_conditions": ["poisoned"],
        "exhaustion_level": 1,
        "active_buffs": ["bless"],
        "concentration_target": None,
        "death_save_successes": 0,
        "death_save_failures": 0,
        "hit_dice_remaining": 3,
        "current_speed": 20,
        "current_ac": 13,
    }


def _settings_for(tmp_path, **overrides: Any) -> Settings:
    """Build a Settings instance pinned to a tmp_path cache file."""
    base = {
        "DISCORD_TOKEN": "test",
        "CHARCACHE_PATH": str(tmp_path / "cache.sqlite"),
    }
    base.update({k: str(v) for k, v in overrides.items()})
    # Settings reads from env aliases — but for tests we go through the
    # constructor with the env file disabled and feed the aliases as init kwargs.
    return Settings(
        _env_file=None,  # type: ignore[call-arg]
        DISCORD_TOKEN="test",
        CHARCACHE_PATH=str(tmp_path / "cache.sqlite"),
        **{k: v for k, v in overrides.items() if k != "CHARCACHE_PATH"},
    )


# ── Snapshot model — allow-list + fail-CLOSED ────────────────────────────────


class TestCharacterSnapshotModel:
    def test_allowed_snapshot_fields_membership_snapshot(self) -> None:
        """PINNED — modifying this REQUIRES reviewing D-125 mechanical-honesty.

        If you add a field to CharacterSnapshot, update this set AND verify
        the new field is genuinely static (does not change from damage,
        buffs, conditions, or any in-combat event).
        """
        expected = {
            "id",
            "name",
            "race",
            "character_class",
            "subclass",
            "level",
            "proficiency_bonus",
            "alignment",
            "languages",
            "max_hp",
            "base_stats",
            "base_ac",
            "base_speed",
            "equipment",
        }
        assert set(ALLOWED_SNAPSHOT_FIELDS) == expected

    @pytest.mark.parametrize(
        "forbidden_field",
        sorted(FORBIDDEN_SNAPSHOT_FIELDS),
    )
    def test_forbidden_fields_rejected(self, forbidden_field: str) -> None:
        """Each D-125 forbidden name MUST raise at construction."""
        good = {
            "id": "x",
            "name": "x",
            "race": "x",
            "character_class": "x",
            "level": 1,
            "proficiency_bonus": 2,
            "max_hp": 10,
            "base_stats": {"STR": 10, "DEX": 10, "CON": 10, "INT": 10, "WIS": 10, "CHA": 10},
            "base_ac": 10,
            "base_speed": 30,
        }
        good[forbidden_field] = 1
        with pytest.raises(ValidationError):
            CharacterSnapshot(**good)

    def test_round_trip_json(self) -> None:
        snap = _project_to_snapshot(_valid_payload())
        payload = snap.model_dump_json()
        rebuilt = CharacterSnapshot.model_validate_json(payload)
        assert rebuilt == snap

    def test_frozen(self) -> None:
        snap = _project_to_snapshot(_valid_payload())
        with pytest.raises(ValidationError):
            snap.name = "Frodo"  # type: ignore[misc]


# ── Projector ────────────────────────────────────────────────────────────────


class TestProjector:
    def test_drops_combat_state(self) -> None:
        snap = _project_to_snapshot(_valid_payload())
        # The combat-mutable fields must NOT have been carried through.
        dumped = snap.model_dump()
        for forbidden in FORBIDDEN_SNAPSHOT_FIELDS:
            assert forbidden not in dumped

    def test_drops_unknown_static_fields(self) -> None:
        snap = _project_to_snapshot(_valid_payload())
        # `xp_total` and `background` from the payload aren't on the allow-list.
        dumped = snap.model_dump()
        assert "xp_total" not in dumped
        assert "background" not in dumped

    def test_missing_required_raises(self) -> None:
        payload = _valid_payload()
        del payload["max_hp"]
        with pytest.raises(ValueError, match="max_hp"):
            _project_to_snapshot(payload)

    def test_legacy_class_key_maps_to_character_class(self) -> None:
        payload = _valid_payload()
        payload["class"] = payload.pop("character_class")
        snap = _project_to_snapshot(payload)
        assert snap.character_class == "fighter"

    def test_languages_normalized_to_sorted(self) -> None:
        payload = _valid_payload()
        payload["languages"] = ["zulu", "elvish", "common"]
        snap = _project_to_snapshot(payload)
        assert snap.languages == ["common", "elvish", "zulu"]

    def test_non_dict_input_raises(self) -> None:
        with pytest.raises(ValueError, match="expected dict"):
            _project_to_snapshot("not-a-dict")  # type: ignore[arg-type]


# ── etag_of ─────────────────────────────────────────────────────────────────


class TestEtag:
    def test_canonical_json_key_order_invariant(self) -> None:
        a = {"a": 1, "b": [1, 2], "c": {"x": 1, "y": 2}}
        b = {"c": {"y": 2, "x": 1}, "b": [1, 2], "a": 1}
        assert etag_of(a) == etag_of(b)

    def test_hash_is_sha256_hex(self) -> None:
        e = etag_of({"a": 1})
        assert len(e) == 64
        int(e, 16)  # must be hex-parseable

    def test_distinct_payloads_have_distinct_etags(self) -> None:
        assert etag_of({"hp": 10}) != etag_of({"hp": 11})


# ── Repo connection / schema ─────────────────────────────────────────────────


class TestRepoSchema:
    async def test_ensure_conn_creates_schema(self, tmp_path) -> None:
        settings = _settings_for(tmp_path)
        repo = CharacterCacheRepo(settings=settings)
        try:
            conn = await repo._ensure_conn()
            cur = await conn.execute("PRAGMA table_info(character_cache_entries)")
            cols = [row[1] for row in await cur.fetchall()]
            await cur.close()
            assert cols == [
                "character_id",
                "snapshot_json",
                "etag",
                "last_seen_ts",
                "refreshed_ts",
            ]
        finally:
            await repo.aclose()

    async def test_path_override_wins(self, tmp_path) -> None:
        settings = _settings_for(tmp_path)
        override = tmp_path / "alt.sqlite"
        repo = CharacterCacheRepo(settings=settings, path=override)
        try:
            assert repo.db_path == override
            await repo._ensure_conn()
            assert override.exists()
        finally:
            await repo.aclose()

    async def test_aclose_is_idempotent(self, tmp_path) -> None:
        repo = CharacterCacheRepo(settings=_settings_for(tmp_path))
        await repo._ensure_conn()
        await repo.aclose()
        await repo.aclose()  # second close must not raise


# ── get_or_fetch behavior ────────────────────────────────────────────────────


class TestGetOrFetch:
    async def test_miss_populates_cache(self, tmp_path) -> None:
        repo = CharacterCacheRepo(settings=_settings_for(tmp_path))
        calls = 0

        async def fetcher(cid: str) -> dict[str, Any]:
            nonlocal calls
            calls += 1
            return _valid_payload(character_id=cid)

        try:
            snap = await repo.get_or_fetch("char-001", fetcher)
            assert snap.id == "char-001"
            assert snap.character_class == "fighter"
            assert calls == 1
            assert repo.misses == 1
        finally:
            await repo.aclose()

    async def test_ttl_hit_skips_fetcher(self, tmp_path) -> None:
        repo = CharacterCacheRepo(settings=_settings_for(tmp_path))
        call_count = 0

        async def fetcher(cid: str) -> dict[str, Any]:
            nonlocal call_count
            call_count += 1
            return _valid_payload(character_id=cid)

        async def exploding_fetcher(cid: str) -> dict[str, Any]:
            raise AssertionError("fetcher must not be called on TTL hit")

        try:
            await repo.get_or_fetch("char-001", fetcher)  # populate
            assert call_count == 1
            # Second call inside TTL → MUST NOT invoke fetcher.
            snap = await repo.get_or_fetch("char-001", exploding_fetcher)
            assert snap.id == "char-001"
            assert repo.hits_ttl == 1
        finally:
            await repo.aclose()

    async def test_etag_match_after_ttl_expiry(
        self, tmp_path, monkeypatch
    ) -> None:
        """TTL expired → fetcher called → ETag matches → no schema rewrite."""
        # Use TTL=1 so we can naturally expire it.
        repo = CharacterCacheRepo(
            settings=_settings_for(tmp_path, CHARCACHE_TTL_S=1)
        )

        async def fetcher(cid: str) -> dict[str, Any]:
            return _valid_payload(character_id=cid)  # deterministic payload

        try:
            await repo.get_or_fetch("char-001", fetcher)
            # Fast-forward int(time.time()) past TTL.
            import eldritch_dm.persistence.character_cache as mod

            real_time = time.time()
            monkeypatch.setattr(
                mod.time, "time", lambda: real_time + 10
            )
            snap = await repo.get_or_fetch("char-001", fetcher)
            assert snap.id == "char-001"
            assert repo.hits_etag == 1
            assert repo.misses == 1  # only the original miss
        finally:
            await repo.aclose()

    async def test_etag_mismatch_updates(self, tmp_path, monkeypatch) -> None:
        repo = CharacterCacheRepo(
            settings=_settings_for(tmp_path, CHARCACHE_TTL_S=1)
        )
        version = {"hp": 38}

        async def fetcher(cid: str) -> dict[str, Any]:
            payload = _valid_payload(character_id=cid)
            payload["max_hp"] = version["hp"]
            return payload

        try:
            await repo.get_or_fetch("char-001", fetcher)
            import eldritch_dm.persistence.character_cache as mod

            real_time = time.time()
            monkeypatch.setattr(mod.time, "time", lambda: real_time + 10)
            version["hp"] = 50  # CHANGE payload → ETag mismatch
            snap = await repo.get_or_fetch("char-001", fetcher)
            assert snap.max_hp == 50
            assert repo.misses == 2
        finally:
            await repo.aclose()

    async def test_get_or_fetch_propagates_projector_errors(
        self, tmp_path
    ) -> None:
        repo = CharacterCacheRepo(settings=_settings_for(tmp_path))

        async def fetcher(cid: str) -> dict[str, Any]:
            payload = _valid_payload(character_id=cid)
            del payload["max_hp"]  # force projector error
            return payload

        try:
            with pytest.raises(ValueError, match="max_hp"):
                await repo.get_or_fetch("char-001", fetcher)
        finally:
            await repo.aclose()


# ── Restart survival ─────────────────────────────────────────────────────────


class TestRestartSurvival:
    async def test_cache_survives_repo_recreation(
        self, tmp_path, monkeypatch
    ) -> None:
        path = tmp_path / "cache.sqlite"
        settings = _settings_for(tmp_path, CHARCACHE_TTL_S=1)

        async def fetcher(cid: str) -> dict[str, Any]:
            return _valid_payload(character_id=cid)

        # First lifecycle: populate.
        repo1 = CharacterCacheRepo(settings=settings, path=path)
        try:
            await repo1.get_or_fetch("char-001", fetcher)
        finally:
            await repo1.aclose()

        # Second lifecycle: same path, advance time past TTL so we go through
        # the ETag path; the etag MUST match the previously-stored one.
        import eldritch_dm.persistence.character_cache as mod

        real_time = time.time()
        monkeypatch.setattr(mod.time, "time", lambda: real_time + 10)
        repo2 = CharacterCacheRepo(settings=settings, path=path)
        try:
            snap = await repo2.get_or_fetch("char-001", fetcher)
            assert snap.id == "char-001"
            assert repo2.hits_etag == 1
            assert repo2.misses == 0
        finally:
            await repo2.aclose()


# ── Invalidate API ───────────────────────────────────────────────────────────


class TestInvalidate:
    async def test_invalidate_all_returns_count(self, tmp_path) -> None:
        repo = CharacterCacheRepo(settings=_settings_for(tmp_path))

        async def fetcher(cid: str) -> dict[str, Any]:
            return _valid_payload(character_id=cid)

        try:
            for cid in ("a", "b", "c"):
                await repo.get_or_fetch(cid, fetcher)
            removed = await repo.invalidate()
            assert removed == 3
            assert repo.invalidations_total == 1
        finally:
            await repo.aclose()

    async def test_invalidate_single_entry(self, tmp_path) -> None:
        repo = CharacterCacheRepo(settings=_settings_for(tmp_path))

        async def fetcher(cid: str) -> dict[str, Any]:
            return _valid_payload(character_id=cid)

        try:
            for cid in ("a", "b", "c"):
                await repo.get_or_fetch(cid, fetcher)
            removed = await repo.invalidate("b")
            assert removed == 1
            metrics = await repo.metrics_snapshot()
            assert metrics.size == 2
        finally:
            await repo.aclose()

    async def test_invalidate_missing_id_returns_zero(self, tmp_path) -> None:
        repo = CharacterCacheRepo(settings=_settings_for(tmp_path))
        try:
            removed = await repo.invalidate("nope")
            assert removed == 0
            assert repo.invalidations_total == 1  # call still counts
        finally:
            await repo.aclose()


# ── Metrics ──────────────────────────────────────────────────────────────────


class TestMetrics:
    async def test_metrics_snapshot_shape(self, tmp_path) -> None:
        repo = CharacterCacheRepo(settings=_settings_for(tmp_path))
        try:
            metrics = await repo.metrics_snapshot()
            assert isinstance(metrics, CharacterCacheMetrics)
            assert metrics.size == 0
            assert metrics.etag_match_rate == 0.0
        finally:
            await repo.aclose()

    async def test_etag_match_rate(self, tmp_path, monkeypatch) -> None:
        repo = CharacterCacheRepo(
            settings=_settings_for(tmp_path, CHARCACHE_TTL_S=1)
        )
        version = {"hp": 38}

        async def fetcher(cid: str) -> dict[str, Any]:
            payload = _valid_payload(character_id=cid)
            payload["max_hp"] = version["hp"]
            return payload

        try:
            # 1 MISS (populate).
            await repo.get_or_fetch("char-001", fetcher)
            import eldritch_dm.persistence.character_cache as mod

            real_time = time.time()
            # 1 ETag match.
            monkeypatch.setattr(mod.time, "time", lambda: real_time + 10)
            await repo.get_or_fetch("char-001", fetcher)
            # 1 ETag mismatch → MISS again.
            monkeypatch.setattr(mod.time, "time", lambda: real_time + 20)
            version["hp"] = 99
            await repo.get_or_fetch("char-001", fetcher)
            metrics = await repo.metrics_snapshot()
            assert metrics.hits_etag == 1
            assert metrics.misses == 2
            assert metrics.etag_match_rate == pytest.approx(1 / 3)
        finally:
            await repo.aclose()


# ── Span emission (Plan 17-02) ──────────────────────────────────────────────


class TestSpanEmission:
    async def test_lookup_span_recorded(self, tmp_path) -> None:
        """Three calls → three rows with layers [miss, ttl_hit, ttl_hit]."""
        from datetime import UTC, datetime

        from eldritch_dm.observability.span_buffer import init_buffer

        buf = init_buffer()
        since = datetime.now(UTC)
        repo = CharacterCacheRepo(settings=_settings_for(tmp_path))

        async def fetcher(cid: str) -> dict[str, Any]:
            return _valid_payload(character_id=cid)

        try:
            await repo.get_or_fetch("char-001", fetcher)
            await repo.get_or_fetch("char-001", fetcher)
            await repo.get_or_fetch("char-001", fetcher)
        finally:
            await repo.aclose()

        buf.flush(timeout_s=2.0)
        rows = buf.query(since=since, span_name="eldritch.character_cache.lookup")
        assert len(rows) >= 3
        layers = [r.driver_path for r in rows[-3:]]
        assert layers[0] == "miss"
        assert layers[1] in {"ttl_hit", "etag_match"}
        assert layers[2] in {"ttl_hit", "etag_match"}

    async def test_invalidation_span_recorded(self, tmp_path) -> None:
        from datetime import UTC, datetime

        from eldritch_dm.observability.span_buffer import init_buffer

        buf = init_buffer()
        since = datetime.now(UTC)
        repo = CharacterCacheRepo(settings=_settings_for(tmp_path))

        async def fetcher(cid: str) -> dict[str, Any]:
            return _valid_payload(character_id=cid)

        try:
            await repo.get_or_fetch("char-001", fetcher)
            await repo.invalidate()
        finally:
            await repo.aclose()

        buf.flush(timeout_s=2.0)
        rows = buf.query(
            since=since, span_name="eldritch.character_cache.invalidation"
        )
        assert len(rows) == 1
        row = rows[0]
        assert row.driver_path == "all"  # scope mapped to driver_path
        assert row.combat_round == 1  # entries_removed mapped to combat_round
