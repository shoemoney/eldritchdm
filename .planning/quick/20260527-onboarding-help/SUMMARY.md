---
id: 260527-onboarding-help
slug: onboarding-help
date: 2026-05-27
status: complete
---

# SUMMARY — Bot Onboarding UX

## Done
- New cog `src/eldritch_dm/bot/cogs/onboarding.py`:
  - `/help` (ephemeral) — embed grouping all 9 commands by Setup / Session / Diagnostics with a "Typical flow" guide.
  - `on_guild_join` listener — posts a public welcome embed to system channel (fallback: first writable text channel). Fails soft on Forbidden/HTTPException.
- Cog registered in `src/eldritch_dm/bot/bot.py` after diagnostics.

## Verified
- `ruff check` — clean.
- `py_compile` — clean.
- Import smoke test — both embed builders construct without error.
- Live bot restart — `cmd_count=9` (was 8), gateway connected, no errors.

## Out of scope (intentionally)
- Localization, persistent buttons, per-channel auto-welcome.
