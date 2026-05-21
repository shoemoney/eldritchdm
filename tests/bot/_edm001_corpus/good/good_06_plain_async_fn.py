"""Good: Plain non-callback async function with no defer — not subject to rule."""
import asyncio


async def do_some_work(value: int) -> int:
    await asyncio.sleep(0)
    return value * 2


async def another_helper() -> str:
    result = await do_some_work(42)
    return f"Result: {result}"
