"""Campaign Execution Task Pack application service (architecture/
application-service-boundary).

Migrates ``mkt build-tasks`` onto the application layer.
Behaviour-identical to the CLI's inline implementation: same build
order, same FLAT output layout, same three output files (Markdown +
JSON + Notion payload JSON), same ``--include-ads-bridge`` opt-in
promotion + audit event (MKT-6H), same atomic audit write (already
migrated onto ``append_audit_event_atomic`` — job-execution-robustness
GAP 1).
"""

from __future__ import annotations

import contextlib
import json

from core.approval import get_latest_for_client
from core.contracts import AuditEventType, AuditTrailEvent
from core.creative import CREATIVE_PACK_KIND, CreativeAssetPack
from core.creative import SINGLETON_ID as CREATIVE_SINGLETON
from core.domain.base import utcnow
from core.execution import TaskFactory, render_markdown_pack, to_notion_payload
from core.memory import EntityNotFound, JsonFileMemory, Memory
from core.strategy import REPORT_KIND, SINGLETON_ID, CampaignStrategyReport
from core.visual import SINGLETON_ID as VISUAL_SINGLETON
from core.visual import VISUAL_PACK_KIND, VisualDirectionPack

from ..artifacts import OutputLayout, write_artifacts
from ..context import OperationContext
from ..result import ErrorCode, OperationResult

_MD_FILENAME = "campaign-execution-tasks.md"
_JSON_FILENAME = "campaign-execution-tasks.json"
_NOTION_FILENAME = "notion-task-payload.json"
_ACTOR = "task_pack_service"


def _load_ads_bridge_pack_or_none(memory: Memory, client_slug: str):
    from core.ads_feedback.models import ADS_FEEDBACK_BRIDGE_PACK_KIND, AdsFeedbackBridgePack
    from core.ads_feedback.models import SINGLETON_ID as ADS_BRIDGE_SINGLETON

    try:
        raw = memory.get(client_slug, ADS_FEEDBACK_BRIDGE_PACK_KIND, ADS_BRIDGE_SINGLETON)
    except EntityNotFound:
        return None
    return AdsFeedbackBridgePack.model_validate(raw)


def _audit_ads_promotion(memory: Memory, *, client_slug: str, bridge_pack_id: str, promotion_result) -> None:
    memory.append_audit_event_atomic(
        client_slug,
        lambda prev_hash_arg: AuditTrailEvent.build(
            event_type=AuditEventType.NOTE,
            actor="ads_bridge_promoter",
            occurred_at=utcnow(),
            client_slug=client_slug,
            payload={
                "ads_bridge_promotion": {
                    "action": "promoted",
                    "target": "campaign_execution_task_pack",
                    "bridge_pack_id": bridge_pack_id,
                    "recommendations_promoted": promotion_result.recommendations_promoted,
                    "tasks_promoted": promotion_result.tasks_promoted,
                    "channel_adjustments_promoted": promotion_result.channel_adjustments_promoted,
                    "content_suggestions_promoted": promotion_result.content_suggestions_promoted,
                    "iteration_actions_promoted": promotion_result.iteration_actions_promoted,
                    "duplicates_skipped": promotion_result.duplicates_skipped,
                }
            },
            prev_hash=prev_hash_arg,
        ),
    )


def build_task_pack(
    ctx: OperationContext, *, include_ads_bridge: bool = False,
) -> OperationResult:
    """Build (and persist + write) the Campaign Execution Task Pack for
    ``ctx.client_slug``."""
    memory = JsonFileMemory(ctx.root)

    try:
        report_raw = memory.get(ctx.client_slug, REPORT_KIND, SINGLETON_ID)
    except EntityNotFound:
        return OperationResult.error_result(
            code=ErrorCode.NOT_FOUND,
            message=f"no CampaignStrategyReport for client {ctx.client_slug!r}",
            remediation="run `mkt run-strategy` first",
        )
    report = CampaignStrategyReport.model_validate(report_raw)

    approval = get_latest_for_client(memory, ctx.client_slug)

    creative: CreativeAssetPack | None = None
    with contextlib.suppress(EntityNotFound):
        creative = CreativeAssetPack.model_validate(
            memory.get(ctx.client_slug, CREATIVE_PACK_KIND, CREATIVE_SINGLETON)
        )

    visual: VisualDirectionPack | None = None
    with contextlib.suppress(EntityNotFound):
        visual = VisualDirectionPack.model_validate(
            memory.get(ctx.client_slug, VISUAL_PACK_KIND, VISUAL_SINGLETON)
        )

    factory = TaskFactory(memory=memory)
    pack = factory.build(report, approval, creative, visual)

    if include_ads_bridge:
        bridge = _load_ads_bridge_pack_or_none(memory, ctx.client_slug)
        if bridge is not None:
            from core.ads_promoter import promote_into_execution_tasks

            result = promote_into_execution_tasks(bridge, pack)
            _audit_ads_promotion(
                memory, client_slug=ctx.client_slug,
                bridge_pack_id=bridge.pack_id, promotion_result=result,
            )

    factory.persist(pack)

    files = {
        _MD_FILENAME: render_markdown_pack(pack),
        _JSON_FILENAME: pack.to_json(indent=2),
        _NOTION_FILENAME: json.dumps(to_notion_payload(pack), indent=2, ensure_ascii=False),
    }
    artifacts, write_err = write_artifacts(
        outputs_root=ctx.outputs_root,
        client_slug=ctx.client_slug,
        layout=OutputLayout.FLAT,
        files=files,
        overwrite=True,
        dry_run=False,
    )
    if write_err is not None:
        return OperationResult.error_result(
            code=write_err.code, message=write_err.message, remediation=write_err.remediation,
        )

    event = memory.append_audit_event_atomic(
        ctx.client_slug,
        lambda prev_hash_arg: AuditTrailEvent.build(
            event_type=AuditEventType.NOTE,
            actor=_ACTOR,
            occurred_at=utcnow(),
            client_slug=ctx.client_slug,
            payload={
                "execution_task_pack": {
                    "pack_id": pack.pack_id,
                    "client_slug": pack.client_slug,
                    "total_tasks": pack.total_tasks,
                    "blocks_publish": pack.blocks_publish,
                    "action": "built",
                }
            },
            prev_hash=prev_hash_arg,
        ),
    )

    return OperationResult.ok_result(data=pack, artifacts=artifacts, audit_event_id=event.event_id)


__all__ = ["build_task_pack"]
