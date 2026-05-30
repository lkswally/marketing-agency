"""Creative Asset Pack layer (MKT-3C).

Contract: ``creative-pack.v1``.

The factory consumes a :class:`CampaignStrategyReport` (MKT-3A) and an
optional :class:`ApprovalPack` (MKT-3B) and produces a deterministic
:class:`CreativeAssetPack` ready for human review. No external APIs,
no LLM, no image generation, no publishing.
"""

from __future__ import annotations

from .factory import (
    CREATIVE_PACK_KIND,
    DEFAULT_TEMPLATE_SET_ID,
    SINGLETON_ID,
    CreativeFactory,
    build_and_persist,
)
from .models import (
    CREATIVE_PACK_VERSION,
    AssetChecklistItem,
    CalendarEntry,
    CreativeAssetKind,
    CreativeAssetPack,
    CreativeAssetState,
    CTAStyle,
    CTAVariant,
    EmailAsset,
    FlyerAsset,
    FlyerFormat,
    HeadlineStyle,
    HeadlineVariant,
    HookVariant,
    ImagePromptAsset,
    ReelsAsset,
    SocialPostAsset,
    SubjectLineVariant,
    SubjectStyle,
    VariantAngle,
)
from .renderer import render_markdown_pack

__all__ = [
    "CREATIVE_PACK_VERSION",
    "CREATIVE_PACK_KIND",
    "SINGLETON_ID",
    "DEFAULT_TEMPLATE_SET_ID",
    # Factory
    "CreativeFactory",
    "build_and_persist",
    # Renderer
    "render_markdown_pack",
    # Top-level
    "CreativeAssetPack",
    "CreativeAssetState",
    "CreativeAssetKind",
    "CalendarEntry",
    # Asset models
    "SocialPostAsset",
    "EmailAsset",
    "ReelsAsset",
    "FlyerAsset",
    "FlyerFormat",
    "ImagePromptAsset",
    # Variants
    "HookVariant",
    "VariantAngle",
    "CTAVariant",
    "CTAStyle",
    "SubjectLineVariant",
    "SubjectStyle",
    "HeadlineVariant",
    "HeadlineStyle",
    # Aux
    "AssetChecklistItem",
]
