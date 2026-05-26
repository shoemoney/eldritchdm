---
adr: 001
title: No public HTTP endpoints — gateway-only Discord integration
status: accepted
date: 2026-05-26
deciders: jeremy@shoemoney.com
related_features:
  - Discord Linked Roles Verification URL
  - Discord Interactions Endpoint URL
  - Webhook-based user-install flows
---

# ADR-001: No public HTTP endpoints — gateway-only Discord integration

## Context

EldritchDM is positioned as a **local-first, self-hostable** Discord bot. The
`INSTALL.md` pre-flight section literally states *"No inbound ports required
(no public endpoints)."* This is a load-bearing product claim, not an
incidental implementation detail — it is what makes the bot installable on a
home Mac mini behind a NAT with zero infrastructure work.

Discord's developer portal exposes several configuration fields that, if used,
require the bot to operate a publicly-reachable HTTPS endpoint:

1. **Interactions Endpoint URL** — routes slash-command interactions via HTTP
   POST instead of the gateway WebSocket. Mutually exclusive with gateway
   delivery: once set, interactions stop flowing through the gateway.
2. **Linked Roles Verification URL** — OAuth2 redirect for the role-metadata
   API. Required if the bot wants to gate Discord roles on bot-controlled
   attributes (e.g. `campaigns_completed >= 1`).
3. **Terms of Service URL** / **Privacy Policy URL** — surfaced in the install
   flow. Required for the App Directory at 75+ servers but optional below.

This ADR captures the decision to **decline #1 and #2 for v1.x**, and to leave
#3 deferred until verification is actually needed.

## Decision

EldritchDM v1.x ships with **no public HTTP endpoints**. The bot communicates
with Discord exclusively over the gateway WebSocket. The following portal
fields are intentionally left **blank**:

- Interactions Endpoint URL → blank
- Linked Roles Verification URL → blank
- Terms of Service URL → blank
- Privacy Policy URL → blank

## Consequences

### Reinforced

- **The "no inbound ports" promise is preserved.** Self-hosters can run the
  bot behind a residential NAT, on a laptop, or in a container without DNS,
  TLS, reverse-proxy, or tunnel setup.
- **Single supervised process is sufficient.** `docker-compose.yml` does not
  need an `nginx` / `caddy` sidecar, no Let's Encrypt cert rotation, no
  Cloudflare Tunnel credential.
- **Attack surface is bounded** to outbound HTTPS + Discord gateway.
  Confirmed by the v1.11 Phase 31 security audit (0 findings across 8
  surfaces — `.planning/SECURITY-AUDIT-v1.11.md`).
- **Stateful design assumptions hold.** The bot keeps long-lived in-memory
  caches (`MCPCache`, `NarrCacheGate`, `SmartMonsterDriver` per-round cache,
  `CharacterSnapshot`), persistent views resumed across restarts, and an
  asyncio orchestrator task per active channel. None of these are compatible
  with a serverless / per-request invocation model.

### Foregone

- **No Linked Roles gating.** Servers cannot auto-grant a role like
  `@Veteran-Player` based on bot-controlled metadata (e.g. completed
  campaigns, peak character level). Mitigation: server admins can grant
  roles manually based on out-of-band knowledge; the bot does not need to
  participate in role assignment.
- **No HTTP-based serverless deployment.** EldritchDM cannot be hosted on
  Cloudflare Workers, AWS Lambda, or Vercel functions. Mitigation: the bot
  is explicitly designed for self-hosting on personal hardware; serverless
  is not a target.
- **No user-install (DM-context) flow.** Discord's user-install model
  requires the Interactions Endpoint URL. Mitigation: EldritchDM is a
  guild-install bot — it operates on a per-channel basis with persistent
  state, which the user-install model does not support.

## Reversal triggers

Re-evaluate this decision if **any** of the following occur in a future
milestone:

1. Multiple users explicitly request Linked Roles after running the bot in
   live play (not before — premature demand-modeling is forbidden per the
   CLAUDE.md SENIOR DEV OVERRIDE).
2. A real user wants to deploy EldritchDM to a serverless / functions-as-a-
   service platform and is willing to maintain the rewrite.
3. The bot's installed-server count crosses the verification threshold
   (75 guilds), at which point Discord requires submission with a privacy
   policy and terms of service URL. At that point, item #3 above (TOS /
   privacy URLs) becomes mandatory but can still point to plain GitHub
   pages — it does not on its own require a live HTTP endpoint.

If a reversal happens, the new ADR must explicitly call out:

- Where the public endpoint is hosted (VPS, tunnel, edge worker)
- How TLS certs rotate
- How OAuth tokens are stored and rotated (current SQLite schema has no
  encrypted-secrets surface)
- The new threat model — re-running the v1.11 audit checklist with
  attention to the new inbound surface

## Alternatives considered

| Option | Rejected because |
|---|---|
| Add Interactions Endpoint URL on v1 | Mutually exclusive with gateway delivery — would silently break every slash command in the running discord.py orchestrator. Requires full rewrite to a stateless model. |
| Add Linked Roles in v1 with a Cloudflare Tunnel | ~2–3 days of work for a cosmetic gamification feature with zero current user demand. Violates the "no inbound ports" product attribute for marginal value. |
| Ship TOS/Privacy stubs on v1 just in case | Not required below 75 guilds. Drafting placeholder documents that may not reflect the eventual data-handling story is worse than honest omission. |

## References

- `INSTALL.md` — pre-flight networking section ("No inbound ports required")
- `.planning/SECURITY-AUDIT-v1.11.md` — 8-surface audit, 0 findings, all
  attack vectors are outbound-only
- `docs/DEPLOYMENT.md` — Docker compose deployment with no exposed ports
- `docs/ARCHITECTURE.md` — three-brain architecture, stateful orchestrator
- Discord docs — [Receiving and Responding to Interactions](https://discord.com/developers/docs/interactions/receiving-and-responding),
  [Linked Roles](https://discord.com/developers/docs/tutorials/configuring-app-metadata-for-linked-roles)
