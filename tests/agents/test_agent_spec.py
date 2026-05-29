"""Pydantic validation tests for agent-spec.v1."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from core.agents import AGENT_SPEC_VERSION, AgentSpec


def _good(**overrides) -> dict:
    base = {
        "agent_id": "copywriter",
        "version": 1,
        "spec_version": AGENT_SPEC_VERSION,
        "status": "spec_only",
        "default_model": "sonnet",
    }
    base.update(overrides)
    return base


def test_minimal_valid() -> None:
    spec = AgentSpec.model_validate(_good())
    assert spec.agent_id == "copywriter"
    assert spec.default_model == "sonnet"


def test_round_trip_json() -> None:
    spec = AgentSpec.model_validate(_good())
    assert AgentSpec.from_json(spec.to_json()).model_dump() == spec.model_dump()


def test_agent_id_pattern_enforced() -> None:
    with pytest.raises(ValidationError):
        AgentSpec.model_validate(_good(agent_id="Bad ID"))


def test_status_pinned() -> None:
    with pytest.raises(ValidationError):
        AgentSpec.model_validate(_good(status="vibing"))


def test_default_model_pinned() -> None:
    with pytest.raises(ValidationError):
        AgentSpec.model_validate(_good(default_model="gpt-99"))


def test_default_model_haiku_ok() -> None:
    spec = AgentSpec.model_validate(_good(default_model="haiku"))
    assert spec.default_model == "haiku"


def test_spec_version_wrong_rejected() -> None:
    with pytest.raises(ValidationError):
        AgentSpec.model_validate(_good(spec_version="agent-spec.v2"))


def test_extra_top_level_field_rejected() -> None:
    with pytest.raises(ValidationError):
        AgentSpec.model_validate({**_good(), "rogue": True})


def test_skill_id_pattern_enforced() -> None:
    with pytest.raises(ValidationError):
        AgentSpec.model_validate(_good(skills=["Bad Skill"]))


def test_duplicate_skills_rejected() -> None:
    with pytest.raises(ValidationError):
        AgentSpec.model_validate(_good(skills=["a", "a"]))


def test_gate_pattern_enforced() -> None:
    with pytest.raises(ValidationError):
        AgentSpec.model_validate(_good(produced_gates=["bad_gate"]))


def test_inputs_outputs_accept_extra_keys() -> None:
    spec = AgentSpec.model_validate(
        _good(
            inputs=[{"kind": "brief", "required": True, "min_count": 1}],
            outputs=[{"kind": "positioning"}],
        )
    )
    assert spec.inputs[0].kind == "brief"


def test_limits_accept_strings_and_dicts() -> None:
    spec = AgentSpec.model_validate(
        _good(limits=["no_external_apis", {"max_audiences_per_run": 3}])
    )
    assert "no_external_apis" in spec.limits
    assert {"max_audiences_per_run": 3} in spec.limits


def test_needs_human_approval_defaults_false() -> None:
    spec = AgentSpec.model_validate(_good())
    assert spec.needs_human_approval is False
