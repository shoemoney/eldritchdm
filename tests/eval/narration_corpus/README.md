# Narration cache corpus

50-scenario test corpus for `NarrCacheGate` (Phase 18 / NARRCACHE-02 / D-131).

## Structure

`corpus.jsonl` — one JSON object per line, pydantic-validated by `loader.py`.

Each entry:

| field                | type   | meaning                                                  |
| -------------------- | ------ | -------------------------------------------------------- |
| `id`                 | str    | stable identifier (e.g. `cache-001`, `leak-023`)         |
| `text`               | str    | the narration fragment under test                        |
| `expected_cacheable` | bool   | ground truth — True iff fail-CLOSED gate should accept   |
| `rationale`          | str    | human-readable why                                       |
| `category`           | enum   | see `loader.CorpusEntry.category` for the full enum      |

## Split

- **25 cacheable** (`expected_cacheable=true`): pure scene / dialogue /
  atmosphere / lore / hooks / travel / worldbuilding. Includes six
  `adversarial_safe` entries that look like leaks but should NOT trip
  the gate (`took N`, `fell to one knee`, `dealer`, `critique`,
  `conditioner`, `invisibly`).

- **25 non-cacheable** (`expected_cacheable=false`): explicit damage,
  explicit HP change, save / DC, dice notation, condition application,
  crit, death, AC check, plus one `adversarial_leak` entry where `HP`
  appears in non-mechanical text — gate MUST still reject (fail-CLOSED).

## Origin and licensing

All text is **original** and written for this corpus under the project's
Apache-2.0 license. No copyrighted RPG material (5e SRD, novels,
adventure modules, or published scenarios) is used.

## Test contract

`tests/eval/test_narration_gate_corpus.py` asserts, per entry:

```python
assert NarrCacheGate.is_pure_narration(entry.text) == entry.expected_cacheable
```

- **False-negative rate (mechanical text wrongly accepted) MUST be 0%.**
  This is the non-negotiable mechanical-honesty bar.
- False-positive rate (cacheable text wrongly rejected) is targeted at
  0% — the current corpus achieves it. Regressions in false-positive
  rate are quality bugs but not safety bugs.
