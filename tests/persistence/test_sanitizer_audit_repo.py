"""
Tests for SanitizerAuditRepo.
"""

from __future__ import annotations

from datetime import datetime, UTC

import pytest

from eldritch_dm.persistence.models import SanitizerAuditRow
from eldritch_dm.persistence.sanitizer_audit_repo import SanitizerAuditRepo


_SENTINEL = object()


def make_row(
    channel_id="ch-1",
    user_id="user-1",
    stripped_tokens=_SENTINEL,
    truncated=False,
) -> SanitizerAuditRow:
    tokens = ["<tool_call>", "</tool_call>"] if stripped_tokens is _SENTINEL else stripped_tokens
    return SanitizerAuditRow(
        channel_id=channel_id,
        user_id=user_id,
        raw_input="I attack <tool_call>x</tool_call>",
        stripped_tokens=tokens,
        redacted_output="I attack ",
        truncated=truncated,
        ts=datetime.now(UTC),
    )


class TestSanitizerAuditInsert:
    async def test_id_autopopulated(self, bootstrapped_db):
        db_path, wq = bootstrapped_db
        repo = SanitizerAuditRepo(db_path, wq)

        row = make_row()
        inserted = await repo.insert(row)

        assert inserted.id is not None
        assert isinstance(inserted.id, int)
        assert inserted.id > 0

    async def test_count_increases_on_insert(self, bootstrapped_db):
        db_path, wq = bootstrapped_db
        repo = SanitizerAuditRepo(db_path, wq)

        before = await repo.count()
        await repo.insert(make_row())
        after = await repo.count()

        assert after == before + 1

    async def test_stripped_tokens_jsonified(self, bootstrapped_db):
        """stripped_tokens list round-trips through JSON TEXT column."""
        db_path, wq = bootstrapped_db
        repo = SanitizerAuditRepo(db_path, wq)

        tokens = ["<tool_call>", "</tool_call>", "<|im_start|>"]
        inserted = await repo.insert(make_row(stripped_tokens=tokens))

        assert inserted.stripped_tokens == tokens

    async def test_truncated_boolean_roundtrip(self, bootstrapped_db):
        """truncated=True/False roundtrips through INTEGER 0/1."""
        db_path, wq = bootstrapped_db
        repo = SanitizerAuditRepo(db_path, wq)

        true_row = await repo.insert(make_row(truncated=True))
        false_row = await repo.insert(make_row(truncated=False))

        assert true_row.truncated is True
        assert false_row.truncated is False

    async def test_empty_stripped_tokens(self, bootstrapped_db):
        """Inserting with empty stripped_tokens list works."""
        db_path, wq = bootstrapped_db
        repo = SanitizerAuditRepo(db_path, wq)

        row = make_row(stripped_tokens=[])
        inserted = await repo.insert(row)
        assert inserted.stripped_tokens == []

    async def test_multiple_inserts_all_counted(self, bootstrapped_db):
        """All inserts are individually counted."""
        db_path, wq = bootstrapped_db
        repo = SanitizerAuditRepo(db_path, wq)

        for i in range(5):
            await repo.insert(make_row(channel_id=f"ch-{i}"))

        total = await repo.count()
        assert total >= 5
