"""Campaign Execution Task Pack (MKT-4E).

Contract: ``campaign-execution-task-pack.v1``.

Reads the per-campaign deliverables (CampaignStrategyReport,
ApprovalPack, CreativeAssetPack, VisualDirectionPack) and produces
a deterministic operational task list — Notion-ready, but NOT sent
to Notion (or to any external system). The pack is persisted to
:class:`JsonFileMemory` like every other artifact in this system.

State and priority follow the same conservative rules as the
upstream packs: anything that depends on an asset in BLOCKED state
inherits ``blocked``; anything that depends on the Approval Pack
blocking publish inherits ``blocked`` too. Nothing in the
generated pack causes any external side-effect.
"""

from __future__ import annotations

from .models import (
    CAMPAIGN_EXECUTION_TASK_PACK_VERSION,
    CampaignExecutionTaskPack,
    ExecutionTask,
    TaskCategory,
    TaskPriority,
    TaskState,
)
from .notion_payload import to_notion_payload
from .renderer import render_markdown_pack
from .task_factory import (
    DEFAULT_TASK_RULE_SET_ID,
    EXECUTION_TASK_PACK_KIND,
    SINGLETON_ID,
    TaskFactory,
    build_and_persist,
)

__all__ = [
    "CAMPAIGN_EXECUTION_TASK_PACK_VERSION",
    "DEFAULT_TASK_RULE_SET_ID",
    "EXECUTION_TASK_PACK_KIND",
    "SINGLETON_ID",
    "CampaignExecutionTaskPack",
    "ExecutionTask",
    "TaskCategory",
    "TaskFactory",
    "TaskPriority",
    "TaskState",
    "build_and_persist",
    "render_markdown_pack",
    "to_notion_payload",
]
