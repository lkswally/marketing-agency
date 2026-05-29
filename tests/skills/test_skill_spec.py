"""Pydantic validation tests for skill-spec.v1."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from core.skills import SKILL_SPEC_VERSION, SkillSpec


def _good(**overrides) -> dict:
    base = {
        "skill_id": "brand-voice-extractor",
        "version": 1,
        "spec_version": SKILL_SPEC_VERSION,
        "status": "spec_only",
        "deterministic": False,
        "external_dependencies": [],
        "inputs": [],
        "outputs": [],
        "used_by": [],
    }
    base.update(overrides)
    return base


def test_minimal_valid() -> None:
    spec = SkillSpec.model_validate(_good())
    assert spec.skill_id == "brand-voice-extractor"


def test_round_trip_json() -> None:
    spec = SkillSpec.model_validate(_good())
    assert SkillSpec.from_json(spec.to_json()).model_dump() == spec.model_dump()


def test_skill_id_pattern_enforced() -> None:
    with pytest.raises(ValidationError):
        SkillSpec.model_validate(_good(skill_id="Bad ID"))


def test_status_pinned() -> None:
    with pytest.raises(ValidationError):
        SkillSpec.model_validate(_good(status="experimental"))


def test_deterministic_partial_allowed() -> None:
    spec = SkillSpec.model_validate(_good(deterministic="partial"))
    assert spec.deterministic == "partial"


def test_deterministic_invalid_string_rejected() -> None:
    with pytest.raises(ValidationError):
        SkillSpec.model_validate(_good(deterministic="maybe"))


def test_spec_version_wrong_rejected() -> None:
    with pytest.raises(ValidationError):
        SkillSpec.model_validate(_good(spec_version="skill-spec.v2"))


def test_used_by_pattern_enforced() -> None:
    with pytest.raises(ValidationError):
        SkillSpec.model_validate(_good(used_by=["Bad Agent"]))


def test_used_by_duplicates_rejected() -> None:
    with pytest.raises(ValidationError):
        SkillSpec.model_validate(_good(used_by=["a", "a"]))


def test_inputs_accept_dict_or_string() -> None:
    spec = SkillSpec.model_validate(
        _good(
            inputs=[{"sample_texts": "list[str]"}, "brand_id: str"],
        )
    )
    assert len(spec.inputs) == 2


def test_inputs_reject_unexpected_type() -> None:
    with pytest.raises(ValidationError):
        SkillSpec.model_validate(_good(inputs=[123]))


def test_extra_top_level_field_rejected() -> None:
    with pytest.raises(ValidationError):
        SkillSpec.model_validate({**_good(), "rogue": True})
