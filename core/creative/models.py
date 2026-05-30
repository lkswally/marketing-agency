"""Pydantic models for the Creative Factory Pack (MKT-3C).

Contract: ``creative-pack.v1``.

The pack is a higher-level artifact than the Markdown deliverable —
it carries per-asset state derived from the Approval Pack (MKT-3B),
A/B variants for hooks / CTAs / subjects / headlines, a per-piece
publishing calendar with concrete dates, and a per-piece checklist.

No asset is ever in a "published" state. The terminal positive state
is ``READY_FOR_PUBLISH``, which means "approved for shipping but not
yet shipped".
"""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import Field, field_validator

from core.domain.base import DomainModel, new_id, validate_slug
from core.domain.enums import ChannelType

CREATIVE_PACK_VERSION = "creative-pack.v1"


# ============ Enums ============

class CreativeAssetState(StrEnum):
    """Per-asset lifecycle.

    Derivation rules (applied by :class:`CreativeFactory`):

    +------------------------------------------------+-------------------------+
    | Condition                                      | State                   |
    +================================================+=========================+
    | ApprovalPack ``blocks_publish=True``           | ``BLOCKED``             |
    | ApprovalPack ``APPROVED`` AND not blocking     | ``READY_FOR_PUBLISH``   |
    | overall_severity in {risky, unsafe}, not appr. | ``NEEDS_REVIEW``        |
    | otherwise                                      | ``DRAFT``               |
    +------------------------------------------------+-------------------------+

    ``PUBLISHED`` is intentionally absent. It is a runtime concept that
    belongs to a future publisher block (post-MKT-MCP-8).
    """

    DRAFT = "draft"
    NEEDS_REVIEW = "needs_review"
    READY_FOR_PUBLISH = "ready_for_publish"
    BLOCKED = "blocked"


class CreativeAssetKind(StrEnum):
    """Type discriminator for assets inside the pack."""

    SOCIAL_POST = "social_post"
    EMAIL = "email"
    REELS_SCRIPT = "reels_script"
    FLYER_COPY = "flyer_copy"
    IMAGE_PROMPT = "image_prompt"


class VariantAngle(StrEnum):
    """Editorial angle for a hook variant."""

    INFORMATIONAL = "informational"
    CURIOSITY = "curiosity"
    CONTRAST = "contrast"
    DATA = "data"


class CTAStyle(StrEnum):
    """Style of a call-to-action variant."""

    DIRECT = "direct"
    SOFT = "soft"
    LOW_FRICTION = "low_friction"
    CHALLENGE = "challenge"


class SubjectStyle(StrEnum):
    """Style of an email subject line variant."""

    BENEFIT = "benefit"
    CURIOSITY = "curiosity"
    QUESTION = "question"
    DIRECT = "direct"


class HeadlineStyle(StrEnum):
    """Style of a headline / flyer variant."""

    BENEFIT = "benefit"
    QUESTION = "question"
    CONTRAST = "contrast"
    POV = "point_of_view"


class FlyerFormat(StrEnum):
    """Standard flyer aspect ratios."""

    SQUARE = "1:1"
    PORTRAIT_4_5 = "4:5"
    STORY_9_16 = "9:16"
    LANDSCAPE_16_9 = "16:9"


# ============ Variant sub-models ============

class HookVariant(DomainModel):
    variant_id: str = Field(min_length=1, max_length=8)
    text: str = Field(min_length=1, max_length=400)
    angle: VariantAngle


class CTAVariant(DomainModel):
    variant_id: str = Field(min_length=1, max_length=8)
    text: str = Field(min_length=1, max_length=120)
    style: CTAStyle


class SubjectLineVariant(DomainModel):
    variant_id: str = Field(min_length=1, max_length=8)
    subject: str = Field(min_length=1, max_length=80)
    preview_text: str = Field(min_length=1, max_length=140)
    style: SubjectStyle


class HeadlineVariant(DomainModel):
    variant_id: str = Field(min_length=1, max_length=8)
    text: str = Field(min_length=1, max_length=200)
    style: HeadlineStyle


# ============ Per-asset checklist ============

class AssetChecklistItem(DomainModel):
    item_id: str = Field(default_factory=new_id)
    title: str = Field(min_length=1, max_length=400)
    severity: Literal["blocker", "must", "should"] = "must"
    notes: str | None = None


# ============ Asset models ============

class SocialPostAsset(DomainModel):
    asset_id: str = Field(default_factory=new_id)
    kind: Literal["social_post"] = "social_post"
    channel: ChannelType
    hook_variants: list[HookVariant] = Field(min_length=1, max_length=4)
    body: str = Field(min_length=1)
    cta_variants: list[CTAVariant] = Field(min_length=1, max_length=4)
    caption_cross_post: str | None = None
    hashtags: list[str] = Field(default_factory=list)
    state: CreativeAssetState = CreativeAssetState.DRAFT
    checklist: list[AssetChecklistItem] = Field(default_factory=list)
    scheduled_for: date | None = None


class EmailAsset(DomainModel):
    asset_id: str = Field(default_factory=new_id)
    kind: Literal["email"] = "email"
    step: int = Field(ge=1)
    subject_line_variants: list[SubjectLineVariant] = Field(min_length=1, max_length=4)
    body: str = Field(min_length=1)
    cta: str = Field(min_length=1, max_length=120)
    send_after_days: int = Field(ge=0)
    state: CreativeAssetState = CreativeAssetState.DRAFT
    checklist: list[AssetChecklistItem] = Field(default_factory=list)
    scheduled_for: date | None = None


class ReelsAsset(DomainModel):
    asset_id: str = Field(default_factory=new_id)
    kind: Literal["reels_script"] = "reels_script"
    title: str = Field(min_length=1, max_length=200)
    hook_variants: list[HookVariant] = Field(min_length=1, max_length=4)
    beats: list[str] = Field(min_length=1)
    voiceover_lines: list[str] = Field(default_factory=list)
    on_screen_text: list[str] = Field(default_factory=list)
    cta: str = Field(min_length=1, max_length=120)
    target_duration_s: int = Field(ge=10, le=120)
    state: CreativeAssetState = CreativeAssetState.DRAFT
    checklist: list[AssetChecklistItem] = Field(default_factory=list)
    scheduled_for: date | None = None


class FlyerAsset(DomainModel):
    asset_id: str = Field(default_factory=new_id)
    kind: Literal["flyer_copy"] = "flyer_copy"
    format: FlyerFormat
    headline_variants: list[HeadlineVariant] = Field(min_length=1, max_length=4)
    subhead: str = Field(min_length=1, max_length=300)
    body: str = Field(min_length=1)
    cta: str = Field(min_length=1, max_length=120)
    state: CreativeAssetState = CreativeAssetState.DRAFT
    checklist: list[AssetChecklistItem] = Field(default_factory=list)
    scheduled_for: date | None = None


class ImagePromptAsset(DomainModel):
    asset_id: str = Field(default_factory=new_id)
    kind: Literal["image_prompt"] = "image_prompt"
    title: str = Field(min_length=1, max_length=200)
    intended_use: str = Field(min_length=1, max_length=200)
    prompt_text: str = Field(min_length=1)
    negative_prompt: str | None = None
    aspect_ratio: str = Field(min_length=1, max_length=8)
    style_notes: str | None = None
    palette_hint: list[str] = Field(default_factory=list)
    accessibility_notes: list[str] = Field(default_factory=list)
    state: CreativeAssetState = CreativeAssetState.DRAFT
    checklist: list[AssetChecklistItem] = Field(default_factory=list)


# ============ Calendar ============

class CalendarEntry(DomainModel):
    entry_id: str = Field(default_factory=new_id)
    asset_id: str
    asset_kind: CreativeAssetKind
    week: int = Field(ge=1, le=52)
    scheduled_for: date
    channel: ChannelType | None = None
    cadence_note: str | None = None


# ============ Top-level ============

class CreativeAssetPack(DomainModel):
    """The full creative output for one campaign cycle."""

    contract_version: Literal["creative-pack.v1"] = CREATIVE_PACK_VERSION
    pack_id: str = Field(default_factory=new_id)
    client_slug: Annotated[str, Field(min_length=2, max_length=64)]
    report_id: str = Field(min_length=1)
    report_contract_version: str = Field(min_length=1)
    approval_pack_id: str | None = None
    approval_pack_contract_version: str | None = None
    derived_overall_state: CreativeAssetState
    blocks_publish: bool = False
    social_posts: list[SocialPostAsset] = Field(default_factory=list)
    emails: list[EmailAsset] = Field(default_factory=list)
    reels: list[ReelsAsset] = Field(default_factory=list)
    flyers: list[FlyerAsset] = Field(default_factory=list)
    image_prompts: list[ImagePromptAsset] = Field(default_factory=list)
    calendar: list[CalendarEntry] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
    rule_set_id: str | None = None  # identifies the factory template version used

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
    def total_assets(self) -> int:
        return (
            len(self.social_posts)
            + len(self.emails)
            + len(self.reels)
            + len(self.flyers)
            + len(self.image_prompts)
        )

    def count_by_state(self) -> dict[str, int]:
        counts = {s.value: 0 for s in CreativeAssetState}
        for asset_list in (
            self.social_posts,
            self.emails,
            self.reels,
            self.flyers,
            self.image_prompts,
        ):
            for a in asset_list:
                counts[a.state.value] += 1
        return counts

    def count_by_kind(self) -> dict[str, int]:
        return {
            "social_post": len(self.social_posts),
            "email": len(self.emails),
            "reels_script": len(self.reels),
            "flyer_copy": len(self.flyers),
            "image_prompt": len(self.image_prompts),
        }
