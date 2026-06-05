"""Tests for the MKT-8A ATLAS bridge contract models."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from core.atlas_bridge.models import (
    ATLAS_HANDOFF_BRIEF_KIND,
    ATLAS_HANDOFF_BRIEF_VERSION,
    AtlasHandoffBrief,
    AtlasHandoffKind,
    BrandingBrief,
    BrandingTokenSet,
    HandoffAssetReference,
    LandingBrief,
    LandingSection,
    PageDesignBlock,
    PageDesignBrief,
    SEOGEOTargets,
)


def _now() -> datetime:
    return datetime(2026, 6, 4, tzinfo=UTC)


def _landing_brief() -> LandingBrief:
    return LandingBrief(
        page_objective="Capture leads.",
        target_audience="SMB owners.",
        primary_cta_label="Solicitar demo",
        sections=[LandingSection(
            name="hero",
            objective="Hook + value prop.",
            body_copy="Bienvenido.",
        )],
        visual_style_notes="Clean, modern, brand palette.",
        acceptance_criteria=["Hero matches approved copy."],
    )


def _branding_brief() -> BrandingBrief:
    return BrandingBrief(
        brand_objective="Coherent identity.",
        target_audience="SMB owners.",
        positioning_statement="The straightforward marketing OS.",
        tokens=BrandingTokenSet(palette_primary=["#000"]),
        deliverables_requested=["logo_primary"],
        acceptance_criteria=["Logo works on dark + light."],
    )


def _page_design_brief() -> PageDesignBrief:
    return PageDesignBrief(
        page_name="about",
        page_objective="Tell the story.",
        target_audience="SMB owners.",
        blocks=[PageDesignBlock(
            name="intro",
            intent="Intro the page.",
            body_copy="Quiénes somos.",
        )],
        visual_style_notes="Clean.",
        acceptance_criteria=["Story arc lands."],
    )


def test_kind_constants() -> None:
    assert ATLAS_HANDOFF_BRIEF_KIND == "atlas_handoff_brief"
    assert ATLAS_HANDOFF_BRIEF_VERSION == "atlas-handoff-brief.v1"


def test_kind_enum_complete() -> None:
    assert {k.value for k in AtlasHandoffKind} == {
        "landing", "branding", "page_design",
    }


def test_landing_handoff_round_trip() -> None:
    h = AtlasHandoffBrief(
        client_slug="acme",
        kind=AtlasHandoffKind.LANDING,
        landing_brief=_landing_brief(),
        created_at=_now(),
    )
    raw = h.model_dump(mode="json")
    again = AtlasHandoffBrief.model_validate(raw)
    assert again.handoff_id == h.handoff_id
    assert again.landing_brief is not None
    assert again.branding_brief is None


def test_branding_handoff_round_trip() -> None:
    h = AtlasHandoffBrief(
        client_slug="acme",
        kind=AtlasHandoffKind.BRANDING,
        branding_brief=_branding_brief(),
        created_at=_now(),
    )
    raw = h.model_dump(mode="json")
    again = AtlasHandoffBrief.model_validate(raw)
    assert again.kind is AtlasHandoffKind.BRANDING


def test_page_design_handoff_round_trip() -> None:
    h = AtlasHandoffBrief(
        client_slug="acme",
        kind=AtlasHandoffKind.PAGE_DESIGN,
        page_design_brief=_page_design_brief(),
        created_at=_now(),
    )
    raw = h.model_dump(mode="json")
    AtlasHandoffBrief.model_validate(raw)


def test_handoff_rejects_zero_briefs() -> None:
    with pytest.raises(ValueError, match="exactly one"):
        AtlasHandoffBrief(
            client_slug="acme",
            kind=AtlasHandoffKind.LANDING,
            created_at=_now(),
        )


def test_handoff_rejects_multiple_briefs() -> None:
    with pytest.raises(ValueError, match="exactly one"):
        AtlasHandoffBrief(
            client_slug="acme",
            kind=AtlasHandoffKind.LANDING,
            landing_brief=_landing_brief(),
            branding_brief=_branding_brief(),
            created_at=_now(),
        )


def test_handoff_rejects_kind_mismatch() -> None:
    with pytest.raises(ValueError, match="requires"):
        AtlasHandoffBrief(
            client_slug="acme",
            kind=AtlasHandoffKind.BRANDING,
            landing_brief=_landing_brief(),
            created_at=_now(),
        )


def test_handoff_rejects_naive_datetime() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        AtlasHandoffBrief(
            client_slug="acme",
            kind=AtlasHandoffKind.LANDING,
            landing_brief=_landing_brief(),
            created_at=datetime(2026, 6, 4),
        )


def test_handoff_rejects_invalid_slug() -> None:
    with pytest.raises(ValueError):
        AtlasHandoffBrief(
            client_slug="UPPER",
            kind=AtlasHandoffKind.LANDING,
            landing_brief=_landing_brief(),
            created_at=_now(),
        )


def test_no_credential_fields_on_any_model() -> None:
    forbidden = {
        "token", "api_key", "secret", "credential", "credentials",
        "webhook_url",
    }
    for cls in (
        AtlasHandoffBrief, LandingBrief, BrandingBrief, PageDesignBrief,
        LandingSection, PageDesignBlock, BrandingTokenSet,
        HandoffAssetReference, SEOGEOTargets,
    ):
        fields = set(cls.model_fields.keys())
        bad = fields & forbidden
        assert not bad, f"{cls.__name__} exposes: {bad}"


def test_landing_section_body_copy_does_not_shadow_copy_method() -> None:
    """Pin: the field is ``body_copy``, not ``copy`` — so
    ``LandingSection.copy()`` still resolves to BaseModel.copy."""
    sec = LandingSection(
        name="hero", objective="Hook.", body_copy="Hello.",
    )
    cloned = sec.model_copy()
    assert cloned.body_copy == "Hello."


def test_landing_brief_requires_at_least_one_section() -> None:
    with pytest.raises(ValueError):
        LandingBrief(
            page_objective="x", target_audience="y",
            primary_cta_label="z", sections=[],
            visual_style_notes="notes", acceptance_criteria=["a"],
        )


def test_branding_brief_requires_deliverables_and_acceptance() -> None:
    with pytest.raises(ValueError):
        BrandingBrief(
            brand_objective="x", target_audience="y",
            positioning_statement="z",
            deliverables_requested=[],
            acceptance_criteria=["a"],
        )
    with pytest.raises(ValueError):
        BrandingBrief(
            brand_objective="x", target_audience="y",
            positioning_statement="z",
            deliverables_requested=["logo_primary"],
            acceptance_criteria=[],
        )
