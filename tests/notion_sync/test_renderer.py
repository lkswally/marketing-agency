"""Markdown renderer tests for the Notion sync dry-run plan."""

from __future__ import annotations

from datetime import UTC, datetime

from core.notion_sync import (
    NotionPlanIssue,
    NotionPlanIssueSeverity,
    NotionPlannedRecord,
    NotionPropertyMapping,
    NotionPropertyType,
    NotionRecommendedDatabase,
    NotionSyncPlan,
    NotionSyncStats,
    PlannedAction,
    render_markdown_plan,
)


def _plan(**overrides):
    db = NotionRecommendedDatabase(
        title="Campaign Tasks — acme",
        description="dry run",
        icon="🗂️",
        property_mappings=[
            NotionPropertyMapping(
                notion_name="Task Name",
                notion_type=NotionPropertyType.TITLE,
                source_field="title",
                required=True,
            ),
            NotionPropertyMapping(
                notion_name="Status",
                notion_type=NotionPropertyType.SELECT,
                source_field="state",
                required=True,
                select_options=["todo", "blocked"],
                notes="Pinned to TaskState enum.",
            ),
        ],
        notes=["No real DB created."],
    )
    base = dict(
        client_slug="acme-saas",
        task_pack_id="tp1",
        task_pack_contract_version="campaign-execution-task-pack.v1",
        notion_payload_schema_version="notion-export.v1",
        recommended_database=db,
        planned_records=[],
        issues=[],
        stats=NotionSyncStats(
            total_tasks=0, would_create=0, skip_blocked=0, skip_invalid=0,
            issues_total=0, issues_error=0, issues_warning=0, issues_info=0,
        ),
        created_at=datetime(2026, 6, 2, 12, 0, tzinfo=UTC),
    )
    base.update(overrides)
    return NotionSyncPlan(**base)


def test_renders_dry_run_warning() -> None:
    md = render_markdown_plan(_plan())
    assert "DRY RUN" in md
    assert "No se conectó a Notion" in md


def test_renders_header_with_plan_id() -> None:
    p = _plan()
    md = render_markdown_plan(p)
    assert p.plan_id in md
    assert "notion-sync-plan.v1" in md


def test_renders_database_recommendation() -> None:
    md = render_markdown_plan(_plan())
    assert "## 02. Base Notion recomendada" in md
    assert "Campaign Tasks — acme" in md
    assert "🗂️" in md


def test_renders_property_mapping_table() -> None:
    md = render_markdown_plan(_plan())
    assert "## 03. Mapping de propiedades" in md
    assert "| `Task Name` | `title` |" in md
    assert "| `Status` | `select` |" in md


def test_renders_records_table_with_action_emoji() -> None:
    p = _plan(
        planned_records=[
            NotionPlannedRecord(
                task_id="t1",
                title="do thing",
                action=PlannedAction.CREATE,
                proposed_status="todo",
                proposed_priority="medium",
                proposed_category="design",
                field_count=8,
            ),
            NotionPlannedRecord(
                task_id="t2",
                title="blocked thing",
                action=PlannedAction.SKIP_BLOCKED,
                reason="upstream block",
                proposed_status="blocked",
                proposed_priority="high",
                proposed_category="publishing",
                field_count=9,
            ),
        ],
        stats=NotionSyncStats(
            total_tasks=2, would_create=1, skip_blocked=1, skip_invalid=0,
            issues_total=0, issues_error=0, issues_warning=0, issues_info=0,
        ),
    )
    md = render_markdown_plan(p)
    assert "## 04. Registros planeados" in md
    assert "🟢 `create`" in md
    assert "🛑 `skip_blocked`" in md
    assert "upstream block" in md


def test_renders_issues_grouped_by_severity() -> None:
    p = _plan(
        issues=[
            NotionPlanIssue(
                severity=NotionPlanIssueSeverity.ERROR,
                code="value_too_long",
                message="too long",
                task_id="abcd1234",
                field="title",
            ),
            NotionPlanIssue(
                severity=NotionPlanIssueSeverity.WARNING,
                code="depends_on_too_long",
                message="dep list long",
            ),
            NotionPlanIssue(
                severity=NotionPlanIssueSeverity.INFO,
                code="task_blocked",
                message="blocked upstream",
                task_id="efgh5678",
            ),
        ],
        stats=NotionSyncStats(
            total_tasks=3, would_create=2, skip_blocked=1, skip_invalid=0,
            issues_total=3, issues_error=1, issues_warning=1, issues_info=1,
        ),
    )
    md = render_markdown_plan(p)
    assert "ERROR (1)" in md
    assert "WARNING (1)" in md
    assert "INFO (1)" in md
    assert "value_too_long" in md
    assert "depends_on_too_long" in md
    assert "task_blocked" in md


def test_renders_no_issues_placeholder_when_empty() -> None:
    md = render_markdown_plan(_plan())
    assert "## 05. Issues de validación" in md
    assert "(sin issues)" in md


def test_footer_explicitly_says_no_notion_call() -> None:
    md = render_markdown_plan(_plan())
    assert "No Notion API was called" in md
    assert "No credential" in md


def test_renderer_is_pure() -> None:
    p = _plan()
    a = render_markdown_plan(p)
    b = render_markdown_plan(p)
    assert a == b
