"""
gen_mcp_wrappers.py — Developer drift-detection tool.

Parses ddmcpskills.md to find all dm20/dice/dnd tool schemas, then cross-checks
against mcp.tools.TOOL_TO_FUNCTION.

Reports:
  - "missing wrapper": tools in ddmcpskills.md not in TOOL_TO_FUNCTION
  - "orphaned wrapper": tools in TOOL_TO_FUNCTION not in ddmcpskills.md

This script is a DEVELOPER TOOL, not a CI step. Its output (tools/_generated.py)
is committed when run intentionally. Human curates the typed signatures.

Usage:
    python tools/gen_mcp_wrappers.py          # print drift report
    python tools/gen_mcp_wrappers.py --check  # exit 1 if unexpected orphans
    python tools/gen_mcp_wrappers.py --write  # write stub wrappers to tools/_generated.py

Note: "missing wrappers" are EXPECTED in Phase 1 — we only implement the first-wave
28 tools out of 116+ in ddmcpskills.md. --check only fails on orphaned wrappers
(wrappers we have but ddmcpskills.md doesn't know about).
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# Project root is one level above tools/
PROJECT_ROOT = Path(__file__).resolve().parent.parent
SKILLS_FILE = PROJECT_ROOT / "ddmcpskills.md"


def parse_tool_names(skills_path: Path) -> set[str]:
    """Extract all fully-qualified tool names from ddmcpskills.md.

    Looks for lines matching '### `<server>__<tool>`'.
    """
    pattern = re.compile(r"^###\s+`([a-z0-9_]+__[a-z0-9_]+)`", re.MULTILINE)
    content = skills_path.read_text(encoding="utf-8")
    return set(pattern.findall(content))


def get_wrapped_tools() -> set[str]:
    """Return the set of tool names in TOOL_TO_FUNCTION."""
    # Add src to path so we can import eldritch_dm without installing
    src_path = str(PROJECT_ROOT / "src")
    if src_path not in sys.path:
        sys.path.insert(0, src_path)

    from eldritch_dm.mcp.tools import TOOL_TO_FUNCTION

    return set(TOOL_TO_FUNCTION.keys())


def generate_stub(tool_name: str) -> str:
    """Generate a minimal stub wrapper for a tool."""
    python_name = tool_name.split("__", 1)[-1]
    return (
        f"async def {python_name}(client: MCPClient, **kwargs: Any) -> dict[str, Any]:\n"
        f'    """Auto-generated stub for {tool_name}."""\n'
        f'    return await client.call("{tool_name}", **kwargs)\n'
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="MCP wrapper drift checker")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit non-zero if orphaned wrappers exist",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="Write stubs for missing wrappers to tools/_generated.py",
    )
    args = parser.parse_args()

    if not SKILLS_FILE.exists():
        print(f"ERROR: {SKILLS_FILE} not found", file=sys.stderr)
        sys.exit(2)

    all_tools = parse_tool_names(SKILLS_FILE)
    wrapped = get_wrapped_tools()

    missing = all_tools - wrapped  # in schema, not wrapped yet
    orphaned = wrapped - all_tools  # wrapped but not in schema

    print(f"Tools in ddmcpskills.md: {len(all_tools)}")
    print(f"Tools in TOOL_TO_FUNCTION: {len(wrapped)}")
    print(f"Missing wrappers (expected — first-wave only): {len(missing)}")
    print(f"Orphaned wrappers (unexpected — check tool names): {len(orphaned)}")

    if orphaned:
        print("\nORPHANED WRAPPERS (review these):")
        for t in sorted(orphaned):
            print(f"  - {t}")

    if args.write and missing:
        out_path = PROJECT_ROOT / "tools" / "_generated.py"
        header = (
            '"""Auto-generated MCP wrapper stubs. Human-curate before promoting to tools.py."""\n'
            "from __future__ import annotations\n"
            "from typing import Any\n"
            "from eldritch_dm.mcp.client import MCPClient\n\n"
        )
        stubs = "\n".join(generate_stub(t) for t in sorted(missing))
        out_path.write_text(header + stubs, encoding="utf-8")
        print(f"\nWrote {len(missing)} stubs to {out_path}")

    # Exit 1 only for orphaned wrappers (names we have that aren't in schema)
    if args.check and orphaned:
        sys.exit(1)


if __name__ == "__main__":
    main()
