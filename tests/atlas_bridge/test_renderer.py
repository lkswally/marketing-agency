"""Tests for the MKT-8A renderer."""

from __future__ import annotations

from datetime import UTC, datetime

from core.atlas_bridge import (
    AtlasHandoffBrief,
    AtlasHandoffKind,
    BrandingBrief,
    BrandingTokenSet,
    LandingBrief,
    LandingSection,
    PageDesignBlock,
    PageDesignBrief,
    SEOGEOTargets,
    render_markdown_atlas_handoff,
)


def _now() -> datetime:
    return datetime(2026, 6, 4, tzinfo=UTC)


def _landing_handoff(blocks_publish: bool = False) -> AtlasHandoffBrief:
    return AtlasHandoffBrief(
        client_slug="acme",
        kind=AtlasHandoffKind.LANDING,
        landing_brief=LandingBrief(
            page_objective="Capture leads.",
            target_audience="SMB owners.",
            primary_cta_label="Solicitar demo",
            sections=[LandingSection(
                name="hero", objective="Hook.",
                body_copy="Bienvenido.",
                cta_label="Empezar",
            )],
            visual_style_notes="Clean modern look.",
            seo_geo=SEOGEOTargets(primary_keyword="marketing OS"),
            acceptance_criteria=["Hero matches approved copy."],
        ),
        blocks_publish=blocks_publish,
        created_at=_now(),
    )


def test_render_landing_handoff() -> None:
    md = render_markdown_atlas_handoff(_landing_handoff())
    assert "ATLAS Handoff" in md
    assert "Landing brief" in md
    assert "Solicitar demo" in md
    assert "marketing OS" in md
    assert "MARKETING-AGENCY-OS does NOT reach" in md


def test_render_landing_handoff_with_warning() -> None:
    md = render_markdown_atlas_handoff(_landing_handoff(blocks_publish=True))
    assert "WARNING" in md
    assert "blocks_publish=True" in md


def test_render_branding_handoff() -> None:
    handoff = AtlasHandoffBrief(
        client_slug="acme",
        kind=AtlasHandoffKind.BRANDING,
        branding_brief=BrandingBrief(
            brand_objective="Identity.",
            target_audience="SMB.",
            positioning_statement="The marketing OS.",
            tokens=BrandingTokenSet(palette_primary=["#0F172A"]),
            deliverables_requested=["logo_primary", "color_palette"],
            acceptance_criteria=["Logo works on dark + light."],
        ),
        created_at=_now(),
    )
    md = render_markdown_atlas_handoff(handoff)
    assert "Branding brief" in md
    assert "logo_primary" in md
    assert "#0F172A" in md


def test_render_page_design_handoff() -> None:
    handoff = AtlasHandoffBrief(
        client_slug="acme",
        kind=AtlasHandoffKind.PAGE_DESIGN,
        page_design_brief=PageDesignBrief(
            page_name="services",
            page_objective="List services.",
            target_audience="SMB.",
            blocks=[PageDesignBlock(
                name="intro", intent="Intro.",
                body_copy="Services overview.",
            )],
            visual_style_notes="Brand-aligned.",
            acceptance_criteria=["All services listed."],
        ),
        created_at=_now(),
    )
    md = render_markdown_atlas_handoff(handoff)
    assert "Page design brief" in md
    assert "services" in md
    assert "Services overview." in md


def test_renderer_is_pure() -> None:
    handoff = _landing_handoff()
    assert render_markdown_atlas_handoff(handoff) == render_markdown_atlas_handoff(handoff)
