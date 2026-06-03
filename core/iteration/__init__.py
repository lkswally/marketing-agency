"""Next Campaign Iteration Plan (MKT-6C).

Converts a :class:`CampaignFeedbackPack` (MKT-6B) into a concrete
plan for the NEXT campaign cycle: actions (repeat / pause /
improve / create new), channel priority changes, new content
ideas, A/B test hypotheses, a suggested calendar and an
executive summary.

Contract: ``next-campaign-iteration-plan.v1``.

**Cardinal rule: the plan never applies changes.** It proposes
the next iteration. A human reviews and decides. No upstream
pack (strategy, creative, visual, task pack) is mutated. No
external API. No publishing. No LLM.
"""

from __future__ import annotations

from .models import (
    NEXT_CAMPAIGN_ITERATION_PLAN_KIND,
    NEXT_CAMPAIGN_ITERATION_PLAN_VERSION,
    SINGLETON_ID,
    ABTestHypothesis,
    IterationAction,
    IterationActionKind,
    IterationActionPriority,
    IterationCalendarEntry,
    IterationExecutiveSummary,
    IterationStats,
    NewContentIdea,
    NewContentKind,
    NextCampaignIterationPlan,
)
from .planner import (
    DEFAULT_ITERATION_PLANNER_RULE_SET_ID,
    IterationPlanner,
    plan_and_persist,
)
from .renderer import render_markdown_iteration_plan

__all__ = [
    "ABTestHypothesis",
    "DEFAULT_ITERATION_PLANNER_RULE_SET_ID",
    "IterationAction",
    "IterationActionKind",
    "IterationActionPriority",
    "IterationCalendarEntry",
    "IterationExecutiveSummary",
    "IterationPlanner",
    "IterationStats",
    "NEXT_CAMPAIGN_ITERATION_PLAN_KIND",
    "NEXT_CAMPAIGN_ITERATION_PLAN_VERSION",
    "NewContentIdea",
    "NewContentKind",
    "NextCampaignIterationPlan",
    "SINGLETON_ID",
    "plan_and_persist",
    "render_markdown_iteration_plan",
]
