"""Pydantic validation tests for WorkflowSpec / PhaseSpec / ApprovalSpec."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from core.workflows import (
    WORKFLOW_SPEC_VERSION,
    ApprovalSpec,
    PhaseSpec,
    WorkflowSpec,
)


def _good_phase(**overrides) -> dict:
    base = {
        "id": "intake",
        "agents": ["mkt-orchestrator"],
        "gates_required_before": [],
        "gates_produced": ["g_brief_captured"],
        "outputs": ["brief"],
    }
    base.update(overrides)
    return base


def _good_spec(**overrides) -> dict:
    base = {
        "workflow_id": "W1_intake_to_strategy",
        "version": 1,
        "spec_version": WORKFLOW_SPEC_VERSION,
        "description": "Onboarding...",
        "phases": [_good_phase()],
    }
    base.update(overrides)
    return base


def test_valid_spec_round_trips() -> None:
    spec = WorkflowSpec.model_validate(_good_spec())
    reloaded = WorkflowSpec.from_json(spec.to_json())
    assert reloaded.model_dump() == spec.model_dump()


def test_workflow_id_pattern_enforced() -> None:
    with pytest.raises(ValidationError):
        WorkflowSpec.model_validate(_good_spec(workflow_id="bad-id"))


def test_phase_id_pattern_enforced() -> None:
    with pytest.raises(ValidationError):
        WorkflowSpec.model_validate(
            _good_spec(phases=[_good_phase(id="Bad-ID")])
        )


def test_phase_requires_at_least_one_agent() -> None:
    with pytest.raises(ValidationError):
        WorkflowSpec.model_validate(_good_spec(phases=[_good_phase(agents=[])]))


def test_phase_rejects_duplicate_agents() -> None:
    with pytest.raises(ValidationError):
        WorkflowSpec.model_validate(
            _good_spec(phases=[_good_phase(agents=["a", "a"])])
        )


def test_gate_name_pattern_enforced() -> None:
    with pytest.raises(ValidationError):
        WorkflowSpec.model_validate(
            _good_spec(phases=[_good_phase(gates_produced=["bad_gate"])])
        )


def test_gate_name_with_caps_rejected() -> None:
    with pytest.raises(ValidationError):
        WorkflowSpec.model_validate(
            _good_spec(phases=[_good_phase(gates_produced=["g_Brief_captured"])])
        )


def test_duplicate_phase_ids_rejected() -> None:
    with pytest.raises(ValidationError):
        WorkflowSpec.model_validate(
            _good_spec(
                phases=[
                    _good_phase(id="intake"),
                    _good_phase(id="intake", agents=["audience-researcher"]),
                ]
            )
        )


def test_approval_human_required_at_must_be_existing_phase() -> None:
    with pytest.raises(ValidationError):
        WorkflowSpec.model_validate(
            _good_spec(
                approval={"state_machine": "standard", "human_required_at": ["nope"]}
            )
        )


def test_approval_human_required_at_existing_phase_ok() -> None:
    spec = WorkflowSpec.model_validate(
        _good_spec(
            approval={"state_machine": "standard", "human_required_at": ["intake"]}
        )
    )
    assert spec.approval is not None
    assert spec.approval.human_required_at == ["intake"]


def test_wrong_spec_version_rejected() -> None:
    with pytest.raises(ValidationError):
        WorkflowSpec.model_validate(
            _good_spec(spec_version="workflow-spec.v2")
        )


def test_extra_field_rejected() -> None:
    with pytest.raises(ValidationError):
        WorkflowSpec.model_validate({**_good_spec(), "rogue": True})


def test_helpers() -> None:
    spec = WorkflowSpec.model_validate(
        _good_spec(
            phases=[
                _good_phase(),
                _good_phase(
                    id="research",
                    agents=["audience-researcher"],
                    gates_required_before=["g_brief_captured"],
                    gates_produced=["g_audience_research_complete"],
                ),
            ]
        )
    )
    assert spec.all_phase_ids == ["intake", "research"]
    assert spec.all_agents == ["mkt-orchestrator", "audience-researcher"]
    assert spec.gates_consumed == {"g_brief_captured"}
    assert spec.gates_emitted == {"g_brief_captured", "g_audience_research_complete"}


def test_approval_spec_state_machine_pinned() -> None:
    with pytest.raises(ValidationError):
        ApprovalSpec.model_validate({"state_machine": "fancy"})


def test_phase_min_length_enforced_via_workflow() -> None:
    with pytest.raises(ValidationError):
        WorkflowSpec.model_validate(_good_spec(phases=[]))


def test_phase_spec_round_trip() -> None:
    p = PhaseSpec.model_validate(_good_phase())
    assert PhaseSpec.from_json(p.to_json()).model_dump() == p.model_dump()
