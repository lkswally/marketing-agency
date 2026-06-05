"""Pydantic models for the MKT-8A ATLAS Bridge Contract.

Four versioned contracts:

- ``landing-brief.v1``       — :class:`LandingBrief`
- ``branding-brief.v1``      — :class:`BrandingBrief`
- ``page-design-brief.v1``   — :class:`PageDesignBrief`
- ``atlas-handoff-brief.v1`` — :class:`AtlasHandoffBrief`
  envelope wrapping exactly one of the above.

No credential / token / api_key field. No URL field is required;
optional URL fields exist only for *reference* (existing
inspiration sites the agency wants ATLAS to evaluate). The
handoff never embeds binary assets — only string references.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator

from core.domain.base import DomainModel, new_id, validate_slug

LANDING_BRIEF_VERSION = "landing-brief.v1"
BRANDING_BRIEF_VERSION = "branding-brief.v1"
PAGE_DESIGN_BRIEF_VERSION = "page-design-brief.v1"

ATLAS_HANDOFF_BRIEF_VERSION = "atlas-handoff-brief.v1"
ATLAS_HANDOFF_BRIEF_KIND = "atlas_handoff_brief"

SINGLETON_ID = "current"


# ============ Enums ============


class AtlasHandoffKind(StrEnum):
    """Which kind of work the handoff describes."""

    LANDING = "landing"
    BRANDING = "branding"
    PAGE_DESIGN = "page_design"


# ============ Shared shapes ============


class HandoffAssetReference(DomainModel):
    """One asset / file the handoff references.

    Crucially, this is a TEXT reference — the operator looks up
    the asset by id, kind or filename hint. The handoff never
    embeds binary data.
    """

    asset_id: str | None = Field(default=None, max_length=64)
    asset_kind: Annotated[str, Field(min_length=1, max_length=64)]
    """Free-form (``"hero_image"``, ``"logo"``, ``"copy_doc"``,
    ``"image_job"``, ``"creative"``, etc.)."""

    label: str | None = Field(default=None, max_length=200)
    filename_hint: str | None = Field(default=None, max_length=200)
    notes: str | None = Field(default=None, max_length=400)


class SEOGEOTargets(DomainModel):
    """SEO + GEO targets the page should hit."""

    primary_keyword: str | None = Field(default=None, max_length=120)
    secondary_keywords: list[str] = Field(default_factory=list)
    target_locations: list[str] = Field(default_factory=list)
    """Free-form (``"Buenos Aires"``, ``"AR-C"``, ``"Florida, US"``,
    ``"global"``)."""

    title_tag_hint: str | None = Field(default=None, max_length=160)
    meta_description_hint: str | None = Field(default=None, max_length=320)
    schema_org_types: list[str] = Field(default_factory=list)
    """``"LocalBusiness"``, ``"Organization"``, ``"Product"`` etc."""


# ============ LandingBrief ============


class LandingSection(DomainModel):
    """One section in the landing page."""

    section_id: str = Field(default_factory=new_id)
    name: Annotated[str, Field(min_length=1, max_length=64)]
    """``"hero"`` / ``"problem"`` / ``"solution"`` / ``"social_proof"``
    / ``"pricing"`` / ``"faq"`` / ``"cta"`` etc."""

    objective: Annotated[str, Field(min_length=1, max_length=400)]
    body_copy: Annotated[str, Field(min_length=1, max_length=4000)]
    """Approved copy — verbatim text the section should display.
    Named ``body_copy`` (not ``copy``) to avoid shadowing
    :meth:`pydantic.BaseModel.copy`."""

    visual_notes: str | None = Field(default=None, max_length=600)
    assets: list[HandoffAssetReference] = Field(default_factory=list)
    cta_label: str | None = Field(default=None, max_length=64)
    cta_target: str | None = Field(default=None, max_length=240)
    """Where the CTA should send the user (text description, not a
    URL the operator has to honour — ATLAS may rewrite)."""


class LandingBrief(DomainModel):
    """A landing-page handoff brief."""

    contract_version: Literal["landing-brief.v1"] = LANDING_BRIEF_VERSION
    brief_id: str = Field(default_factory=new_id)

    page_objective: Annotated[str, Field(min_length=1, max_length=400)]
    """Top-of-funnel? Mid-funnel? Lead-capture? Direct purchase?"""

    target_audience: Annotated[str, Field(min_length=1, max_length=400)]
    primary_cta_label: Annotated[str, Field(min_length=1, max_length=64)]
    secondary_cta_label: str | None = Field(default=None, max_length=64)

    sections: list[LandingSection] = Field(min_length=1, max_length=20)
    visual_style_notes: Annotated[str, Field(min_length=1, max_length=2000)]
    reference_links: list[str] = Field(default_factory=list)
    """Optional URLs the agency wants ATLAS to evaluate as visual
    inspiration. The handoff itself does not fetch them."""

    seo_geo: SEOGEOTargets = Field(default_factory=SEOGEOTargets)
    constraints: list[str] = Field(default_factory=list)
    acceptance_criteria: list[str] = Field(min_length=1, max_length=20)


# ============ BrandingBrief ============


class BrandingTokenSet(DomainModel):
    """Token set the brand identity should produce / honour."""

    palette_primary: list[str] = Field(default_factory=list)
    """Free-form (``"#0F172A"``, ``"slate-950"``, ``"ink"``)."""

    palette_accent: list[str] = Field(default_factory=list)
    typography_principles: list[str] = Field(default_factory=list)
    voice_tone_principles: list[str] = Field(default_factory=list)
    logo_usage_principles: list[str] = Field(default_factory=list)
    do_use: list[str] = Field(default_factory=list)
    do_not_use: list[str] = Field(default_factory=list)


class BrandingBrief(DomainModel):
    """A branding (visual identity) handoff brief."""

    contract_version: Literal["branding-brief.v1"] = BRANDING_BRIEF_VERSION
    brief_id: str = Field(default_factory=new_id)

    brand_objective: Annotated[str, Field(min_length=1, max_length=400)]
    target_audience: Annotated[str, Field(min_length=1, max_length=400)]
    positioning_statement: Annotated[str, Field(min_length=1, max_length=600)]
    competitor_landscape: str | None = Field(default=None, max_length=1000)

    tokens: BrandingTokenSet = Field(default_factory=BrandingTokenSet)
    deliverables_requested: list[str] = Field(min_length=1, max_length=20)
    """``"logo_primary"`` / ``"logo_compact"`` / ``"color_palette"``
    / ``"typography_system"`` / ``"brand_voice_guide"`` etc."""

    reference_links: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    acceptance_criteria: list[str] = Field(min_length=1, max_length=20)


# ============ PageDesignBrief ============


class PageDesignBlock(DomainModel):
    """One block inside a generic page (not a landing)."""

    block_id: str = Field(default_factory=new_id)
    name: Annotated[str, Field(min_length=1, max_length=64)]
    intent: Annotated[str, Field(min_length=1, max_length=400)]
    body_copy: Annotated[str, Field(min_length=1, max_length=4000)]
    visual_notes: str | None = Field(default=None, max_length=600)
    assets: list[HandoffAssetReference] = Field(default_factory=list)


class PageDesignBrief(DomainModel):
    """Generic page (about / services / pricing / case study) brief."""

    contract_version: Literal["page-design-brief.v1"] = PAGE_DESIGN_BRIEF_VERSION
    brief_id: str = Field(default_factory=new_id)

    page_name: Annotated[str, Field(min_length=1, max_length=64)]
    """``"about"`` / ``"services"`` / ``"pricing"`` /
    ``"case_study_acme"`` etc."""

    page_objective: Annotated[str, Field(min_length=1, max_length=400)]
    target_audience: Annotated[str, Field(min_length=1, max_length=400)]
    blocks: list[PageDesignBlock] = Field(min_length=1, max_length=30)
    visual_style_notes: Annotated[str, Field(min_length=1, max_length=2000)]
    reference_links: list[str] = Field(default_factory=list)
    seo_geo: SEOGEOTargets = Field(default_factory=SEOGEOTargets)
    constraints: list[str] = Field(default_factory=list)
    acceptance_criteria: list[str] = Field(min_length=1, max_length=20)


# ============ Envelope ============


class AtlasHandoffBrief(DomainModel):
    """Envelope that wraps exactly one of the three briefs above.

    Persisted under ``atlas_handoff_brief/current.json``. Operator
    copies / pastes into whatever ATLAS workflow they use today —
    this side never reaches into ATLAS.
    """

    contract_version: Literal["atlas-handoff-brief.v1"] = (
        ATLAS_HANDOFF_BRIEF_VERSION
    )
    handoff_id: str = Field(default_factory=new_id)
    client_slug: Annotated[str, Field(min_length=2, max_length=64)]

    kind: AtlasHandoffKind
    landing_brief: LandingBrief | None = None
    branding_brief: BrandingBrief | None = None
    page_design_brief: PageDesignBrief | None = None

    # Provenance — back-refs into MARKETING-AGENCY-OS packs.
    strategy_report_id: str | None = Field(default=None, max_length=64)
    creative_pack_id: str | None = Field(default=None, max_length=64)
    visual_pack_id: str | None = Field(default=None, max_length=64)
    approval_pack_id: str | None = Field(default=None, max_length=64)
    image_job_pack_id: str | None = Field(default=None, max_length=64)

    blocks_publish: bool = False
    """Mirrors the approval / visual posture so ATLAS knows
    whether the upstream campaign is OK to ship."""

    notes: str | None = Field(default=None, max_length=2000)
    created_at: datetime
    rule_set_id: str | None = None

    @field_validator("client_slug")
    @classmethod
    def _slug(cls, v: str) -> str:
        return validate_slug(v)

    @field_validator("created_at")
    @classmethod
    def _tz(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("created_at must be timezone-aware (UTC)")
        return v

    @model_validator(mode="after")
    def _exactly_one_brief(self) -> AtlasHandoffBrief:
        present = [
            ("landing_brief", self.landing_brief),
            ("branding_brief", self.branding_brief),
            ("page_design_brief", self.page_design_brief),
        ]
        non_none = [name for name, value in present if value is not None]
        if len(non_none) != 1:
            raise ValueError(
                "AtlasHandoffBrief must carry exactly one of "
                "{landing_brief, branding_brief, page_design_brief}; "
                f"got {non_none}"
            )
        expected = {
            AtlasHandoffKind.LANDING: "landing_brief",
            AtlasHandoffKind.BRANDING: "branding_brief",
            AtlasHandoffKind.PAGE_DESIGN: "page_design_brief",
        }[self.kind]
        if non_none[0] != expected:
            raise ValueError(
                f"kind={self.kind.value!r} requires {expected!r} to be set "
                f"(got {non_none[0]!r})"
            )
        return self


__all__ = [
    "ATLAS_HANDOFF_BRIEF_KIND",
    "ATLAS_HANDOFF_BRIEF_VERSION",
    "AtlasHandoffBrief",
    "AtlasHandoffKind",
    "BRANDING_BRIEF_VERSION",
    "BrandingBrief",
    "BrandingTokenSet",
    "HandoffAssetReference",
    "LANDING_BRIEF_VERSION",
    "LandingBrief",
    "LandingSection",
    "PAGE_DESIGN_BRIEF_VERSION",
    "PageDesignBlock",
    "PageDesignBrief",
    "SEOGEOTargets",
    "SINGLETON_ID",
]
