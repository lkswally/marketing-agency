"""Tests for the job contract and state machine (MKT-11C)."""

from __future__ import annotations

import itertools

import pytest
from pydantic import ValidationError

from core.jobs.models import (
    ALLOWED_TRANSITIONS,
    TERMINAL_STATES,
    JobOutcome,
    JobOutcomeStatus,
    JobRecord,
    JobState,
    can_transition,
)


def test_default_state_is_queued() -> None:
    record = JobRecord(client_slug="acme", operation="demo.echo")
    assert record.state is JobState.QUEUED
    assert record.is_terminal is False


def test_invalid_slug_rejected() -> None:
    with pytest.raises(ValidationError):
        JobRecord(client_slug="Not_A_Slug!", operation="demo.echo")


def test_terminal_states() -> None:
    assert {JobState.COMPLETED, JobState.FAILED, JobState.CANCELLED} == TERMINAL_STATES
    for state in TERMINAL_STATES:
        record = JobRecord(client_slug="acme", operation="demo.echo", state=state)
        assert record.is_terminal is True


# ---------- exhaustive transition matrix ----------

_ALL_STATES = list(JobState)


@pytest.mark.parametrize(
    "current,target", itertools.product(_ALL_STATES, _ALL_STATES),
)
def test_transition_matrix_matches_declared_table(current: JobState, target: JobState) -> None:
    expected = target in ALLOWED_TRANSITIONS[current]
    assert can_transition(current, target) is expected


def test_queued_to_running_allowed() -> None:
    assert can_transition(JobState.QUEUED, JobState.RUNNING)


def test_queued_to_cancelled_allowed() -> None:
    assert can_transition(JobState.QUEUED, JobState.CANCELLED)


def test_queued_to_completed_not_allowed() -> None:
    assert not can_transition(JobState.QUEUED, JobState.COMPLETED)


def test_running_to_completed_allowed() -> None:
    assert can_transition(JobState.RUNNING, JobState.COMPLETED)


def test_running_to_failed_allowed() -> None:
    assert can_transition(JobState.RUNNING, JobState.FAILED)


def test_running_to_waiting_approval_allowed() -> None:
    assert can_transition(JobState.RUNNING, JobState.WAITING_APPROVAL)


def test_running_to_cancelled_not_allowed() -> None:
    """RUNNING has no direct path to CANCELLED — see the runner's
    documented cancellation limitation."""
    assert not can_transition(JobState.RUNNING, JobState.CANCELLED)


def test_waiting_approval_to_queued_allowed_for_future_resume() -> None:
    assert can_transition(JobState.WAITING_APPROVAL, JobState.QUEUED)


def test_waiting_approval_to_cancelled_allowed() -> None:
    assert can_transition(JobState.WAITING_APPROVAL, JobState.CANCELLED)


def test_terminal_states_have_no_outbound_transitions() -> None:
    for state in TERMINAL_STATES:
        assert ALLOWED_TRANSITIONS[state] == frozenset()


# ---------- JobOutcome ----------

def test_outcome_completed_factory() -> None:
    outcome = JobOutcome.completed(data={"x": 1}, result_ref="ref-1")
    assert outcome.status is JobOutcomeStatus.COMPLETED
    assert outcome.data == {"x": 1}
    assert outcome.result_ref == "ref-1"
    assert outcome.error is None


def test_outcome_failed_factory() -> None:
    from core.application.result import ErrorCode

    outcome = JobOutcome.failed(code=ErrorCode.INVALID_INPUT, message="bad")
    assert outcome.status is JobOutcomeStatus.FAILED
    assert outcome.error is not None
    assert outcome.error.code is ErrorCode.INVALID_INPUT


def test_outcome_waiting_approval_factory() -> None:
    outcome = JobOutcome.waiting_approval(reason="needs review")
    assert outcome.status is JobOutcomeStatus.WAITING_APPROVAL
    assert outcome.approval_reason == "needs review"


def test_outcome_status_is_explicit_not_inferred() -> None:
    """The status field is what a runner reads — never a string match on
    a message or a warning."""
    outcome = JobOutcome.waiting_approval(reason="approval needed")
    assert outcome.status is JobOutcomeStatus.WAITING_APPROVAL
    # Changing the reason text must not change the status.
    outcome2 = JobOutcome(status=JobOutcomeStatus.COMPLETED, approval_reason="approval needed")
    assert outcome2.status is JobOutcomeStatus.COMPLETED


def test_no_progress_field_on_job_record() -> None:
    """Deliberate: InlineJobRunner is synchronous, so no observer can read
    an intermediate value. A progress field would be fiction."""
    record = JobRecord(client_slug="acme", operation="demo.echo")
    assert "progress" not in record.model_dump()
