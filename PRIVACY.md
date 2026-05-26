# Privacy Policy

**Effective date:** 2026-05-26
**Project:** EldritchDM
**Maintainer:** Jeremy Schoemaker — jeremy@shoemoney.com
**License:** Apache-2.0
**Source:** https://github.com/shoemoney/eldritchdm

> ⚠️ **This is a self-hostable open-source Discord bot.** Each person who runs
> EldritchDM is operating their own instance on their own hardware. The
> *project maintainer* (Jeremy Schoemaker) does **not** operate a hosted
> service, does **not** receive data from anyone's bot installation, and
> cannot see what happens inside your instance. The privacy practices that
> matter to your users are the practices of *whoever runs the specific bot
> instance they interact with*. If that's you, this document also serves as
> a template — fork it and update the operator contact.

---

## 1. Who this policy applies to

This policy applies to **the reference EldritchDM software as distributed at
https://github.com/shoemoney/eldritchdm**. If you install and run the bot, you
are an "Operator" and you become the data controller for the data your
specific instance handles.

If you are a Discord user interacting with an EldritchDM bot installed on
someone else's Discord server, ask the server owner who their Operator is —
they will know what data is stored and where.

## 2. What the bot stores (default configuration)

EldritchDM stores its state in a **local SQLite file** on the Operator's
machine (default path: `./eldritch.sqlite3`). The schema captures only what
is needed to run a Dungeons & Dragons 5e game:

- Discord user IDs of players who have joined an active campaign
- Discord channel IDs the bot is active in
- Character sheets uploaded by players (name, class, race, ability scores,
  spells, inventory — the content of a typical D&D character sheet)
- In-progress game state (current HP, conditions, initiative order,
  combat log, narration history)
- Persistent UI state needed to resume the bot after a restart

The bot does **not** store:

- Email addresses (Discord does not expose them)
- Real names (unless a player types one into a free-text field)
- IP addresses
- Voice data
- Direct messages outside the bot's own channels
- Anything from Discord channels the bot is not invited to

## 3. What the bot sends to third parties

EldritchDM contacts the following services in normal operation:

| Service | Why | What is sent |
|---|---|---|
| **Discord gateway** (gateway.discord.gg, discord.com) | Required — this is how a Discord bot works | Slash commands, button clicks, message content in active channels |
| **Open5e API** (api.open5e.com) | Read-only lookups for SRD rules content | Search queries for spells, monsters, items — no user identifiers |
| **A local LLM** (default: oMLX at http://localhost:8765/v1, on the Operator's machine) | Narration + character-sheet ingest | Sanitized game-state snippets — never the player's Discord ID, never raw PII |

The bot **does not by default** send any data to:
- Hosted OpenAI, Anthropic, Google, or any other commercial AI API
- Analytics or telemetry services
- The project maintainer

An Operator **may optionally** configure alternate LLM backends (e.g.
OpenRouter, Ollama, OpenAI). If they do, game data will flow to that backend
under that vendor's privacy policy. The Operator is responsible for
disclosing this choice to their players.

## 4. Optional observability

EldritchDM ships with optional Phoenix / OpenTelemetry tracing
(`OBSERVABILITY_ENABLED=true`). This is **off by default**. When enabled, the
bot emits spans to a local Phoenix instance on the Operator's machine. No
data leaves the Operator's host unless they have configured an external OTLP
collector — in which case the Operator is responsible for that collector's
privacy posture.

## 5. Retention

State is retained **until the Operator deletes it**. There is no automatic
expiry. The bot does not phone home, does not log to any external system,
and does not back up your data anywhere.

To delete your data on a specific instance, ask the Operator. To delete
*everything*, an Operator can stop the bot and remove the SQLite file. There
is no remote tombstone to clear.

## 6. Player rights

If you are a Discord user playing in an EldritchDM-hosted campaign:

- You can ask the Operator to show you what character sheet they have stored
  for you (it is just a row in their SQLite).
- You can ask the Operator to delete your character at any time.
- You can leave the campaign channel; the bot will stop receiving events
  from you immediately.
- The bot does not have a "right to be forgotten" automation. The Operator
  has full database access and can honor any request manually.

## 7. Children's privacy

EldritchDM is not designed for users under 13 — neither is Discord (it
requires age 13+ globally and 16+ in some jurisdictions). If you are a
parent and want a child removed from a specific instance, contact that
instance's Operator.

## 8. Security

The Operator is responsible for:
- Securing the host running the bot (OS updates, firewall, full-disk
  encryption if appropriate)
- Keeping the `DISCORD_TOKEN` and any LLM API keys out of public git history
- Restricting access to the SQLite file (default permissions inherit from
  the running user)

EldritchDM as software:
- Stores no plaintext passwords or session tokens *for users* — Discord
  handles authentication
- Has passed a v1.11 security audit (`.planning/SECURITY-AUDIT-v1.11.md` in
  the repo, 0 findings across 8 attack surfaces)
- Has no inbound network ports by design — the bot communicates outbound
  only

## 9. Changes to this policy

The reference policy in the repository may evolve. Operators who fork this
project are encouraged to keep their version current. The `Effective date`
at the top reflects the most recent revision.

## 10. Contact

- **Project maintainer** (software questions, vulnerability reports):
  jeremy@shoemoney.com
- **Your instance's Operator** (your data, your character, your campaign):
  ask the server owner

---

**Not legal advice.** This document describes the software's behavior in
plain language. It is not a substitute for legal counsel. Operators with
specific compliance obligations (GDPR, CCPA, COPPA, HIPAA, etc.) should
consult a lawyer for their jurisdiction.
