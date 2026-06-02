"""Pydantic validation tests for the sync report models."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from core.notion_sync import (
    NOTION_SYNC_REPORT_VERSION,
    NotionSyncedPageEntry,
    NotionSyncedPagesIndex,
    NotionSyncReport,
    SyncedRecord,
    SyncedRecordOutcome,
    SyncMode,
    SyncStats,
)


def _now() -> datetime:
    return datetime(2026, 6, 2, 12, 0, tzinfo=UTC)


def _stats(**overrides) -> SyncStats:
    base = dict(
        total_records=0,
        created=0,
        skipped_blocked=0,
        skipped_invalid=0,
        skipped_already_synced=0,
        skipped_refused=0,
        failed=0,
    )
    base.update(overrides)
    return SyncStats(**base)


def _minimal_report(**overrides) -> dict:
    base = {
        "client_slug": "acme-saas",
        "plan_id": "p1",
        "plan_contract_version": "notion-sync-plan.v1",
        "task_pack_id": "tp1",
        "mode": "dry_run",
        "confirmed": False,
        "write_attempted": False,
        "token_env_present": False,
        "database_id_env_present": False,
        "sdk_available": False,
        "records": [],
        "stats": _stats().model_dump(mode="json"),
        "started_at": _now().isoformat(),
        "finished_at": _now().isoformat(),
    }
    base.update(overrides)
    return base


# ---------- SyncedRecord ----------

def test_synced_record_minimal() -> None:
    r = SyncedRecord(
        task_id="t1",
        title="do the thing",
        outcome=SyncedRecordOutcome.CREATED,
    )
    assert r.page_id is None
    assert r.error_type is None


def test_synced_record_all_outcomes_accepted() -> None:
    for o in SyncedRecordOutcome:
        r = SyncedRecord(task_id="t", title="x", outcome=o)
        assert r.outcome is o


def test_synced_record_oversize_error_message_rejected() -> None:
    with pytest.raises(ValidationError):
        SyncedRecord(
            task_id="t",
            title="x",
            outcome=SyncedRecordOutcome.FAILED,
            error_message="x" * 500,
        )


def test_synced_record_negative_duration_rejected() -> None:
    with pytest.raises(ValidationError):
        SyncedRecord(
            task_id="t",
            title="x",
            outcome=SyncedRecordOutcome.CREATED,
            duration_ms=-1.0,
        )


# ---------- NotionSyncReport ----------

def test_minimal_report_validates() -> None:
    r = NotionSyncReport.model_validate(_minimal_report())
    assert r.contract_version == NOTION_SYNC_REPORT_VERSION
    assert r.mode is SyncMode.DRY_RUN
    assert r.write_attempted is False


def test_report_round_trip_json() -> None:
    r = NotionSyncReport.model_validate(_minimal_report())
    reloaded = NotionSyncReport.from_json(r.to_json())
    assert reloaded.model_dump() == r.model_dump()


def test_report_naive_timestamp_rejected() -> None:
    with pytest.raises(ValidationError):
        NotionSyncReport.model_validate(
            _minimal_report(started_at="2026-06-02T12:00:00")
        )


def test_report_bad_slug_rejected() -> None:
    with pytest.raises(ValidationError):
        NotionSyncReport.model_validate(_minimal_report(client_slug="Bad Slug"))


def test_report_version_pinned() -> None:
    with pytest.raises(ValidationError):
        NotionSyncReport.model_validate(
            _minimal_report(contract_version="notion-sync-report.v2")
        )


def test_report_extra_field_rejected() -> None:
    data = _minimal_report()
    data["rogue"] = True
    with pytest.raises(ValidationError):
        NotionSyncReport.model_validate(data)


def test_report_duration_seconds() -> None:
    r = NotionSyncReport.model_validate(
        _minimal_report(
            started_at="2026-06-02T12:00:00+00:00",
            finished_at="2026-06-02T12:00:42+00:00",
        )
    )
    assert r.duration_seconds == 42.0


def test_report_has_no_token_field() -> None:
    """Sanity: the report Pydantic shape MUST NOT have a token field."""
    fields = set(NotionSyncReport.model_fields.keys())
    for forbidden in ("token", "api_key", "secret", "credential"):
        assert forbidden not in fields


# ---------- Idempotency index ----------

def test_synced_pages_index_validates() -> None:
    idx = NotionSyncedPagesIndex(
        client_slug="acme-saas",
        entries=[],
        updated_at=_now(),
    )
    assert idx.entries == []


def test_synced_pages_index_naive_ts_rejected() -> None:
    with pytest.raises(ValidationError):
        NotionSyncedPagesIndex(
            client_slug="acme-saas",
            entries=[],
            updated_at=datetime(2026, 6, 2, 12, 0),
        )


def test_synced_pages_index_as_dict() -> None:
    entry = NotionSyncedPageEntry(
        task_id="t1",
        page_id="p1",
        synced_at=_now(),
        sync_report_id="rep1",
    )
    idx = NotionSyncedPagesIndex(
        client_slug="acme-saas",
        entries=[entry],
        updated_at=_now(),
    )
    d = idx.as_dict()
    assert d["t1"].page_id == "p1"
