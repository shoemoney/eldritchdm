"""
Parser for dm20__start_party_mode markdown output.

dm20's start_party_mode returns a markdown string (not structured data).
This pure module extracts the server URL and per-character connection info
using a small set of tolerant regexes per RESEARCH.md §1 (Pattern 2).

Design:
  - PURE: no I/O, no async, no Discord runtime dependency.
  - Importable in tests without a running bot.
  - Parser is tolerant of extra whitespace and blank lines between fields.
  - QR paths are resolved eagerly: if the file does not exist on disk,
    qr_path is set to None rather than retaining a stale path (T-03-05).

Key pitfalls handled (per RESEARCH.md):
  - Pitfall 8: "already running" response starts with "Party Mode is already
    running" — detected first; only **Server:** is parsed, members=[], flag set.
  - Pitfall 3 / T-03-05: QR PNG paths are absolute filesystem paths that
    belong to dm20's campaign dir. Read bytes immediately; never log raw paths.
  - Malformed / error responses raise ValueError immediately (T-03-05).

CONTEXT references: D-01 (lobby flow), RESEARCH §1 (Pattern 2), RESEARCH §3
(Pitfall 7 — not directly related to parsing but drives the module_bound logic
upstream), RESEARCH §12 (manage_channels).
"""
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import NamedTuple

# ── Regex patterns (per RESEARCH §1, Pattern 2) ─────────────────────────────────

_SERVER_RE = re.compile(r"^\*\*Server:\*\* (?P<url>http[s]?://\S+)$", re.MULTILINE)
_HEADER_RE = re.compile(r"^### (?P<name>.+)$", re.MULTILINE)
_URL_RE = re.compile(r"^- \*\*URL:\*\* (?P<url>http[s]?://\S+)$", re.MULTILINE)
_QR_RE = re.compile(r"^- \*\*QR Code:\*\* (?P<path>\S+)$", re.MULTILINE)

# Sentinel string emitted by dm20 when QR generation fails at its end
_QR_FAIL = "(generation failed, use URL instead)"

# Already-running prefix (Pitfall 8)
_ALREADY_RUNNING_PREFIX = "Party Mode is already running"


# ── Public types ─────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class PartyMember:
    """Per-character connection info extracted from start_party_mode output.

    Attributes:
        character_name: Character name from the ``### Name`` header.
        url: Full party mode URL including per-character token.
        qr_path: Absolute path to the QR PNG on dm20's filesystem, or None if
            QR generation failed or the file no longer exists.

    Security note (T-03-05): never log ``qr_path`` raw — it contains an absolute
    path inside dm20's campaign directory that has no meaning to Discord users
    and constitutes minor information disclosure.
    """

    character_name: str
    url: str
    qr_path: Path | None


class ParsePartyResult(NamedTuple):
    """Result of parsing a start_party_mode markdown response.

    Attributes:
        server_url: Base URL of the party mode server.
        members: List of :class:`PartyMember` objects (empty when
            ``already_running=True``).
        already_running: True when dm20 indicated party mode was already
            started (Pitfall 8). Callers should call ``get_party_status``
            to recover the full member list in this case.
    """

    server_url: str
    members: list[PartyMember]
    already_running: bool


# ── Public API ────────────────────────────────────────────────────────────────────


def parse_party_mode_response(markdown: str) -> ParsePartyResult:
    """Parse dm20__start_party_mode markdown output.

    Args:
        markdown: Raw markdown string returned by the dm20 tool.

    Returns:
        :class:`ParsePartyResult` with ``server_url``, ``members``, and
        ``already_running`` fields.

    Raises:
        ValueError: If the response starts with "Error:", if the **Server:**
            line is missing, or if the input is empty.

    RESEARCH refs: RESEARCH.md §1 (Pattern 2), Pitfall 8 (already running).
    CONTEXT refs: D-09 (lobby flow), T-03-05 (info disclosure — qr_path).
    """
    # Empty input is always an error
    stripped = markdown.strip()
    if not stripped:
        raise ValueError("Party Mode response missing **Server:** line")

    # Error prefix: dm20 signals explicit failures with "Error:" prefix
    if stripped.lstrip().startswith("Error:"):
        raise ValueError(stripped.strip())

    # Already-running detection (Pitfall 8)
    first_line = stripped.split("\n")[0].strip()
    if first_line.startswith(_ALREADY_RUNNING_PREFIX):
        server_match = _SERVER_RE.search(markdown)
        if not server_match:
            raise ValueError("Party Mode response missing **Server:** line")
        return ParsePartyResult(
            server_url=server_match.group("url"),
            members=[],
            already_running=True,
        )

    # Normal response: extract server URL first
    server_match = _SERVER_RE.search(markdown)
    if not server_match:
        raise ValueError("Party Mode response missing **Server:** line")
    server_url = server_match.group("url")

    # Extract per-character blocks split on ### headers
    members: list[PartyMember] = []
    # Split on "\n### " to get individual member sections
    sections = markdown.split("\n### ")
    for section in sections[1:]:  # skip preamble before first ###
        name_end = section.find("\n")
        if name_end == -1:
            continue
        character_name = section[:name_end].strip()
        body = section[name_end:]

        url_m = _URL_RE.search(body)
        if not url_m:
            continue  # malformed section — skip

        # QR path: None if sentinel or file doesn't exist
        qr_m = _QR_RE.search(body)
        qr_path: Path | None = None
        if qr_m:
            raw_path = qr_m.group("path")
            if _QR_FAIL not in raw_path:
                candidate = Path(raw_path)
                if candidate.exists():
                    qr_path = candidate

        members.append(
            PartyMember(
                character_name=character_name,
                url=url_m.group("url"),
                qr_path=qr_path,
            )
        )

    return ParsePartyResult(
        server_url=server_url,
        members=members,
        already_running=False,
    )
