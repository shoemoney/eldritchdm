# Discord Developer Portal — App Setup Walkthrough

Step-by-step guide for registering EldritchDM as a Discord application and
inviting it to your server. Follow once per Discord account that wants to
self-host the bot.

**Time required:** 10–15 minutes.
**Prerequisites:** A Discord account, admin access to the Discord server
you want to install the bot in.

---

## 1. Create the application

1. Open https://discord.com/developers/applications (sign in if prompted)
2. Click **"New Application"** (top-right)
3. Name it `EldritchDM`
4. Tick the developer-terms checkbox
5. Click **"Create"**

You are now on the application's **General Information** page.

## 2. Fill General Information

| Field | Value |
|---|---|
| **App Icon** | Upload `assets/avatars/eldritchdm_avatar.png` (1024×1024) |
| **Cover Image** | Optional — upload the same avatar or a wider variant |
| **Description** | `A local-first, self-hosted AI Dungeon Master for Dungeons & Dragons 5e. Narration runs on your own machine via oMLX. Every die roll, HP change, AC check, and turn boundary is enforced by a deterministic Python rules engine — the AI is forbidden from doing the math. A forever DM that won't cheat.` |
| **Tags** | `dnd`, `dungeons-and-dragons`, `dungeon-master`, `tabletop`, `rpg` |
| **Interactions Endpoint URL** | **Leave BLANK** (see ADR-001) |
| **Linked Roles Verification URL** | **Leave BLANK** (see ADR-001) |
| **Terms of Service URL** | `https://github.com/<your-fork>/eldritchdm/blob/main/TERMS.md` (only required at 75+ guilds; safe to leave blank otherwise) |
| **Privacy Policy URL** | `https://github.com/<your-fork>/eldritchdm/blob/main/PRIVACY.md` (same — only required at 75+ guilds) |

Click **"Save Changes"** at the bottom of the page.

> ⚠️ **Do NOT set Interactions Endpoint URL.** It is mutually exclusive
> with gateway delivery — if you put a URL there, every slash command will
> stop working in the running bot. See `.planning/ADR-001-no-public-http-endpoints.md`
> for the full reasoning.

## 3. Configure the Bot tab

Click **"Bot"** in the left sidebar.

### Bot Profile
| Field | Value |
|---|---|
| **Username** | `EldritchDM` |
| **Avatar** | The portal usually inherits this from the App Icon; if not, upload `assets/avatars/eldritchdm_avatar.png` again |
| **Banner** | Optional |
| **About Me** | `Your mechanically-honest AI Dungeon Master. I narrate the story. The dice and rules engine decide what actually happens. /start_game to begin.` (190-char limit — current draft is 143) |

### Authorization Flags

| Toggle | State |
|---|---|
| **Public Bot** | **OFF** — only you should be able to invite this bot to servers |
| **Requires OAuth2 Code Grant** | **OFF** — standard bot install |

### Privileged Gateway Intents

EldritchDM uses `discord.Intents.default()` and explicitly disables
`message_content` for security (`src/eldritch_dm/bot/bot.py:60-61`,
*"bot never reads raw messages"* per D-04). It does not iterate guild
members or track presence either. **Leave all three privileged intents
OFF.**

| Intent | State | Why |
|---|---|---|
| **Presence Intent** | **OFF** | Bot does not track who is online |
| **Server Members Intent** | **OFF** | Bot resolves player IDs from interaction payloads, not from guild member iteration. Character rosters come from dm20, not Discord members |
| **Message Content Intent** | **OFF** | Only inputs are slash commands and modal submissions, both delivered via interactions (not gated by this intent) |

Side benefit: leaving these OFF means the bot is exempt from Discord's
75-guild verification gate for privileged intents. The bot is honest
about needing zero privileged data.

### Bot Token

1. Click **"Reset Token"** (a fresh token is safer than the placeholder)
2. Confirm the dialog — Discord shows you the new token **exactly once**
3. Copy it immediately
4. Paste it into your `.env` as `DISCORD_TOKEN=...`

> 🔐 **Treat the token like a password.** Never commit it to git. Never
> paste it into a chat with a third party. If it leaks, return here and
> click "Reset Token" again — the old one stops working instantly.

## 4. Build the install link

Click **"OAuth2"** → **"URL Generator"** in the left sidebar.

### Scopes (top half)

Check exactly these two boxes:
- ☑ `bot`
- ☑ `applications.commands`

Everything else stays unchecked.

### Bot Permissions (lower half)

Check these:

| Permission | Why |
|---|---|
| ☑ Send Messages | Post narration, embeds, and combat updates |
| ☑ Embed Links | The combat tracker and lobby use rich embeds |
| ☑ Attach Files | Character sheet PDFs and avatar attachments |
| ☑ Read Message History | Needed to resume sessions after a restart |
| ☑ Use Slash Commands | `/start_game`, `/load_adventure`, etc. |
| ☑ Manage Messages | Clean up ephemeral interaction artifacts |

A **Generated URL** appears below. Copy it.

### Integration Type

In the dropdown above the generated URL, leave it set to **"Guild Install"**
(the default). Do **not** pick "User Install" — EldritchDM is per-channel
stateful and the user-install model does not support that.

## 5. Invite the bot to your server

1. Paste the generated URL into a browser
2. Pick the target server from the dropdown (you must have **Manage Server**
   permission on it)
3. Confirm the permissions list
4. Solve the captcha if shown
5. Discord redirects you with a "EldritchDM has been added to <server>"
   confirmation

The bot now appears in your server's member list as **offline**. It will
go online the first time you start the bot process.

## 6. First run

In a terminal on your bot host:

```bash
cd path/to/eldritchdm
cp .env.example .env
# Edit .env and paste your DISCORD_TOKEN
./scripts/run.sh    # or: docker compose up -d
```

Watch the logs for `bot_ready` — that confirms the gateway connection is
live. Then in your Discord server, type `/start_game` in any channel the
bot has access to. If the slash command autocompletes, you're set up
correctly.

## 7. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Slash commands don't autocomplete | Commands haven't synced yet — global sync can take up to 1 hour | Set `DISCORD_GUILD_IDS=<your-server-id>` in `.env` for instant sync to that specific guild |
| "This interaction failed" on every click | `Message Content Intent` is off, or `DISCORD_TOKEN` is wrong | Re-check intents in the Bot tab; reset and re-paste the token |
| Bot online but doesn't respond to /start_game | Bot lacks Send Messages or Use Slash Commands in that channel | Check channel-level permission overrides |
| `403 Forbidden` in logs when posting embeds | Missing Embed Links permission | Re-invite the bot with the URL from step 4 (the new permissions overwrite the old) |
| Bot crashes immediately on start with `LoginFailure` | Token invalid or revoked | Reset Token in the portal, update `.env`, restart |
| Slash commands work in DM but not server | Server has slash commands disabled at the integration level | Server settings → Integrations → EldritchDM → enable the relevant commands |

For deeper bot issues, see `docs/TROUBLESHOOTING.md` (general) or
`docs/dm20-troubleshooting.md` (rules engine specifically).

## 8. Optional — App Emojis

The **Emojis** tab in the portal lets you upload up to 2,000 custom emojis
that belong to the application (not a specific server). They render inline
in any message the bot posts. EldritchDM v1.x uses Unicode emojis
(`⚔️ Attack`, `🛡️ Dodge`, `⚗️ Cast Spell`, `⏭️ End Turn`) that work
without any upload.

**Recommendation:** leave this empty in v1. Unicode is fine and zero-config.

If you later want a small set of high-impact custom emojis, the targets
that punch above their weight are:

| Emoji name (must match regex `[a-zA-Z0-9_]{2,32}`) | Where it would show |
|---|---|
| `d20_glow` | Combat tracker headers — matches the bot avatar |
| `crit_20` | Attack roll results that land a natural 20 |
| `crit_1` | Attack roll results that land a natural 1 |
| `hp_full` / `hp_half` / `hp_low` | Initiative tracker HP indicator |
| `cond_poisoned`, `cond_prone`, `cond_blessed`, ... | Initiative tracker condition badges |

After uploading, reference them in bot code by their snowflake ID:
`<:d20_glow:1234567890>` (not by name). The Discord portal shows the ID
under each emoji once it is uploaded.

**Upload constraints:** PNG/JPEG/GIF/WEBP/AVIF, ≤256 KB, 128×128 recommended.
Names must be 2–32 characters, alphanumeric + underscore only.

Doing the 4–6 most-visible emojis is ~1 hour of work — only do it after
the bot has run live and you've identified which moments genuinely need
custom iconography.

## 9. Optional — disable Public Bot toggle once tested

After you've confirmed the bot works:
- General Information → confirm Description and tags are final
- Bot → confirm Public Bot is OFF if it's only for your friends
- OAuth2 → re-generate the install URL with the same scopes/perms and
  bookmark it for future server installs

## References

- `.planning/ADR-001-no-public-http-endpoints.md` — why Interactions
  Endpoint URL and Linked Roles Verification URL stay blank
- `PRIVACY.md` — what to link in the Privacy Policy URL field
- `TERMS.md` — what to link in the Terms of Service URL field
- `INSTALL.md` — full self-host setup including oMLX and dm20 MCP
- [Discord Developer Portal](https://discord.com/developers/applications) —
  the page you're configuring
- [Discord Intents docs](https://discord.com/developers/docs/topics/gateway#privileged-intents) —
  details on Message Content and Server Members intents
