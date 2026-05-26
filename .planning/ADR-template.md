---
adr: NNN
title: One-sentence verb-led title — what was decided, in plain language
status: proposed
date: YYYY-MM-DD
deciders: name@email.com
related_features:
  - Specific Discord field, API endpoint, library, or product surface
  - One bullet per affected thing — keep this list short and concrete
# Optional fields (delete if not used):
# supersedes: ADR-NNN
# superseded_by: ADR-MMM
---

# ADR-NNN: One-sentence verb-led title

> **Template usage.** Copy this file to `.planning/ADR-NNN-<kebab-slug>.md`,
> pick the next free NNN, fill every section below, then delete this blockquote
> and the inline `<!-- guidance -->` comments. The frontmatter `status` should
> start as `proposed` while under discussion and flip to `accepted` once you've
> decided to live with it. If a later ADR overturns this one, change `status`
> to `superseded` and add a `superseded_by: ADR-MMM` field — do **not** delete
> the file; the historical reasoning is the point of having ADRs.

## Context

<!--
Two to four short paragraphs. Cover:
  - What changed in the project / world / requirements that surfaced the
    question. Don't write a novel — assume the reader knows the codebase.
  - The forces in tension. (Speed vs correctness, simplicity vs flexibility,
    self-host vs hosted, etc.) Name them explicitly.
  - Any constraint that narrows the option space — pinned dependency floor,
    a product-attribute claim like "no inbound ports", a regulatory line.
  - If the trigger was a specific event (PR review, incident, audit finding,
    user request), link it.

If the Context can't be written without re-stating the Decision, the
decision isn't really decided yet — flip status back to `proposed` and
write more context.
-->

## Decision

<!--
One short paragraph. State the chosen path imperatively:
  "We will X by Y, with Z as a guardrail."
No hedging. No "we could also..." — that's the Alternatives section.

If the decision has multiple parts, list them as a tight bullet list
under this paragraph. Each bullet is a discrete commitment.
-->

## Consequences

### Reinforced

<!--
What this decision PRESERVES or AMPLIFIES that the project already cares about.
This is where you connect the local decision to the larger product story:
  - "The 'no inbound ports' promise from INSTALL.md is preserved."
  - "Attack surface remains outbound-only (matches v1.11 audit)."
  - "Self-hosters can still install on a home laptop with no infra."

If you can't think of anything this reinforces, you might be deciding
in isolation from the rest of the system. Reconsider.
-->

### Foregone

<!--
What this decision GIVES UP. Be honest. List the actual capability cost,
not a euphemism for it. For each foregone capability include a one-line
mitigation if there is one ("Mitigation: ..."), or admit there isn't.

This section is the most-read part of an ADR six months later. Make it
truthful and specific, not aspirational.
-->

## Reversal triggers

<!--
Concrete, observable signals that would justify revisiting this decision.
Phrase each as something a future reader could check against reality:

  1. "Multiple users explicitly request X after running the bot in
      live play (not before — premature demand-modeling is forbidden)."
  2. "Library Y reaches version N and adds capability we need."
  3. "Monthly cost crosses $Z."

Bad triggers (don't write these):
  - "If it ever stops working"            (too vague)
  - "If someone wants to use feature Y"   (someone always wants something)
  - "Re-evaluate every quarter"           (calendar-based reviews rot)

If you cannot name even one observable trigger, the decision may be
too vague — or it may genuinely be permanent (e.g. "we will not use
language X" for a moral/license reason). In the permanent case, write
"None — this decision is permanent because <reason>." and move on.
-->

## Alternatives considered

<!--
A two-column table is usually enough. One row per alternative. Each
"Rejected because" must be the specific reason — not a tautology like
"because we chose the other one".

| Option | Rejected because |
|---|---|
| Alternative A | Specific reason rooted in a constraint above |
| Alternative B | Specific reason — cost, complexity, license, etc. |
| Alternative C | Specific reason |

If you only considered one option, this isn't really an ADR — it's a
decision log entry. Either find at least one real alternative or
demote the file to a TODO/note.
-->

## References

<!--
Link the ground truth. ADRs lose value when their factual claims are
unverifiable. Cite:
  - The specific file(s) and line(s) the decision protects or constrains
  - Vendor / library / spec docs that informed the choice
  - Prior ADRs this builds on or scopes
  - Issues, audits, or incidents that triggered the decision
-->

- `path/to/file.md` — short description of why it's relevant
- [External doc title](https://example.com/url) — anchor link to specific
  section preferred over a bare URL
- `.planning/ADR-MMM-related-decision.md` — sibling ADR this extends or scopes
