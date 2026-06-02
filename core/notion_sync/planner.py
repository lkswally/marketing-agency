"""NotionSyncPlanner — dry-run planner for the future Notion sync (MKT-5A).

Reads a persisted :class:`CampaignExecutionTaskPack` (MKT-4E) plus
the :func:`to_notion_payload` output the same block ships, and
emits a :class:`NotionSyncPlan` that describes exactly what a
future synchroniser WOULD do.

This module imports **no** Notion SDK, opens **no** socket, reads
**no** credential, and writes **nothing** to Notion. The plan is
pure data and lives only in our own memory + on-disk outputs.

Notion property mapping the planner emits (matches the user's spec
for MKT-5A):

| Notion property   | Notion type    | Source field on ExecutionTask   |
|-------------------|----------------|----------------------------------|
| Task Name         | title          | ``title``                        |
| Client            | rich_text      | ``pack.client_slug``             |
| Campaign          | rich_text      | ``pack.report_id``               |
| Category          | select         | ``category``                     |
| Channel           | select         | ``channel`` (when present)       |
| Priority          | select         | ``priority``                     |
| Status            | select         | ``state``                        |
| Due Date          | date           | ``due_date``                     |
| Depends On        | rich_text      | ``depends_on`` (joined)          |
| Blocked Reason    | rich_text      | ``blocked_reason``               |
| Asset Ref         | rich_text      | ``asset_ref``                    |
| Approval State    | select         | derived from upstream state      |
| Notes             | rich_text      | ``notes`` + ``description``      |

The planner also emits validation issues for any task whose values
would exceed Notion's documented limits, and a per-task action
(``CREATE`` / ``SKIP_BLOCKED`` / ``SKIP_INVALID``).
"""

from __future__ import annotations

from collections.abc import Iterable

from core.contracts import AuditEventType, AuditTrailEvent
from core.domain.base import utcnow
from core.execution import (
    CampaignExecutionTaskPack,
    ExecutionTask,
    TaskCategory,
    TaskPriority,
    TaskState,
    to_notion_payload,
)
from core.memory import Memory

from .models import (
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

NOTION_SYNC_PLAN_KIND = "notion_sync_plan"
SINGLETON_ID = "current"
DEFAULT_PLANNER_RULE_SET_ID = "notion-sync-plan-default.v1"

# Notion documented limits applied by the planner.
_TITLE_MAX = 2000
_RICH_TEXT_MAX = 2000
_URL_MAX = 2000
_SELECT_OPTION_MAX = 100


# ---------- public API ----------


class NotionSyncPlanner:
    """Build + persist a :class:`NotionSyncPlan` from a task pack."""

    def __init__(self, memory: Memory) -> None:
        self._memory = memory

    def plan(self, pack: CampaignExecutionTaskPack) -> NotionSyncPlan:
        # Materialise the Notion payload from MKT-4E so the planner
        # validates the same shape a future synchroniser would push.
        payload = to_notion_payload(pack)
        payload_schema = payload.get("schema_version", "notion-export.v1")

        property_mappings = _build_property_mappings()
        database = NotionRecommendedDatabase(
            title=f"Campaign Tasks — {pack.client_slug}",
            description=(
                f"Operational tasks for campaign {pack.report_id} "
                f"({pack.client_slug}). Generated dry-run from "
                f"campaign-execution-task-pack {pack.pack_id}."
            ),
            property_mappings=property_mappings,
            icon="🗂️",
            notes=[
                "DRY RUN — this database has not been created in Notion.",
                "Status options must match the six values used by the "
                "execution task pack (todo / blocked / needs_review / "
                "approved / ready / done).",
                "Category and Priority select options are pinned to the "
                "task pack contract; do not rename in Notion.",
            ],
        )

        issues: list[NotionPlanIssue] = []
        planned_records: list[NotionPlannedRecord] = []

        # Global validation: zero tasks → INFO issue, not error.
        if not pack.tasks:
            issues.append(
                NotionPlanIssue(
                    severity=NotionPlanIssueSeverity.INFO,
                    code="empty_pack",
                    message=(
                        "El task pack no tiene tareas; el sync no crearía "
                        "ninguna página."
                    ),
                    mitigation="Ejecutar `mkt build-tasks` con un pack completo.",
                )
            )

        for task in pack.tasks:
            record, task_issues = _plan_one_task(task, pack)
            planned_records.append(record)
            issues.extend(task_issues)

        stats = _compute_stats(pack, planned_records, issues)

        return NotionSyncPlan(
            client_slug=pack.client_slug,
            task_pack_id=pack.pack_id,
            task_pack_contract_version=pack.contract_version,
            notion_payload_schema_version=payload_schema,
            blocks_publish=pack.blocks_publish,
            upstream_overall_state=pack.upstream_overall_state,
            recommended_database=database,
            planned_records=planned_records,
            issues=issues,
            stats=stats,
            created_at=utcnow(),
            rule_set_id=DEFAULT_PLANNER_RULE_SET_ID,
        )

    def persist(self, plan: NotionSyncPlan) -> None:
        self._memory.put(
            plan.client_slug,
            NOTION_SYNC_PLAN_KIND,
            SINGLETON_ID,
            plan.model_dump(mode="json"),
        )
        # Audit event so a re-build is observable.
        prev = self._memory.last_audit_hash(plan.client_slug)
        event = AuditTrailEvent.build(
            event_type=AuditEventType.NOTE,
            actor="notion_sync_planner",
            occurred_at=utcnow(),
            client_slug=plan.client_slug,
            payload={
                "notion_sync_plan": {
                    "plan_id": plan.plan_id,
                    "task_pack_id": plan.task_pack_id,
                    "would_create": plan.stats.would_create,
                    "skip_blocked": plan.stats.skip_blocked,
                    "skip_invalid": plan.stats.skip_invalid,
                    "issues_error": plan.stats.issues_error,
                    "blocks_publish": plan.blocks_publish,
                    "action": "planned",
                }
            },
            prev_hash=prev,
        )
        self._memory.append_audit_event(event)

    def load_latest(self, client_slug: str) -> NotionSyncPlan:
        raw = self._memory.get(client_slug, NOTION_SYNC_PLAN_KIND, SINGLETON_ID)
        return NotionSyncPlan.model_validate(raw)


def plan_and_persist(
    memory: Memory, pack: CampaignExecutionTaskPack
) -> NotionSyncPlan:
    planner = NotionSyncPlanner(memory=memory)
    plan = planner.plan(pack)
    planner.persist(plan)
    return plan


# ---------- property mapping ----------


def _build_property_mappings() -> list[NotionPropertyMapping]:
    """Return the 13-property schema spec'd in the MKT-5A request."""
    return [
        NotionPropertyMapping(
            notion_name="Task Name",
            notion_type=NotionPropertyType.TITLE,
            source_field="title",
            required=True,
            notes="Maps to the task title; capped at 2000 chars by Notion.",
        ),
        NotionPropertyMapping(
            notion_name="Client",
            notion_type=NotionPropertyType.RICH_TEXT,
            source_field="pack.client_slug",
            required=True,
        ),
        NotionPropertyMapping(
            notion_name="Campaign",
            notion_type=NotionPropertyType.RICH_TEXT,
            source_field="pack.report_id",
            required=True,
            notes="The CampaignStrategyReport id from MKT-3A.",
        ),
        NotionPropertyMapping(
            notion_name="Category",
            notion_type=NotionPropertyType.SELECT,
            source_field="category",
            required=True,
            select_options=[c.value for c in TaskCategory],
        ),
        NotionPropertyMapping(
            notion_name="Channel",
            notion_type=NotionPropertyType.SELECT,
            source_field="channel",
            required=False,
            notes=(
                "Channel options are open: the sync should add new options "
                "on first occurrence rather than failing."
            ),
        ),
        NotionPropertyMapping(
            notion_name="Priority",
            notion_type=NotionPropertyType.SELECT,
            source_field="priority",
            required=True,
            select_options=[p.value for p in TaskPriority],
        ),
        NotionPropertyMapping(
            notion_name="Status",
            notion_type=NotionPropertyType.SELECT,
            source_field="state",
            required=True,
            select_options=[s.value for s in TaskState],
        ),
        NotionPropertyMapping(
            notion_name="Due Date",
            notion_type=NotionPropertyType.DATE,
            source_field="due_date",
            required=False,
        ),
        NotionPropertyMapping(
            notion_name="Depends On",
            notion_type=NotionPropertyType.RICH_TEXT,
            source_field="depends_on",
            required=False,
            notes=(
                "Joined as comma-separated task_ids. A future revision can "
                "promote this to a Notion relation property pointing at the "
                "same database (P-5A.x)."
            ),
        ),
        NotionPropertyMapping(
            notion_name="Blocked Reason",
            notion_type=NotionPropertyType.RICH_TEXT,
            source_field="blocked_reason",
            required=False,
        ),
        NotionPropertyMapping(
            notion_name="Asset Ref",
            notion_type=NotionPropertyType.RICH_TEXT,
            source_field="asset_ref",
            required=False,
            notes="Joined with asset_kind so a sync tool can route by kind.",
        ),
        NotionPropertyMapping(
            notion_name="Approval State",
            notion_type=NotionPropertyType.SELECT,
            source_field="(derived: pack.upstream_overall_state)",
            required=False,
            select_options=[
                "draft", "needs_review", "ready_for_publish", "blocked"
            ],
            notes=(
                "Same value for every task in a single sync (one campaign = "
                "one upstream state). Useful for filtering in Notion views."
            ),
        ),
        NotionPropertyMapping(
            notion_name="Notes",
            notion_type=NotionPropertyType.RICH_TEXT,
            source_field="notes + description",
            required=False,
            notes="Concatenated description + notes, capped at 2000 chars.",
        ),
    ]


# ---------- per-task planning ----------


def _plan_one_task(
    task: ExecutionTask, pack: CampaignExecutionTaskPack
) -> tuple[NotionPlannedRecord, list[NotionPlanIssue]]:
    issues: list[NotionPlanIssue] = []

    # Field count = mapped properties that would be populated.
    fields = _count_populated_fields(task)

    # ---- Validations ----
    if len(task.title) > _TITLE_MAX:
        issues.append(
            NotionPlanIssue(
                severity=NotionPlanIssueSeverity.ERROR,
                code="value_too_long",
                message=(
                    f"Task title excede {_TITLE_MAX} chars "
                    f"({len(task.title)})."
                ),
                task_id=task.task_id,
                field="title",
                mitigation="Truncar el título antes de sincronizar.",
            )
        )
    for field_name, value in (
        ("description", task.description),
        ("notes", task.notes),
        ("blocked_reason", task.blocked_reason),
    ):
        if value and len(value) > _RICH_TEXT_MAX:
            issues.append(
                NotionPlanIssue(
                    severity=NotionPlanIssueSeverity.ERROR,
                    code="value_too_long",
                    message=(
                        f"`{field_name}` excede {_RICH_TEXT_MAX} chars "
                        f"({len(value)})."
                    ),
                    task_id=task.task_id,
                    field=field_name,
                )
            )

    # depends_on becomes a comma-joined string; check joined length.
    joined_deps = ", ".join(task.depends_on)
    if len(joined_deps) > _RICH_TEXT_MAX:
        issues.append(
            NotionPlanIssue(
                severity=NotionPlanIssueSeverity.WARNING,
                code="depends_on_too_long",
                message=(
                    f"depends_on joined excede {_RICH_TEXT_MAX} chars; "
                    "considerar la propuesta de relación (P-5A.*)."
                ),
                task_id=task.task_id,
                field="depends_on",
            )
        )

    # Required-field-missing checks (only when the planner can't
    # synthesize a sensible default).
    if not task.title.strip():
        issues.append(
            NotionPlanIssue(
                severity=NotionPlanIssueSeverity.ERROR,
                code="missing_required_field",
                message="Task title está vacío.",
                task_id=task.task_id,
                field="title",
                mitigation="Generar título por defecto antes de sincronizar.",
            )
        )

    # Blocked-task INFO: a future sync should not auto-advance these.
    if task.state is TaskState.BLOCKED:
        issues.append(
            NotionPlanIssue(
                severity=NotionPlanIssueSeverity.INFO,
                code="task_blocked",
                message=(
                    "Task BLOCKED upstream; el sync creará la página pero "
                    "con Status=blocked y NO debe avanzarla automáticamente."
                ),
                task_id=task.task_id,
                field="state",
                mitigation=task.blocked_reason or "Resolver el bloqueo upstream.",
            )
        )

    # ---- Decide action ----
    task_errors = [
        i for i in issues
        if i.task_id == task.task_id and i.severity is NotionPlanIssueSeverity.ERROR
    ]
    if task_errors:
        action = PlannedAction.SKIP_INVALID
        reason = f"{len(task_errors)} validación(es) ERROR — ver `issues`."
    elif task.state is TaskState.BLOCKED:
        # Blocked tasks ARE created (so they're visible in Notion) but
        # the action label captures that the sync should not progress
        # them. PlannedAction.SKIP_BLOCKED communicates intent.
        action = PlannedAction.SKIP_BLOCKED
        reason = (
            task.blocked_reason
            or "Task BLOCKED upstream; crear pero no avanzar estado."
        )
    else:
        action = PlannedAction.CREATE
        reason = None

    record = NotionPlannedRecord(
        task_id=task.task_id,
        title=task.title,
        action=action,
        reason=reason,
        proposed_status=task.state.value,
        proposed_priority=task.priority.value,
        proposed_category=task.category.value,
        field_count=fields,
    )
    return record, issues


def _count_populated_fields(task: ExecutionTask) -> int:
    """Count of the 13 mapped Notion properties that would be populated
    for this task. Title, Client, Campaign, Category, Priority,
    Status and Approval State are always populated (= 7). The rest
    are conditional."""
    populated = 7  # always-on properties
    if task.channel:
        populated += 1
    if task.due_date is not None:
        populated += 1
    if task.depends_on:
        populated += 1
    if task.blocked_reason:
        populated += 1
    if task.asset_ref:
        populated += 1
    if task.notes or task.description:
        populated += 1
    return populated


# ---------- stats ----------


def _compute_stats(
    pack: CampaignExecutionTaskPack,
    records: Iterable[NotionPlannedRecord],
    issues: Iterable[NotionPlanIssue],
) -> NotionSyncStats:
    records_list = list(records)
    issues_list = list(issues)
    by_action: dict[str, int] = {
        PlannedAction.CREATE.value: 0,
        PlannedAction.SKIP_BLOCKED.value: 0,
        PlannedAction.SKIP_INVALID.value: 0,
    }
    for r in records_list:
        by_action[r.action.value] = by_action.get(r.action.value, 0) + 1

    return NotionSyncStats(
        total_tasks=pack.total_tasks,
        would_create=by_action[PlannedAction.CREATE.value],
        skip_blocked=by_action[PlannedAction.SKIP_BLOCKED.value],
        skip_invalid=by_action[PlannedAction.SKIP_INVALID.value],
        issues_total=len(issues_list),
        issues_error=sum(
            1 for i in issues_list if i.severity is NotionPlanIssueSeverity.ERROR
        ),
        issues_warning=sum(
            1 for i in issues_list if i.severity is NotionPlanIssueSeverity.WARNING
        ),
        issues_info=sum(
            1 for i in issues_list if i.severity is NotionPlanIssueSeverity.INFO
        ),
        by_category=pack.count_by_category(),
        by_priority=pack.count_by_priority(),
        by_state=pack.count_by_state(),
    )


__all__ = [
    "DEFAULT_PLANNER_RULE_SET_ID",
    "NOTION_SYNC_PLAN_KIND",
    "NotionSyncPlanner",
    "SINGLETON_ID",
    "plan_and_persist",
]
