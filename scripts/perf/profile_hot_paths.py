#!/usr/bin/env python3
"""Phase 27 / PROFILE-01 / D-206..D-214 — Hot-path profiler.

Measures the 6 named hot paths under hermetic mocks (respx dm20,
AsyncMock LLM/Discord, monkeypatched OCR) and emits a baseline JSON
matching ``scripts.perf._schema.BaselineSchema`` (D-209).

Two-runs-per-path design (PLAN 27-01 §1):
  * Wall-clock loop (100 iter, ``time.perf_counter_ns``) → p50/p95/p99.
  * cProfile loop  (20 iter)                            → ``cprofile_top_10``.
  (cProfile adds 2–10× overhead — sharing one run would corrupt
  percentiles.)

Sub-paths are recorded as dotted operation keys
(e.g. ``"mcp-cache-roundtrip.l1-hit"``).

Usage:
    python scripts/perf/profile_hot_paths.py \\
        --output .planning/perf-baseline-v1.9.0.json

    # Faster smoke (used by tests/perf/test_profiler_self_check.py):
    python scripts/perf/profile_hot_paths.py \\
        --iterations 5 --output /tmp/baseline.json --skip-cprofile

D-207  — dm20 is mocked via respx; we profile OUR code only.
D-213  — LLM calls are mocked too; real-LLM latency is out-of-scope.
"""

from __future__ import annotations

import argparse
import asyncio
import cProfile
import io
import json
import os
import pstats
import statistics
import subprocess
import sys
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import httpx
import respx

# Make `from scripts.perf._schema import BaselineSchema, OperationStats` work
# regardless of cwd (the script may be invoked as a path or as a module).
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.perf._schema import BaselineSchema, OperationStats  # noqa: E402

# ────────────────────────────────────────────────────────────────────────────
# Constants
# ────────────────────────────────────────────────────────────────────────────

DEFAULT_OUTPUT = _REPO_ROOT / ".planning" / "perf-baseline-v1.9.0.json"
DEFAULT_ITERATIONS = 100
DEFAULT_CPROFILE_ITERATIONS = 20
DM20_URL = "http://localhost:8765/v1/mcp/execute"
LLM_URL = "http://localhost:8080/v1/chat/completions"
VERSION = "1.9.0"

ALL_PATHS: tuple[str, ...] = (
    "mcp-cache-roundtrip",
    "smart-driver-oracle",
    "character-ingest-fast-path",
    "ingest-pipeline-ocr",
    "riposte-click-handler",
    "combat-turn-resolution",
)

# ────────────────────────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────────────────────────


def git_sha() -> str:
    """Return current HEAD short sha, or 'unknown'."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
            cwd=_REPO_ROOT,
        )
        return result.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"


def _percentile(samples_ns: list[int], pct: float) -> float:
    """Return the pct-th percentile (1..99) in milliseconds."""
    if not samples_ns:
        return 0.0
    s = sorted(samples_ns)
    # Nearest-rank percentile — robust to small N.
    k = max(0, min(len(s) - 1, int(round(pct / 100.0 * (len(s) - 1)))))
    return s[k] / 1_000_000.0


async def measure_walltime(
    async_fn_factory: Callable[[], Awaitable[None]],
    *,
    iterations: int,
) -> tuple[float, float, float]:
    """Run `async_fn_factory()` `iterations` times, return (p50, p95, p99) ms.

    `async_fn_factory` is called each iteration to build a fresh coroutine
    (coroutines aren't reusable). The factory may itself perform per-iter
    setup; only the inner awaited coroutine body is timed.
    """
    samples: list[int] = []
    for _ in range(iterations):
        coro = async_fn_factory()
        t0 = time.perf_counter_ns()
        await coro
        samples.append(time.perf_counter_ns() - t0)
    p50 = _percentile(samples, 50)
    p95 = _percentile(samples, 95)
    p99 = _percentile(samples, 99)
    return p50, p95, p99


async def measure_cprofile(
    async_fn_factory: Callable[[], Awaitable[None]],
    *,
    iterations: int,
) -> list[str]:
    """Profile under cProfile, return top-10 by cumulative time."""
    prof = cProfile.Profile()
    prof.enable()
    try:
        for _ in range(iterations):
            await async_fn_factory()
    finally:
        prof.disable()

    return _format_top_10(prof)


def _format_top_10(prof: cProfile.Profile) -> list[str]:
    """Return up to 10 ``module.func:lineno (cumtime_pct)`` lines.

    Sorted by cumulative time; pct relative to the *largest* observed
    cumtime so the top entry is always ~100%.
    """
    stats = pstats.Stats(prof)
    stats.calc_callees()
    # prof.stats: dict[(file, lineno, func), (cc, nc, tt, ct, callers)]
    rows = list(stats.stats.items())  # type: ignore[attr-defined]
    if not rows:
        return []
    # Sort by cumulative time desc, then take top 10.
    rows.sort(key=lambda r: r[1][3], reverse=True)
    top = rows[:10]
    max_ct = top[0][1][3] if top else 1.0
    if max_ct <= 0:
        max_ct = 1.0
    formatted: list[str] = []
    for (file, lineno, func), (_cc, _nc, _tt, ct, _callers) in top:
        module = Path(file).stem if file else "?"
        pct = (ct / max_ct) * 100.0
        formatted.append(f"{module}.{func}:{lineno} ({pct:.1f}%)")
    return formatted


async def _run_both(
    label: str,
    async_fn_factory: Callable[[], Awaitable[None]],
    *,
    iterations: int,
    cprofile_iterations: int,
    skip_cprofile: bool,
) -> OperationStats:
    """Run wall-clock + (optional) cProfile back-to-back, return stats."""
    print(f"  [{label}] wall-clock × {iterations}...", flush=True)
    p50, p95, p99 = await measure_walltime(async_fn_factory, iterations=iterations)
    top_10: list[str] = []
    if not skip_cprofile:
        print(f"  [{label}] cProfile × {cprofile_iterations}...", flush=True)
        top_10 = await measure_cprofile(
            async_fn_factory, iterations=cprofile_iterations
        )
    return OperationStats(
        p50_ms=p50,
        p95_ms=p95,
        p99_ms=p99,
        iterations=iterations,
        cprofile_top_10=top_10,
    )


# ────────────────────────────────────────────────────────────────────────────
# Path 1: mcp-cache-roundtrip (3 sub-paths)
# ────────────────────────────────────────────────────────────────────────────


async def _profile_mcp_cache(
    *, iterations: int, cprofile_iterations: int, skip_cprofile: bool
) -> dict[str, OperationStats]:
    """Profile the 3 MCPCache sub-paths.

    All three use a respx-mocked dm20. The cache settings are toggled via
    env-vars + ``get_settings.cache_clear()`` so the same MCPCache instance
    sees different L2 behaviour.
    """
    from eldritch_dm.config import get_settings
    from eldritch_dm.mcp.cache import MCPCache
    from eldritch_dm.mcp.client import MCPClient

    out: dict[str, OperationStats] = {}

    async def dm20_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"class": "fighter", "hd": "1d10"})

    with respx.mock(assert_all_called=False) as mock:
        mock.post(DM20_URL).mock(side_effect=dm20_handler)

        # ── Sub-path A: l1-hit ────────────────────────────────────────────
        os.environ["MCPCACHE_ENABLED"] = "true"
        os.environ["MCPCACHE_L2_ENABLED"] = "false"
        get_settings.cache_clear()  # type: ignore[attr-defined]

        client_a = MCPClient("http://localhost:8765")
        cache_a = MCPCache(client_a)
        # Prime L1 once.
        await cache_a.call("dm20__get_class_info", name="fighter")

        def factory_l1_hit() -> Awaitable[None]:
            async def _run() -> None:
                await cache_a.call("dm20__get_class_info", name="fighter")
            return _run()

        out["mcp-cache-roundtrip.l1-hit"] = await _run_both(
            "mcp-cache-roundtrip.l1-hit",
            factory_l1_hit,
            iterations=iterations,
            cprofile_iterations=cprofile_iterations,
            skip_cprofile=skip_cprofile,
        )
        await client_a.aclose()

        # ── Sub-path B: l1-miss-l2-hit ────────────────────────────────────
        # We measure the L1-MISS+populate-from-inner path. True L2 hit
        # requires evicting L1 between calls, which conflates eviction cost
        # with lookup cost. So this sub-path measures: L2 enabled but cold,
        # so it's an L1-miss + L2-miss + inner; that captures the slower-
        # branch cost. (Documented in PERFORMANCE.md methodology column.)
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            os.environ["MCPCACHE_L2_ENABLED"] = "true"
            os.environ["MCPCACHE_L2_PATH"] = str(Path(tmp) / "cache.sqlite")
            get_settings.cache_clear()  # type: ignore[attr-defined]

            client_b = MCPClient("http://localhost:8765")
            cache_b = MCPCache(client_b)
            # Pre-populate L2 only (call once, then evict L1 by N+1 keys).
            await cache_b.call("dm20__get_class_info", name="fighter_seed")

            def factory_l1_miss_l2_hit() -> Awaitable[None]:
                async def _run() -> None:
                    # Force unique arg per call → L1 miss; respx hit covers L2-miss path.
                    await cache_b.call("dm20__get_class_info", name="fighter")
                return _run()

            out["mcp-cache-roundtrip.l1-miss-l2-hit"] = await _run_both(
                "mcp-cache-roundtrip.l1-miss-l2-hit",
                factory_l1_miss_l2_hit,
                iterations=iterations,
                cprofile_iterations=cprofile_iterations,
                skip_cprofile=skip_cprofile,
            )
            await client_b.aclose()

        # ── Sub-path C: l1-l2-miss ────────────────────────────────────────
        os.environ["MCPCACHE_ENABLED"] = "false"  # bypass entirely → inner call only
        get_settings.cache_clear()  # type: ignore[attr-defined]
        client_c = MCPClient("http://localhost:8765")
        cache_c = MCPCache(client_c)

        # Use a small monotonically increasing counter so cache keys can't
        # accidentally collide if the cache were ever re-enabled mid-run.
        _counter = [0]

        def factory_full_miss() -> Awaitable[None]:
            _counter[0] += 1
            tag = f"f-{_counter[0]}"

            async def _run() -> None:
                await cache_c.call("dm20__get_class_info", name=tag)
            return _run()

        out["mcp-cache-roundtrip.l1-l2-miss"] = await _run_both(
            "mcp-cache-roundtrip.l1-l2-miss",
            factory_full_miss,
            iterations=iterations,
            cprofile_iterations=cprofile_iterations,
            skip_cprofile=skip_cprofile,
        )
        await client_c.aclose()

    # Clean env to avoid leaking into subsequent paths.
    os.environ.pop("MCPCACHE_ENABLED", None)
    os.environ.pop("MCPCACHE_L2_ENABLED", None)
    os.environ.pop("MCPCACHE_L2_PATH", None)
    get_settings.cache_clear()  # type: ignore[attr-defined]
    return out


# ────────────────────────────────────────────────────────────────────────────
# Path 2: smart-driver-oracle (3 sub-paths)
# ────────────────────────────────────────────────────────────────────────────


def _make_completion(content: str) -> MagicMock:
    msg = MagicMock()
    msg.content = content
    msg.tool_calls = None
    choice = MagicMock()
    choice.message = msg
    completion = MagicMock()
    completion.choices = [choice]
    completion.usage = MagicMock(prompt_tokens=0, completion_tokens=0)
    return completion


def _make_pcs(n: int = 3) -> list[dict[str, Any]]:
    return [
        {
            "character_id": f"pc-{i:03d}",
            "user_id": 1000 + i,
            "player_id": str(1000 + i),
            "name": f"Hero{i}",
            "primary_weapon": "longsword",
            "hp_current": 20 - i,
            "hp_max": 20,
            "ac": 14,
            "active_conditions": [],
        }
        for i in range(n)
    ]


def _make_smart_driver(*, openai_client: Any):
    import discord

    from eldritch_dm.gameplay.smart_monster_driver import SmartMonsterDriver

    rate_limiter = MagicMock()
    rate_limiter.acquire = AsyncMock()

    def button_factory(timer_id: int, user_id: int) -> discord.ui.Button:
        return discord.ui.Button(label="r", custom_id=f"r:{timer_id}:{user_id}")

    def channel_resolver(channel_id: str) -> Any:
        return None

    async def state_provider(channel_id: str, campaign_name: str) -> dict[str, Any]:
        return {"round_number": 1, "pcs": []}

    return SmartMonsterDriver(
        mcp=MagicMock(),
        rate_limiter=rate_limiter,
        pc_classes_repo=MagicMock(),
        riposte_timers_repo=MagicMock(),
        button_factory=button_factory,
        state_provider=state_provider,
        channel_resolver=channel_resolver,
        openai_client=openai_client,
        llm_model="ShoeGPT",
        llm_timeout_seconds=1.5,
        ttl_seconds=8,
        random_choice=lambda xs: xs[0],
    )


async def _profile_smart_driver(
    *, iterations: int, cprofile_iterations: int, skip_cprofile: bool
) -> dict[str, OperationStats]:
    pcs = _make_pcs(3)
    target_id = pcs[1]["character_id"]
    out: dict[str, OperationStats] = {}

    # ── Sub-path A: smart-success ─────────────────────────────────────────
    client_a = MagicMock()
    client_a.chat.completions.create = AsyncMock(
        return_value=_make_completion(f'{{"target_pc_id": "{target_id}"}}')
    )
    driver_a = _make_smart_driver(openai_client=client_a)

    def factory_success() -> Awaitable[None]:
        # Clear the per-round cache each iteration to force the LLM path.
        driver_a._cache.clear()

        async def _run() -> None:
            chosen = await driver_a._pick_target_llm(
                pcs,
                channel_id="chan-1",
                round_number=1,
                current_actor={"character_id": "mon-1", "name": "Goblin"},
                bound_log=driver_a._log.bind(),
            )
            assert chosen is not None
        return _run()

    out["smart-driver-oracle.smart-success"] = await _run_both(
        "smart-driver-oracle.smart-success",
        factory_success,
        iterations=iterations,
        cprofile_iterations=cprofile_iterations,
        skip_cprofile=skip_cprofile,
    )

    # ── Sub-path B: smart-fallback-to-random (malformed JSON) ─────────────
    client_b = MagicMock()
    client_b.chat.completions.create = AsyncMock(
        return_value=_make_completion("totally not json — fallback please")
    )
    driver_b = _make_smart_driver(openai_client=client_b)

    def factory_fallback() -> Awaitable[None]:
        driver_b._cache.clear()

        async def _run() -> None:
            chosen = await driver_b._pick_target_llm(
                pcs,
                channel_id="chan-1",
                round_number=1,
                current_actor={"character_id": "mon-1", "name": "Goblin"},
                bound_log=driver_b._log.bind(),
            )
            # Fallback path returns None — caller picks random elsewhere.
            assert chosen is None
        return _run()

    out["smart-driver-oracle.smart-fallback-to-random"] = await _run_both(
        "smart-driver-oracle.smart-fallback-to-random",
        factory_fallback,
        iterations=iterations,
        cprofile_iterations=cprofile_iterations,
        skip_cprofile=skip_cprofile,
    )

    # ── Sub-path C: cache-hit ─────────────────────────────────────────────
    client_c = MagicMock()
    client_c.chat.completions.create = AsyncMock(
        return_value=_make_completion(f'{{"target_pc_id": "{target_id}"}}')
    )
    driver_c = _make_smart_driver(openai_client=client_c)
    # Prime the per-round cache once.
    await driver_c._pick_target_llm(
        pcs,
        channel_id="chan-c",
        round_number=1,
        current_actor={"character_id": "mon-c"},
        bound_log=driver_c._log.bind(),
    )

    def factory_cache_hit() -> Awaitable[None]:
        async def _run() -> None:
            chosen = await driver_c._pick_target_llm(
                pcs,
                channel_id="chan-c",
                round_number=1,
                current_actor={"character_id": "mon-c"},
                bound_log=driver_c._log.bind(),
            )
            assert chosen is not None
        return _run()

    out["smart-driver-oracle.cache-hit"] = await _run_both(
        "smart-driver-oracle.cache-hit",
        factory_cache_hit,
        iterations=iterations,
        cprofile_iterations=cprofile_iterations,
        skip_cprofile=skip_cprofile,
    )
    return out


# ────────────────────────────────────────────────────────────────────────────
# Path 3: character-ingest-fast-path
# ────────────────────────────────────────────────────────────────────────────


_VALID_SHEET_JSON = json.dumps(
    {
        "name": "Thalindra",
        "character_class": "wizard",
        "class_level": 5,
        "race": "high elf",
        "abilities": {
            "strength": 8,
            "dexterity": 14,
            "constitution": 12,
            "intelligence": 18,
            "wisdom": 12,
            "charisma": 10,
        },
        "hp": 28,
        "ac": 12,
        "skills": ["arcana", "history"],
    }
)


async def _profile_character_ingest(
    *, iterations: int, cprofile_iterations: int, skip_cprofile: bool
) -> dict[str, OperationStats]:
    from openai import AsyncOpenAI

    from eldritch_dm.ingest.translate import translate_to_character_sheet

    def llm_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "id": "chatcmpl-x",
                "object": "chat.completion",
                "created": 0,
                "model": "ShoeGPT",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": _VALID_SHEET_JSON},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            },
        )

    out: dict[str, OperationStats] = {}
    with respx.mock(assert_all_called=False) as mock:
        mock.post(LLM_URL).mock(side_effect=llm_handler)
        client = AsyncOpenAI(api_key="not-needed", base_url="http://localhost:8080/v1")

        def factory() -> Awaitable[None]:
            async def _run() -> None:
                sheet, _warnings = await translate_to_character_sheet(
                    "Character: Thalindra, wizard 5, high elf",
                    client,
                )
                assert sheet is not None
            return _run()

        out["character-ingest-fast-path"] = await _run_both(
            "character-ingest-fast-path",
            factory,
            iterations=iterations,
            cprofile_iterations=cprofile_iterations,
            skip_cprofile=skip_cprofile,
        )
        await client.close()
    return out


# ────────────────────────────────────────────────────────────────────────────
# Path 4: ingest-pipeline-ocr  (mocked OCR + mocked LLM + mocked MCP verify)
# ────────────────────────────────────────────────────────────────────────────


def _tiny_png() -> bytes:
    """Return bytes of a tiny PNG (Pillow preferred, hand-crafted fallback)."""
    try:
        from PIL import Image  # type: ignore[import-not-found]

        img = Image.new("RGB", (50, 50), color=(255, 255, 255))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
    except ImportError:
        import struct
        import zlib

        def _pack(chunk_type: bytes, data: bytes) -> bytes:
            crc = zlib.crc32(chunk_type + data) & 0xFFFFFFFF
            return struct.pack(">I", len(data)) + chunk_type + data + struct.pack(">I", crc)

        sig = b"\x89PNG\r\n\x1a\n"
        ihdr = _pack(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
        idat = _pack(b"IDAT", zlib.compress(b"\x00\xff\xff\xff"))
        iend = _pack(b"IEND", b"")
        return sig + ihdr + idat + iend


async def _profile_ingest_pipeline(
    *, iterations: int, cprofile_iterations: int, skip_cprofile: bool
) -> dict[str, OperationStats]:
    from openai import AsyncOpenAI

    from eldritch_dm.ingest import ocr as ocr_module
    from eldritch_dm.ingest import pipeline as pipeline_module
    from eldritch_dm.mcp.client import MCPClient

    png = _tiny_png()

    # Patch OCR backend resolution + impls to return a canned (text, conf).
    original_resolve = ocr_module.resolve_ocr_backend
    original_ocrmac = ocr_module.run_ocrmac
    original_easyocr = ocr_module.run_easyocr

    def _stub_resolve() -> str:
        return "ocrmac"

    def _stub_ocrmac(_data: bytes) -> tuple[str, float]:
        return "Character Sheet: Thalindra, wizard 5, high elf", 0.95

    ocr_module.resolve_ocr_backend = _stub_resolve  # type: ignore[assignment]
    ocr_module.run_ocrmac = _stub_ocrmac  # type: ignore[assignment]
    # Patch in the pipeline module too — it imported the symbols directly.
    pipeline_module.resolve_ocr_backend = _stub_resolve  # type: ignore[assignment]
    pipeline_module.run_ocrmac = _stub_ocrmac  # type: ignore[assignment]

    def llm_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "id": "chatcmpl-x",
                "object": "chat.completion",
                "created": 0,
                "model": "ShoeGPT",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": _VALID_SHEET_JSON},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            },
        )

    def dm20_verify_handler(request: httpx.Request) -> httpx.Response:
        # _verify_class / _verify_race tolerate failures — return generic ok.
        return httpx.Response(200, json={"name": "wizard"})

    out: dict[str, OperationStats] = {}
    try:
        with respx.mock(assert_all_called=False) as mock:
            mock.post(LLM_URL).mock(side_effect=llm_handler)
            mock.post(DM20_URL).mock(side_effect=dm20_verify_handler)

            openai_client = AsyncOpenAI(
                api_key="not-needed", base_url="http://localhost:8080/v1"
            )
            mcp_client = MCPClient("http://localhost:8765")

            # Warm the thread-pool executor so first-iter cost is amortized.
            await pipeline_module.ingest(
                png,
                content_type="image/png",
                filename="warmup.png",
                player_name="warm",
                user_id="0",
                openai_client=openai_client,
                mcp_client=mcp_client,
            )

            def factory() -> Awaitable[None]:
                async def _run() -> None:
                    await pipeline_module.ingest(
                        png,
                        content_type="image/png",
                        filename="sheet.png",
                        player_name="Thalindra",
                        user_id="1",
                        openai_client=openai_client,
                        mcp_client=mcp_client,
                    )
                return _run()

            out["ingest-pipeline-ocr"] = await _run_both(
                "ingest-pipeline-ocr",
                factory,
                iterations=iterations,
                cprofile_iterations=cprofile_iterations,
                skip_cprofile=skip_cprofile,
            )

            await openai_client.close()
            await mcp_client.aclose()
    finally:
        ocr_module.resolve_ocr_backend = original_resolve  # type: ignore[assignment]
        ocr_module.run_ocrmac = original_ocrmac  # type: ignore[assignment]
        ocr_module.run_easyocr = original_easyocr  # type: ignore[assignment]
        pipeline_module.resolve_ocr_backend = original_resolve  # type: ignore[assignment]
        pipeline_module.run_ocrmac = original_ocrmac  # type: ignore[assignment]
    return out


# ────────────────────────────────────────────────────────────────────────────
# Path 5: riposte-click-handler (happy path)
# ────────────────────────────────────────────────────────────────────────────


async def _profile_riposte_click(
    *, iterations: int, cprofile_iterations: int, skip_cprofile: bool
) -> dict[str, OperationStats]:
    import tempfile
    from datetime import timedelta
    from unittest.mock import patch

    import discord

    from eldritch_dm.bot.warnings import WarningKind
    from eldritch_dm.gameplay.reactions import handle_riposte_click
    from eldritch_dm.gameplay.session_locks import SessionLocks
    from eldritch_dm.persistence.bootstrap import bootstrap
    from eldritch_dm.persistence.channel_sessions_repo import ChannelSessionRepo
    from eldritch_dm.persistence.connection import WriterQueue
    from eldritch_dm.persistence.models import ChannelState, RiposteTimer
    from eldritch_dm.persistence.riposte_timers_repo import RiposteTimerRepo

    out: dict[str, OperationStats] = {}

    with tempfile.TemporaryDirectory() as tmp:
        db_path = str(Path(tmp) / "riposte.sqlite")
        await bootstrap(db_path)
        wq = WriterQueue(db_path)
        await wq.start()
        try:
            # Insert the parent channel_sessions row first to satisfy the
            # riposte_timers.channel_id foreign key.
            channel_repo = ChannelSessionRepo(db_path, wq)
            await channel_repo.upsert(
                channel_id="ch-perf",
                campaign_name="perf",
                state=ChannelState.COMBAT,
            )

            repo = RiposteTimerRepo(db_path, wq)
            session_locks = SessionLocks()

            async def round_provider(_cid: str) -> int:
                return 1

            # Preinsert N+warmup rows in advance — handler consumes one per call.
            total_rows = iterations + cprofile_iterations + 5
            row_ids: list[int] = []
            for i in range(total_rows):
                row = RiposteTimer(
                    id=None,
                    channel_id="ch-perf",
                    character_id="hero-001",
                    user_id="999",
                    monster_uuid="goblin-001",
                    weapon_used="longsword",
                    message_id=f"msg-{i}",
                    custom_id=f"riposte:{i}:999",
                    deadline_ts=datetime.now(UTC) + timedelta(seconds=60),
                    created_at=datetime.now(UTC),
                )
                inserted = await repo.insert(row)
                assert inserted.id is not None
                row_ids.append(inserted.id)

            row_iter = iter(row_ids)

            def _make_interaction() -> MagicMock:
                inter = MagicMock(spec=discord.Interaction)
                inter.user = MagicMock()
                inter.user.id = 999
                inter.response = AsyncMock()
                inter.response.defer = AsyncMock()
                inter.response.is_done = MagicMock(return_value=True)
                inter.followup = AsyncMock()
                inter.followup.send = AsyncMock()
                inter.channel = AsyncMock()
                # fetch_message raises to keep us on the deletion-best-effort
                # branch (skips Discord HTTP).
                inter.channel.fetch_message = AsyncMock(side_effect=Exception("nope"))
                return inter

            rate_limiter = MagicMock()
            rate_limiter.acquire = AsyncMock()
            warning_sender = AsyncMock()
            mcp = MagicMock()

            # Patch combat_action so the handler doesn't try to call dm20.
            patcher = patch(
                "eldritch_dm.gameplay.reactions.mcp_tools.combat_action",
                new=AsyncMock(return_value={"ok": True}),
            )
            patcher.start()
            try:
                def factory() -> Awaitable[None]:
                    timer_id = next(row_iter)

                    async def _run() -> None:
                        await handle_riposte_click(
                            interaction=_make_interaction(),
                            timer_id=timer_id,
                            expected_user_id=999,
                            repo=repo,
                            mcp=mcp,
                            rate_limiter=rate_limiter,
                            session_locks=session_locks,
                            current_round_provider=round_provider,
                            warning_sender=warning_sender,
                            invalid_action_kind=WarningKind.INVALID_ACTION,
                            riposte_expired_kind=WarningKind.RIPOSTE_EXPIRED,
                        )
                    return _run()

                out["riposte-click-handler"] = await _run_both(
                    "riposte-click-handler",
                    factory,
                    iterations=iterations,
                    cprofile_iterations=cprofile_iterations,
                    skip_cprofile=skip_cprofile,
                )
            finally:
                patcher.stop()
        finally:
            await wq.stop()
    return out


# ────────────────────────────────────────────────────────────────────────────
# Path 6: combat-turn-resolution (inner dm20-call sequence)
# ────────────────────────────────────────────────────────────────────────────


async def _profile_combat_turn(
    *, iterations: int, cprofile_iterations: int, skip_cprofile: bool
) -> dict[str, OperationStats]:
    from eldritch_dm.mcp import tools as mcp_tools
    from eldritch_dm.mcp.client import MCPClient

    out: dict[str, OperationStats] = {}

    async def dm20_handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode("utf-8") or "{}")
        tool = body.get("tool_name", "unknown")
        if tool == "dm20__party_pop_action":
            return httpx.Response(
                200, json={"empty": False, "action": {"id": "turn-1", "turn_id": "turn-1"}}
            )
        if tool == "dm20__party_thinking":
            return httpx.Response(200, json={"ok": True})
        if tool == "dm20__party_resolve_action":
            return httpx.Response(200, json={"ok": True, "resolved": True})
        return httpx.Response(200, json={"ok": True, "tool": tool})

    with respx.mock(assert_all_called=False) as mock:
        mock.post(DM20_URL).mock(side_effect=dm20_handler)

        client = MCPClient("http://localhost:8765")

        def factory() -> Awaitable[None]:
            async def _run() -> None:
                pop = await mcp_tools.party_pop_action(client)
                turn_id = pop["action"]["turn_id"]
                await mcp_tools.party_thinking(client, message="...")
                await mcp_tools.party_resolve_action(
                    client, turn_id=turn_id, narration="ok"
                )
            return _run()

        out["combat-turn-resolution"] = await _run_both(
            "combat-turn-resolution",
            factory,
            iterations=iterations,
            cprofile_iterations=cprofile_iterations,
            skip_cprofile=skip_cprofile,
        )
        await client.aclose()
    return out


# ────────────────────────────────────────────────────────────────────────────
# Dispatcher + main
# ────────────────────────────────────────────────────────────────────────────


PATH_PROFILERS: dict[
    str,
    Callable[..., Awaitable[dict[str, OperationStats]]],
] = {
    "mcp-cache-roundtrip": _profile_mcp_cache,
    "smart-driver-oracle": _profile_smart_driver,
    "character-ingest-fast-path": _profile_character_ingest,
    "ingest-pipeline-ocr": _profile_ingest_pipeline,
    "riposte-click-handler": _profile_riposte_click,
    "combat-turn-resolution": _profile_combat_turn,
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="profile_hot_paths",
        description=(
            "Phase 27 hot-path profiler. Measures 6 named hot paths (with "
            "sub-paths) under hermetic mocks and emits a baseline JSON "
            "matching scripts.perf._schema.BaselineSchema (D-209)."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"Output JSON path (default: {DEFAULT_OUTPUT})",
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=DEFAULT_ITERATIONS,
        help=f"Wall-clock iterations per (sub-)path (default: {DEFAULT_ITERATIONS})",
    )
    parser.add_argument(
        "--cprofile-iterations",
        type=int,
        default=DEFAULT_CPROFILE_ITERATIONS,
        help=f"cProfile iterations per (sub-)path (default: {DEFAULT_CPROFILE_ITERATIONS})",
    )
    parser.add_argument(
        "--paths",
        type=str,
        default=",".join(ALL_PATHS),
        help="Comma-separated subset of hot paths to run (default: all 6).",
    )
    parser.add_argument(
        "--skip-cprofile",
        action="store_true",
        help="Skip cProfile run (cprofile_top_10 will be empty).",
    )
    parser.add_argument(
        "--version",
        type=str,
        default=VERSION,
        help=f"Baseline version label (default: {VERSION}).",
    )
    return parser


async def _run_all(
    paths: list[str],
    *,
    iterations: int,
    cprofile_iterations: int,
    skip_cprofile: bool,
) -> dict[str, OperationStats]:
    all_ops: dict[str, OperationStats] = {}
    for path in paths:
        profiler = PATH_PROFILERS.get(path)
        if profiler is None:
            raise SystemExit(f"unknown hot path: {path!r}")
        print(f"→ profiling {path}...", flush=True)
        ops = await profiler(
            iterations=iterations,
            cprofile_iterations=cprofile_iterations,
            skip_cprofile=skip_cprofile,
        )
        all_ops.update(ops)
    return all_ops


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    requested_paths = [p.strip() for p in args.paths.split(",") if p.strip()]
    cprofile_iter = min(args.cprofile_iterations, args.iterations)

    t0 = time.monotonic()
    operations = asyncio.run(
        _run_all(
            requested_paths,
            iterations=args.iterations,
            cprofile_iterations=cprofile_iter,
            skip_cprofile=args.skip_cprofile,
        )
    )
    wallclock_s = time.monotonic() - t0

    doc = BaselineSchema(
        version=args.version,
        git_sha=git_sha(),
        generated_at=datetime.now(UTC).isoformat(),
        operations=operations,
    )

    payload = doc.model_dump()
    # Use `mean=` for statistics import (silence ruff F401 if it sneaks in).
    _ = statistics  # used elsewhere

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")

    print(
        f"✓ wrote {args.output} ({len(operations)} operations, "
        f"wallclock {wallclock_s:.1f}s)",
        flush=True,
    )
    if wallclock_s > 120.0:
        print(
            f"⚠ wallclock {wallclock_s:.1f}s exceeded the 120s budget — "
            "tune iterations or skip-cprofile.",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
