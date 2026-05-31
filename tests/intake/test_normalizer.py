"""IntakeNormalizer tests — produces a valid StrategyInputBrief; no fabrication."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from core.domain.enums import ChannelType
from core.intake import (
    DEFAULT_DURATION_WEEKS,
    DEFAULT_LOCALE,
    DEFAULT_PRIMARY_KPI,
    ClientIntake,
    CompetitorIntake,
    IntakeNormalizationError,
    IntakeValidator,
    normalize_intake,
)
from core.strategy import StrategyInputBrief

REPO_ROOT = Path(__file__).resolve().parents[2]
DEMO = REPO_ROOT / "examples" / "intake" / "demo-business.json"


def _full_intake(**overrides) -> ClientIntake:
    data = dict(
        client_name="Acme",
        industry="SaaS",
        market="LATAM",
        product_or_service="Acme Pro suite",
        product_type="subscription",
        audience_description="solo founders",
        commercial_objective="200 trials/month",
        brand_tone=["claro", "directo"],
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
        additional_context="ctx",
    )
    data.update(overrides)
    return ClientIntake.model_validate(data)


def _validate(intake: ClientIntake):
    return IntakeValidator().validate(intake)


# ---------- happy path ----------

def test_normalize_produces_strategy_input_brief() -> None:
    intake = _full_intake()
    validation = _validate(intake)
    brief = normalize_intake(intake, validation)
    assert isinstance(brief, StrategyInputBrief)
    assert brief.client.slug == "acme"
    assert brief.client.name == "Acme"


def test_brief_round_trip_through_pydantic() -> None:
    """The brief produced by the normalizer must parse cleanly as
    ``StrategyInputBrief`` (MKT-3A compatibility)."""
    intake = _full_intake()
    brief = normalize_intake(intake, _validate(intake))
    reloaded = StrategyInputBrief.from_json(brief.to_json())
    assert reloaded.model_dump() == brief.model_dump()


def test_normalize_demo_file_chain_works() -> None:
    data = json.loads(DEMO.read_text(encoding="utf-8"))
    intake = ClientIntake.model_validate(data)
    validation = _validate(intake)
    brief = normalize_intake(intake, validation)
    assert brief.client.slug == "acme-bootstrapped"


# ---------- field mapping ----------

def test_brand_voice_preserved_verbatim() -> None:
    intake = _full_intake(
        brand_tone=["claro", "directo"],
        preferred_words=["equipos"],
        forbidden_words=["disruptivo"],
    )
    brief = normalize_intake(intake, _validate(intake))
    assert brief.brand.tone_words == ["claro", "directo"]
    assert brief.brand.lexicon_do == ["equipos"]
    assert brief.brand.banned_words == ["disruptivo"]


def test_claims_to_avoid_appended_to_constraints() -> None:
    intake = _full_intake(
        constraints=["No paid"],
        claims_to_avoid=["guaranteed", "best ever"],
    )
    brief = normalize_intake(intake, _validate(intake))
    assert "No paid" in brief.constraints
    assert any("Claim to avoid: guaranteed" in c for c in brief.constraints)
    assert any("Claim to avoid: best ever" in c for c in brief.constraints)


def test_competitors_mapped_to_input_competitor() -> None:
    intake = _full_intake(
        known_competitors=[
            CompetitorIntake(name="Big", url="https://big.example", notes="enterprise"),
        ]
    )
    brief = normalize_intake(intake, _validate(intake))
    assert len(brief.competitors_known) == 1
    c = brief.competitors_known[0]
    assert c.name == "Big"
    assert c.url == "https://big.example"
    assert c.positioning_summary == "enterprise"


def test_channels_mapped_to_enum_dropping_unknowns() -> None:
    intake = _full_intake(possible_channels=["newsletter", "snail_mail", "linkedin"])
    brief = normalize_intake(intake, _validate(intake))
    assert ChannelType.NEWSLETTER in brief.preferred_channels
    assert ChannelType.LINKEDIN in brief.preferred_channels
    # unknown is silently dropped (already surfaced as warning in the validator).
    assert len(brief.preferred_channels) == 2


def test_market_propagated_to_audience_demographics() -> None:
    intake = _full_intake(market="LATAM")
    brief = normalize_intake(intake, _validate(intake))
    assert brief.audience_hints[0].demographics.get("geo") == "LATAM"


# ---------- defaults ----------

def test_duration_weeks_default_used_when_missing() -> None:
    intake = _full_intake(duration_weeks=None)
    brief = normalize_intake(intake, _validate(intake))
    assert brief.duration_weeks == DEFAULT_DURATION_WEEKS


def test_primary_kpi_default_used_when_missing() -> None:
    intake = _full_intake(primary_kpi=None)
    brief = normalize_intake(intake, _validate(intake))
    assert brief.primary_kpi == DEFAULT_PRIMARY_KPI


def test_locale_default_used_when_missing() -> None:
    intake = _full_intake(locale=None)
    brief = normalize_intake(intake, _validate(intake))
    assert brief.client.locale == DEFAULT_LOCALE


# ---------- non-invention invariant ----------

def test_industry_preserved_as_none_when_missing() -> None:
    intake = _full_intake(industry=None)
    brief = normalize_intake(intake, _validate(intake))
    assert brief.client.industry is None


def test_budget_preserved_as_none_when_missing() -> None:
    intake = _full_intake(budget_estimate=None, budget_currency=None)
    brief = normalize_intake(intake, _validate(intake))
    assert brief.budget_amount is None
    assert brief.budget_currency is None


def test_brand_tone_empty_when_missing() -> None:
    intake = _full_intake(brand_tone=[])
    brief = normalize_intake(intake, _validate(intake))
    assert brief.brand.tone_words == []


def test_forbidden_words_empty_when_missing() -> None:
    intake = _full_intake(forbidden_words=[])
    brief = normalize_intake(intake, _validate(intake))
    assert brief.brand.banned_words == []


# ---------- critical-missing path raises ----------

def test_normalize_raises_on_critical_missing() -> None:
    intake = _full_intake(product_or_service=None)
    validation = _validate(intake)
    assert validation.can_normalize is False
    with pytest.raises(IntakeNormalizationError):
        normalize_intake(intake, validation)


def test_normalize_raises_on_audience_missing() -> None:
    intake = _full_intake(audience_description=None)
    validation = _validate(intake)
    with pytest.raises(IntakeNormalizationError):
        normalize_intake(intake, validation)
