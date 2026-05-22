---
title: Character Sheet Ingest Formats
audience: self-host
last_updated: 2026-05-22
---

# Character Sheet Ingest — Supported Formats

EldritchDM supports three ways for a player to load a character into a
running game. The bot tries them in order: D&D Beyond URL → OCR/PDF
→ manual modal. Each is exposed as a slash command in the
[`IngestCog`](../src/eldritch_dm/bot/cogs/ingest.py).

| Format | Slash command | Source | Best for |
| ------ | ------------- | ------ | -------- |
| D&D Beyond character URL | `/upload_character_url` | dm20's `dm20__import_from_dndbeyond` | Players who already use DDB; the cleanest path |
| Image (PNG/JPG) or PDF   | `/upload_character_file` | OCR/PDF pipeline → oMLX schema translation | Scanned sheets, printed character sheets, phone photos |
| Manual entry             | (modal triggered by low-confidence OCR, OR by clicking "Enter manually" in a confirmation modal) | Player types fields directly | Homebrew sheets, anything OCR couldn't parse |

---

## 1. D&D Beyond URL (preferred path)

**Command:** `/upload_character_url url:https://www.dndbeyond.com/characters/12345`

**Requirements:**

- The character must be set to **Public** on D&D Beyond (Settings →
  Privacy → Public). If it's Private, dm20's importer cannot fetch the
  JSON, and the bot will return an ephemeral error.
- The URL must be a *character* URL, not a campaign or homebrew listing.

**Round-trip time:** ~3-5 seconds for a typical character (HTTP fetch +
schema translation + `dm20__create_character`). INGEST-11 budget is 8s.

**What ships into dm20:** every standard field — class, subclass, level,
race, ability scores, HP, AC, proficiencies, equipment, spells (if any),
features. Homebrew flags from DDB are passed through verbatim.

---

## 2. Image / PDF upload (OCR + AI translation)

**Command:** `/upload_character_file` then attach the file.

**Supported formats:**

| Format | macOS path | Linux path | Notes |
| ------ | ---------- | ---------- | ----- |
| PNG    | `ocrmac` (Apple Vision) | `easyocr` (PyTorch + EasyOCR weights) | Best for printed sheets and phone snaps |
| JPG / JPEG | `ocrmac` | `easyocr` | Same as PNG |
| PDF (digital, with text layer) | PyMuPDF (`fitz`) text extraction | PyMuPDF | Fastest path — sub-second extraction |
| PDF (scanned, image-only)      | PyMuPDF rasterize → `ocrmac` | PyMuPDF rasterize → `easyocr` | 5-15s — slowest path |

**Pipeline:**

1. **Extract text** (OCR or PyMuPDF text layer).
2. **Confidence score** computed from OCR output (per-token confidence
   averaged; lower bound for `easyocr`, higher for `ocrmac`).
3. **Translate** to JSON via oMLX (`response_format=json_object`,
   `temperature=0.05` for determinism).
4. **Validate** via pydantic v2 (`CharacterSheet`); ability score
   ranges, class/race lookup against `dm20__get_class_info` /
   `get_race_info`.
5. **Confirm** via `CharacterReviewModal` (5-component cap; ability
   scores packed into one TextInput).
6. **Commit** to dm20 via `dm20__create_character`.

**Confidence gate** (INGEST-09): if the OCR confidence is below `0.6`,
the pipeline skips the review modal and routes the user straight to
`CharacterEntryModal` (manual entry) as a first-class path. This avoids
the "garbage-in, weird-modal-out" UX where the player would just hit
the cancel button anyway.

**Round-trip time targets** (INGEST-11):

| Source | Target |
| ------ | ------ |
| Digital PDF (text layer)  | < 4 s |
| Image with `ocrmac`       | < 6 s |
| Image with `easyocr`      | < 12 s (Linux best-effort) |
| Scanned PDF (rasterize+OCR) | < 15 s |

If you exceed these consistently, capture a debug trace
(`LOG_LEVEL=DEBUG`) and file a bug with the file size, dimensions, and
oMLX wall-clock from the structured logs.

**License note:** the primary PDF parser is PyMuPDF, which is AGPL-3.0.
For self-hosting (the typical use case) this is fine. If you intend to
fork EldritchDM and deploy it as a closed-source hosted service, swap
to the `pypdf` fallback path — see [README "License & Third-Party"](../README.md#license).

---

## 3. Manual entry modal

Two ways to land here:

1. **Forced by low confidence** (INGEST-09): an OCR pass returned a
   confidence below `0.6`. The bot does not show the review modal;
   it opens `CharacterEntryModal` directly with empty fields.

2. **Player-initiated**: in the review modal, the player clicks
   "Enter manually" instead of "Confirm". The modal reopens blank
   (player overrides any extracted fields).

**Modal structure (5-component cap — Discord limit):**

| Field | Type | Notes |
| ----- | ---- | ----- |
| Name | TextInput (short) | Free text |
| Class & Subclass | TextInput (short) | "Fighter / Battle Master", "Wizard / Evoker", etc. |
| Level | TextInput (short) | Integer 1-20 |
| Race | TextInput (short) | "Human", "Half-Elf", etc. — validated against `dm20__get_race_info` |
| Ability scores | TextInput (single line) | Six numbers, space-separated, STR/DEX/CON/INT/WIS/CHA order: e.g. `15 14 13 12 10 8` |

On submit, the same pydantic validation runs as for OCR'd characters.
Mismatches surface as ephemeral errors with field-level detail.

---

## Restrictions and security notes

- **Uploader gating** (INGEST-10): only the invoking user OR a DM can
  upload to a given character slot. Other players see an ephemeral
  "❌ Not your character" warning.
- **Confirmations are ephemeral** so the player can correct mistakes
  privately. The final `dm20__create_character` call is non-ephemeral
  (the lobby embed updates publicly when a slot fills).
- **Sanitizer applies** to every TextInput value before it reaches any
  MCP call. See `docs/ARCHITECTURE.md` § Sanitizer for the rules.
