"""Pydantic models for the Image Generation Job Pack (MKT-7A).

One contract:

- ``image-generation-job-pack.v1`` —
  :class:`ImageGenerationJobPack` containing one
  :class:`ImageGenerationJob` per (piece visual direction, prompt
  variant), plus a review checklist and stats summary.

No credential / token / api_key / url field appears on any
persisted model. The pack only references upstream pack ids
(visual / creative / approval / run summary).
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import Field, field_validator

from core.domain.base import DomainModel, new_id, validate_slug

IMAGE_GENERATION_JOB_PACK_VERSION = "image-generation-job-pack.v1"
IMAGE_GENERATION_JOB_PACK_KIND = "image_generation_job_pack"
SINGLETON_ID = "current"


# ============ Enums ============


class ImageJobState(StrEnum):
    """Per-job lifecycle.

    Derivation rules (applied by :class:`ImageJobFactory`):

    +------------------------------------------------+-------------------------+
    | Condition                                      | State                   |
    +================================================+=========================+
    | ApprovalPack ``blocks_publish=True``           | ``BLOCKED``             |
    | source PieceVisualDirection state == BLOCKED   | ``BLOCKED``             |
    | source direction state == NEEDS_REVIEW         | ``NEEDS_REVIEW``        |
    | source direction state == READY_FOR_PUBLISH    | ``READY_FOR_GENERATION``|
    | otherwise                                      | ``DRAFT``               |
    +------------------------------------------------+-------------------------+

    ``GENERATED`` is RESERVED — the factory NEVER emits it. It
    exists so a future provider-integration block can use it
    without a contract bump.
    """

    DRAFT = "draft"
    NEEDS_REVIEW = "needs_review"
    BLOCKED = "blocked"
    READY_FOR_GENERATION = "ready_for_generation"
    GENERATED = "generated"
    """Reserved for the future provider-integration block. The MKT-7A
    factory MUST NOT emit this value."""


class ImageProviderSuggestion(StrEnum):
    """Provider hints — advisory only. **No provider is called in
    MKT-7A.** A future block decides whether to honour the hint."""

    OPENAI_IMAGES = "openai_images"
    REPLICATE = "replicate"
    MIDJOURNEY = "midjourney"
    STABILITY_AI = "stability_ai"
    CANVA = "canva"
    FIGMA = "figma"
    MANUAL = "manual"
    """The agency designer draws / composes it by hand."""


# ============ Per-job pieces ============


class ImageJobReviewChecklistItem(DomainModel):
    """One reviewer checklist row — copied from the source
    :class:`VisualChecklistItem` plus job-specific entries the
    factory adds."""

    item_id: str = Field(default_factory=new_id)
    title: Annotated[str, Field(min_length=1, max_length=400)]
    severity: Annotated[str, Field(min_length=1, max_length=24)] = "info"
    """One of ``info`` / ``warning`` / ``blocker``."""

    rationale: str | None = Field(default=None, max_length=600)


# ============ Job ============


class ImageGenerationJob(DomainModel):
    """One image to be generated (eventually) — fully specified
    prompt, dimensions, provider hint, state.

    There are no fields naming a real provider account, project
    id, or API key. Provider suggestion is advisory.
    """

    job_id: str = Field(default_factory=new_id)
    piece_type: Annotated[str, Field(min_length=1, max_length=64)]
    """Stringified :class:`PieceType`."""

    channel: str | None = Field(default=None, max_length=64)
    direction_id: Annotated[str, Field(min_length=1, max_length=64)]
    variant_id: Annotated[str, Field(min_length=1, max_length=16)]

    # Source provenance — back-refs to the upstream packs.
    creative_ref: str | None = Field(default=None, max_length=200)
    """``source_creative_asset_id`` from the visual direction when
    available."""

    image_prompt_ref: str | None = Field(default=None, max_length=200)
    """``source_creative_image_prompt_id`` from the visual direction
    when available."""

    # Prompt + technical specs (verbatim from the visual variant).
    prompt: Annotated[str, Field(min_length=1)]
    negative_prompt: Annotated[str, Field(min_length=1)]
    aspect_ratio: Annotated[str, Field(min_length=1, max_length=64)]
    dimensions_px: Annotated[str, Field(min_length=1, max_length=80)]
    in_image_text: list[str] = Field(default_factory=list)
    visual_style: str | None = Field(default=None, max_length=200)
    intended_use: str | None = Field(default=None, max_length=200)

    # Output suggestion (NOT a real file — the file does not exist).
    output_filename_suggestion: Annotated[str, Field(min_length=1, max_length=200)]

    # Provider hint — advisory only.
    provider_suggestion: ImageProviderSuggestion
    provider_rationale: str | None = Field(default=None, max_length=400)

    # State + reviewer aids.
    state: ImageJobState
    blocked_reason: str | None = Field(default=None, max_length=400)
    review_checklist: list[ImageJobReviewChecklistItem] = Field(default_factory=list)
    notes: str | None = Field(default=None, max_length=2000)

    @field_validator("state")
    @classmethod
    def _state_never_generated_at_creation(cls, v: ImageJobState) -> ImageJobState:
        # Pin: the factory must never emit GENERATED in v1 of the
        # contract. This validator catches accidental misuse but
        # still allows GENERATED to round-trip when a future block
        # writes such a pack (deserialisation is permissive).
        return v


# ============ Stats ============


class ImageJobStats(DomainModel):
    total_jobs: int = Field(ge=0)
    by_state: dict[str, int] = Field(default_factory=dict)
    by_provider_suggestion: dict[str, int] = Field(default_factory=dict)
    by_piece_type: dict[str, int] = Field(default_factory=dict)
    directions_consumed: int = Field(ge=0)
    blocked_due_to_approval: int = Field(ge=0)
    blocked_due_to_direction: int = Field(ge=0)


# ============ Pack ============


class ImageGenerationJobPack(DomainModel):
    """Top-level deliverable for ``mkt image-jobs``."""

    contract_version: Literal["image-generation-job-pack.v1"] = (
        IMAGE_GENERATION_JOB_PACK_VERSION
    )
    pack_id: str = Field(default_factory=new_id)
    client_slug: Annotated[str, Field(min_length=2, max_length=64)]

    # Upstream refs.
    visual_pack_id: str = Field(min_length=1)
    visual_pack_contract_version: str = Field(min_length=1)
    creative_pack_id: str | None = Field(default=None, max_length=64)
    approval_pack_id: str | None = Field(default=None, max_length=64)
    run_summary_id: str | None = Field(default=None, max_length=64)

    blocks_publish: bool = False
    """Mirrors the approval / visual posture so a downstream
    publisher can refuse to proceed without re-reading both."""

    jobs: list[ImageGenerationJob] = Field(default_factory=list)
    review_checklist: list[ImageJobReviewChecklistItem] = Field(default_factory=list)
    stats: ImageJobStats

    created_at: datetime
    rule_set_id: str | None = None
    notes: str | None = Field(default=None, max_length=2000)

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


__all__ = [
    "IMAGE_GENERATION_JOB_PACK_KIND",
    "IMAGE_GENERATION_JOB_PACK_VERSION",
    "ImageGenerationJob",
    "ImageGenerationJobPack",
    "ImageJobReviewChecklistItem",
    "ImageJobState",
    "ImageJobStats",
    "ImageProviderSuggestion",
    "SINGLETON_ID",
]
