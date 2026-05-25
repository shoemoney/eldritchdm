"""Tests for eldritch_dm.tools.cache_clear (Phase 17 / CHARCACHE-03)."""

from __future__ import annotations

from typing import Any

from eldritch_dm.config import Settings
from eldritch_dm.persistence.character_cache import CharacterCacheRepo
from eldritch_dm.tools.cache_clear import (
    EXIT_OK,
    EXIT_USER_ERROR,
    build_parser,
    main,
)


def run_cli(argv: list[str]) -> int:
    """Run the CLI main() in a fresh thread so its asyncio.run() can spin
    up its own loop without colliding with the test's pytest-asyncio loop.
    """
    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
        return ex.submit(main, argv).result()


def _settings_for(tmp_path) -> Settings:
    return Settings(
        _env_file=None,  # type: ignore[call-arg]
        DISCORD_TOKEN="t",
        CHARCACHE_PATH=str(tmp_path / "cache.sqlite"),
    )


def _valid_payload(cid: str) -> dict[str, Any]:
    return {
        "id": cid,
        "name": "n",
        "race": "human",
        "character_class": "fighter",
        "level": 1,
        "proficiency_bonus": 2,
        "max_hp": 10,
        "base_stats": {"STR": 10, "DEX": 10, "CON": 10, "INT": 10, "WIS": 10, "CHA": 10},
        "base_ac": 10,
        "base_speed": 30,
    }


async def _populate(tmp_path, ids: list[str]) -> str:
    """Populate the cache with the given character ids; return the db path."""
    settings = _settings_for(tmp_path)
    repo = CharacterCacheRepo(settings=settings)

    async def fetcher(cid: str) -> dict[str, Any]:
        return _valid_payload(cid)

    try:
        for cid in ids:
            await repo.get_or_fetch(cid, fetcher)
    finally:
        await repo.aclose()
    return str(repo.db_path)


# ── Parser ───────────────────────────────────────────────────────────────────


def test_parser_requires_a_scope_returns_nonzero(tmp_path) -> None:
    """Running without --characters MUST exit non-zero."""
    rc = run_cli(["--cache-path", str(tmp_path / "missing.sqlite")])
    assert rc == EXIT_USER_ERROR


def test_parser_help_runs() -> None:
    parser = build_parser()
    # build_parser must construct without error and provide --characters.
    actions = {a.dest for a in parser._actions}
    assert "characters" in actions
    assert "character_id" in actions
    assert "dry_run" in actions
    assert "cache_path" in actions


# ── Dry-run ──────────────────────────────────────────────────────────────────


async def test_dry_run_no_writes(tmp_path, capsys) -> None:
    db_path = await _populate(tmp_path, ["a", "b", "c"])
    rc = run_cli(["--characters", "--cache-path", db_path, "--dry-run"])
    assert rc == EXIT_OK
    captured = capsys.readouterr()
    assert "DRY-RUN" in captured.out
    assert "3" in captured.out
    # Verify file is unchanged — open the cache fresh and count.
    import aiosqlite

    async with aiosqlite.connect(db_path) as conn:
        cur = await conn.execute("SELECT COUNT(*) FROM character_cache_entries")
        row = await cur.fetchone()
        await cur.close()
    assert row is not None and row[0] == 3


async def test_dry_run_filtered_by_id(tmp_path, capsys) -> None:
    db_path = await _populate(tmp_path, ["a", "b", "c"])
    rc = run_cli(
        [
            "--characters",
            "--cache-path",
            db_path,
            "--character-id",
            "b",
            "--dry-run",
        ]
    )
    assert rc == EXIT_OK
    captured = capsys.readouterr()
    assert "would remove 1 row" in captured.out


# ── Real clear paths ─────────────────────────────────────────────────────────


async def test_clear_all_characters(tmp_path, capsys) -> None:
    db_path = await _populate(tmp_path, ["a", "b", "c"])
    rc = run_cli(["--characters", "--cache-path", db_path])
    assert rc == EXIT_OK
    captured = capsys.readouterr()
    assert "Removed 3" in captured.out
    import aiosqlite

    async with aiosqlite.connect(db_path) as conn:
        cur = await conn.execute("SELECT COUNT(*) FROM character_cache_entries")
        row = await cur.fetchone()
        await cur.close()
    assert row is not None and row[0] == 0


async def test_clear_single_character_id(tmp_path) -> None:
    db_path = await _populate(tmp_path, ["a", "b", "c"])
    rc = run_cli(
        [
            "--characters",
            "--cache-path",
            db_path,
            "--character-id",
            "b",
        ]
    )
    assert rc == EXIT_OK
    import aiosqlite

    async with aiosqlite.connect(db_path) as conn:
        cur = await conn.execute(
            "SELECT character_id FROM character_cache_entries ORDER BY character_id"
        )
        rows = [r[0] for r in await cur.fetchall()]
        await cur.close()
    assert rows == ["a", "c"]


# ── Error paths ──────────────────────────────────────────────────────────────


def test_missing_cache_file_returns_user_error(tmp_path) -> None:
    rc = main(
        [
            "--characters",
            "--cache-path",
            str(tmp_path / "does-not-exist.sqlite"),
        ]
    )
    assert rc == EXIT_USER_ERROR
