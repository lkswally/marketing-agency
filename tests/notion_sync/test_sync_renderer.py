"""Markdown renderer tests for the NotionSyncReport."""

from __future__ import annotations

from datetime import UTC, datetime

from core.notion_sync import (
    NotionSyncReport,
    SyncedRecord,
    SyncedRecordOutcome,
    SyncMode,
    SyncStats,
    render_markdown_report,
)


def _report(**overrides) -> NotionSyncReport:
    base = dict(
        client_slug="acme-saas",
        plan_id="p1",
        plan_contract_version="notion-sync-plan.v1",
        task_pack_id="tp1",
        mode=SyncMode.DRY_RUN,
        confirmed=False,
        write_attempted=False,
        token_env_present=False,
        database_id_env_present=False,
        sdk_available=False,
        records=[],
        stats=SyncStats(
            total_records=0, created=0, skipped_blocked=0, skipped_invalid=0,
            skipped_already_synced=0, skipped_refused=0, failed=0,
        ),
        started_at=datetime(2026, 6, 2, 12, 0, tzinfo=UTC),
        finished_at=datetime(2026, 6, 2, 12, 0, tzinfo=UTC),
    )
    base.update(overrides)
    return NotionSyncReport(**base)


def test_dry_run_label_in_header() -> None:
    md = render_markdown_report(_report())
    assert "DRY-RUN" in md
    assert "No Notion API" not in md  # appears only in footer for dry-run


def test_dry_run_footer_says_no_notion() -> None:
    md = render_markdown_report(_report())
    assert "No se conectó a Notion" in md
    assert "No se creó ninguna página" in md


def test_write_attempted_label_in_header() -> None:
    md = render_markdown_report(
        _report(mode=SyncMode.WRITE, confirmed=True, write_attempted=True)
    )
    assert "WRITE (real, confirmed)" in md


def test_renders_write_blocked_warning() -> None:
    md = render_markdown_report(
        _report(
            mode=SyncMode.WRITE,
            confirmed=True,
            write_attempted=False,
            write_blocked_reason="missing token",
        )
    )
    assert "Write requested but BLOCKED" in md
    assert "missing token" in md


def test_summary_counts_rendered() -> None:
    r = _report(stats=SyncStats(
        total_records=10, created=4, skipped_blocked=3, skipped_invalid=1,
        skipped_already_synced=1, skipped_refused=1, failed=0,
    ))
    md = render_markdown_report(r)
    assert "`created`: 4" in md
    assert "`skipped_blocked`: 3" in md
    assert "`skipped_invalid`: 1" in md
    assert "`skipped_already_synced`: 1" in md
    assert "`skipped_refused`: 1" in md


def test_records_table_rendered() -> None:
    r = _report(
        records=[
            SyncedRecord(
                task_id="t1", title="ok task", outcome=SyncedRecordOutcome.CREATED,
                page_id="pg-001",
            ),
            SyncedRecord(
                task_id="t2", title="blocked task",
                outcome=SyncedRecordOutcome.SKIPPED_BLOCKED, page_id="pg-002",
                reason="approval blocks publish",
            ),
            SyncedRecord(
                task_id="t3", title="failed task",
                outcome=SyncedRecordOutcome.FAILED,
                error_type="APIError", error_message="rate limit",
            ),
        ],
        stats=SyncStats(
            total_records=3, created=1, skipped_blocked=1, skipped_invalid=0,
            skipped_already_synced=0, skipped_refused=0, failed=1,
        ),
    )
    md = render_markdown_report(r)
    assert "## 02. Registros" in md
    assert "ok task" in md
    assert "pg-001" in md
    assert "approval blocks publish" in md
    assert "rate limit" in md
    # Failed sorts first.
    failed_idx = md.find("failed task")
    created_idx = md.find("ok task")
    assert failed_idx < created_idx


def test_empty_records_placeholder() -> None:
    md = render_markdown_report(_report())
    assert "## 02. Registros" in md
    assert "(sin registros)" in md


def test_credentials_status_in_header() -> None:
    md = render_markdown_report(
        _report(token_env_present=True, database_id_env_present=True, sdk_available=True)
    )
    assert "NOTION_TOKEN presente**: `True`" in md
    assert "NOTION_TASKS_DATABASE_ID presente**: `True`" in md


def test_renderer_is_pure() -> None:
    r = _report()
    a = render_markdown_report(r)
    b = render_markdown_report(r)
    assert a == b


def test_renderer_does_not_leak_token() -> None:
    """The report has no token field; rendering can't possibly leak
    a real token value. We only check that the env-var NAME is
    referenced exclusively as a label string (no `os.environ.get`
    or token interpolation)."""
    import inspect

    import core.notion_sync.sync_renderer as mod
    src = inspect.getsource(mod)
    # The name is allowed as a label inside an f-string. What MUST
    # NOT appear is any read or interpolation of the token value.
    assert "os.environ" not in src
    assert "{report.token}" not in src
    # And the report model has no token field, so leaking is
    # mechanically impossible.
    from core.notion_sync import NotionSyncReport
    assert "token" not in NotionSyncReport.model_fields
