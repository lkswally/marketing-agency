"""Pydantic models for MKT-7B.

Contract: ``image-provider-recommendation-pack.v1``.

No credential / token / api_key / url field appears on any
persisted model. The dry-run receipt holds a simulated request
*shape* — never a real URL, never a real account / customer id.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import Field, field_validator

from core.domain.base import DomainModel, new_id, validate_slug

IMAGE_PROVIDER_RECOMMENDATION_PACK_VERSION = (
    "image-provider-recommendation-pack.v1"
)
IMAGE_PROVIDER_RECOMMENDATION_PACK_KIND = "image_provider_recommendation_pack"
SINGLETON_ID = "current"


# ============ Enums ============


class ProviderDryRunStatus(StrEnum):
    """Status of a dry-run preview.

    Locked to ``dry_run`` in v1 of the contract — no real call
    is ever made. A future provider integration block (P-7A.6 /
    MKT-7C) will add real statuses with a new contract version.
    """

    DRY_RUN = "dry_run"
    SKIPPED_BLOCKED = "skipped_blocked"
    SKIPPED_MANUAL = "skipped_manual"


# ============ Per-criterion score ============


class ProviderCriterionScore(DomainModel):
    """One (provider, criterion) cell — 0..5 score + optional note."""

    criterion: Annotated[str, Field(min_length=1, max_length=64)]
    score: int = Field(ge=0, le=5)
    note: str | None = Field(default=None, max_length=400)


# ============ Per-provider snapshot ============


class ProviderEvaluation(DomainModel):
    """Per-provider rollup for the report — scores + meta facts."""

    provider: Annotated[str, Field(min_length=1, max_length=24)]
    scores: list[ProviderCriterionScore] = Field(default_factory=list)
    estimated_cost_usd_per_image: float = Field(ge=0.0)
    """Static estimate at the provider's default resolution. Real
    cost depends on dimensions, variants, and provider pricing
    tier — see P-7B.2 for per-job cost estimation."""

    commercial_use_ok: bool
    credentials_required: list[str] = Field(default_factory=list)
    """Names of env vars the operator would need to set to actually
    call this provider. The block does NOT read them."""

    supported_aspect_ratios: list[str] = Field(default_factory=list)
    supported_formats: list[str] = Field(default_factory=list)
    integration_difficulty: Annotated[str, Field(min_length=1, max_length=16)]
    """One of ``low`` / ``medium`` / ``high``."""

    external_dependency_risk: Annotated[str, Field(min_length=1, max_length=16)]
    """One of ``low`` / ``medium`` / ``high``."""

    notes: str | None = Field(default=None, max_length=600)


# ============ Per-job recommendation ============


class ImageProviderRecommendation(DomainModel):
    """One job → recommended provider + alternatives + rationale."""

    job_id: Annotated[str, Field(min_length=1, max_length=64)]
    piece_type: Annotated[str, Field(min_length=1, max_length=64)]
    job_state: Annotated[str, Field(min_length=1, max_length=32)]
    job_provider_suggestion: Annotated[str, Field(min_length=1, max_length=24)]
    """The provider hint the MKT-7A factory wrote on the job.
    The planner may agree or override."""

    recommended_provider: Annotated[str, Field(min_length=1, max_length=24)]
    recommended_score: float = Field(ge=0.0)
    alternative_providers: list[str] = Field(default_factory=list)
    fallback_provider: Annotated[str, Field(min_length=1, max_length=24)] = "manual"

    rationale: Annotated[str, Field(min_length=1, max_length=600)]
    risk_notes: list[str] = Field(default_factory=list)
    estimated_cost_usd: float = Field(ge=0.0)


# ============ Dry-run receipt ============


class ProviderDryRunReceipt(DomainModel):
    """Simulated request preview for one job.

    Carries the *shape* of the request the operator would
    eventually send to the provider — model name, prompt length,
    aspect ratio, dimensions. NEVER carries a real URL,
    credential, customer id, or webhook.

    ``simulated_output_filename`` is the same value the MKT-7A
    factory wrote on the source job; it is a TEXT suggestion,
    not a real file path that exists on disk.
    """

    job_id: Annotated[str, Field(min_length=1, max_length=64)]
    provider: Annotated[str, Field(min_length=1, max_length=24)]
    status: ProviderDryRunStatus
    reason: str | None = Field(default=None, max_length=400)
    """Set when status is one of the skipped values."""

    model_hint: Annotated[str, Field(min_length=1, max_length=64)]
    """Model name the integration would use (e.g.
    ``dall-e-3`` for OpenAI Images). Static per provider."""

    prompt_length_chars: int = Field(ge=0)
    aspect_ratio: Annotated[str, Field(min_length=1, max_length=64)]
    dimensions_px: Annotated[str, Field(min_length=1, max_length=80)]
    simulated_output_filename: Annotated[str, Field(min_length=1, max_length=200)]
    notes: str | None = Field(default=None, max_length=400)


# ============ Stats ============


class ImageProviderRecommendationStats(DomainModel):
    total_jobs: int = Field(ge=0)
    by_recommended_provider: dict[str, int] = Field(default_factory=dict)
    by_dry_run_status: dict[str, int] = Field(default_factory=dict)
    overrode_job_suggestion: int = Field(ge=0)
    skipped_blocked: int = Field(ge=0)
    skipped_manual: int = Field(ge=0)
    total_estimated_cost_usd: float = Field(ge=0.0)


# ============ Pack ============


class ImageProviderRecommendationPack(DomainModel):
    """Top-level deliverable for ``mkt image-provider-plan``."""

    contract_version: Literal["image-provider-recommendation-pack.v1"] = (
        IMAGE_PROVIDER_RECOMMENDATION_PACK_VERSION
    )
    pack_id: str = Field(default_factory=new_id)
    client_slug: Annotated[str, Field(min_length=2, max_length=64)]

    job_pack_id: str = Field(min_length=1)
    job_pack_contract_version: str = Field(min_length=1)
    visual_pack_id: str | None = Field(default=None, max_length=64)
    creative_pack_id: str | None = Field(default=None, max_length=64)
    approval_pack_id: str | None = Field(default=None, max_length=64)

    blocks_publish: bool = False

    evaluations: list[ProviderEvaluation] = Field(default_factory=list)
    recommendations: list[ImageProviderRecommendation] = Field(default_factory=list)
    dry_run_receipts: list[ProviderDryRunReceipt] = Field(default_factory=list)
    stats: ImageProviderRecommendationStats

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
    "IMAGE_PROVIDER_RECOMMENDATION_PACK_KIND",
    "IMAGE_PROVIDER_RECOMMENDATION_PACK_VERSION",
    "ImageProviderRecommendation",
    "ImageProviderRecommendationPack",
    "ImageProviderRecommendationStats",
    "ProviderCriterionScore",
    "ProviderDryRunReceipt",
    "ProviderDryRunStatus",
    "ProviderEvaluation",
    "SINGLETON_ID",
]
