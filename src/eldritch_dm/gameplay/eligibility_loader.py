"""Homebrew Riposte eligibility YAML loader (Phase 08 / HOMEBREW-01 + 02).

Decisions referenced (CONTEXT D-29..D-40):
  - D-29  3-tier path precedence: env > per-install > in-repo default.
  - D-30  In-repo default ships v1.0 D-C frozenset (battle-master fighter only).
  - D-31  `yaml.safe_load` ONLY — CI grep gate enforces this discipline.
  - D-32  Pydantic v2 schema with `model_config = ConfigDict(extra='forbid')`.
  - D-33  Fail-soft to DEFAULT_ELIGIBILITY on any error; never crash the bot.
  - D-34  Extend-by-default; `mode: replace` opts in to full override.
  - D-36  Casing normalized via shared `gameplay.normalize.normalize`.
  - D-40  Schema reserves `version` field; reject version != 1 with fallback.

Pitfalls referenced (research/PITFALLS.md):
  - YAML-1 (CRITICAL)  yaml.load is RCE; we use safe_load exclusively.
  - YAML-3 (HIGH)      Fail-soft + structured warning on any error.
  - YAML-4             Mode is explicit; resolved set is logged.
  - YAML-6             Case normalization is non-optional.

Threat mitigations (T-08-01, T-08-02, T-08-05): see PHASE 08 threat register.

Public surface:
    DEFAULT_ELIGIBILITY  — frozenset[tuple[str, str]] matching v1.0 reactions.
    EligibilityFile      — Pydantic schema for the on-disk YAML.
    load_eligibility(s)  — Public entrypoint. NEVER raises.

This module is import-linter-safe: lives in `gameplay/`, imports only
`gameplay.normalize`, `logging`, `pydantic`, `yaml`, `pathlib`, and TYPE_CHECKING
`config.Settings`. No upward imports.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Literal

import yaml
from pydantic import BaseModel, ConfigDict, ValidationError

from eldritch_dm.gameplay.normalize import normalize
from eldritch_dm.logging import get_logger

if TYPE_CHECKING:
    from eldritch_dm.config import Settings

log = get_logger(__name__)


# D-30: matches v1.0 reactions.ELIGIBLE_CLASS_SUBCLASSES exactly.
DEFAULT_ELIGIBILITY: frozenset[tuple[str, str]] = frozenset(
    {("fighter", "battle master")}
)


class EligibilityFile(BaseModel):
    """Pydantic v2 schema for the homebrew eligibility YAML (D-32, D-40)."""

    model_config = ConfigDict(extra="forbid")

    version: int = 1
    mode: Literal["extend", "replace"] = "extend"
    eligible: dict[str, list[str]]


# ── Path resolution (D-29 — 3-tier precedence; FIRST hit wins) ────────────────


def _resolve_path(settings: Settings) -> Path | None:
    """Walk the 3-tier path order: env > per-install > in-repo default.

    Returns the first existing path, or None if no file is found at any tier.
    """
    # Tier 1: explicit env override via Settings.eligibility_yaml_path.
    env_path = getattr(settings, "eligibility_yaml_path", None)
    if env_path is not None:
        p = Path(env_path)
        if p.is_file():
            return p

    # Tier 2: per-install user file under $HOME/.eldritch/eligibility.yaml.
    per_install = Path.home() / ".eldritch" / "eligibility.yaml"
    if per_install.is_file():
        return per_install

    # Tier 3: in-repo default. `__file__` lives in
    #   <repo>/src/eldritch_dm/gameplay/eligibility_loader.py
    # so `parents[3]` is `<repo>`. Under `pip install` (site-packages) this
    # walk falls outside the source tree and the `is_file()` check returns
    # False — caller falls through to DEFAULT_ELIGIBILITY (D-33), which IS
    # the v1.0 default (D-30), so the behavior is correct either way.
    in_repo = Path(__file__).resolve().parents[3] / "database" / "eligibility.yaml"
    if in_repo.is_file():
        return in_repo

    return None


# ── Conversion (extend vs replace; normalize casing) ──────────────────────────


def _to_frozenset(parsed: EligibilityFile) -> frozenset[tuple[str, str]]:
    """Normalize + apply extend/replace semantics (D-34, D-36)."""
    user_set: frozenset[tuple[str, str]] = frozenset(
        (normalize(cls), normalize(sub))
        for cls, subs in parsed.eligible.items()
        for sub in subs
    )
    if parsed.mode == "replace":
        return user_set
    # extend — union with DEFAULT_ELIGIBILITY.
    return DEFAULT_ELIGIBILITY | user_set


# ── Public entrypoint ─────────────────────────────────────────────────────────


def load_eligibility(settings: Settings) -> frozenset[tuple[str, str]]:
    """Resolve the eligibility frozenset. NEVER raises (D-33 fail-soft).

    On any failure (missing file, parse error, schema violation, unsupported
    version), logs a structured `eligibility.fallback` warning and returns
    DEFAULT_ELIGIBILITY. On success, logs `eligibility.resolved` at INFO
    (PITFALLS YAML-4 — operator can grep their JSON log for what was loaded).
    """
    try:
        path = _resolve_path(settings)
        if path is None:
            log.warning(
                "eligibility.fallback",
                reason="no_eligibility_yaml_found",
            )
            return DEFAULT_ELIGIBILITY

        raw_text = path.read_text(encoding="utf-8")

        # D-31 / PITFALLS YAML-1 / T-08-01: safe_load ONLY. CI gate enforces.
        try:
            raw = yaml.safe_load(raw_text)
        except yaml.YAMLError as e:
            log.warning(
                "eligibility.fallback",
                reason="yaml_parse_error",
                error=str(e),
                source=str(path),
            )
            return DEFAULT_ELIGIBILITY

        if raw is None:
            log.warning(
                "eligibility.fallback",
                reason="empty_yaml_file",
                source=str(path),
            )
            return DEFAULT_ELIGIBILITY

        try:
            parsed = EligibilityFile.model_validate(raw)
        except ValidationError as e:
            log.warning(
                "eligibility.fallback",
                reason="schema_validation_error",
                error=str(e),
                source=str(path),
            )
            return DEFAULT_ELIGIBILITY

        if parsed.version != 1:
            log.warning(
                "eligibility.fallback",
                reason="unsupported_schema_version",
                version=parsed.version,
                source=str(path),
            )
            return DEFAULT_ELIGIBILITY

        resolved = _to_frozenset(parsed)

        log.info(
            "eligibility.resolved",
            source=str(path),
            mode=parsed.mode,
            count=len(resolved),
            entries=sorted(f"{c}:{s}" for c, s in resolved),
        )
        return resolved

    except Exception as e:  # noqa: BLE001
        # Belt-and-suspenders catch-all per D-33: NEVER crash on bad YAML.
        log.warning(
            "eligibility.fallback",
            reason=e.__class__.__name__,
            error=str(e),
        )
        return DEFAULT_ELIGIBILITY


# ── Hot-reload watcher (Phase 22 / OPQOL-01 / D-167 / D-168) ─────────────────


class EligibilityFileWatcher:
    """Background mtime-poll watcher that hot-reloads eligibility.yaml.

    Phase 22 / OPQOL-01. Polls `path.stat().st_mtime_ns` every
    `poll_interval_s` (default 60s). On mtime change, re-invokes
    `load_eligibility(settings)`. The loader is already fail-soft (Phase 8
    D-31/D-33) so it never raises; the watcher additionally distinguishes
    "loader returned DEFAULT (fallback)" from "loader returned the same
    DEFAULT we already had" via last-known-good comparison.

    Public surface:
        current          — frozenset[(class, sub)] currently in effect
        start()/stop()   — idempotent task lifecycle
        poll_once()      — deterministic test seam; returns True iff reload

    Fail-soft contract (D-174):
        ANY exception inside `poll_once` is caught, logged
        `eldritch.eligibility.watcher_error`, and returns False. The
        background loop catches everything except CancelledError, so the
        bot event loop is never disturbed.

    Scope cut: when a live `MonsterDriver` already holds the old
    `eligibility_set` frozenset (Phase 8 D-38 injection), this watcher
    updates `bot.eligibility_set` only — rebuilding a live driver
    mid-combat is out of scope for v1.6 (documented in 22-01-SUMMARY).
    """

    def __init__(
        self,
        settings: Settings,
        *,
        initial_set: frozenset[tuple[str, str]] | None = None,
        poll_interval_s: float = 60.0,
        on_reload: Callable[[frozenset[tuple[str, str]]], None] | None = None,
    ) -> None:
        self._settings = settings
        # Resolve path ONCE at init (advisor #4): mid-run tier changes do not
        # silently switch the source file.
        self._path: Path | None = _resolve_path(settings)
        self._poll_interval_s = poll_interval_s
        self._on_reload = on_reload
        self._current: frozenset[tuple[str, str]] = (
            initial_set if initial_set is not None else DEFAULT_ELIGIBILITY
        )
        self._last_mtime_ns: int | None = None
        # Seed baseline mtime if the resolved path is readable now so the
        # first real `poll_once()` call returns False (no spurious reload).
        if self._path is not None:
            try:
                self._last_mtime_ns = self._path.stat().st_mtime_ns
            except OSError:
                self._last_mtime_ns = None
        self._task: asyncio.Task[None] | None = None
        self._stop_event: asyncio.Event | None = None
        # One-shot log flags so we don't spam the JSON log every 60s.
        self._logged_no_path = False
        self._logged_file_missing = False

    @property
    def current(self) -> frozenset[tuple[str, str]]:
        """Return the currently-active eligibility frozenset."""
        return self._current

    def poll_once(self) -> bool:
        """Run exactly one poll iteration. Test seam. Returns True iff reloaded.

        Fail-soft: catches every Exception, logs, returns False.
        """
        try:
            if self._path is None:
                if not self._logged_no_path:
                    log.info("eldritch.eligibility.watcher_no_path")
                    self._logged_no_path = True
                return False

            try:
                mtime_ns = self._path.stat().st_mtime_ns
            except FileNotFoundError:
                if not self._logged_file_missing:
                    log.warning(
                        "eldritch.eligibility.watcher_file_missing",
                        source=str(self._path),
                    )
                    self._logged_file_missing = True
                return False

            # If the file reappeared after a missing event, reset the
            # missing-flag so the next disappearance is logged again.
            self._logged_file_missing = False

            if self._last_mtime_ns is not None and mtime_ns == self._last_mtime_ns:
                return False

            # mtime changed — attempt reload via the existing loader (which
            # is itself fail-soft).
            new_set = load_eligibility(self._settings)

            # Distinguish "real valid load" from "loader fell back to
            # DEFAULT_ELIGIBILITY because the file is bad". Heuristic: if
            # the new set is DEFAULT and the last_known_good was NOT
            # DEFAULT, treat as a failed reload — keep last-known-good and
            # log `reload_failed`. Otherwise accept the new set.
            if (
                new_set == DEFAULT_ELIGIBILITY
                and self._current != DEFAULT_ELIGIBILITY
            ):
                log.warning(
                    "eldritch.eligibility.reload_failed",
                    source=str(self._path),
                    note="loader fell back to DEFAULT; keeping last-known-good",
                )
                # Advance the baseline mtime anyway so we don't re-log on
                # every subsequent poll until the operator edits again.
                self._last_mtime_ns = mtime_ns
                return False

            self._current = new_set
            self._last_mtime_ns = mtime_ns
            log.info(
                "eldritch.eligibility.reload_succeeded",
                source=str(self._path),
                count=len(new_set),
            )
            if self._on_reload is not None:
                try:
                    self._on_reload(new_set)
                except Exception as cb_exc:  # noqa: BLE001
                    log.warning(
                        "eldritch.eligibility.on_reload_error",
                        error_type=type(cb_exc).__name__,
                        error=str(cb_exc)[:200],
                    )
            return True

        except Exception as exc:  # noqa: BLE001
            log.warning(
                "eldritch.eligibility.watcher_error",
                error_type=type(exc).__name__,
                error=str(exc)[:200],
            )
            return False

    async def start(self) -> None:
        """Spawn the background poll task. Idempotent."""
        if self._task is not None and not self._task.done():
            return
        self._stop_event = asyncio.Event()
        self._task = asyncio.create_task(
            self._run(), name="EligibilityFileWatcher._run"
        )

    async def stop(self) -> None:
        """Cancel the background task. Idempotent."""
        if self._task is None:
            return
        if self._stop_event is not None:
            self._stop_event.set()
        self._task.cancel()
        try:
            await self._task
        except (asyncio.CancelledError, Exception):  # noqa: BLE001
            pass
        self._task = None
        self._stop_event = None

    async def _run(self) -> None:
        """The poll loop. Sleeps `poll_interval_s` then runs `poll_once`."""
        assert self._stop_event is not None
        while not self._stop_event.is_set():
            try:
                await asyncio.wait_for(
                    self._stop_event.wait(), timeout=self._poll_interval_s
                )
                return  # stop event fired
            except TimeoutError:
                pass
            except asyncio.CancelledError:
                raise

            try:
                self.poll_once()
            except Exception as exc:  # noqa: BLE001
                # poll_once is already try/except — this is belt+suspenders.
                log.warning(
                    "eldritch.eligibility.watcher_loop_error",
                    error_type=type(exc).__name__,
                    error=str(exc)[:200],
                )
