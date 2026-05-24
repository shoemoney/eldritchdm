"""Tests for eldritch_dm.tools.backfill_pc_classes (Phase 9 / TD-3).

Test categories (D-49):
  - argparse + module-shape smoke (T-09-01-01)
  - dm20 fetch loop with respx-mocked MCP (T-09-01-02)
  - dry-run no-write, --force re-process, idempotency (T-09-01-03)
"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
import respx

from eldritch_dm.persistence.bootstrap import bootstrap
from eldritch_dm.tools import backfill_pc_classes as backfill

# ── T-09-01-01: scaffold smoke tests ─────────────────────────────────────────


def test_module_importable() -> None:
    """Plain import should work; no side-effects allowed."""
    assert hasattr(backfill, "main")
    assert hasattr(backfill, "build_parser")
    assert backfill.EXIT_OK == 0
    assert backfill.EXIT_USER_ERROR == 1
    assert backfill.EXIT_PARTIAL == 2
    assert backfill.EXIT_FATAL == 3


def test_help_exits_zero(capsys: pytest.CaptureFixture[str]) -> None:
    """argparse --help should exit cleanly with code 0."""
    with pytest.raises(SystemExit) as exc_info:
        backfill.main(["--help"])
    assert exc_info.value.code == 0
    out = capsys.readouterr().out
    assert "eldritch-dm-backfill-pc-classes" in out
    assert "--dry-run" in out
    assert "--force" in out


def test_dry_run_and_force_flags_parse() -> None:
    parser = backfill.build_parser()
    args = parser.parse_args([])
    assert args.dry_run is False
    assert args.force is False

    args = parser.parse_args(["--dry-run", "--force"])
    assert args.dry_run is True
    assert args.force is True


def test_dm20_url_resolution_cli_wins(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DM20_MCP_URL", "http://from-env:9999")
    monkeypatch.setenv("OMLX_ENDPOINT", "http://from-omlx:8765/v1")
    assert (
        backfill.resolve_dm20_url("http://from-cli:1234")
        == "http://from-cli:1234"
    )


def test_dm20_url_resolution_env_dm20(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DM20_MCP_URL", "http://from-env:9999/")
    monkeypatch.delenv("OMLX_ENDPOINT", raising=False)
    assert backfill.resolve_dm20_url(None) == "http://from-env:9999"


def test_dm20_url_resolution_omlx_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DM20_MCP_URL", raising=False)
    monkeypatch.setenv("OMLX_ENDPOINT", "http://omlx-host:8765/v1")
    assert backfill.resolve_dm20_url(None) == "http://omlx-host:8765"


def test_dm20_url_resolution_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DM20_MCP_URL", raising=False)
    monkeypatch.delenv("OMLX_ENDPOINT", raising=False)
    assert backfill.resolve_dm20_url(None) == "http://localhost:8765"


# ── T-09-01-02: dm20 fetch loop tests ────────────────────────────────────────


async def _seed_channel_session(db_path: str, channel_id: str, campaign: str) -> None:
    """Insert a channel_sessions row directly (bypass repo to avoid coupling)."""
    import aiosqlite

    async with aiosqlite.connect(db_path) as conn:
        await conn.execute(
            "INSERT INTO channel_sessions "
            "(channel_id, campaign_name, claudmaster_session_id, "
            " dm20_party_token, state) "
            "VALUES (?, ?, NULL, NULL, 'LOBBY')",
            (channel_id, campaign),
        )
        await conn.commit()


@pytest.fixture
def tmp_db(tmp_path: Path) -> str:
    """Bootstrap an empty eldritch.sqlite3 schema in a tmp dir."""
    import asyncio

    db = tmp_path / "eldritch.sqlite3"
    asyncio.run(bootstrap(str(db)))
    return str(db)


async def test_collect_rows_empty_db_returns_empty(tmp_db: str) -> None:
    rows, failures = await backfill.collect_rows(
        db_path=tmp_db, dm20_url="http://localhost:8765"
    )
    assert rows == []
    assert failures == []


async def test_collect_rows_happy_path(tmp_db: str) -> None:
    await _seed_channel_session(tmp_db, "111", "test-campaign")

    payload = {
        "characters": [
            {
                "character_id": "char-fighter-01",
                "character_class": "Fighter",
                "name": "Aragorn",
            },
            {
                "character_id": "char-rogue-01",
                "character_class": "  ROGUE  ",
                "name": "Legolas",
            },
        ]
    }

    with respx.mock(assert_all_called=False) as router:
        route = router.post("http://localhost:8765/v1/mcp/execute").mock(
            return_value=httpx.Response(200, json=payload)
        )
        rows, failures = await backfill.collect_rows(
            db_path=tmp_db, dm20_url="http://localhost:8765"
        )

    assert route.call_count == 1
    assert failures == []
    assert len(rows) == 2
    classes = sorted(r.class_name for r in rows)
    assert classes == ["fighter", "rogue"]  # normalized
    assert all(r.subclass == "" for r in rows)
    assert all(r.channel_id == "111" for r in rows)


async def test_collect_rows_dm20_unreachable_buckets_failures(tmp_db: str) -> None:
    await _seed_channel_session(tmp_db, "222", "doomed-campaign")

    with respx.mock(assert_all_called=False) as router:
        router.post("http://localhost:8765/v1/mcp/execute").mock(
            return_value=httpx.Response(503, json={"error": "service unavailable"})
        )
        rows, failures = await backfill.collect_rows(
            db_path=tmp_db, dm20_url="http://localhost:8765"
        )

    assert rows == []
    assert len(failures) == 1
    assert failures[0][0] == "222"


async def test_collect_rows_subclass_warning_emitted(
    tmp_db: str, capsys: pytest.CaptureFixture[str]
) -> None:
    """Each successfully-discovered character produces a subclass_unknown WARN."""
    await _seed_channel_session(tmp_db, "333", "warning-campaign")
    payload = {
        "characters": [
            {"character_id": "x", "character_class": "Fighter"},
        ]
    }
    with respx.mock(assert_all_called=False) as router:
        router.post("http://localhost:8765/v1/mcp/execute").mock(
            return_value=httpx.Response(200, json=payload)
        )
        rows, _ = await backfill.collect_rows(
            db_path=tmp_db, dm20_url="http://localhost:8765"
        )
    assert len(rows) == 1
    # structlog renders to stdout via console renderer in tests; verify the
    # subclass_unknown event was emitted with the character_id.
    out = capsys.readouterr().out + capsys.readouterr().err
    assert "subclass_unknown" in out


async def test_collect_rows_partial_success_across_channels(tmp_db: str) -> None:
    """One channel succeeds, one fails — both buckets non-empty."""
    await _seed_channel_session(tmp_db, "good", "good-campaign")
    await _seed_channel_session(tmp_db, "bad", "bad-campaign")

    good_payload = {
        "characters": [{"character_id": "g1", "character_class": "Cleric"}]
    }

    def _handler(request: httpx.Request) -> httpx.Response:
        body = request.content.decode("utf-8")
        if "good-campaign" in body:
            return httpx.Response(200, json=good_payload)
        return httpx.Response(503, json={"error": "down"})

    with respx.mock(assert_all_called=False) as router:
        router.post("http://localhost:8765/v1/mcp/execute").mock(side_effect=_handler)
        rows, failures = await backfill.collect_rows(
            db_path=tmp_db, dm20_url="http://localhost:8765"
        )

    assert len(rows) == 1
    assert rows[0].channel_id == "good"
    assert len(failures) == 1
    assert failures[0][0] == "bad"


# ── T-09-01-03: dry-run + force + idempotency tests ──────────────────────────


async def _count_pc_classes(db_path: str) -> int:
    import aiosqlite

    async with aiosqlite.connect(db_path) as conn:
        cur = await conn.execute("SELECT COUNT(*) FROM pc_classes")
        row = await cur.fetchone()
    assert row is not None
    return int(row[0])


def _two_rows() -> list[backfill.BackfillRow]:
    return [
        backfill.BackfillRow(
            channel_id="ch1",
            character_id="c1",
            class_name="fighter",
            subclass="",
        ),
        backfill.BackfillRow(
            channel_id="ch1",
            character_id="c2",
            class_name="rogue",
            subclass="",
        ),
    ]


async def test_dry_run_makes_no_writes(tmp_db: str) -> None:
    await _seed_channel_session(tmp_db, "ch1", "campaign-1")
    assert await _count_pc_classes(tmp_db) == 0

    report = await backfill.apply_rows(
        _two_rows(), db_path=tmp_db, dry_run=True, force=False
    )

    # post-state assertion — driver-level write prohibition held
    assert await _count_pc_classes(tmp_db) == 0
    assert report.would_insert == 2
    assert report.would_skip == 0
    assert report.would_update == 0
    assert report.inserted == 0


async def test_dry_run_uses_readonly_uri(
    tmp_db: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify the URI passed to aiosqlite.connect includes mode=ro + uri=True."""
    captured: dict[str, object] = {}
    real_connect = backfill.aiosqlite.connect

    def _spy(*args: object, **kwargs: object) -> object:
        # Only capture the first apply-rows connect; collect_rows also opens
        # read-only so spy must record every call.
        captured.setdefault("calls", []).append((args, kwargs))  # type: ignore[union-attr]
        return real_connect(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(backfill.aiosqlite, "connect", _spy)

    await backfill.apply_rows(
        _two_rows(), db_path=tmp_db, dry_run=True, force=False
    )

    calls = captured["calls"]
    assert isinstance(calls, list) and calls
    # Find at least one call whose first positional arg is a mode=ro URI
    ro_calls = [
        c for c in calls
        if c[0] and isinstance(c[0][0], str) and "mode=ro" in c[0][0]
        and c[1].get("uri") is True
    ]
    assert ro_calls, f"no mode=ro URI in any aiosqlite.connect call: {calls!r}"


async def test_real_run_inserts_new_rows(tmp_db: str) -> None:
    await _seed_channel_session(tmp_db, "ch1", "campaign-1")
    report = await backfill.apply_rows(
        _two_rows(), db_path=tmp_db, dry_run=False, force=False
    )
    assert report.inserted == 2
    assert report.updated == 0
    assert report.skipped_existing == 0
    assert await _count_pc_classes(tmp_db) == 2


async def test_idempotent_re_run_skips(tmp_db: str) -> None:
    await _seed_channel_session(tmp_db, "ch1", "campaign-1")
    rows = _two_rows()

    first = await backfill.apply_rows(rows, db_path=tmp_db, dry_run=False, force=False)
    assert first.inserted == 2

    second = await backfill.apply_rows(rows, db_path=tmp_db, dry_run=False, force=False)
    assert second.inserted == 0
    assert second.skipped_existing == 2
    assert await _count_pc_classes(tmp_db) == 2


async def test_force_re_processes_existing(tmp_db: str) -> None:
    """--force updates an existing row whose class_name had drifted."""
    await _seed_channel_session(tmp_db, "ch1", "campaign-1")

    # Seed with stale data via the repo directly.
    from eldritch_dm.persistence.pc_classes_repo import PCClassesRepo

    repo = PCClassesRepo(tmp_db)
    await repo.upsert(
        channel_id="ch1",
        character_id="c1",
        class_name="stale_class",
        subclass="",
    )

    fresh_rows = [
        backfill.BackfillRow(
            channel_id="ch1",
            character_id="c1",
            class_name="fighter",
            subclass="",
        )
    ]

    report = await backfill.apply_rows(
        fresh_rows, db_path=tmp_db, dry_run=False, force=True
    )
    assert report.updated == 1
    assert report.inserted == 0

    info = await repo.get("ch1", "c1")
    assert info is not None
    assert info.class_name == "fighter"


async def test_db_locked_returns_exit_fatal(
    tmp_db: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """sqlite3.OperationalError('database is locked') → EXIT_FATAL via _run()."""
    import sqlite3 as _sqlite3

    from eldritch_dm.persistence import pc_classes_repo as repo_module

    await _seed_channel_session(tmp_db, "ch1", "campaign-1")

    async def _boom(self: object, **kwargs: object) -> None:
        raise _sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(repo_module.PCClassesRepo, "upsert", _boom)

    payload = {
        "characters": [{"character_id": "c1", "character_class": "Fighter"}]
    }
    parser = backfill.build_parser()
    args = parser.parse_args(
        ["--db-path", tmp_db, "--dm20-url", "http://localhost:8765"]
    )
    with respx.mock(assert_all_called=False) as router:
        router.post("http://localhost:8765/v1/mcp/execute").mock(
            return_value=httpx.Response(200, json=payload)
        )
        rc = await backfill._run(args)

    assert rc == backfill.EXIT_FATAL


async def test_main_happy_path_end_to_end(
    tmp_db: str, capsys: pytest.CaptureFixture[str]
) -> None:
    """Full _run(): seed → dm20 mock → real write → exit 0 + summary printed."""
    await _seed_channel_session(tmp_db, "ch1", "campaign-1")
    payload = {
        "characters": [
            {"character_id": "c1", "character_class": "Fighter"},
            {"character_id": "c2", "character_class": "Rogue"},
        ]
    }
    parser = backfill.build_parser()
    args = parser.parse_args(
        ["--db-path", tmp_db, "--dm20-url", "http://localhost:8765"]
    )
    with respx.mock(assert_all_called=False) as router:
        router.post("http://localhost:8765/v1/mcp/execute").mock(
            return_value=httpx.Response(200, json=payload)
        )
        rc = await backfill._run(args)
    assert rc == backfill.EXIT_OK
    out = capsys.readouterr().out
    assert "rows discovered: 2" in out
    assert "inserted       : 2" in out
    assert await _count_pc_classes(tmp_db) == 2


async def test_main_dm20_unreachable_returns_exit_user_error(
    tmp_db: str,
) -> None:
    await _seed_channel_session(tmp_db, "ch1", "campaign-1")
    parser = backfill.build_parser()
    args = parser.parse_args(
        ["--db-path", tmp_db, "--dm20-url", "http://localhost:8765"]
    )
    with respx.mock(assert_all_called=False) as router:
        router.post("http://localhost:8765/v1/mcp/execute").mock(
            return_value=httpx.Response(503, json={"error": "down"})
        )
        rc = await backfill._run(args)
    assert rc == backfill.EXIT_USER_ERROR


def test_main_sync_entry_point_invokes_asyncio_run(
    tmp_db: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Synchronous main() must wrap _run() in asyncio.run() so the
    [project.scripts] entry can be invoked from a non-async context.
    """
    called: dict[str, object] = {}

    async def _stub_run(args: object) -> int:
        called["args"] = args
        return 42

    monkeypatch.setattr(backfill, "_run", _stub_run)
    rc = backfill.main(["--db-path", tmp_db])
    assert rc == 42
    assert "args" in called
