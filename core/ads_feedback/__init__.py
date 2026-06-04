"""Ads Insights → Feedback Loop bridge (MKT-6G).

Bridges the MKT-6F :class:`GoogleAdsInsightPack` and the MKT-6B
:class:`CampaignFeedbackPack` so Google-Ads-specific insights
become first-class suggestions the operator reviews alongside the
rest of the campaign feedback. Optionally cross-references the
existing :class:`CampaignExecutionTaskPack` (MKT-4E) and
:class:`NextCampaignIterationPlan` (MKT-6C) for traceability.

Contract: ``ads-feedback-bridge-pack.v1``.

**No external API. No campaign mutation. No keyword add. No
budget change. No pause execution.** The bridge produces
recommendations + suggested tasks only; a human reviews them and
decides whether to apply.
"""

from __future__ import annotations

from .bridge import (
    DEFAULT_ADS_BRIDGE_RULE_SET_ID,
    AdsFeedbackBridge,
    bridge_and_persist,
)
from .models import (
    ADS_FEEDBACK_BRIDGE_PACK_KIND,
    ADS_FEEDBACK_BRIDGE_PACK_VERSION,
    SINGLETON_ID,
    AdsAdjustmentKind,
    AdsBridgeStats,
    AdsCampaignAdjustment,
    AdsFeedbackBridgePack,
    AdsKeywordProposal,
    AdsRecommendation,
    AdsRecommendationKind,
    AdsRecommendationPriority,
    AdsSuggestedTask,
)
from .renderer import render_markdown_ads_bridge

__all__ = [
    "ADS_FEEDBACK_BRIDGE_PACK_KIND",
    "ADS_FEEDBACK_BRIDGE_PACK_VERSION",
    "AdsAdjustmentKind",
    "AdsBridgeStats",
    "AdsCampaignAdjustment",
    "AdsFeedbackBridge",
    "AdsFeedbackBridgePack",
    "AdsKeywordProposal",
    "AdsRecommendation",
    "AdsRecommendationKind",
    "AdsRecommendationPriority",
    "AdsSuggestedTask",
    "DEFAULT_ADS_BRIDGE_RULE_SET_ID",
    "SINGLETON_ID",
    "bridge_and_persist",
    "render_markdown_ads_bridge",
]
