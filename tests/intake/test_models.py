"""Pydantic validation tests for intake models."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from core.intake import (
    CLIENT_INTAKE_VERSION,
    INTAKE_VALIDATION_VERSION,
    ClientIntake,
    CompetitorIntake,
    IntakeValidationResult,
    IntakeWarning,
)


def _now() -> datetime:
    return datetime(2026, 5, 30, 12, 0, tzinfo=UTC)


# ---------- ClientIntake ----------

def test_minimal_intake_validates() -> None:
    intake = ClientIntake(client_name="Acme")
    assert intake.schema_version == CLIENT_INTAKE_VERSION
    assert intake.industry is None
    assert intake.brand_tone == []


def test_intake_requires_client_name() -> None:
    with pytest.raises(ValidationError):
        ClientIntake(client_name="")


def test_intake_round_trip_json() -> None:
    intake = ClientIntake(
        client_name="Acme",
        industry="SaaS",
        brand_tone=["claro", "directo"],
        forbidden_words=["disruptivo"],
        known_competitors=[
            CompetitorIntake(name="Big SaaS", url="https://big.example")
        ],
    )
    reloaded = ClientIntake.from_json(intake.to_json())
    assert reloaded.model_dump() == intake.model_dump()


def test_intake_extra_fields_rejected() -> None:
    with pytest.raises(ValidationError):
        ClientIntake.model_validate({"client_name": "Acme", "rogue": True})


def test_intake_product_type_enum() -> None:
    with pytest.raises(ValidationError):
        ClientIntake(client_name="Acme", product_type="vibes")  # type: ignore[arg-type]


def test_intake_negative_budget_rejected() -> None:
    with pytest.raises(ValidationError):
        ClientIntake(client_name="Acme", budget_estimate=-1)


def test_intake_duration_weeks_bounds() -> None:
    with pytest.raises(ValidationError):
        ClientIntake(client_name="Acme", duration_weeks=0)
    with pytest.raises(ValidationError):
        ClientIntake(client_name="Acme", duration_weeks=99)


def test_intake_slug_override_rejected_when_bad() -> None:
    with pytest.raises(ValidationError):
        ClientIntake(client_name="Acme", client_slug_override="Bad Slug")


def test_intake_slug_override_accepted_when_valid() -> None:
    intake = ClientIntake(client_name="Acme", client_slug_override="acme")
    assert intake.client_slug_override == "acme"


def test_intake_competitors_round_trip() -> None:
    c = CompetitorIntake(name="Big", url="https://big.example", notes="enterprise")
    reloaded = CompetitorIntake.from_json(c.to_json())
    assert reloaded.model_dump() == c.model_dump()


def test_competitor_name_required() -> None:
    with pytest.raises(ValidationError):
        CompetitorIntake(name="")


# ---------- IntakeWarning ----------

def test_warning_severity_enum() -> None:
    with pytest.raises(ValidationError):
        IntakeWarning(field_path="x", severity="meh", message="x")  # type: ignore[arg-type]


def test_warning_round_trip() -> None:
    w = IntakeWarning(
        field_path="industry",
        severity="warning",
        message="missing",
        suggested_action="ask client",
    )
    reloaded = IntakeWarning.from_json(w.to_json())
    assert reloaded.model_dump() == w.model_dump()


# ---------- IntakeValidationResult ----------

def _minimal_result(**overrides) -> dict:
    base = {
        "contract_version": INTAKE_VALIDATION_VERSION,
        "intake_id": "i1",
        "client_slug": "acme",
        "is_valid": True,
        "can_normalize": True,
        "warnings": [],
        "missing_critical_count": 0,
        "missing_warning_count": 0,
        "missing_info_count": 0,
        "operational_defaults_applied": {},
        "created_at": _now().isoformat(),
        "updated_at": _now().isoformat(),
    }
    base.update(overrides)
    return base


def test_validation_result_round_trip() -> None:
    r = IntakeValidationResult.model_validate(_minimal_result())
    reloaded = IntakeValidationResult.from_json(r.to_json())
    assert reloaded.model_dump() == r.model_dump()


def test_validation_result_rejects_naive_timestamp() -> None:
    with pytest.raises(ValidationError):
        IntakeValidationResult.model_validate(
            _minimal_result(created_at="2026-05-30T12:00:00")
        )


def test_validation_result_rejects_bad_slug() -> None:
    with pytest.raises(ValidationError):
        IntakeValidationResult.model_validate(_minimal_result(client_slug="Bad Slug"))


def test_validation_result_negative_counts_rejected() -> None:
    with pytest.raises(ValidationError):
        IntakeValidationResult.model_validate(
            _minimal_result(missing_critical_count=-1)
        )


def test_validation_count_by_severity() -> None:
    warnings = [
        IntakeWarning(field_path="a", severity="critical", message="x").model_dump(mode="json"),
        IntakeWarning(field_path="b", severity="warning", message="x").model_dump(mode="json"),
        IntakeWarning(field_path="c", severity="warning", message="x").model_dump(mode="json"),
        IntakeWarning(field_path="d", severity="info", message="x").model_dump(mode="json"),
    ]
    r = IntakeValidationResult.model_validate(_minimal_result(warnings=warnings))
    counts = r.count_by_severity()
    assert counts == {"info": 1, "warning": 2, "critical": 1}


def test_validation_extra_field_rejected() -> None:
    data = _minimal_result()
    data["rogue"] = True
    with pytest.raises(ValidationError):
        IntakeValidationResult.model_validate(data)
