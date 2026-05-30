"""Campaign strategy engine — deterministic outputs for one workflow (W7).

Contract: ``campaign-strategy.v1``.
"""

from __future__ import annotations

from .backend import (
    REPORT_KIND,
    SINGLETON_ID,
    STRATEGY_WORKFLOW_ID,
    TemplatedStrategyBackend,
    load_input_brief_from_file,
    persist_input_brief,
)
from .models import (
    CAMPAIGN_STRATEGY_VERSION,
    ApprovalChecklist,
    BusinessDiagnosis,
    BuyerPersona,
    CampaignSchedule,
    CampaignStrategy,
    CampaignStrategyReport,
    ChannelEntry,
    ChannelRecommendation,
    ChecklistItem,
    CompetitorBenchmark,
    CompetitorEntry,
    CreativeBriefEntry,
    CreativeBriefPack,
    EmailDraft,
    EmailSequenceDraft,
    ExecutiveSummary,
    KeywordCluster,
    KeywordPlan,
    ReelsScriptEntry,
    ReelsScriptPack,
    RiskAssessment,
    RiskItem,
    ScheduleEntry,
    SocialPostDraft,
    StrategyInputBrief,
    SuggestedPiece,
    TargetAudience,
    ValueProposition,
)
from .pipeline import (
    DEFAULT_WORKFLOW_PATH,
    StrategyPipeline,
    StrategyPipelineError,
    StrategyRunResult,
)
from .renderer import render_markdown_report

__all__ = [
    "CAMPAIGN_STRATEGY_VERSION",
    "STRATEGY_WORKFLOW_ID",
    "REPORT_KIND",
    "SINGLETON_ID",
    "DEFAULT_WORKFLOW_PATH",
    # Pipeline
    "StrategyPipeline",
    "StrategyRunResult",
    "StrategyPipelineError",
    # Backend
    "TemplatedStrategyBackend",
    "persist_input_brief",
    "load_input_brief_from_file",
    # Renderer
    "render_markdown_report",
    # Models
    "StrategyInputBrief",
    "CampaignStrategyReport",
    "ExecutiveSummary",
    "BusinessDiagnosis",
    "TargetAudience",
    "BuyerPersona",
    "ValueProposition",
    "CompetitorBenchmark",
    "CompetitorEntry",
    "ChannelRecommendation",
    "ChannelEntry",
    "KeywordPlan",
    "KeywordCluster",
    "CampaignStrategy",
    "SuggestedPiece",
    "CreativeBriefPack",
    "CreativeBriefEntry",
    "SocialPostDraft",
    "EmailSequenceDraft",
    "EmailDraft",
    "ReelsScriptPack",
    "ReelsScriptEntry",
    "CampaignSchedule",
    "ScheduleEntry",
    "ApprovalChecklist",
    "ChecklistItem",
    "RiskAssessment",
    "RiskItem",
]
