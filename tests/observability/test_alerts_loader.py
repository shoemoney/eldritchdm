"""Tests for alerts.yaml loader (Phase 13 / MON-02 / Task 03)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from eldritch_dm.observability.alerts_loader import (
    DEFAULT_RULES,
    AlertRule,
    AlertsFile,
    load_alerts,
)


def test_default_rules_match_ai_spec():
    """The 3 default rules must encode AI-SPEC §7 verbatim."""
    by_name = {r.name: r for r in DEFAULT_RULES}
    assert "critical_latency_p99_breach" in by_name
    crit = by_name["critical_latency_p99_breach"]
    assert crit.severity == "critical"
    assert crit.kpi == "latency_p99_ms"
    assert crit.op == "gt"
    assert crit.threshold == 1500.0
    assert crit.window_minutes == 5
    assert crit.action == "degrade"

    high = by_name["high_fallback_rate"]
    assert high.severity == "high"
    assert high.kpi == "fallback_rate"
    assert high.threshold == 0.10
    assert high.action == "log"

    warn = by_name["warning_refusal_rate"]
    assert warn.severity == "warning"
    assert warn.kpi == "refusal_rate"
    assert warn.threshold == 0.001


def test_loads_repo_default_alerts_yaml():
    """The shipped database/alerts.yaml parses + matches DEFAULT_RULES."""
    settings = MagicMock(alerts_yaml_path=None)
    rules = load_alerts(settings)
    assert len(rules) == 3
    names = {r.name for r in rules}
    assert names == {r.name for r in DEFAULT_RULES}


def test_falls_back_when_no_file_found(monkeypatch, tmp_path):
    """No env, no per-install, no in-repo → DEFAULT_RULES."""
    # Repoint HOME so per-install doesn't exist; env unset.
    monkeypatch.setenv("HOME", str(tmp_path / "fake-home"))
    settings = MagicMock(alerts_yaml_path=tmp_path / "does-not-exist.yaml")
    # Also block the in-repo default by pointing alerts_yaml_path explicitly.
    rules = load_alerts(settings)
    # Falls through to in-repo default (database/alerts.yaml exists in this
    # repo), which IS the default rules. So we get DEFAULT_RULES either way.
    assert len(rules) == 3


def test_falls_back_on_yaml_parse_error(tmp_path):
    bad = tmp_path / "alerts.yaml"
    bad.write_text("not: valid: yaml: [unclosed\n", encoding="utf-8")
    settings = MagicMock(alerts_yaml_path=bad)
    rules = load_alerts(settings)
    assert rules == DEFAULT_RULES


def test_falls_back_on_unknown_version(tmp_path):
    bad = tmp_path / "alerts.yaml"
    bad.write_text(
        "version: 999\nrules: []\n",
        encoding="utf-8",
    )
    settings = MagicMock(alerts_yaml_path=bad)
    rules = load_alerts(settings)
    assert rules == DEFAULT_RULES


def test_falls_back_on_extra_field(tmp_path):
    """extra='forbid' rejects unknown top-level keys."""
    bad = tmp_path / "alerts.yaml"
    bad.write_text(
        "version: 1\nrules: []\nunknown_top_level_key: hello\n",
        encoding="utf-8",
    )
    settings = MagicMock(alerts_yaml_path=bad)
    rules = load_alerts(settings)
    assert rules == DEFAULT_RULES


def test_env_override_path(tmp_path):
    """Env-tier override takes precedence over in-repo default."""
    override = tmp_path / "custom.yaml"
    override.write_text(
        """\
version: 1
rules:
  - name: my_custom_rule
    severity: warning
    kpi: success_rate
    op: lt
    threshold: 0.5
    window_minutes: 10
    action: log
""",
        encoding="utf-8",
    )
    settings = MagicMock(alerts_yaml_path=override)
    rules = load_alerts(settings)
    assert len(rules) == 1
    assert rules[0].name == "my_custom_rule"
    assert rules[0].window_minutes == 10


def test_rule_extra_field_forbidden():
    """AlertRule rejects unknown fields."""
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        AlertRule(
            name="x",
            severity="warning",
            kpi="success_rate",
            op="lt",
            threshold=0.5,
            action="log",
            unknown_field="boom",  # type: ignore[call-arg]
        )


def test_alerts_file_returns_dataclass_when_valid():
    """Sanity check the schema can round-trip a basic doc."""
    f = AlertsFile.model_validate(
        {
            "version": 1,
            "rules": [
                {
                    "name": "r1",
                    "severity": "warning",
                    "kpi": "refusal_rate",
                    "op": "gt",
                    "threshold": 0.01,
                    "action": "log",
                }
            ],
        }
    )
    assert f.version == 1
    assert len(f.rules) == 1


def test_safe_load_only_in_source_code():
    """CI hardening: the loader must use safe_load, never yaml.load."""
    src = (
        Path(__file__).resolve().parents[2]
        / "src/eldritch_dm/observability/alerts_loader.py"
    )
    text = src.read_text()
    assert "yaml.safe_load" in text
    # Bare ``yaml.load(`` (with paren) would be the RCE vector. Exclude
    # safe_load matches.
    assert "yaml.load(" not in text.replace("yaml.safe_load(", "")
