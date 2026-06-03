"""N8nPayloadPlanner — builds the n8n dry-run payload (MKT-5C).

Reads (best-effort) the persisted upstream artifacts and emits one
:class:`N8nAction` per surface that a future n8n workflow would
handle:

- Creative pack emails → ``email_draft`` actions.
- Creative pack social posts → ``social_post_draft`` actions.
- Campaign run summary → one ``campaign_report_notification`` +
  one ``telegram_notification`` (campaign milestone alert).
- Visual direction pack → one ``drive_asset_folder`` per direction
  (so n8n can mirror the folder skeleton in Drive).
- Notion sync report → one ``notion_status_update`` per record
  the executor actually created.

When a pack is missing the planner skips its actions silently
(``actions_of_type`` returns ``[]``). Missing inputs are not an
error — a campaign without a creative pack still gets the report
notification.

**No HTTP. No env var read. No webhook URL stored anywhere.**
The ``target_webhook`` field is a logical name; the future sync
tool maps it to a real URL from its own config.
"""

from __future__ import annotations

from typing import Any

from core.contracts import AuditEventType, AuditTrailEvent
from core.creative import CREATIVE_PACK_KIND, CreativeAssetPack
from core.creative import SINGLETON_ID as CREATIVE_SINGLETON
from core.domain.base import utcnow
from core.execution import EXECUTION_TASK_PACK_KIND, CampaignExecutionTaskPack
from core.execution import SINGLETON_ID as TASK_PACK_SINGLETON
from core.memory import EntityNotFound, Memory
from core.notion_sync import (
    NOTION_SYNC_REPORT_KIND,
    NotionSyncReport,
)
from core.notion_sync import REPORT_SINGLETON_ID as NOTION_REPORT_SINGLETON
from core.pipeline import (
    PIPELINE_RUN_KIND,
    PIPELINE_RUN_SINGLETON,
    CampaignRunSummary,
)
from core.visual import SINGLETON_ID as VISUAL_SINGLETON
from core.visual import VISUAL_PACK_KIND, VisualDirectionPack

from .models import (
    N8nAction,
    N8nActionStatus,
    N8nActionType,
    N8nExecutionPayload,
    N8nPayloadStats,
)

N8N_EXECUTION_PAYLOAD_KIND = "n8n_execution_payload"
SINGLETON_ID = "current"
DEFAULT_N8N_PLANNER_RULE_SET_ID = "n8n-payload-planner.v1"


class N8nPayloadPlanner:
    """Build + persist a :class:`N8nExecutionPayload` from upstream
    artifacts."""

    def __init__(self, memory: Memory) -> None:
        self._memory = memory

    # ---------- public API ----------

    def plan(self, client_slug: str) -> N8nExecutionPayload:
        run_summary = self._try_load(
            client_slug, PIPELINE_RUN_KIND, PIPELINE_RUN_SINGLETON,
            CampaignRunSummary,
        )
        task_pack = self._try_load(
            client_slug, EXECUTION_TASK_PACK_KIND, TASK_PACK_SINGLETON,
            CampaignExecutionTaskPack,
        )
        creative = self._try_load(
            client_slug, CREATIVE_PACK_KIND, CREATIVE_SINGLETON,
            CreativeAssetPack,
        )
        visual = self._try_load(
            client_slug, VISUAL_PACK_KIND, VISUAL_SINGLETON,
            VisualDirectionPack,
        )
        notion_report = self._try_load(
            client_slug, NOTION_SYNC_REPORT_KIND, NOTION_REPORT_SINGLETON,
            NotionSyncReport,
        )

        blocks_publish = self._derive_blocks_publish(
            run_summary, task_pack, creative
        )

        actions: list[N8nAction] = []

        # 1. Campaign-level notifications (always emitted when we
        # have a run summary).
        if run_summary is not None:
            actions.append(self._build_campaign_report(run_summary))
            actions.append(
                self._build_telegram_notification(run_summary, blocks_publish)
            )

        # 2. Creative pack → email + social drafts.
        if creative is not None:
            for email in creative.emails:
                actions.append(
                    self._build_email_draft(creative, email, blocks_publish)
                )
            for post in creative.social_posts:
                actions.append(
                    self._build_social_post_draft(creative, post, blocks_publish)
                )

        # 3. Visual direction pack → drive folder hints.
        if visual is not None:
            for direction in getattr(visual, "directions", []) or []:
                actions.append(
                    self._build_drive_asset_folder(visual, direction)
                )

        # 4. Notion sync report → status updates per CREATED record.
        if notion_report is not None:
            for rec in notion_report.records:
                if rec.outcome.value == "created" and rec.page_id:
                    actions.append(
                        self._build_notion_status_update(notion_report, rec)
                    )

        stats = self._compute_stats(actions)

        return N8nExecutionPayload(
            client_slug=client_slug,
            run_summary_id=getattr(run_summary, "run_id", None),
            run_summary_contract_version=getattr(
                run_summary, "contract_version", None
            ),
            task_pack_id=getattr(task_pack, "pack_id", None),
            task_pack_contract_version=getattr(
                task_pack, "contract_version", None
            ),
            creative_pack_id=getattr(creative, "pack_id", None),
            creative_pack_contract_version=getattr(
                creative, "contract_version", None
            ),
            visual_pack_id=getattr(visual, "pack_id", None),
            visual_pack_contract_version=getattr(
                visual, "contract_version", None
            ),
            notion_sync_report_id=getattr(notion_report, "report_id", None),
            notion_sync_report_contract_version=getattr(
                notion_report, "contract_version", None
            ),
            blocks_publish=blocks_publish,
            actions=actions,
            stats=stats,
            created_at=utcnow(),
            rule_set_id=DEFAULT_N8N_PLANNER_RULE_SET_ID,
        )

    def persist(self, payload: N8nExecutionPayload) -> None:
        self._memory.put(
            payload.client_slug,
            N8N_EXECUTION_PAYLOAD_KIND,
            SINGLETON_ID,
            payload.model_dump(mode="json"),
        )
        prev = self._memory.last_audit_hash(payload.client_slug)
        event = AuditTrailEvent.build(
            event_type=AuditEventType.NOTE,
            actor="n8n_payload_planner",
            occurred_at=utcnow(),
            client_slug=payload.client_slug,
            payload={
                "n8n_execution_payload": {
                    "payload_id": payload.payload_id,
                    "total_actions": payload.stats.total_actions,
                    "planned": payload.stats.planned,
                    "blocked": payload.stats.blocked,
                    "blocks_publish": payload.blocks_publish,
                    "action": "planned",
                }
            },
            prev_hash=prev,
        )
        self._memory.append_audit_event(event)

    def load_latest(self, client_slug: str) -> N8nExecutionPayload:
        raw = self._memory.get(client_slug, N8N_EXECUTION_PAYLOAD_KIND, SINGLETON_ID)
        return N8nExecutionPayload.model_validate(raw)

    # ---------- internals ----------

    def _try_load(self, client_slug: str, kind: str, entity_id: str, cls):
        try:
            raw = self._memory.get(client_slug, kind, entity_id)
        except EntityNotFound:
            return None
        return cls.model_validate(raw)

    @staticmethod
    def _derive_blocks_publish(
        run_summary: CampaignRunSummary | None,
        task_pack: CampaignExecutionTaskPack | None,
        creative: CreativeAssetPack | None,
    ) -> bool:
        for src in (run_summary, task_pack, creative):
            if src is None:
                continue
            if bool(getattr(src, "blocks_publish", False)):
                return True
        return False

    # ---------- per-action builders ----------

    @staticmethod
    def _build_campaign_report(summary: CampaignRunSummary) -> N8nAction:
        return N8nAction(
            action_type=N8nActionType.CAMPAIGN_REPORT_NOTIFICATION,
            status=N8nActionStatus.PLANNED,
            target_webhook="campaign_reports",
            source_kind="campaign_run_summary",
            source_ref=summary.run_id,
            payload={
                "client_slug": summary.client_slug,
                "run_id": summary.run_id,
                "overall_state": summary.overall_state.value,
                "blocks_publish": summary.blocks_publish,
                "intake_critical_count": summary.intake_critical_count,
                "stage_counts": summary.count_by_outcome(),
                "report_id": summary.report_id,
                "approval_pack_id": summary.approval_pack_id,
                "creative_pack_id": summary.creative_pack_id,
                "visual_pack_id": summary.visual_pack_id,
            },
        )

    @staticmethod
    def _build_telegram_notification(
        summary: CampaignRunSummary, blocks_publish: bool
    ) -> N8nAction:
        # Telegram notifications are always PLANNED — alerting the
        # team about a blocked campaign is the whole point.
        if blocks_publish:
            text = (
                f"🛑 Campaña {summary.client_slug}: bloquea publicación. "
                "Revisar Approval Pack antes de seguir."
            )
        else:
            text = (
                f"✅ Campaña {summary.client_slug}: pipeline completo "
                f"({summary.overall_state.value}). Lista para revisión humana."
            )
        return N8nAction(
            action_type=N8nActionType.TELEGRAM_NOTIFICATION,
            status=N8nActionStatus.PLANNED,
            target_webhook="telegram_alerts",
            source_kind="campaign_run_summary",
            source_ref=summary.run_id,
            payload={
                "chat_target": "ops_team",
                "text": text,
                "parse_mode": "Markdown",
                "client_slug": summary.client_slug,
                "blocks_publish": blocks_publish,
            },
        )

    @staticmethod
    def _build_email_draft(
        creative: CreativeAssetPack, email, blocks_publish: bool
    ) -> N8nAction:
        subject = (
            email.subject_line_variants[0].subject
            if email.subject_line_variants
            else f"email step {email.step}"
        )
        preview = (
            email.subject_line_variants[0].preview_text
            if email.subject_line_variants
            else ""
        )
        payload: dict[str, Any] = {
            "client_slug": creative.client_slug,
            "creative_pack_id": creative.pack_id,
            "asset_id": email.asset_id,
            "step": email.step,
            "subject": subject,
            "preview_text": preview,
            "body": email.body,
            "cta": email.cta,
            "send_after_days": email.send_after_days,
            "draft_only": True,  # n8n must NEVER send; only create draft
        }
        if blocks_publish:
            return N8nAction(
                action_type=N8nActionType.EMAIL_DRAFT,
                status=N8nActionStatus.BLOCKED,
                target_webhook="email_drafts",
                source_kind="creative_asset_pack.email",
                source_ref=email.asset_id,
                payload=payload,
                blocked_reason=(
                    "ApprovalPack blocks publish; n8n debe NO crear este "
                    "draft hasta resolver el bloqueo."
                ),
            )
        return N8nAction(
            action_type=N8nActionType.EMAIL_DRAFT,
            status=N8nActionStatus.PLANNED,
            target_webhook="email_drafts",
            source_kind="creative_asset_pack.email",
            source_ref=email.asset_id,
            payload=payload,
        )

    @staticmethod
    def _build_social_post_draft(
        creative: CreativeAssetPack, post, blocks_publish: bool
    ) -> N8nAction:
        hook = post.hook_variants[0].text if post.hook_variants else ""
        cta = post.cta_variants[0].text if post.cta_variants else ""
        payload: dict[str, Any] = {
            "client_slug": creative.client_slug,
            "creative_pack_id": creative.pack_id,
            "asset_id": post.asset_id,
            "channel": post.channel.value,
            "hook": hook,
            "body": post.body,
            "cta": cta,
            "hashtags": list(post.hashtags),
            "draft_only": True,
        }
        if blocks_publish:
            return N8nAction(
                action_type=N8nActionType.SOCIAL_POST_DRAFT,
                status=N8nActionStatus.BLOCKED,
                target_webhook="social_drafts",
                source_kind="creative_asset_pack.social_post",
                source_ref=post.asset_id,
                payload=payload,
                blocked_reason=(
                    "ApprovalPack blocks publish; n8n debe NO crear este "
                    "draft hasta resolver el bloqueo."
                ),
            )
        return N8nAction(
            action_type=N8nActionType.SOCIAL_POST_DRAFT,
            status=N8nActionStatus.PLANNED,
            target_webhook="social_drafts",
            source_kind="creative_asset_pack.social_post",
            source_ref=post.asset_id,
            payload=payload,
        )

    @staticmethod
    def _build_drive_asset_folder(
        visual: VisualDirectionPack, direction
    ) -> N8nAction:
        direction_id = getattr(direction, "direction_id", None) or getattr(
            direction, "asset_id", None
        )
        title = (
            getattr(direction, "title", None)
            or getattr(direction, "concept_name", None)
            or "untitled-direction"
        )
        return N8nAction(
            action_type=N8nActionType.DRIVE_ASSET_FOLDER,
            status=N8nActionStatus.PLANNED,
            target_webhook="drive_folders",
            source_kind="visual_direction_pack.direction",
            source_ref=direction_id,
            payload={
                "client_slug": visual.client_slug,
                "visual_pack_id": visual.pack_id,
                "folder_name": f"{visual.client_slug}/{title}",
                "subfolders": ["renders", "reference", "approved"],
                "share_with_role": "designer",
            },
        )

    @staticmethod
    def _build_notion_status_update(
        report: NotionSyncReport, record
    ) -> N8nAction:
        return N8nAction(
            action_type=N8nActionType.NOTION_STATUS_UPDATE,
            status=N8nActionStatus.PLANNED,
            target_webhook="notion_updates",
            source_kind="notion_sync_report.record",
            source_ref=record.page_id,
            payload={
                "client_slug": report.client_slug,
                "report_id": report.report_id,
                "task_id": record.task_id,
                "page_id": record.page_id,
                "outcome": record.outcome.value,
                # n8n must NOT advance the status by itself; this is
                # a no-op notification + UTM sync stub.
                "advance_status": False,
            },
        )

    # ---------- stats ----------

    @staticmethod
    def _compute_stats(actions: list[N8nAction]) -> N8nPayloadStats:
        by_type: dict[str, int] = {}
        planned = 0
        blocked = 0
        for a in actions:
            by_type[a.action_type.value] = by_type.get(a.action_type.value, 0) + 1
            if a.status is N8nActionStatus.BLOCKED:
                blocked += 1
            else:
                planned += 1
        return N8nPayloadStats(
            total_actions=len(actions),
            planned=planned,
            blocked=blocked,
            by_type=by_type,
        )


def plan_and_persist(memory: Memory, client_slug: str) -> N8nExecutionPayload:
    planner = N8nPayloadPlanner(memory=memory)
    payload = planner.plan(client_slug)
    planner.persist(payload)
    return payload


__all__ = [
    "DEFAULT_N8N_PLANNER_RULE_SET_ID",
    "N8N_EXECUTION_PAYLOAD_KIND",
    "N8nPayloadPlanner",
    "SINGLETON_ID",
    "plan_and_persist",
]
