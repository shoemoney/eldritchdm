# EldritchDM Tactical Eval Corpus — License & Provenance

## License

This corpus (`tactical_corpus.jsonl`) is licensed under the
**Apache License, Version 2.0**. See the LICENSE file at the repository
root for full text.

## Provenance Statement (Phase 12 / D-76)

Every scenario in `tactical_corpus.jsonl` is **original content,
hand-authored in 2026** by the EldritchDM maintainers specifically for
this project. No scenario is derived, transcribed, paraphrased, or
otherwise based on any copyrighted role-playing-game source material,
including but not limited to:

- *The Monsters Know What They're Doing* and its sequels (Keith Ammann)
- Any published Wizards of the Coast adventure module
- Any third-party 5e adventure module sold under a non-permissive license

Monsters referenced in this corpus are drawn from the Systems Reference
Document 5.1 (SRD 5.1), which Wizards of the Coast released under the
Creative Commons Attribution 4.0 International License. Generic SRD
monster names (ogre, goblin, mind flayer, lich, swarm of rats, etc.) are
used. Player-character names (Aria, Borin, Cassia, Doran, Elena, ...)
are generic and do not correspond to characters from any published
adventure.

## Contribution Guidance

Future contributors adding scenarios MUST:

1. Author the scenario from scratch (no copy-paste from copyrighted
   sources, including AI-generated text that may have memorized them).
2. Use only SRD-safe monster names.
3. Use generic PC names that do not appear in published modules.
4. Include a meaningful `rationale` field (≥10 chars) explaining WHY
   the `expected_target_pool` is correct, so reviewers can audit corpus
   quality without re-deriving the tactical logic.

See `.planning/phases/12-llm-judge-tactical/12-CONTEXT.md` (D-76) for
the canonical decision record.
