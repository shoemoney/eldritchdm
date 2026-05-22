"""
ExplorationBatch + BatchCoordinator — 30s action batching for EXPLORATION state.

When multiple players declare actions within a 30-second window, their intents
are collected and flushed as a single batched payload to dm20 via player_action.

Design (D-07, D-08, D-09, D-10):
  - BatchCoordinator holds one ExplorationBatch per channel_id.
  - First submit() starts a new batch with deadline = now + 30s.
  - Subsequent submits append to the existing batch (deduped by user_id).
  - Flush occurs when:
    a. len(submissions) == active_party_size (all players submitted), OR
    b. tick(now) is called and deadline has passed.
  - After flush, the batch is removed; next submit starts a new batch.
  - Serialization: submissions are already-wrapped <player_action ...> strings
    from the sanitizer; joined inside a <batch>…</batch> envelope.

Thread safety: asyncio.Lock per channel_id in BatchCoordinator ensures
concurrent submit() calls from multiple modal on_submit coroutines do not
double-flush (D-07 Test 7 concurrency requirement).

Phase 4 Plan 01 — EXPLORE-06.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Callable


# ── Data classes ──────────────────────────────────────────────────────────────


@dataclass
class PlayerIntent:
    """A single player's declared action, post-sanitization.

    Attributes:
        user_id: Discord user snowflake string.
        sanitized_wrapped: Already-sanitized, XML-wrapped intent string from
            sanitize_player_input().wrapped (form: <player_action ...>...</player_action>).
        character_id: dm20 character ID (may be None if not yet resolved).
        ts: UTC timestamp when the intent was received.
    """

    user_id: str
    sanitized_wrapped: str
    character_id: str | None
    ts: datetime


@dataclass
class ExplorationBatch:
    """A time-bounded collection of player intents for one channel.

    Attributes:
        first_submission_ts: When the first intent arrived (UTC).
        deadline_ts: When this batch expires (first_submission_ts + window_seconds).
        submissions: Ordered list of PlayerIntent (deduped by user_id — last wins).
    """

    first_submission_ts: datetime
    deadline_ts: datetime
    submissions: list[PlayerIntent] = field(default_factory=list)


@dataclass
class SubmitResult:
    """Result of a BatchCoordinator.submit() call.

    Attributes:
        flushed: True if this submission triggered a batch flush.
        batch: The flushed ExplorationBatch (when flushed=True); None otherwise.
    """

    flushed: bool
    batch: ExplorationBatch | None


# ── Serializer ────────────────────────────────────────────────────────────────


def serialize_batch_payload(batch: ExplorationBatch) -> str:
    """Serialize an ExplorationBatch into a <batch>…</batch> XML envelope.

    Each submission's sanitized_wrapped string is already in the form
    <player_action speaker="…" user_id="…">…</player_action>.

    The result is suitable as the `context` arg to dm20__player_action:
        await player_action(client, session_id=..., action="batch_intents",
                            context=serialize_batch_payload(batch))

    Args:
        batch: A flushed ExplorationBatch with at least one submission.

    Returns:
        A string like:
        <batch>
          <player_action speaker="Aria" user_id="123">I search the chest</player_action>
          <player_action speaker="Thorin" user_id="456">I guard the door</player_action>
        </batch>
    """
    inner = "\n  ".join(s.sanitized_wrapped for s in batch.submissions)
    return f"<batch>\n  {inner}\n</batch>"


# ── BatchCoordinator ──────────────────────────────────────────────────────────


class BatchCoordinator:
    """Per-channel exploration action batch coordinator.

    Holds at most one open ExplorationBatch per channel_id. When a batch is
    flushed (by party size or deadline), the caller receives flushed=True and
    is responsible for serializing and sending the payload to dm20.

    Args:
        window_seconds: Batch window duration in seconds (default 30 per D-07).
        clock: Callable returning UTC datetime (injectable for testing).

    Usage::

        coordinator = BatchCoordinator(window_seconds=30)
        coordinator.set_active_party_size("ch-123", 4)
        result = await coordinator.submit("ch-123", intent)
        if result.flushed:
            payload = serialize_batch_payload(result.batch)
            # send payload to dm20 via player_action(...)
    """

    def __init__(
        self,
        window_seconds: float = 30.0,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._window_seconds = window_seconds
        self._clock: Callable[[], datetime] = clock or (
            lambda: datetime.now(UTC)
        )
        # channel_id → open ExplorationBatch
        self._batches: dict[str, ExplorationBatch] = {}
        # channel_id → known party size (None = unknown → deadline-only flush)
        self._party_sizes: dict[str, int | None] = {}
        # per-channel lock to serialize concurrent submits
        self._locks: dict[str, asyncio.Lock] = {}

    def _get_lock(self, channel_id: str) -> asyncio.Lock:
        if channel_id not in self._locks:
            self._locks[channel_id] = asyncio.Lock()
        return self._locks[channel_id]

    def set_active_party_size(self, channel_id: str, n: int) -> None:
        """Cache the active party size for a channel (used for early flush).

        Args:
            channel_id: The Discord channel snowflake string.
            n: Number of players in the active party for this session.
        """
        self._party_sizes[channel_id] = n

    async def submit(self, channel_id: str, intent: PlayerIntent) -> SubmitResult:
        """Add a PlayerIntent to the channel's batch.

        If no batch is open, starts a new one. If the batch fills (all players
        submitted) or is past its deadline when this call arrives, flushes.

        Args:
            channel_id: The Discord channel snowflake string.
            intent: The player's sanitized intent (from DeclareActionModal).

        Returns:
            SubmitResult(flushed=True, batch=...) if a flush occurred (caller
            must send the payload to dm20), or SubmitResult(flushed=False, batch=None).
        """
        lock = self._get_lock(channel_id)
        async with lock:
            now = self._clock()

            # Check if existing batch is past deadline
            if channel_id in self._batches:
                batch = self._batches[channel_id]
                if now >= batch.deadline_ts:
                    # Deadline expired before this submit — flush the old batch
                    # and start a new one with this intent
                    old_batch = self._batches.pop(channel_id)
                    # Start new batch with this intent
                    new_batch = self._start_batch(channel_id, intent, now)
                    self._batches[channel_id] = new_batch
                    return SubmitResult(flushed=True, batch=old_batch)

                # Dedup by user_id (last submission wins)
                batch.submissions = [
                    s for s in batch.submissions if s.user_id != intent.user_id
                ]
                batch.submissions.append(intent)
            else:
                # No existing batch — start one
                batch = self._start_batch(channel_id, intent, now)
                self._batches[channel_id] = batch

            # Check if party size is filled
            party_size = self._party_sizes.get(channel_id)
            if party_size is not None and len(batch.submissions) >= party_size:
                flushed_batch = self._batches.pop(channel_id)
                return SubmitResult(flushed=True, batch=flushed_batch)

            return SubmitResult(flushed=False, batch=None)

    def _start_batch(
        self,
        channel_id: str,
        first_intent: PlayerIntent,
        now: datetime,
    ) -> ExplorationBatch:
        """Create a new ExplorationBatch starting with the given intent."""
        from datetime import timedelta

        deadline = now + timedelta(seconds=self._window_seconds)
        return ExplorationBatch(
            first_submission_ts=now,
            deadline_ts=deadline,
            submissions=[first_intent],
        )

    def tick(self, now: datetime) -> list[tuple[str, ExplorationBatch]]:
        """Check for and flush expired batches.

        Called periodically by the PartyModeOrchestrator loop to implement
        deadline-based flushing (D-08 step 4b).

        Args:
            now: Current UTC datetime.

        Returns:
            List of (channel_id, batch) tuples for all expired batches.
            Each returned batch has been removed from the coordinator.
            The caller is responsible for serializing and sending payloads.
        """
        expired: list[tuple[str, ExplorationBatch]] = []
        for channel_id in list(self._batches.keys()):
            batch = self._batches[channel_id]
            if now >= batch.deadline_ts:
                expired.append((channel_id, self._batches.pop(channel_id)))
        return expired

    def has_batch(self, channel_id: str) -> bool:
        """Return True if a batch is currently open for this channel."""
        return channel_id in self._batches

    def get_deadline_seconds_remaining(self, channel_id: str) -> float | None:
        """Return seconds until the batch deadline, or None if no batch is open."""
        if channel_id not in self._batches:
            return None
        now = self._clock()
        remaining = (self._batches[channel_id].deadline_ts - now).total_seconds()
        return max(0.0, remaining)
