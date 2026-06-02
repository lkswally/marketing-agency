"""Pydantic validation tests for the Notion sync plan models."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from core.notion_sync import (
    NOTION_SYNC_PLAN_VERSION,
    NotionPlanIssue,
    NotionPlanIssueSeverity,
    NotionPlannedRecord,
    NotionPropertyMapping,
    NotionPropertyType,
    NotionRecommendedDatabase,
    NotionSyncPlan,
    NotionSyncStats,
    PlannedAction,
)


def _now() -> datetime:
    return datetime(2026, 6, 2, 12, 0, tzinfo=UTC)


def _db() -> NotionRecommendedDatabase:
    return NotionRecommendedDatabase(
        title="Campaign Tasks — acme",
        property_mappings=[
            NotionPropertyMapping(
                notion_name="Task Name",
                notion_type=NotionPropertyType.TITLE,
                source_field="title",
                required=True,
            )
        ],
    )


def _stats(**overrides) -> NotionSyncStats:
    base = dict(
        total_tasks=0,
        would_create=0,
        skip_blocked=0,
        skip_invalid=0,
        issues_total=0,
        issues_error=0,
        issues_warning=0,
        issues_info=0,
    )
    base.update(overrides)
    return NotionSyncStats(**base)


def _minimal_plan(**overrides) -> dict:
    base = {
        "client_slug": "acme-saas",
        "task_pack_id": "tp1",
        "task_pack_contract_version": "campaign-execution-task-pack.v1",
        "notion_payload_schema_version": "notion-export.v1",
        "recommended_database": _db().model_dump(mode="json"),
        "planned_records": [],
        "issues": [],
        "stats": _stats().model_dump(mode="json"),
        "created_at": _now().isoformat(),
    }
    base.update(overrides)
    return base


# ---------- NotionPropertyMapping ----------

def test_property_mapping_minimal() -> None:
    m = NotionPropertyMapping(
        notion_name="Status",
        notion_type=NotionPropertyType.SELECT,
        source_field="state",
    )
    assert m.required is False
    assert m.select_options == []


def test_property_mapping_with_options() -> None:
    m = NotionPropertyMapping(
        notion_name="Priority",
        notion_type=NotionPropertyType.SELECT,
        source_field="priority",
        select_options=["high", "medium", "low"],
    )
    assert m.select_options == ["high", "medium", "low"]


def test_property_mapping_unknown_type_rejected() -> None:
    with pytest.raises(ValidationError):
        NotionPropertyMapping(
            notion_name="X",
            notion_type="formula",  # type: ignore[arg-type]
            source_field="x",
        )


# ---------- NotionPlannedRecord ----------

def test_record_minimal() -> None:
    r = NotionPlannedRecord(
        task_id="t1",
        title="do the thing",
        action=PlannedAction.CREATE,
        proposed_status="todo",
        proposed_priority="medium",
        proposed_category="operational",
        field_count=8,
    )
    assert r.action is PlannedAction.CREATE
    assert r.reason is None


def test_record_skip_invalid_with_reason() -> None:
    r = NotionPlannedRecord(
        task_id="t1",
        title="x",
        action=PlannedAction.SKIP_INVALID,
        reason="title too long",
        proposed_status="todo",
        proposed_priority="medium",
        proposed_category="operational",
        field_count=5,
    )
    assert r.reason == "title too long"


def test_record_negative_field_count_rejected() -> None:
    with pytest.raises(ValidationError):
        NotionPlannedRecord(
            task_id="t1",
            title="x",
            action=PlannedAction.CREATE,
            proposed_status="todo",
            proposed_priority="medium",
            proposed_category="operational",
            field_count=-1,
        )


# ---------- NotionPlanIssue ----------

def test_issue_minimal() -> None:
    i = NotionPlanIssue(
        severity=NotionPlanIssueSeverity.WARNING,
        code="value_too_long",
        message="msg",
    )
    assert i.task_id is None
    assert i.field is None


def test_issue_severity_enum() -> None:
    i = NotionPlanIssue(
        severity=NotionPlanIssueSeverity.ERROR,
        code="x",
        message="m",
    )
    assert i.severity is NotionPlanIssueSeverity.ERROR


def test_issue_oversize_message_rejected() -> None:
    with pytest.raises(ValidationError):
        NotionPlanIssue(
            severity=NotionPlanIssueSeverity.INFO,
            code="x",
            message="x" * 500,
        )


# ---------- NotionSyncPlan ----------

def test_minimal_plan_validates() -> None:
    p = NotionSyncPlan.model_validate(_minimal_plan())
    assert p.contract_version == NOTION_SYNC_PLAN_VERSION
    assert p.total_records == 0


def test_plan_round_trip_json() -> None:
    p = NotionSyncPlan.model_validate(_minimal_plan())
    reloaded = NotionSyncPlan.from_json(p.to_json())
    assert reloaded.model_dump() == p.model_dump()


def test_plan_naive_timestamp_rejected() -> None:
    with pytest.raises(ValidationError):
        NotionSyncPlan.model_validate(
            _minimal_plan(created_at="2026-06-02T12:00:00")
        )


def test_plan_bad_slug_rejected() -> None:
    with pytest.raises(ValidationError):
        NotionSyncPlan.model_validate(_minimal_plan(client_slug="Bad Slug"))


def test_plan_version_pinned() -> None:
    with pytest.raises(ValidationError):
        NotionSyncPlan.model_validate(
            _minimal_plan(contract_version="notion-sync-plan.v2")
        )


def test_plan_extra_field_rejected() -> None:
    data = _minimal_plan()
    data["rogue"] = True
    with pytest.raises(ValidationError):
        NotionSyncPlan.model_validate(data)


def test_plan_issues_for_filter() -> None:
    data = _minimal_plan(
        issues=[
            NotionPlanIssue(
                severity=NotionPlanIssueSeverity.ERROR, code="e", message="m"
            ).model_dump(mode="json"),
            NotionPlanIssue(
                severity=NotionPlanIssueSeverity.WARNING, code="w", message="m"
            ).model_dump(mode="json"),
            NotionPlanIssue(
                severity=NotionPlanIssueSeverity.INFO, code="i", message="m"
            ).model_dump(mode="json"),
        ]
    )
    p = NotionSyncPlan.model_validate(data)
    assert len(p.issues_for(NotionPlanIssueSeverity.ERROR)) == 1
    assert p.has_errors() is True


def test_plan_has_errors_false_when_only_warnings() -> None:
    data = _minimal_plan(
        issues=[
            NotionPlanIssue(
                severity=NotionPlanIssueSeverity.WARNING, code="w", message="m"
            ).model_dump(mode="json"),
        ]
    )
    p = NotionSyncPlan.model_validate(data)
    assert p.has_errors() is False
