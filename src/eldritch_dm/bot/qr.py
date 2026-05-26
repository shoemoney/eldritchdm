"""
QR code rendering helper for Discord embed thumbnails.

Extracted from LobbyCog's inline ``_render_qr`` in Plan 01; now a shared
module usable by any cog that needs QR codes.

RESEARCH ref: §11 (segno vs qrcode decision — segno is smaller, no native deps)

Usage::

    qr_file = render_qr_for_embed(server_url, filename="party_qr.png")
    embed.set_thumbnail(url="attachment://party_qr.png")
    await interaction.followup.send(embed=embed, files=[qr_file])

**Frozen contract** (Plan 01 SUMMARY — do not change without testing Discord
embed thumbnail dimensions):
  - error='m'    — 15% correction, robust to camera glare without size bloat
  - scale=8      — ~250×250 px, the sweet spot for Discord embed thumbnails
  - border=2     — minimal quiet zone; Discord renders below 4 without artefacts

Color palette follows EmbedColor in embeds.py:
  - dark='black', light='white' — clean render on Discord dark and light themes
"""
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import io

import discord
import segno


def render_qr_for_embed(url: str, *, filename: str = "qr.png") -> discord.File:
    """Generate a QR code as an in-memory PNG suitable for a Discord embed thumbnail.

    Args:
        url:      URL to encode in the QR code.
        filename: Discord attachment filename (must end in .png for embed support).

    Returns:
        A :class:`discord.File` ready for
        ``interaction.followup.send(files=[...])`` and
        ``embed.set_thumbnail(url=f"attachment://{filename}")``.

    RESEARCH ref: §11 (segno usage, error correction levels, scale trade-offs)
    Plan ref: Plan 01 SUMMARY — function signature and params are FROZEN.
    """
    qr = segno.make(url, error="m")
    buf = io.BytesIO()
    qr.save(buf, kind="png", scale=8, border=2, dark="black", light="white")
    buf.seek(0)
    return discord.File(buf, filename=filename)
