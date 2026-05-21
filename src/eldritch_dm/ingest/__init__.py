"""EldritchDM ingest package.

Public API:
    CharacterSheet   — validated character data (pydantic v2)
    AbilityScores    — D&D 5e ability scores (pydantic v2)
    IngestResult     — output envelope from the ingest pipeline
    ingest           — async pipeline entry-point (added in plan-02 Task 6)
"""

from eldritch_dm.ingest.schema import AbilityScores, CharacterSheet, IngestResult

__all__ = ["AbilityScores", "CharacterSheet", "IngestResult"]
