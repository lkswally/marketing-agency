"""Pydantic models for the Visual Direction Pack (MKT-3D).

Contract: ``visual-direction-pack.v1``.

The pack is a richer companion to the Creative Asset Pack (MKT-3C). Where
the creative pack carries copy variants per asset, the visual direction
pack carries per-channel visual specifications, structured prompt variants
with 12 explicit fields per the user spec, a campaign-wide style guide,
visual risks, and a checklist for designers.

Reuses :class:`CreativeAssetState` from MKT-3C — the ``PUBLISHED`` state
intentionally does not exist anywhere in the codebase.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import Field, field_validator

from core.creative.models import CreativeAssetState
from core.domain.base import DomainModel, new_id, validate_slug
from core.domain.enums import ChannelType

from .specs import PieceType, PieceTypeSpec

VISUAL_DIRECTION_PACK_VERSION = "visual-direction-pack.v1"


# ============ Sub-models ============

class VisualPromptVariant(DomainModel):
    """One A/B variant for a single piece type.

    Carries the 12 explicit fields the user spec required (objective,
    audience, style, tone, composition, in-image text, elements, colors,
    aspect ratio, restrictions, negative prompt, intended use).
    ``full_prompt_text`` is the assembled ready-to-paste string.
    """

    variant_id: str = Field(min_length=1, max_length=8)

    # The 12 required fields:
    objective: str = Field(min_length=1, max_length=500)
    target_audience: str = Field(min_length=1, max_length=300)
    visual_style: str = Field(min_length=1, max_length=200)
    emotional_tone: str = Field(min_length=1, max_length=200)
    composition: str = Field(min_length=1, max_length=300)
    in_image_text: list[str] = Field(default_factory=list)
    visual_elements: list[str] = Field(default_factory=list)
    suggested_colors: list[str] = Field(default_factory=list)
    aspect_ratio: str = Field(min_length=1, max_length=64)
    restrictions: list[str] = Field(default_factory=list)
    negative_prompt: str = Field(min_length=1)
    intended_use: str = Field(min_length=1, max_length=200)

    # Ready-to-paste:
    full_prompt_text: str = Field(min_length=1)


class VisualStyleGuide(DomainModel):
    """Campaign-wide style guide.

    Lives once per pack — not per piece. Same visual identity across every
    asset in a campaign cycle.
    """

    palette_primary: list[str] = Field(default_factory=list)
    palette_accent: list[str] = Field(default_factory=list)
    typography_headline: str
    typography_body: str
    typography_principles: list[str] = Field(default_factory=list)
    overall_mood: str
    visual_motifs: list[str] = Field(default_factory=list)
    composition_principles: list[str] = Field(default_factory=list)
    do_use: list[str] = Field(default_factory=list)
    do_not_use: list[str] = Field(default_factory=list)


class VisualChecklistItem(DomainModel):
    """One line in the per-piece or pack-wide visual checklist."""

    item_id: str = Field(default_factory=new_id)
    title: str = Field(min_length=1, max_length=400)
    severity: Literal["blocker", "must", "should"] = "must"
    category: Literal[
        "composition",
        "typography",
        "accessibility",
        "brand",
        "format",
        "claims",
        "operational",
    ]
    notes: str | None = None


class VisualRisk(DomainModel):
    """A campaign-level visual risk the designer should avoid."""

    risk_id: str = Field(default_factory=new_id)
    category: Literal[
        "stock_cliche",
        "ip_violation",
        "brand_voice_mismatch",
        "accessibility",
        "platform_policy",
        "ai_artifacts",
        "off_brand_palette",
    ]
    severity: Literal["low", "medium", "high"] = "medium"
    description: str = Field(min_length=1, max_length=500)
    mitigation: str | None = None


class PieceVisualDirection(DomainModel):
    """The visual direction for one piece type."""

    direction_id: str = Field(default_factory=new_id)
    piece_type: PieceType
    channel: ChannelType | None = None
    spec: PieceTypeSpec
    prompt_variants: list[VisualPromptVariant] = Field(min_length=1, max_length=4)
    state: CreativeAssetState = CreativeAssetState.DRAFT
    checklist: list[VisualChecklistItem] = Field(default_factory=list)
    source_creative_image_prompt_id: str | None = None
    source_creative_asset_id: str | None = None
    scheduled_for: date | None = None


# ============ Top-level ============

class VisualDirectionPack(DomainModel):
    """The complete output of the Visual Direction & Image Prompt Pack."""

    contract_version: Literal["visual-direction-pack.v1"] = VISUAL_DIRECTION_PACK_VERSION
    pack_id: str = Field(default_factory=new_id)
    client_slug: Annotated[str, Field(min_length=2, max_length=64)]

    # Provenance references:
    report_id: str = Field(min_length=1)
    report_contract_version: str = Field(min_length=1)
    approval_pack_id: str | None = None
    approval_pack_contract_version: str | None = None
    creative_pack_id: str | None = None
    creative_pack_contract_version: str | None = None

    # State + policy:
    derived_overall_state: CreativeAssetState
    blocks_publish: bool = False

    # Content:
    style_guide: VisualStyleGuide
    directions: list[PieceVisualDirection] = Field(default_factory=list)
    global_visual_risks: list[VisualRisk] = Field(default_factory=list)
    global_checklist: list[VisualChecklistItem] = Field(default_factory=list)

    # Lifecycle:
    created_at: datetime
    updated_at: datetime
    rule_set_id: str | None = None

    @field_validator("client_slug")
    @classmethod
    def _slug(cls, v: str) -> str:
        return validate_slug(v)

    @field_validator("created_at", "updated_at")
    @classmethod
    def _tz(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("timestamps must be timezone-aware (UTC)")
        return v

    # -------- helpers --------

    @property
    def total_directions(self) -> int:
        return len(self.directions)

    @property
    def total_prompt_variants(self) -> int:
        return sum(len(d.prompt_variants) for d in self.directions)

    def count_by_state(self) -> dict[str, int]:
        counts = {s.value: 0 for s in CreativeAssetState}
        for d in self.directions:
            counts[d.state.value] += 1
        return counts

    def count_by_piece_type(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for d in self.directions:
            out[d.piece_type.value] = out.get(d.piece_type.value, 0) + 1
        return out

    def count_risks_by_severity(self) -> dict[str, int]:
        counts = {"low": 0, "medium": 0, "high": 0}
        for r in self.global_visual_risks:
            counts[r.severity] += 1
        return counts
