"""Contract tests for WorkflowRunSummary (workflow-run.v1)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from core.contracts import (
    ContractError,
    EnvelopeStatus,
    PhaseGateResult,
    StepResult,
    WorkflowRunStatus,
    WorkflowRunSummary,
    validate_workflow_run,
    validate_workflow_run_strict,
)

pytestmark = pytest.mark.contract


def _t(offset_minutes: int = 0) -> datetime:
    return datetime(2026, 5, 22, 12, 0, tzinfo=UTC) + timedelta(minutes=offset_minutes)


def _running_payload() -> dict:
    return {
        "workflow_name": "onboarding",
        "client_slug": "demo-co",
        "started_at": _t(0).isoformat(),
        "status": "running",
    }


# ---------- Happy path ----------

def test_minimal_running_summary() -> None:
    r = WorkflowRunSummary(**_running_payload())
    assert r.contract_version == "workflow-run.v1"
    assert r.status is WorkflowRunStatus.RUNNING
    assert r.duration_seconds is None


def test_terminal_summary_round_trip() -> None:
    r = WorkflowRunSummary(
        workflow_name="onboarding",
        client_slug="demo-co",
        started_at=_t(0),
        finished_at=_t(30),
        status=WorkflowRunStatus.SUCCEEDED,
        steps=[
            StepResult(
                step_id="s1",
                agent="strategist",
                status=EnvelopeStatus.COMPLETADO,
                started_at=_t(0),
                finished_at=_t(10),
            )
        ],
        metrics={"retries": 0, "duration_s": 1800.0},
    )
    reloaded = WorkflowRunSummary.from_json(r.to_json())
    assert reloaded.model_dump() == r.model_dump()
    assert reloaded.duration_seconds == 1800.0


# ---------- Date order ----------

def test_finished_before_started_rejected() -> None:
    with pytest.raises(ValidationError):
        WorkflowRunSummary(
            workflow_name="x",
            client_slug="demo-co",
            started_at=_t(30),
            finished_at=_t(0),
            status=WorkflowRunStatus.SUCCEEDED,
        )


# ---------- Terminal status requires finished_at ----------

@pytest.mark.parametrize("status", ["succeeded", "failed", "cancelled"])
def test_terminal_status_without_finished_at_rejected(status: str) -> None:
    payload = {**_running_payload(), "status": status}
    ok, errs = validate_workflow_run(payload)
    assert ok is False


# ---------- succeeded cannot contain failed steps ----------

def test_succeeded_with_failed_step_rejected() -> None:
    with pytest.raises(ValidationError):
        WorkflowRunSummary(
            workflow_name="x",
            client_slug="demo-co",
            started_at=_t(0),
            finished_at=_t(10),
            status=WorkflowRunStatus.SUCCEEDED,
            steps=[
                StepResult(
                    step_id="s1",
                    agent="a",
                    status=EnvelopeStatus.FAIL,
                    started_at=_t(0),
                    finished_at=_t(5),
                )
            ],
        )


def test_failed_run_can_contain_failed_step() -> None:
    r = WorkflowRunSummary(
        workflow_name="x",
        client_slug="demo-co",
        started_at=_t(0),
        finished_at=_t(10),
        status=WorkflowRunStatus.FAILED,
        steps=[
            StepResult(
                step_id="s1",
                agent="a",
                status=EnvelopeStatus.FAIL,
                started_at=_t(0),
                finished_at=_t(5),
            )
        ],
    )
    assert r.status is WorkflowRunStatus.FAILED


# ---------- Step constraints ----------

def test_step_finished_before_started_rejected() -> None:
    with pytest.raises(ValidationError):
        StepResult(
            step_id="s1",
            agent="a",
            status=EnvelopeStatus.COMPLETADO,
            started_at=_t(10),
            finished_at=_t(0),
        )


def test_step_naive_timestamp_rejected() -> None:
    with pytest.raises(ValidationError):
        StepResult(
            step_id="s1",
            agent="a",
            status=EnvelopeStatus.COMPLETADO,
            started_at=datetime(2026, 5, 22, 12),
        )


def test_step_negative_retries_rejected() -> None:
    with pytest.raises(ValidationError):
        StepResult(
            step_id="s1",
            agent="a",
            status=EnvelopeStatus.COMPLETADO,
            started_at=_t(0),
            retries=-1,
        )


# ---------- Slug ----------

def test_bad_client_slug_rejected() -> None:
    payload = {**_running_payload(), "client_slug": "Bad Slug"}
    ok, errs = validate_workflow_run(payload)
    assert ok is False


# ---------- Strict ----------

def test_strict_raises_on_bad_payload() -> None:
    with pytest.raises(ContractError):
        validate_workflow_run_strict({**_running_payload(), "status": "vibing"})


# ---------- gate_results coexistence ----------

def test_summary_accepts_gate_results() -> None:
    r = WorkflowRunSummary(
        workflow_name="x",
        client_slug="demo-co",
        started_at=_t(0),
        status=WorkflowRunStatus.RUNNING,
        gate_results=[
            PhaseGateResult(gate_id="g1", passed=True, evaluated_at=_t(1))
        ],
    )
    assert len(r.gate_results) == 1
