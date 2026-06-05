"""Image Provider Selection & Generation Dry Run (MKT-7B).

Analysis layer on top of MKT-7A: reads the persisted
:class:`ImageGenerationJobPack`, scores each candidate provider
against the user-supplied criteria, picks a recommendation per
job (with explicit fallback to MANUAL) and emits a **dry-run
receipt** per job — a simulated request payload + simulated
output filename, with status ``dry_run``.

Contract: ``image-provider-recommendation-pack.v1``.

**No image generation.** No provider API call. No SDK import. No
HTTP. No credential read. No file write of PNG/JPG/WebP. The
block is pure analysis + dry-run preview.
"""

from __future__ import annotations

from .models import (
    IMAGE_PROVIDER_RECOMMENDATION_PACK_KIND,
    IMAGE_PROVIDER_RECOMMENDATION_PACK_VERSION,
    SINGLETON_ID,
    ImageProviderRecommendation,
    ImageProviderRecommendationPack,
    ImageProviderRecommendationStats,
    ProviderCriterionScore,
    ProviderDryRunReceipt,
    ProviderDryRunStatus,
)
from .planner import (
    DEFAULT_PROVIDER_PLANNER_RULE_SET_ID,
    ImageProviderPlanner,
    build_and_persist_provider_plan,
)
from .profiles import (
    DEFAULT_PROVIDER_PROFILES,
    PROVIDER_CRITERIA,
    ImageProviderProfile,
    ProviderCriterion,
)
from .renderer import render_markdown_provider_plan

__all__ = [
    "DEFAULT_PROVIDER_PLANNER_RULE_SET_ID",
    "DEFAULT_PROVIDER_PROFILES",
    "IMAGE_PROVIDER_RECOMMENDATION_PACK_KIND",
    "IMAGE_PROVIDER_RECOMMENDATION_PACK_VERSION",
    "ImageProviderPlanner",
    "ImageProviderProfile",
    "ImageProviderRecommendation",
    "ImageProviderRecommendationPack",
    "ImageProviderRecommendationStats",
    "PROVIDER_CRITERIA",
    "ProviderCriterion",
    "ProviderCriterionScore",
    "ProviderDryRunReceipt",
    "ProviderDryRunStatus",
    "SINGLETON_ID",
    "build_and_persist_provider_plan",
    "render_markdown_provider_plan",
]
