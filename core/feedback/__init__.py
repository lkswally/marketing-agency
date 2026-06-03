"""Campaign feedback loop (MKT-6B).

Bridges the analytics layer (MKT-6A's
:class:`OptimizationRecommendationPack`) and the operational
layers (MKT-4E task pack, MKT-3* creative / visual / strategy)
by emitting a :class:`CampaignFeedbackPack` — a structured
deliverable the operator can review with the client and feed
back into the next campaign cycle.

Contract: ``campaign-feedback-pack.v1``.

**No external API. No MCP. No publishing. No automatic campaign
mutation.** The pack contains suggestions only; a human reviews
and decides whether to apply them.
"""

from __future__ import annotations

from .models import (
    CAMPAIGN_FEEDBACK_PACK_KIND,
    CAMPAIGN_FEEDBACK_PACK_VERSION,
    SINGLETON_ID,
    CampaignFeedbackPack,
    ChannelAdjustment,
    ChannelPriority,
    ContentSuggestion,
    ContentSuggestionKind,
    EmailRecommendation,
    ExecutiveSummary,
    FeedbackStats,
    SEORecommendation,
    SocialRecommendation,
    SuggestedTask,
    SuggestedTaskCategory,
    SuggestedTaskPriority,
)
from .planner import (
    DEFAULT_FEEDBACK_PLANNER_RULE_SET_ID,
    FeedbackPlanner,
    plan_and_persist,
)
from .renderer import render_markdown_feedback

__all__ = [
    "CAMPAIGN_FEEDBACK_PACK_KIND",
    "CAMPAIGN_FEEDBACK_PACK_VERSION",
    "CampaignFeedbackPack",
    "ChannelAdjustment",
    "ChannelPriority",
    "ContentSuggestion",
    "ContentSuggestionKind",
    "DEFAULT_FEEDBACK_PLANNER_RULE_SET_ID",
    "EmailRecommendation",
    "ExecutiveSummary",
    "FeedbackPlanner",
    "FeedbackStats",
    "SEORecommendation",
    "SINGLETON_ID",
    "SocialRecommendation",
    "SuggestedTask",
    "SuggestedTaskCategory",
    "SuggestedTaskPriority",
    "plan_and_persist",
    "render_markdown_feedback",
]
