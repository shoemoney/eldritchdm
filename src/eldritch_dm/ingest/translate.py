"""Backend-agnostic JSON-mode translation wrapper for the ingest pipeline.

Converts raw OCR/PDF text into a validated CharacterSheet pydantic model
using any OpenAI-compatible Chat Completions endpoint with
``response_format=json_object``. The actual backend (oMLX / Ollama /
OpenRouter) is selected by ``INGEST_BACKEND`` in Settings — this module
just consumes the resolved ``AsyncOpenAI`` client and model id (D-27).

Key design choices (D-22, D-27):
  - This module lives in ingest/, NOT mcp/tools.py — the import-linter contract
    forbids mcp from importing eldritch_dm.ingest (which would import schema.py).
  - The OpenAI-compatible client is an AsyncOpenAI instance; the cog creates
    it from ``Settings.resolve_ingest_config()`` (D-27 multi-backend).
  - temperature=0.05: minimal creativity, maximally deterministic JSON output.
  - TRANSLATE_SYSTEM_PROMPT embeds the JSON schema so the model knows the output shape.
  - _defensive_json_parse strips ``` fences defensively even though oMLX shouldn't emit them.
    OpenRouter-hosted models are more likely to emit fences — defensive strip helps there too.

D-22 deviation note: translate_character_sheet was planned for mcp/tools.py, but
the import-linter contract (mcp must not import ingest) required relocation here.

Public API:
    TRANSLATE_SYSTEM_PROMPT           — str, embedded in chat requests
    translate_character_sheet(...)    — async, calls the configured backend, returns raw dict
    translate_to_character_sheet(...) — async, full pipeline: sanitize → translate → validate
"""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, Any

from pydantic import ValidationError

from eldritch_dm.ingest.schema import CharacterSheet
from eldritch_dm.logging import get_logger
from eldritch_dm.safety.sanitizer import sanitize_player_input

if TYPE_CHECKING:
    from openai import AsyncOpenAI

log = get_logger(__name__)

# ---------------------------------------------------------------------------
# System prompt — embeds full JSON schema (D-23)
# ---------------------------------------------------------------------------


def _get_schema_json() -> str:
    """Return the CharacterSheet JSON schema as a compact string.

    Called once at module level to build TRANSLATE_SYSTEM_PROMPT.
    Uses json.dumps for consistent, compact output.
    """
    return json.dumps(CharacterSheet.model_json_schema(), sort_keys=True)


_SCHEMA_JSON = _get_schema_json()

TRANSLATE_SYSTEM_PROMPT = (
    "You are a strict D&D 5e character sheet parser. "
    "Extract character data from the raw OCR/PDF text in the <player_action> block and "
    "return ONLY a JSON object matching this schema. "
    "Do not include markdown fences, code blocks, or any commentary.\n\n"
    f"Schema: {_SCHEMA_JSON}\n\n"
    "Rules:\n"
    "- Return ONLY valid JSON. No markdown fences or explanation text.\n"
    "- If a field is absent or illegible, use null for optional fields.\n"
    "- All six ability scores must be present; guess 10 if illegible.\n"
    "- class_level must be between 1 and 20."
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


def _defensive_json_parse(raw_response: str) -> dict[str, Any]:
    """Parse JSON from an oMLX response, stripping ``` fences defensively.

    Per RESEARCH Pitfall 4: ShoeGPT verified-live does not emit fences, but
    a future model swap could regress. Strip defensively.

    Args:
        raw_response: The raw string content from the oMLX completion.

    Returns:
        Parsed dict.

    Raises:
        ValueError: If JSON parsing fails after fence stripping.
    """
    text = raw_response.strip()

    # Strip ``` fences (shouldn't happen with json_object format, but defensive)
    match = _FENCE_RE.search(text)
    if match:
        text = match.group(1).strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"oMLX response is not valid JSON: {exc}") from exc


# ---------------------------------------------------------------------------
# Public API — oMLX wrapper
# ---------------------------------------------------------------------------


async def translate_character_sheet(
    openai_client: AsyncOpenAI,
    raw_text_wrapped: str,
    *,
    model: str = "ShoeGPT",
) -> dict[str, Any]:
    """Call the configured ingest backend with ``response_format=json_object`` (D-27).

    Verified live 2026-05-21 against ShoeGPT on omlx serve :8765 — JSON mode
    returns clean JSON with no markdown wrappers. Ollama and OpenRouter
    expose the same OpenAI-compatible surface; the defensive fence strip in
    ``_defensive_json_parse`` covers cloud models that sometimes wrap JSON
    in ```` ```json ```` fences despite ``response_format``.

    Args:
        openai_client:    Backend-agnostic AsyncOpenAI client (oMLX, Ollama,
                          or OpenRouter — selected by ``INGEST_BACKEND``).
        raw_text_wrapped: OCR/PDF text already wrapped in <player_action> sentinels.
        model:            Model id (default "ShoeGPT" for legacy test call sites;
                          real callers resolve this via Settings).

    Returns:
        Parsed dict from the LLM response.

    Raises:
        json.JSONDecodeError: If the LLM response cannot be parsed as JSON.
    """
    completion = await openai_client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": TRANSLATE_SYSTEM_PROMPT},
            {"role": "user", "content": raw_text_wrapped},
        ],
        response_format={"type": "json_object"},
        temperature=0.05,
        max_tokens=600,
    )
    content = completion.choices[0].message.content or ""
    log.debug("omlx_raw_response", char_count=len(content))
    return _defensive_json_parse(content)


# ---------------------------------------------------------------------------
# Public API — full pipeline step
# ---------------------------------------------------------------------------


async def translate_to_character_sheet(
    raw_text: str,
    openai_client: AsyncOpenAI,
    *,
    speaker: str = "character_sheet_ocr",
    user_id: str = "system",
    channel_id: str = "ingest",
    model: str = "ShoeGPT",
) -> tuple[CharacterSheet | None, list[str]]:
    """Translate raw OCR/PDF text into a validated CharacterSheet.

    Pipeline:
      1. sanitize_player_input — wraps in <player_action> sentinels (D-22 security)
      2. translate_character_sheet — calls the configured ingest backend (D-27)
      3. CharacterSheet.model_validate — pydantic v2 validation with range checks

    Args:
        raw_text:      Text extracted from the character sheet attachment.
        openai_client: Backend-agnostic AsyncOpenAI client (oMLX / Ollama /
                       OpenRouter — selected by ``INGEST_BACKEND``; D-27).
        speaker:       Character name for sanitizer sentinel (audit context).
        user_id:       Discord user ID (sanitizer audit context).
        channel_id:    Discord channel ID (sanitizer audit context).
        model:         Model id to use (default "ShoeGPT" for legacy callers).

    Returns:
        (parsed_sheet, warnings):
          - parsed_sheet: validated CharacterSheet, or None if parsing failed.
          - warnings: list of non-fatal issues (truncation, validation failures, etc.)
    """
    warnings: list[str] = []

    # Step 1: Sanitize raw OCR text before sending to oMLX (D-22, T-03-09)
    sanitized = sanitize_player_input(
        raw_text,
        speaker=speaker,
        user_id=user_id,
        channel_id=channel_id,
        max_chars=4000,  # generous limit for character sheets
    )
    if sanitized.truncated:
        warnings.append(
            f"Character sheet text truncated to 4000 chars (original: {len(raw_text)} chars)"
        )
    if sanitized.stripped_tokens:
        warnings.append(
            f"Stripped {len(sanitized.stripped_tokens)} suspicious token(s) from OCR text"
        )

    wrapped_text = sanitized.wrapped

    # Step 2: Call oMLX (ValueError wraps json.JSONDecodeError from _defensive_json_parse)
    try:
        data = await translate_character_sheet(openai_client, wrapped_text, model=model)
    except ValueError as exc:
        log.warning("translate_json_parse_error", error=str(exc))
        warnings.append(f"oMLX returned non-JSON response: {exc}")
        return None, warnings
    except Exception as exc:
        log.warning("translate_omlx_error", error=str(exc))
        warnings.append(f"oMLX translation failed: {exc}")
        return None, warnings

    # Step 3: Pydantic validation
    try:
        sheet = CharacterSheet.model_validate(data)
    except ValidationError as exc:
        log.warning("translate_validation_error", error=str(exc))
        # Surface each field error individually for the review modal
        field_errors = [
            f"{'.'.join(str(loc) for loc in e['loc'])}: {e['msg']}" for e in exc.errors()
        ]
        warnings.extend(field_errors)
        return None, warnings

    log.info(
        "translate_ok",
        name=sheet.name,
        character_class=sheet.character_class,
        class_level=sheet.class_level,
    )
    return sheet, warnings
