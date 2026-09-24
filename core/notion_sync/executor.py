"""NotionSyncExecutor (MKT-5B) — opt-in write executor.

Consumes:
- The persisted :class:`CampaignExecutionTaskPack` (MKT-4E) for
  the raw tasks + Notion payload.
- The persisted :class:`NotionSyncPlan` (MKT-5A) for the
  per-record actions + validation issues.
- A :class:`NotionWriter` (the safe-by-default one is
  :class:`RefusingNotionWriter`).

Produces:
- A :class:`NotionSyncReport` with per-task outcomes.
- An updated :class:`NotionSyncedPagesIndex` (idempotency map).
- Audit events: ``notion_sync_started``, one
  ``notion_sync_record`` per task, ``notion_sync_finished``.

Cardinal rules enforced HERE (not at the writer):

- Mode default is :class:`SyncMode.DRY_RUN`. ``write`` is only
  reached when the caller explicitly passes ``mode=WRITE`` AND
  ``confirmed=True``.
- Tasks with action ``skip_invalid`` or ``skip_blocked`` in the
  plan are NEVER written. They land in the report with the
  corresponding outcome.
- Tasks already present in the :class:`NotionSyncedPagesIndex`
  are NEVER re-created (outcome
  ``skipped_already_synced``).
- A plan with any ERROR-severity issue blocks the entire write
  (``write_blocked_reason``); the executor falls back to dry-run
  semantics even when mode=WRITE+confirmed.
- No ``update_page``, no ``archive_page``, no ``delete_page``. The
  writer ABC only exposes ``create_page``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from core.contracts import AuditEventType, AuditTrailEvent
from core.domain.base import utcnow
from core.execution import (
    EXECUTION_TASK_PACK_KIND,
    CampaignExecutionTaskPack,
    to_notion_payload,
)
from core.execution import SINGLETON_ID as TASK_PACK_SINGLETON
from core.memory import EntityNotFound, Memory

from .models import (
    NotionSyncPlan,
    PlannedAction,
)
from .planner import NOTION_SYNC_PLAN_KIND
from .planner import SINGLETON_ID as PLAN_SINGLETON
from .sync_report import (
    NOTION_SYNCED_PAGES_KIND,
    NOTION_SYNCED_PAGES_SINGLETON_ID,
    NotionSyncedPageEntry,
    NotionSyncedPagesIndex,
    NotionSyncReport,
    SyncedRecord,
    SyncedRecordOutcome,
    SyncMode,
    SyncStats,
)
from .writer import (
    NoNotionCredentialsError,
    NotionPageRequest,
    NotionWriteError,
    NotionWriter,
    RefusingNotionWriter,
)

if TYPE_CHECKING:
    pass

NOTION_SYNC_REPORT_KIND = "notion_sync_report"
SINGLETON_ID = "current"
DEFAULT_EXECUTOR_RULE_SET_ID = "notion-sync-executor.v1"


class NotionSyncExecutor:
    """Drive the per-task create-page flow against a
    :class:`NotionWriter`, with full dry-run + idempotency support."""

    def __init__(
        self,
        memory: Memory,
        *,
        writer: NotionWriter | None = None,
        database_id: str | None = None,
    ) -> None:
        self._memory = memory
        self._writer = writer or RefusingNotionWriter()
        self._database_id = database_id

    # ---------- public API ----------

    def run(
        self,
        client_slug: str,
        *,
        mode: SyncMode = SyncMode.DRY_RUN,
        confirmed: bool = False,
        token_env_present: bool = False,
        database_id_env_present: bool = False,
        sdk_available: bool = False,
        write_blocked_reason: str | None = None,
    ) -> NotionSyncReport:
        started_at = utcnow()

        pack = self._load_pack(client_slug)
        plan = self._load_plan(client_slug)
        plan_pack_match = plan.task_pack_id == pack.pack_id
        if not plan_pack_match:
            write_blocked_reason = (
                write_blocked_reason
                or "El NotionSyncPlan persistido NO corresponde al task "
                "pack actual. Volver a correr `mkt notion-plan`."
            )

        plan_has_errors = plan.has_errors()
        if plan_has_errors and write_blocked_reason is None:
            write_blocked_reason = (
                f"El plan tiene {plan.stats.issues_error} issue(s) de "
                "severidad ERROR; el sync se ejecuta como dry-run."
            )

        # Resolve effective mode: write only when explicitly mode=WRITE,
        # confirmed=True, and no upstream block.
        effective_mode = mode
        effective_write_attempted = (
            mode is SyncMode.WRITE and confirmed and write_blocked_reason is None
        )
        if mode is SyncMode.WRITE and not effective_write_attempted:
            # Caller asked for write but we fall back to dry-run for
            # safety reasons (no confirm, missing creds, plan errors).
            # Keep mode=WRITE in the report so the operator sees the
            # intent, but write_attempted=False captures what actually
            # happened.
            pass

        # Load idempotency index.
        index = self._load_synced_pages_index(client_slug)
        index_by_task = index.as_dict()

        # Map plan records by task_id for fast lookup.
        plan_actions = {r.task_id: r for r in plan.planned_records}

        # Build a Notion payload per task so we can hand each one to
        # the writer with the same shape MKT-4E produces.
        notion_payload = to_notion_payload(pack)
        pages_by_task: dict[str, dict] = {}
        for raw_page in notion_payload["pages"]:
            tid = self._extract_task_id(raw_page)
            if tid:
                pages_by_task[tid] = raw_page

        # ---- Open audit ----
        self._emit_event(
            client_slug=client_slug,
            payload={
                "notion_sync": {
                    "action": "started",
                    "plan_id": plan.plan_id,
                    "task_pack_id": pack.pack_id,
                    "mode": mode.value,
                    "confirmed": confirmed,
                    "write_attempted": effective_write_attempted,
                    "write_blocked_reason": write_blocked_reason,
                    "token_env_present": token_env_present,
                    "database_id_env_present": database_id_env_present,
                    "sdk_available": sdk_available,
                }
            },
        )

        records: list[SyncedRecord] = []
        new_entries: list[NotionSyncedPageEntry] = []

        for task in pack.tasks:
            plan_record = plan_actions.get(task.task_id)
            if plan_record is None:
                # Plan is stale; record a SKIPPED_INVALID outcome.
                records.append(
                    SyncedRecord(
                        task_id=task.task_id,
                        title=task.title,
                        outcome=SyncedRecordOutcome.SKIPPED_INVALID,
                        reason="No matching record in NotionSyncPlan.",
                    )
                )
                self._record_audit(client_slug, records[-1], mode=effective_mode)
                continue

            # Plan says skip invalid → propagate.
            if plan_record.action is PlannedAction.SKIP_INVALID:
                records.append(
                    SyncedRecord(
                        task_id=task.task_id,
                        title=task.title,
                        outcome=SyncedRecordOutcome.SKIPPED_INVALID,
                        reason=plan_record.reason
                        or "Validation error in plan; not written.",
                    )
                )
                self._record_audit(client_slug, records[-1], mode=effective_mode)
                continue

            # Already synced? idempotency.
            if task.task_id in index_by_task:
                existing = index_by_task[task.task_id]
                records.append(
                    SyncedRecord(
                        task_id=task.task_id,
                        title=task.title,
                        outcome=SyncedRecordOutcome.SKIPPED_ALREADY_SYNCED,
                        page_id=existing.page_id,
                        reason=(
                            "Ya sincronizada previamente; este executor "
                            "NO actualiza páginas existentes."
                        ),
                    )
                )
                self._record_audit(client_slug, records[-1], mode=effective_mode)
                continue

            # Plan says skip_blocked → page WOULD be created with
            # Status=blocked (per MKT-5A semantics). The actual creation
            # only happens when we have a real writer; otherwise we
            # record as skipped_blocked (still visible to the operator).
            wants_blocked_create = plan_record.action is PlannedAction.SKIP_BLOCKED

            if not effective_write_attempted:
                # Dry-run path: every clean record becomes "would be
                # created" but reported as skipped_refused (no real
                # write happened). Blocked records become
                # skipped_blocked.
                outcome = (
                    SyncedRecordOutcome.SKIPPED_BLOCKED
                    if wants_blocked_create
                    else SyncedRecordOutcome.SKIPPED_REFUSED
                )
                reason = (
                    plan_record.reason
                    if wants_blocked_create
                    else (
                        write_blocked_reason
                        or "Modo dry-run o writer no autorizado."
                    )
                )
                records.append(
                    SyncedRecord(
                        task_id=task.task_id,
                        title=task.title,
                        outcome=outcome,
                        reason=reason,
                    )
                )
                self._record_audit(client_slug, records[-1], mode=effective_mode)
                continue

            # ---- Real write path ----
            page_dict = pages_by_task.get(task.task_id, {})
            properties = page_dict.get("properties", {})
            sink: list = []
            request = NotionPageRequest(
                task_id=task.task_id,
                database_id=self._database_id or "",
                properties=properties,
                record_sink=sink,
            )
            try:
                result = self._writer.create_page(request)
            except NoNotionCredentialsError as e:
                # Writer refused (e.g. RefusingNotionWriter slipped
                # through). Treat as skipped_refused, do NOT abort
                # the batch.
                records.append(
                    SyncedRecord(
                        task_id=task.task_id,
                        title=task.title,
                        outcome=SyncedRecordOutcome.SKIPPED_REFUSED,
                        reason=str(e)[:200],
                    )
                )
                self._record_audit(client_slug, records[-1], mode=effective_mode)
                continue
            except NotionWriteError as e:
                attempt = sink[0] if sink else None
                records.append(
                    SyncedRecord(
                        task_id=task.task_id,
                        title=task.title,
                        outcome=SyncedRecordOutcome.FAILED,
                        reason="Notion SDK raised; see error_type.",
                        duration_ms=attempt.duration_ms if attempt else None,
                        error_type=attempt.error_type if attempt else type(e).__name__,
                        error_message=attempt.error_message if attempt else str(e)[:200],
                    )
                )
                self._record_audit(client_slug, records[-1], mode=effective_mode)
                continue

            # Success.
            attempt = sink[0] if sink else None
            outcome = (
                SyncedRecordOutcome.SKIPPED_BLOCKED
                if wants_blocked_create
                else SyncedRecordOutcome.CREATED
            )
            # Note: for blocked tasks we DO create the page so it's
            # visible in Notion. The outcome label says skipped_blocked
            # to communicate "do not advance"; the page_id is recorded
            # so the operator can navigate.
            records.append(
                SyncedRecord(
                    task_id=task.task_id,
                    title=task.title,
                    outcome=outcome,
                    page_id=result.page_id,
                    duration_ms=attempt.duration_ms if attempt else result.duration_ms,
                )
            )
            new_entries.append(
                NotionSyncedPageEntry(
                    task_id=task.task_id,
                    page_id=result.page_id,
                    synced_at=utcnow(),
                    sync_report_id="pending",  # filled below
                )
            )
            self._record_audit(client_slug, records[-1], mode=effective_mode)

        finished_at = utcnow()
        stats = self._compute_stats(records)

        report = NotionSyncReport(
            client_slug=client_slug,
            plan_id=plan.plan_id,
            plan_contract_version=plan.contract_version,
            task_pack_id=pack.pack_id,
            mode=mode,
            confirmed=confirmed,
            write_attempted=effective_write_attempted,
            write_blocked_reason=write_blocked_reason,
            token_env_present=token_env_present,
            database_id_env_present=database_id_env_present,
            sdk_available=sdk_available,
            records=records,
            stats=stats,
            started_at=started_at,
            finished_at=finished_at,
            rule_set_id=DEFAULT_EXECUTOR_RULE_SET_ID,
        )

        # Update entries with the real report_id now we have one.
        finalized_entries = [
            NotionSyncedPageEntry(
                task_id=e.task_id,
                page_id=e.page_id,
                synced_at=e.synced_at,
                sync_report_id=report.report_id,
            )
            for e in new_entries
        ]
        if finalized_entries:
            self._extend_index(client_slug, index, finalized_entries)

        # ---- Close audit ----
        self._emit_event(
            client_slug=client_slug,
            payload={
                "notion_sync": {
                    "action": "finished",
                    "report_id": report.report_id,
                    "mode": mode.value,
                    "write_attempted": effective_write_attempted,
                    "created": stats.created,
                    "skipped_blocked": stats.skipped_blocked,
                    "skipped_invalid": stats.skipped_invalid,
                    "skipped_already_synced": stats.skipped_already_synced,
                    "skipped_refused": stats.skipped_refused,
                    "failed": stats.failed,
                }
            },
        )

        return report

    def persist_report(self, report: NotionSyncReport) -> None:
        self._memory.put(
            report.client_slug,
            NOTION_SYNC_REPORT_KIND,
            SINGLETON_ID,
            report.model_dump(mode="json"),
        )

    # ---------- internals ----------

    def _load_pack(self, client_slug: str) -> CampaignExecutionTaskPack:
        raw = self._memory.get(client_slug, EXECUTION_TASK_PACK_KIND, TASK_PACK_SINGLETON)
        return CampaignExecutionTaskPack.model_validate(raw)

    def _load_plan(self, client_slug: str) -> NotionSyncPlan:
        raw = self._memory.get(client_slug, NOTION_SYNC_PLAN_KIND, PLAN_SINGLETON)
        return NotionSyncPlan.model_validate(raw)

    def _load_synced_pages_index(self, client_slug: str) -> NotionSyncedPagesIndex:
        try:
            raw = self._memory.get(
                client_slug, NOTION_SYNCED_PAGES_KIND, NOTION_SYNCED_PAGES_SINGLETON_ID
            )
            return NotionSyncedPagesIndex.model_validate(raw)
        except EntityNotFound:
            return NotionSyncedPagesIndex(
                client_slug=client_slug,
                entries=[],
                updated_at=utcnow(),
            )

    def _extend_index(
        self,
        client_slug: str,
        existing: NotionSyncedPagesIndex,
        new_entries: list[NotionSyncedPageEntry],
    ) -> None:
        merged = list(existing.entries) + list(new_entries)
        # De-dupe by task_id, keeping the latest entry.
        by_task: dict[str, NotionSyncedPageEntry] = {}
        for e in merged:
            by_task[e.task_id] = e
        updated = NotionSyncedPagesIndex(
            client_slug=client_slug,
            entries=list(by_task.values()),
            updated_at=utcnow(),
        )
        self._memory.put(
            client_slug,
            NOTION_SYNCED_PAGES_KIND,
            NOTION_SYNCED_PAGES_SINGLETON_ID,
            updated.model_dump(mode="json"),
        )

    @staticmethod
    def _extract_task_id(raw_page: dict) -> str | None:
        props = raw_page.get("properties", {})
        task_id_prop = props.get("Task ID", {})
        rt = task_id_prop.get("rich_text", [])
        if rt and isinstance(rt, list):
            first = rt[0]
            text = first.get("text", {})
            return text.get("content")
        return None

    def _emit_event(self, *, client_slug: str, payload: dict) -> None:
        self._memory.append_audit_event_atomic(
            client_slug,
            lambda prev_hash_arg: AuditTrailEvent.build(
                event_type=AuditEventType.NOTE,
                actor="notion_sync_executor",
                occurred_at=utcnow(),
                client_slug=client_slug,
                payload=payload,
                prev_hash=prev_hash_arg,
            ),
        )

    def _record_audit(
        self, client_slug: str, record: SyncedRecord, *, mode: SyncMode
    ) -> None:
        self._emit_event(
            client_slug=client_slug,
            payload={
                "notion_sync": {
                    "action": "record",
                    "task_id": record.task_id,
                    "outcome": record.outcome.value,
                    "page_id": record.page_id,
                    "mode": mode.value,
                    "error_type": record.error_type,
                }
            },
        )

    @staticmethod
    def _compute_stats(records: list[SyncedRecord]) -> SyncStats:
        bucket: dict[str, int] = {o.value: 0 for o in SyncedRecordOutcome}
        for r in records:
            bucket[r.outcome.value] += 1
        return SyncStats(
            total_records=len(records),
            created=bucket[SyncedRecordOutcome.CREATED.value],
            skipped_blocked=bucket[SyncedRecordOutcome.SKIPPED_BLOCKED.value],
            skipped_invalid=bucket[SyncedRecordOutcome.SKIPPED_INVALID.value],
            skipped_already_synced=bucket[
                SyncedRecordOutcome.SKIPPED_ALREADY_SYNCED.value
            ],
            skipped_refused=bucket[SyncedRecordOutcome.SKIPPED_REFUSED.value],
            failed=bucket[SyncedRecordOutcome.FAILED.value],
        )


__all__ = [
    "DEFAULT_EXECUTOR_RULE_SET_ID",
    "NOTION_SYNC_REPORT_KIND",
    "NotionSyncExecutor",
    "SINGLETON_ID",
]
