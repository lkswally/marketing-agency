"""Pydantic validation tests for the Campaign Execution Task Pack."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from pydantic import ValidationError

from core.execution import (
    CAMPAIGN_EXECUTION_TASK_PACK_VERSION,
    CampaignExecutionTaskPack,
    ExecutionTask,
    TaskCategory,
    TaskPriority,
    TaskState,
)


def _now() -> datetime:
    return datetime(2026, 6, 1, 12, 0, tzinfo=UTC)


def _minimal_pack(**overrides) -> dict:
    base = {
        "client_slug": "acme-saas",
        "report_id": "r1",
        "report_contract_version": "campaign-strategy.v1",
        "tasks": [],
        "created_at": _now().isoformat(),
        "updated_at": _now().isoformat(),
    }
    base.update(overrides)
    return base


def _task(**overrides) -> dict:
    base = {
        "title": "Sample task",
        "category": "operational",
        "priority": "medium",
        "state": "todo",
    }
    base.update(overrides)
    return base


# ---------- ExecutionTask ----------

def test_minimal_task_validates() -> None:
    t = ExecutionTask.model_validate(_task())
    assert t.state is TaskState.TODO
    assert t.priority is TaskPriority.MEDIUM
    assert t.category is TaskCategory.OPERATIONAL


def test_task_invalid_state_rejected() -> None:
    with pytest.raises(ValidationError):
        ExecutionTask.model_validate(_task(state="in_progress"))


def test_task_title_too_long_rejected() -> None:
    with pytest.raises(ValidationError):
        ExecutionTask.model_validate(_task(title="x" * 300))


def test_task_dependencies_default_empty() -> None:
    t = ExecutionTask.model_validate(_task())
    assert t.depends_on == []


def test_task_blocked_reason_optional() -> None:
    t = ExecutionTask.model_validate(_task(state="blocked", blocked_reason="dep"))
    assert t.state is TaskState.BLOCKED
    assert t.blocked_reason == "dep"


# ---------- CampaignExecutionTaskPack ----------

def test_minimal_pack_validates() -> None:
    p = CampaignExecutionTaskPack.model_validate(_minimal_pack())
    assert p.contract_version == CAMPAIGN_EXECUTION_TASK_PACK_VERSION
    assert p.total_tasks == 0


def test_pack_round_trip_json() -> None:
    p = CampaignExecutionTaskPack.model_validate(_minimal_pack())
    reloaded = CampaignExecutionTaskPack.from_json(p.to_json())
    assert reloaded.model_dump() == p.model_dump()


def test_pack_naive_timestamp_rejected() -> None:
    with pytest.raises(ValidationError):
        CampaignExecutionTaskPack.model_validate(
            _minimal_pack(created_at="2026-06-01T12:00:00")
        )


def test_pack_bad_slug_rejected() -> None:
    with pytest.raises(ValidationError):
        CampaignExecutionTaskPack.model_validate(_minimal_pack(client_slug="Bad Slug"))


def test_pack_version_pinned() -> None:
    with pytest.raises(ValidationError):
        CampaignExecutionTaskPack.model_validate(
            _minimal_pack(contract_version="campaign-execution-task-pack.v2")
        )


def test_pack_extra_field_rejected() -> None:
    data = _minimal_pack()
    data["rogue"] = True
    with pytest.raises(ValidationError):
        CampaignExecutionTaskPack.model_validate(data)


def test_count_by_state_with_mixed_tasks() -> None:
    tasks = [
        _task(state="todo"),
        _task(state="blocked", blocked_reason="x"),
        _task(state="done"),
        _task(state="ready"),
    ]
    p = CampaignExecutionTaskPack.model_validate(_minimal_pack(tasks=tasks))
    counts = p.count_by_state()
    assert counts["todo"] == 1
    assert counts["blocked"] == 1
    assert counts["done"] == 1
    assert counts["ready"] == 1
    assert counts["needs_review"] == 0


def test_count_by_priority() -> None:
    tasks = [
        _task(priority="high"),
        _task(priority="medium"),
        _task(priority="medium"),
        _task(priority="low"),
    ]
    p = CampaignExecutionTaskPack.model_validate(_minimal_pack(tasks=tasks))
    counts = p.count_by_priority()
    assert counts["high"] == 1
    assert counts["medium"] == 2
    assert counts["low"] == 1


def test_count_by_category() -> None:
    tasks = [
        _task(category="approval"),
        _task(category="design"),
        _task(category="design"),
    ]
    p = CampaignExecutionTaskPack.model_validate(_minimal_pack(tasks=tasks))
    counts = p.count_by_category()
    assert counts["approval"] == 1
    assert counts["design"] == 2


def test_tasks_in_category() -> None:
    tasks = [
        _task(category="approval", title="A"),
        _task(category="design", title="D"),
    ]
    p = CampaignExecutionTaskPack.model_validate(_minimal_pack(tasks=tasks))
    approval = p.tasks_in_category(TaskCategory.APPROVAL)
    assert len(approval) == 1
    assert approval[0].title == "A"


def test_blocked_tasks_helper() -> None:
    tasks = [
        _task(title="ok"),
        _task(title="bad", state="blocked", blocked_reason="x"),
    ]
    p = CampaignExecutionTaskPack.model_validate(_minimal_pack(tasks=tasks))
    blocked = p.blocked_tasks()
    assert len(blocked) == 1
    assert blocked[0].title == "bad"


def test_task_due_date_optional_and_typed() -> None:
    t = ExecutionTask.model_validate(_task(due_date="2026-07-01"))
    assert t.due_date == date(2026, 7, 1)
