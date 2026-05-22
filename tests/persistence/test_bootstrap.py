"""
Tests for eldritch_dm.persistence.bootstrap — schema application.
"""

from __future__ import annotations

import aiosqlite
import pytest

from eldritch_dm.persistence.bootstrap import bootstrap, main


class TestBootstrapCreatesTables:
    """bootstrap() creates all four tables and four indexes."""

    async def test_bootstrap_creates_tables(
        self,
        tmp_path: pytest.TempPathFactory,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        db_path = str(tmp_path / "eld.sqlite3")
        monkeypatch.setenv("ELDRITCH_DB_PATH", db_path)
        monkeypatch.setenv("DISCORD_TOKEN", "t")

        await bootstrap(db_path)

        async with aiosqlite.connect(db_path) as conn:
            # Check tables
            cursor = await conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            )
            tables = {row[0] for row in await cursor.fetchall()}

        expected_tables = {
            "channel_sessions",
            "combat_conditions",  # Phase 4 Plan 02 dodge shim (D-22)
            "pc_classes",  # Phase 5 Plan 01 — subclass at ingest for Riposte
            "persistent_views",
            "riposte_timers",
            "sanitizer_audit",
            "sqlite_sequence",  # created by AUTOINCREMENT
        }
        assert expected_tables == tables, (
            f"Expected tables {expected_tables!r}, got {tables!r}"
        )

    async def test_bootstrap_creates_indexes(
        self,
        tmp_path: pytest.TempPathFactory,
    ) -> None:
        db_path = str(tmp_path / "eld_idx.sqlite3")
        await bootstrap(db_path)

        async with aiosqlite.connect(db_path) as conn:
            cursor = await conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index' ORDER BY name"
            )
            indexes = {row[0] for row in await cursor.fetchall()}

        expected_indexes = {
            "idx_views_channel",
            "idx_riposte_channel",
            "idx_riposte_pending_deadline",
            "idx_audit_ts",
        }
        assert expected_indexes.issubset(indexes), (
            f"Missing indexes. Expected {expected_indexes!r} in {indexes!r}"
        )


class TestBootstrapIdempotent:
    """Running bootstrap twice does not raise and leaves zero rows."""

    async def test_bootstrap_idempotent(self, tmp_path: pytest.TempPathFactory) -> None:
        db_path = str(tmp_path / "eld_idem.sqlite3")

        # First run
        await bootstrap(db_path)

        # Second run must not raise
        await bootstrap(db_path)

        # Tables still exist and are empty
        async with aiosqlite.connect(db_path) as conn:
            cursor = await conn.execute("SELECT COUNT(*) FROM channel_sessions")
            row = await cursor.fetchone()
            assert row[0] == 0


class TestCheckConstraintsEnforced:
    """CHECK constraints reject invalid state values."""

    async def test_check_constraints_enforced(self, tmp_path: pytest.TempPathFactory) -> None:
        db_path = str(tmp_path / "eld_check.sqlite3")
        await bootstrap(db_path)

        async with aiosqlite.connect(db_path) as conn:
            await conn.execute("PRAGMA foreign_keys = ON")
            with pytest.raises(aiosqlite.IntegrityError):
                await conn.execute(
                    """INSERT INTO channel_sessions
                       (channel_id, campaign_name, state, created_at, updated_at)
                       VALUES (?, ?, ?, datetime('now'), datetime('now'))""",
                    ("ch-1", "Test Campaign", "BOGUS"),
                )
                await conn.commit()


class TestForeignKeyCascade:
    """ON DELETE CASCADE removes child rows when parent is deleted."""

    async def test_foreign_key_cascade(self, tmp_path: pytest.TempPathFactory) -> None:
        db_path = str(tmp_path / "eld_fk.sqlite3")
        await bootstrap(db_path)

        async with aiosqlite.connect(db_path) as conn:
            await conn.execute("PRAGMA foreign_keys = ON")

            # Insert parent row
            await conn.execute(
                """INSERT INTO channel_sessions
                   (channel_id, campaign_name, state, created_at, updated_at)
                   VALUES (?, ?, ?, datetime('now'), datetime('now'))""",
                ("ch-parent", "Test Campaign", "LOBBY"),
            )
            # Insert child row referencing the parent
            await conn.execute(
                """INSERT INTO persistent_views
                   (custom_id, view_class, message_id, channel_id, created_at)
                   VALUES (?, ?, ?, ?, datetime('now'))""",
                ("view-1", "LobbyView", "msg-1", "ch-parent"),
            )
            await conn.commit()

            # Verify child row exists
            cursor = await conn.execute(
                "SELECT COUNT(*) FROM persistent_views WHERE channel_id = ?",
                ("ch-parent",),
            )
            row = await cursor.fetchone()
            assert row[0] == 1

            # Delete parent — child should cascade
            await conn.execute(
                "DELETE FROM channel_sessions WHERE channel_id = ?",
                ("ch-parent",),
            )
            await conn.commit()

            # Child row must be gone
            cursor = await conn.execute(
                "SELECT COUNT(*) FROM persistent_views WHERE channel_id = ?",
                ("ch-parent",),
            )
            row = await cursor.fetchone()
            assert row[0] == 0, "Expected ON DELETE CASCADE to remove persistent_views row"


class TestPhase5Migration:
    """Phase 5 Plan 01: idempotent ALTER adds consumed_in_round to riposte_timers."""

    async def test_consumed_in_round_column_present_after_bootstrap(
        self, tmp_path: pytest.TempPathFactory
    ) -> None:
        """Test 1: PRAGMA table_info exposes consumed_in_round INTEGER nullable."""
        db_path = str(tmp_path / "eld_migrate_1.sqlite3")
        await bootstrap(db_path)

        async with aiosqlite.connect(db_path) as conn:
            cursor = await conn.execute("PRAGMA table_info(riposte_timers)")
            cols = await cursor.fetchall()
        # PRAGMA table_info row tuple: (cid, name, type, notnull, dflt_value, pk)
        col_info = {row[1]: row for row in cols}
        assert "consumed_in_round" in col_info, (
            f"Expected consumed_in_round column. Columns: {list(col_info.keys())}"
        )
        # Type column index 2
        assert col_info["consumed_in_round"][2].upper() == "INTEGER"
        # notnull column index 3 → 0 means nullable
        assert col_info["consumed_in_round"][3] == 0

    async def test_bootstrap_idempotent_does_not_error_on_existing_column(
        self, tmp_path: pytest.TempPathFactory
    ) -> None:
        """Test 2: second bootstrap call does NOT raise duplicate column error."""
        db_path = str(tmp_path / "eld_migrate_2.sqlite3")
        await bootstrap(db_path)
        # Second call must not raise even though column already exists.
        await bootstrap(db_path)

        # Sanity: column still there exactly once
        async with aiosqlite.connect(db_path) as conn:
            cursor = await conn.execute("PRAGMA table_info(riposte_timers)")
            cols = await cursor.fetchall()
        names = [r[1] for r in cols]
        assert names.count("consumed_in_round") == 1

    async def test_pc_classes_table_shape(
        self, tmp_path: pytest.TempPathFactory
    ) -> None:
        """Test 3: pc_classes has channel_id, character_id, class_name, subclass."""
        db_path = str(tmp_path / "eld_pc_classes.sqlite3")
        await bootstrap(db_path)

        async with aiosqlite.connect(db_path) as conn:
            cursor = await conn.execute("PRAGMA table_info(pc_classes)")
            cols = await cursor.fetchall()
        names = {r[1] for r in cols}
        assert names == {"channel_id", "character_id", "class_name", "subclass"}, (
            f"Unexpected columns in pc_classes: {names}"
        )

        # subclass should default to '' (not null)
        subclass_row = next(r for r in cols if r[1] == "subclass")
        assert subclass_row[3] == 1  # notnull
        # Default '' (SQLite stores TEXT defaults with quotes preserved)
        assert subclass_row[4] in ("''", "'\\''", '""'), (
            f"Expected subclass default empty string, got: {subclass_row[4]!r}"
        )

    async def test_pc_classes_cascades_on_channel_delete(
        self, tmp_path: pytest.TempPathFactory
    ) -> None:
        """Test 4: FK CASCADE deletes pc_classes rows when channel_session is removed."""
        db_path = str(tmp_path / "eld_pc_cascade.sqlite3")
        await bootstrap(db_path)

        async with aiosqlite.connect(db_path) as conn:
            await conn.execute("PRAGMA foreign_keys = ON")
            await conn.execute(
                """INSERT INTO channel_sessions
                   (channel_id, campaign_name, state, created_at, updated_at)
                   VALUES (?, ?, ?, datetime('now'), datetime('now'))""",
                ("ch-cascade", "Test", "LOBBY"),
            )
            await conn.execute(
                """INSERT INTO pc_classes (channel_id, character_id, class_name, subclass)
                   VALUES (?, ?, ?, ?)""",
                ("ch-cascade", "hero-1", "fighter", "battle master"),
            )
            await conn.commit()

            # Delete parent — child must cascade
            await conn.execute(
                "DELETE FROM channel_sessions WHERE channel_id = ?",
                ("ch-cascade",),
            )
            await conn.commit()

            cursor = await conn.execute(
                "SELECT COUNT(*) FROM pc_classes WHERE channel_id = ?",
                ("ch-cascade",),
            )
            row = await cursor.fetchone()
        assert row[0] == 0, "Expected ON DELETE CASCADE to remove pc_classes rows"

    async def test_first_bootstrap_logs_migration_then_quiet_second_run(
        self,
        tmp_path: pytest.TempPathFactory,
        capsys: pytest.CaptureFixture,
    ) -> None:
        """Test 5: first run logs riposte_timers_migrated_consumed_in_round; second does NOT.

        Structlog is configured to write to stdout in console mode; we capture via
        capsys rather than caplog (which only sees stdlib logging records, not
        structlog's processor pipeline).
        """
        db_path = str(tmp_path / "eld_migrate_log.sqlite3")

        await bootstrap(db_path)
        first_out = capsys.readouterr().out
        assert "riposte_timers_migrated_consumed_in_round" in first_out, (
            f"Expected migration log on first run; stdout was:\n{first_out}"
        )

        await bootstrap(db_path)
        second_out = capsys.readouterr().out
        assert "riposte_timers_migrated_consumed_in_round" not in second_out, (
            f"Expected NO migration log on second run; stdout was:\n{second_out}"
        )


class TestBootstrapMainRuns:
    """bootstrap.main() creates the DB file and prints a success line."""

    def test_bootstrap_main_runs(
        self,
        tmp_path: pytest.TempPathFactory,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture,
    ) -> None:
        db_file = tmp_path / "main_test.sqlite3"
        monkeypatch.setenv("DISCORD_TOKEN", "t")
        monkeypatch.setenv("ELDRITCH_DB_PATH", str(db_file))

        from eldritch_dm.config import get_settings
        get_settings.cache_clear()

        main()

        get_settings.cache_clear()

        # DB file must exist
        assert db_file.exists(), f"Expected DB file at {db_file}"

        # stdout must contain a success line
        captured = capsys.readouterr()
        assert "Bootstrap complete" in captured.out, (
            f"Expected 'Bootstrap complete' in stdout:\n{captured.out}"
        )
