"""Campaign Pipeline Orchestrator (MKT-3F).

Contract: ``pipeline-run.v1``.

Chains the five pipeline layers (intake → strategy → approval → creative →
visual) into one ``mkt run-campaign`` invocation. Produces a
:class:`CampaignRunSummary` plus the Markdown rendering, all persisted to
memory and to ``outputs/<slug>/``.
"""

from __future__ import annotations

from .models import (
    PIPELINE_RUN_VERSION,
    CampaignRunSummary,
    StageId,
    StageOutcome,
    StageResult,
)
from .orchestrator import (
    DEFAULT_RULE_SET_ID,
    PIPELINE_RUN_KIND,
    PIPELINE_RUN_SINGLETON,
    PipelineBlockedByApproval,
    PipelineOrchestrator,
    PipelineStrictFailure,
)
from .renderer import render_markdown_summary

__all__ = [
    "PIPELINE_RUN_VERSION",
    "PIPELINE_RUN_KIND",
    "PIPELINE_RUN_SINGLETON",
    "DEFAULT_RULE_SET_ID",
    # Models
    "CampaignRunSummary",
    "StageId",
    "StageOutcome",
    "StageResult",
    # Orchestrator
    "PipelineOrchestrator",
    "PipelineBlockedByApproval",
    "PipelineStrictFailure",
    # Renderer
    "render_markdown_summary",
]
