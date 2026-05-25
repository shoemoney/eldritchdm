"""Per-entry corpus assertion (Phase 18 / NARRCACHE-02 / D-131).

The non-negotiable success bar: ``NarrCacheGate.is_pure_narration(entry.text)
== entry.expected_cacheable`` for EVERY corpus entry. Parametrized by entry
id so a failure points directly at the offending entry's rationale.

False-negative rate (mechanical text wrongly classified as cacheable) is
the dangerous case and MUST be 0% — that violates the v1.0
mechanical-honesty contract.
"""

from __future__ import annotations

import pytest

from eldritch_dm.observability.narration_cache import NarrCacheGate
from tests.eval.narration_corpus.loader import CorpusEntry, load_corpus

_ENTRIES: list[CorpusEntry] = load_corpus()


@pytest.mark.parametrize(
    "entry",
    _ENTRIES,
    ids=[e.id for e in _ENTRIES],
)
def test_gate_classification_matches_corpus(entry: CorpusEntry) -> None:
    actual = NarrCacheGate.is_pure_narration(entry.text)
    assert actual == entry.expected_cacheable, (
        f"\ncorpus[{entry.id}] ({entry.category}): gate disagreed with ground truth\n"
        f"  text: {entry.text!r}\n"
        f"  expected_cacheable: {entry.expected_cacheable}\n"
        f"  actual:             {actual}\n"
        f"  rationale: {entry.rationale}"
    )


def test_corpus_zero_false_negatives() -> None:
    """Aggregate guard: 0% false-negative rate (mechanical wrongly accepted).

    The parametrized test above catches each individual failure; this
    aggregate test exists so a single visible PASS/FAIL line in CI states
    the safety invariant.
    """
    fn = [
        e for e in _ENTRIES if not e.expected_cacheable and NarrCacheGate.is_pure_narration(e.text)
    ]
    assert not fn, "FAIL-CLOSED VIOLATED — mechanical text wrongly accepted by gate:\n" + "\n".join(
        f"  {e.id}: {e.text!r}" for e in fn
    )


def test_corpus_zero_false_positives() -> None:
    """Quality bar: 0% false-positive rate (cacheable wrongly rejected).

    Not safety-critical, but a regression here costs the operator real
    cache hit-rate, so we lock it in.
    """
    fp = [
        e for e in _ENTRIES if e.expected_cacheable and not NarrCacheGate.is_pure_narration(e.text)
    ]
    assert not fp, "Cacheable text wrongly rejected by gate (false-positive):\n" + "\n".join(
        f"  {e.id}: {e.text!r}" for e in fp
    )
