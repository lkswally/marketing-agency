"""Notion sync planning (MKT-5A) — DRY RUN ONLY.

Contract: ``notion-sync-plan.v1``.

Reads the persisted :class:`CampaignExecutionTaskPack` (MKT-4E) and
the Notion-ready payload it ships, validates the payload against
Notion's documented limits, derives a property mapping, and emits a
plan describing exactly what a future synchroniser WOULD create
inside Notion.

The plan is data. **Nothing in this module imports a Notion SDK,
opens a socket, reads credentials, or writes anything to Notion.**
The real sync (with auth + write) is the explicit scope of a
later block (placeholder: ``P-4E.6``).
"""

from __future__ import annotations

from .models import (
    NOTION_SYNC_PLAN_VERSION,
    NotionPlanIssue,
    NotionPlanIssueSeverity,
    NotionPlannedRecord,
    NotionPropertyMapping,
    NotionPropertyType,
    NotionRecommendedDatabase,
    NotionSyncPlan,
    NotionSyncStats,
    PlannedAction,
)
from .planner import (
    DEFAULT_PLANNER_RULE_SET_ID,
    NOTION_SYNC_PLAN_KIND,
    SINGLETON_ID,
    NotionSyncPlanner,
    plan_and_persist,
)
from .renderer import render_markdown_plan

__all__ = [
    "DEFAULT_PLANNER_RULE_SET_ID",
    "NOTION_SYNC_PLAN_KIND",
    "NOTION_SYNC_PLAN_VERSION",
    "NotionPlanIssue",
    "NotionPlanIssueSeverity",
    "NotionPlannedRecord",
    "NotionPropertyMapping",
    "NotionPropertyType",
    "NotionRecommendedDatabase",
    "NotionSyncPlan",
    "NotionSyncPlanner",
    "NotionSyncStats",
    "PlannedAction",
    "SINGLETON_ID",
    "plan_and_persist",
    "render_markdown_plan",
]
