"""IntakeValidator tests — severity surfacing, slug derivation, defaults."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from core.intake import (
    DEFAULT_DURATION_WEEKS,
    DEFAULT_LOCALE,
    DEFAULT_PRIMARY_KPI,
    ClientIntake,
    CompetitorIntake,
    IntakeValidator,
    derive_slug,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
DEMO = REPO_ROOT / "examples" / "intake" / "demo-business.json"


def _full_intake(**overrides) -> ClientIntake:
    """Return a complete intake (no warnings). Override fields to introduce gaps."""
    data = dict(
        client_name="Acme",
        industry="SaaS",
        market="LATAM",
        product_or_service="Acme Pro suite",
        product_type="subscription",
        audience_description="solo founders",
        commercial_objective="200 trials/month",
        brand_tone=["claro"],
        preferred_words=["lanzar"],
        forbidden_words=["disruptivo"],
        claim_style="specific",
        possible_channels=["newsletter", "linkedin"],
        known_competitors=[CompetitorIntake(name="Big SaaS")],
        budget_estimate=5000.0,
        budget_currency="USD",
        deadline=date(2026, 9, 30),
        duration_weeks=8,
        primary_kpi="qualified_leads",
        locale="es-AR",
        constraints=["No paid"],
        claims_to_avoid=["guaranteed"],
        good_examples=["x"],
        bad_examples=["y"],
        additional_context="ctx",
    )
    data.update(overrides)
    return ClientIntake.model_validate(data)


# ---------- slug derivation ----------

def test_derive_slug_basic() -> None:
    assert derive_slug("Acme Corp") == "acme-corp"


def test_derive_slug_handles_accents() -> None:
    # Accents are not alnum so they collapse to dashes.
    s = derive_slug("Demó Saas")
    assert "demo" not in s  # the ó is dropped
    assert s.startswith("dem")


def test_derive_slug_strips_outer_dashes() -> None:
    assert derive_slug("  Acme  ") == "acme"


def test_derive_slug_collapses_runs() -> None:
    assert derive_slug("Acme!!!Corp???") == "acme-corp"


def test_derive_slug_max_64_chars() -> None:
    name = "a" * 100
    assert len(derive_slug(name)) <= 64


def test_derive_slug_rejects_empty_result() -> None:
    with pytest.raises(ValueError):
        derive_slug("!!!")


# ---------- happy path ----------

def test_validate_full_intake_has_no_warnings() -> None:
    intake = _full_intake()
    result = IntakeValidator().validate(intake)
    assert result.is_valid is True
    assert result.can_normalize is True
    assert result.missing_critical_count == 0
    assert result.missing_warning_count == 0
    assert result.missing_info_count == 0


def test_validate_full_intake_no_defaults_applied() -> None:
    intake = _full_intake()
    result = IntakeValidator().validate(intake)
    assert result.operational_defaults_applied == {}


def test_validate_real_demo_file() -> None:
    data = json.loads(DEMO.read_text(encoding="utf-8"))
    intake = ClientIntake.model_validate(data)
    result = IntakeValidator().validate(intake)
    assert result.is_valid is True
    assert result.can_normalize is True


# ---------- critical missing ----------

@pytest.mark.parametrize(
    "field",
    ["product_or_service", "commercial_objective", "audience_description"],
)
def test_critical_when_field_missing(field: str) -> None:
    intake = _full_intake(**{field: None})
    result = IntakeValidator().validate(intake)
    assert result.is_valid is False
    assert result.can_normalize is False
    assert result.missing_critical_count >= 1
    severities = {w.field_path for w in result.warnings if w.severity == "critical"}
    assert field in severities


def test_critical_when_field_empty_string() -> None:
    intake = _full_intake(product_or_service="   ")
    result = IntakeValidator().validate(intake)
    assert result.is_valid is False


# ---------- warning-level missing ----------

@pytest.mark.parametrize(
    "field,override",
    [
        ("industry", {"industry": None}),
        ("market", {"market": None}),
        ("brand_tone", {"brand_tone": []}),
        ("known_competitors", {"known_competitors": []}),
        ("budget_estimate", {"budget_estimate": None}),
        ("constraints", {"constraints": []}),
    ],
)
def test_warning_when_field_missing(field: str, override: dict) -> None:
    intake = _full_intake(**override)
    result = IntakeValidator().validate(intake)
    severities = {w.field_path for w in result.warnings if w.severity == "warning"}
    assert field in severities


# ---------- info-level missing + defaults ----------

def test_duration_weeks_default_applied_and_reported() -> None:
    intake = _full_intake(duration_weeks=None)
    result = IntakeValidator().validate(intake)
    assert result.operational_defaults_applied.get("duration_weeks") == str(DEFAULT_DURATION_WEEKS)
    info_fields = {w.field_path for w in result.warnings if w.severity == "info"}
    assert "duration_weeks" in info_fields


def test_primary_kpi_default_applied_and_reported() -> None:
    intake = _full_intake(primary_kpi=None)
    result = IntakeValidator().validate(intake)
    assert result.operational_defaults_applied.get("primary_kpi") == DEFAULT_PRIMARY_KPI


def test_locale_default_applied_and_reported() -> None:
    intake = _full_intake(locale=None)
    result = IntakeValidator().validate(intake)
    assert result.operational_defaults_applied.get("locale") == DEFAULT_LOCALE


def test_deadline_missing_is_info_only() -> None:
    intake = _full_intake(deadline=None)
    result = IntakeValidator().validate(intake)
    info_fields = {w.field_path for w in result.warnings if w.severity == "info"}
    assert "deadline" in info_fields


# ---------- channel sanity ----------

def test_unknown_channel_surfaces_warning() -> None:
    intake = _full_intake(possible_channels=["newsletter", "snail_mail"])
    result = IntakeValidator().validate(intake)
    paths = {w.field_path for w in result.warnings if w.severity == "warning"}
    assert any(p.startswith("possible_channels[") for p in paths)


def test_known_channels_dont_warn() -> None:
    intake = _full_intake(possible_channels=["newsletter", "linkedin"])
    result = IntakeValidator().validate(intake)
    paths = {w.field_path for w in result.warnings}
    assert not any(p.startswith("possible_channels[") for p in paths)


# ---------- slug resolution ----------

def test_slug_derived_from_name() -> None:
    intake = _full_intake(client_name="Acme Corp")
    result = IntakeValidator().validate(intake)
    assert result.client_slug == "acme-corp"


def test_slug_uses_override() -> None:
    intake = _full_intake(client_slug_override="custom-slug")
    result = IntakeValidator().validate(intake)
    assert result.client_slug == "custom-slug"


def test_slug_reserved_rejected_as_critical() -> None:
    # Pydantic rejects ``_shared`` at model layer via validate_slug.
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        _full_intake(client_slug_override="_shared")


def test_slug_underivable_critical() -> None:
    intake = ClientIntake(
        client_name="!!!",  # produces empty slug
        product_or_service="x",
        commercial_objective="x",
        audience_description="x",
    )
    result = IntakeValidator().validate(intake)
    assert result.is_valid is False
    critical_fields = {w.field_path for w in result.warnings if w.severity == "critical"}
    assert "client_name" in critical_fields


# ---------- no-data fabrication invariant ----------

def test_validator_never_mutates_intake() -> None:
    intake = _full_intake(industry=None, brand_tone=[])
    before = intake.model_dump()
    IntakeValidator().validate(intake)
    after = intake.model_dump()
    assert before == after
