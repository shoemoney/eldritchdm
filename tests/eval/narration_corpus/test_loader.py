"""Loader-only smoke test (Phase 18 / NARRCACHE-02 / D-131).

The full per-entry gate assertion lives in
``tests/eval/test_narration_gate_corpus.py``. Here we pin the corpus
schema: 50 entries, 25/25 split, no malformed lines.
"""

from __future__ import annotations

import pytest

from tests.eval.narration_corpus.loader import CorpusEntry, load_corpus


def test_corpus_total_count() -> None:
    entries = load_corpus()
    assert len(entries) == 50, f"corpus must have 50 entries; got {len(entries)}"


def test_corpus_split_25_25() -> None:
    entries = load_corpus()
    cacheable = [e for e in entries if e.expected_cacheable]
    non_cache = [e for e in entries if not e.expected_cacheable]
    assert len(cacheable) == 25, f"expected 25 cacheable; got {len(cacheable)}"
    assert len(non_cache) == 25, f"expected 25 non-cacheable; got {len(non_cache)}"


def test_corpus_unique_ids() -> None:
    entries = load_corpus()
    ids = [e.id for e in entries]
    assert len(ids) == len(set(ids)), "duplicate ids in corpus"


def test_corpus_entries_are_typed() -> None:
    entries = load_corpus()
    assert all(isinstance(e, CorpusEntry) for e in entries)


def test_corpus_id_naming_convention() -> None:
    entries = load_corpus()
    for entry in entries:
        if entry.expected_cacheable:
            assert entry.id.startswith("cache-"), (
                f"cacheable entry id must start with 'cache-': {entry.id}"
            )
        else:
            assert entry.id.startswith("leak-"), (
                f"non-cacheable entry id must start with 'leak-': {entry.id}"
            )


def test_corpus_loader_rejects_malformed_json(tmp_path) -> None:
    bad = tmp_path / "corpus.jsonl"
    bad.write_text("this is not json\n", encoding="utf-8")
    with pytest.raises(ValueError, match="invalid JSON"):
        load_corpus(bad)


def test_corpus_loader_rejects_bad_schema(tmp_path) -> None:
    bad = tmp_path / "corpus.jsonl"
    bad.write_text('{"id":"x","text":"y"}\n', encoding="utf-8")  # missing fields
    with pytest.raises(ValueError, match="schema validation failed"):
        load_corpus(bad)
