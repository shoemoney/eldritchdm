"""Tests for the 3-tier homebrew Riposte eligibility loader (Phase 08).

Covers all 14 behaviors enumerated in 08-01-PLAN.md Task 3.

These tests exercise the loader as a black box from `Settings` → resolved
frozenset, which is the same shape the production path (bot.setup_hook)
calls it with. The malicious-YAML test doubles as a T-08-01 / PITFALLS
YAML-1 mitigation — it would scribble a sentinel file to disk if
`yaml.safe_load` ever regressed to `yaml.load`.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import structlog

from eldritch_dm.config import Settings
from eldritch_dm.gameplay.eligibility_loader import (
    DEFAULT_ELIGIBILITY,
    EligibilityFile,
    load_eligibility,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "eligibility"


def _settings_with(path: Path | None) -> Settings:
    """Build a Settings with the env-tier path set (or None to test other tiers)."""
    if path is None:
        return Settings()
    return Settings(eligibility_yaml_path=path)


# ── 1: default constant matches v1.0 ──────────────────────────────────────────


def test_default_eligibility_constant_matches_v1_0() -> None:
    assert DEFAULT_ELIGIBILITY == frozenset({("fighter", "battle master")})
    # Also matches the in-module fallback in reactions.py (D-30).
    from eldritch_dm.gameplay.reactions import ELIGIBLE_CLASS_SUBCLASSES

    assert DEFAULT_ELIGIBILITY == ELIGIBLE_CLASS_SUBCLASSES


# ── 2: env path tier wins ─────────────────────────────────────────────────────


def test_env_path_overrides_per_install_and_in_repo() -> None:
    """Tier-1 env path takes precedence — adds Swashbuckler to default set."""
    s = _settings_with(FIXTURES / "swashbuckler_extend.yaml")
    resolved = load_eligibility(s)
    assert ("fighter", "battle master") in resolved
    assert ("rogue", "swashbuckler") in resolved


# ── 3: per-install tier ───────────────────────────────────────────────────────


def test_per_install_path_overrides_in_repo(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Tier-2: ~/.eldritch/eligibility.yaml is used when no env path is set."""
    home = tmp_path / "home"
    (home / ".eldritch").mkdir(parents=True)
    (home / ".eldritch" / "eligibility.yaml").write_text(
        "version: 1\nmode: extend\neligible:\n  rogue:\n    - swashbuckler\n"
    )
    monkeypatch.setattr(Path, "home", lambda: home)
    s = _settings_with(None)
    resolved = load_eligibility(s)
    assert ("rogue", "swashbuckler") in resolved
    assert ("fighter", "battle master") in resolved  # extend semantics


# ── 4: in-repo tier ───────────────────────────────────────────────────────────


def test_in_repo_default_used_when_no_overrides(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Tier-3: database/eligibility.yaml ships v1.0 D-C set exactly."""
    # Point HOME to a dir with no .eldritch file, forcing the loader to fall
    # through to the in-repo default.
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    s = _settings_with(None)
    resolved = load_eligibility(s)
    # The in-repo default is `extend` mode with `{fighter: [battle master]}` —
    # since DEFAULT_ELIGIBILITY already contains that, resolved == DEFAULT.
    assert resolved == DEFAULT_ELIGIBILITY


# ── 5: all 3 tiers miss → fail-soft ───────────────────────────────────────────


def test_no_files_anywhere_returns_default_with_warning(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """When every tier misses, fall back to DEFAULT_ELIGIBILITY (D-33)."""
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    # Point the loader at a non-existent file at every tier.
    bogus = tmp_path / "does_not_exist.yaml"

    # Also mask the in-repo default by monkeypatching Path.is_file for that
    # specific path. Simpler: monkeypatch the loader's _resolve_path to None.
    from eldritch_dm.gameplay import eligibility_loader

    monkeypatch.setattr(eligibility_loader, "_resolve_path", lambda _s: None)
    s = _settings_with(bogus)
    resolved = load_eligibility(s)
    assert resolved == DEFAULT_ELIGIBILITY


# ── 6: extend mode ────────────────────────────────────────────────────────────


def test_extend_mode_unions_with_default() -> None:
    s = _settings_with(FIXTURES / "valid_extend.yaml")
    resolved = load_eligibility(s)
    assert ("fighter", "battle master") in resolved
    assert ("fighter", "echo knight") in resolved


# ── 7: replace mode ───────────────────────────────────────────────────────────


def test_replace_mode_wipes_default() -> None:
    s = _settings_with(FIXTURES / "valid_replace.yaml")
    resolved = load_eligibility(s)
    assert resolved == frozenset({("rogue", "swashbuckler")})
    assert ("fighter", "battle master") not in resolved


# ── 8: T-08-01 / YAML-1 — malicious YAML must not execute ─────────────────────


def test_malicious_python_object_yaml_does_not_execute() -> None:
    """safe_load MUST refuse `!!python/object/apply:os.system` payloads."""
    sentinel = Path("/tmp/eldritch_pwn_DO_NOT_RUN")
    if sentinel.exists():
        sentinel.unlink()
    s = _settings_with(FIXTURES / "malicious_python_object.yaml")
    resolved = load_eligibility(s)
    assert resolved == DEFAULT_ELIGIBILITY, "fail-soft should return v1.0 default"
    assert not sentinel.exists(), (
        "safe_load must NOT have executed the os.system payload (RCE breach)"
    )


# ── 9: unknown YAML key rejected by pydantic ──────────────────────────────────


def test_unknown_yaml_key_rejected_by_pydantic() -> None:
    """`extra='forbid'` rejects `evil_field: 1` → fall back to default (D-32)."""
    s = _settings_with(FIXTURES / "unknown_key.yaml")
    resolved = load_eligibility(s)
    assert resolved == DEFAULT_ELIGIBILITY


# ── 10: bad version ───────────────────────────────────────────────────────────


def test_unsupported_version_falls_back() -> None:
    """version: 2 must trigger fallback per D-40."""
    s = _settings_with(FIXTURES / "bad_version.yaml")
    resolved = load_eligibility(s)
    assert resolved == DEFAULT_ELIGIBILITY


# ── 11: casing normalization through shared helper ────────────────────────────


def test_casing_normalized_via_shared_helper() -> None:
    """`Fighter` / `BATTLE MASTER` in YAML normalize to lowercase frozenset entries."""
    s = _settings_with(FIXTURES / "valid_extend.yaml")
    resolved = load_eligibility(s)
    assert ("fighter", "battle master") in resolved
    # Confirm no uppercase variant snuck through.
    for cls, sub in resolved:
        assert cls == cls.lower(), f"class {cls!r} not lowercased"
        assert sub == sub.lower(), f"subclass {sub!r} not lowercased"


# ── 12: resolved-set INFO log ─────────────────────────────────────────────────


def test_resolved_set_logged_at_info_level() -> None:
    """PITFALLS YAML-4: operator should be able to grep `eligibility.resolved`."""
    s = _settings_with(FIXTURES / "valid_extend.yaml")
    with structlog.testing.capture_logs() as cap:
        load_eligibility(s)
    events = [e for e in cap if e.get("event") == "eligibility.resolved"]
    assert len(events) == 1, f"expected 1 resolved event, got {len(events)}: {cap}"
    e = events[0]
    assert e["log_level"] == "info"
    assert e["mode"] == "extend"
    assert e["count"] == len(load_eligibility(s))
    assert "entries" in e
    assert isinstance(e["entries"], list)


# ── 13: empty eligible in extend mode ─────────────────────────────────────────


def test_empty_eligible_dict_in_extend_returns_default(tmp_path: Path) -> None:
    p = tmp_path / "empty_extend.yaml"
    p.write_text("version: 1\nmode: extend\neligible: {}\n")
    s = _settings_with(p)
    assert load_eligibility(s) == DEFAULT_ELIGIBILITY


# ── 14: empty eligible in replace mode — footgun ──────────────────────────────


def test_empty_eligible_dict_in_replace_returns_empty_frozenset(tmp_path: Path) -> None:
    """Documented footgun: `mode: replace` with `eligible: {}` = nobody is eligible."""
    p = tmp_path / "empty_replace.yaml"
    p.write_text("version: 1\nmode: replace\neligible: {}\n")
    s = _settings_with(p)
    assert load_eligibility(s) == frozenset()


# ── 15: parametrized never-raises invariant ───────────────────────────────────


@pytest.mark.parametrize(
    "fixture_name",
    [
        "malicious_python_object.yaml",
        "unknown_key.yaml",
        "bad_version.yaml",
    ],
)
def test_load_eligibility_never_raises(fixture_name: str) -> None:
    """D-33: every failure path returns DEFAULT_ELIGIBILITY, never raises."""
    s = _settings_with(FIXTURES / fixture_name)
    result = load_eligibility(s)  # must NOT raise
    assert result == DEFAULT_ELIGIBILITY


# ── Schema-level sanity ───────────────────────────────────────────────────────


def test_eligibility_file_extra_forbid() -> None:
    """Direct unit test of pydantic schema: extra keys raise ValidationError."""
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        EligibilityFile.model_validate(
            {"version": 1, "mode": "extend", "eligible": {}, "evil": True}
        )


def test_eligibility_file_invalid_mode() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        EligibilityFile.model_validate(
            {"version": 1, "mode": "ignore", "eligible": {}}
        )
