"""NotionSyncExecutor tests — end-to-end against the demo intake.

ALL tests use mocked writers. No real Notion call. No env var read.
"""

from __future__ import annotations

import json
from pathlib import Path

from core.approval import ApprovalPackBuilder
from core.creative import CreativeFactory
from core.execution import TaskFactory
from core.intake import ClientIntake, IntakeValidator, normalize_intake
from core.memory import JsonFileMemory
from core.notion_sync import (
    NOTION_SYNC_REPORT_KIND,
    NOTION_SYNCED_PAGES_KIND,
    NOTION_SYNCED_PAGES_SINGLETON_ID,
    REPORT_SINGLETON_ID,
    NotionSyncedPagesIndex,
    NotionSyncExecutor,
    NotionSyncPlanner,
    RefusingNotionWriter,
    ScriptedNotionWriter,
    SyncedRecordOutcome,
    SyncMode,
)
from core.strategy import StrategyPipeline
from core.visual import VisualPromptFactory

REPO_ROOT = Path(__file__).resolve().parents[2]
DEMO_INTAKE = REPO_ROOT / "examples" / "intake" / "demo-business.json"


def _full_pipeline(tmp_path: Path, *, risky: bool = False):
    data = json.loads(DEMO_INTAKE.read_text(encoding="utf-8"))
    if risky:
        data["product_or_service"] = (
            "Demo Pro - te aseguramos resultados garantizados sin riesgo"
        )
    intake_path = tmp_path / "intake.json"
    intake_path.write_text(json.dumps(data), encoding="utf-8")
    intake = ClientIntake.model_validate(json.loads(intake_path.read_text(encoding="utf-8")))
    v = IntakeValidator().validate(intake)
    brief = normalize_intake(intake, v)
    mem = JsonFileMemory(tmp_path / "mem")
    rep = StrategyPipeline(memory=mem).run_from_brief(brief).report
    ab = ApprovalPackBuilder(memory=mem)
    apk = ab.build_from_report(rep)
    ab.persist(apk)
    cf = CreativeFactory(memory=mem)
    cp = cf.build(rep, apk)
    cf.persist(cp)
    vf = VisualPromptFactory(memory=mem)
    vp = vf.build(rep, apk, cp)
    vf.persist(vp)
    tf = TaskFactory(memory=mem)
    pack = tf.build(rep, apk, cp, vp)
    tf.persist(pack)
    plan = NotionSyncPlanner(memory=mem).plan(pack)
    NotionSyncPlanner(memory=mem).persist(plan)
    return mem, pack, plan


# ---------- dry-run path ----------

def test_dry_run_does_not_call_writer(tmp_path: Path) -> None:
    mem, pack, _ = _full_pipeline(tmp_path)
    writer = ScriptedNotionWriter()
    executor = NotionSyncExecutor(memory=mem, writer=writer, database_id="db1")
    report = executor.run(pack.client_slug, mode=SyncMode.DRY_RUN)
    assert writer.calls == []
    assert report.write_attempted is False
    assert report.stats.created == 0
    assert report.stats.skipped_refused == pack.total_tasks


def test_dry_run_blocked_tasks_become_skipped_blocked(tmp_path: Path) -> None:
    mem, pack, _ = _full_pipeline(tmp_path, risky=True)
    writer = ScriptedNotionWriter()
    executor = NotionSyncExecutor(memory=mem, writer=writer, database_id="db1")
    report = executor.run(pack.client_slug, mode=SyncMode.DRY_RUN)
    assert report.stats.skipped_blocked > 0
    # Zero writer calls in dry-run, even for blocked tasks.
    assert writer.calls == []


# ---------- write path ----------

def test_write_mode_without_confirmed_falls_back(tmp_path: Path) -> None:
    """mode=WRITE but confirmed=False → executor does not call writer."""
    mem, pack, _ = _full_pipeline(tmp_path)
    writer = ScriptedNotionWriter()
    executor = NotionSyncExecutor(memory=mem, writer=writer, database_id="db1")
    report = executor.run(pack.client_slug, mode=SyncMode.WRITE, confirmed=False)
    assert report.write_attempted is False
    assert writer.calls == []


def test_write_with_confirm_calls_writer(tmp_path: Path) -> None:
    mem, pack, _ = _full_pipeline(tmp_path)
    writer = ScriptedNotionWriter()
    executor = NotionSyncExecutor(memory=mem, writer=writer, database_id="db1")
    report = executor.run(pack.client_slug, mode=SyncMode.WRITE, confirmed=True)
    assert report.write_attempted is True
    assert report.stats.created > 0
    # Writer called for every non-blocked / non-invalid task.
    assert len(writer.calls) == report.stats.created + report.stats.skipped_blocked


def test_blocked_tasks_are_created_with_blocked_outcome(tmp_path: Path) -> None:
    """A blocked task → page IS created (visible in Notion) but the
    record outcome is SKIPPED_BLOCKED (do-not-advance signal)."""
    mem, pack, _ = _full_pipeline(tmp_path, risky=True)
    writer = ScriptedNotionWriter()
    executor = NotionSyncExecutor(memory=mem, writer=writer, database_id="db1")
    report = executor.run(pack.client_slug, mode=SyncMode.WRITE, confirmed=True)
    blocked_records = [
        r for r in report.records if r.outcome is SyncedRecordOutcome.SKIPPED_BLOCKED
    ]
    assert blocked_records
    for r in blocked_records:
        assert r.page_id  # page was created
        # The proposed status was blocked; the record never advances.
        assert r.outcome is not SyncedRecordOutcome.CREATED


def test_blocked_pages_carry_status_blocked_property(tmp_path: Path) -> None:
    """The properties handed to the writer for blocked tasks must
    have Status=blocked (never advanced to ready / done)."""
    mem, pack, _ = _full_pipeline(tmp_path, risky=True)
    writer = ScriptedNotionWriter()
    executor = NotionSyncExecutor(memory=mem, writer=writer, database_id="db1")
    executor.run(pack.client_slug, mode=SyncMode.WRITE, confirmed=True)
    blocked_task_ids = {t.task_id for t in pack.tasks if t.state.value == "blocked"}
    blocked_calls = [c for c in writer.calls if c.task_id in blocked_task_ids]
    assert blocked_calls
    for call in blocked_calls:
        status_select = call.properties["Status"]["select"]
        assert status_select["name"] == "blocked"


def test_write_blocked_when_plan_has_errors(tmp_path: Path) -> None:
    """A plan with ERROR-severity issues blocks write entirely
    even with --write --confirm."""
    mem, pack, _ = _full_pipeline(tmp_path)
    raw = mem.get(pack.client_slug, "notion_sync_plan", "current")
    raw["issues"].append({
        "issue_id": "err1",
        "severity": "error",
        "code": "value_too_long",
        "message": "injected",
    })
    mem.put(pack.client_slug, "notion_sync_plan", "current", raw)
    writer = ScriptedNotionWriter()
    executor = NotionSyncExecutor(memory=mem, writer=writer, database_id="db1")
    report = executor.run(pack.client_slug, mode=SyncMode.WRITE, confirmed=True)
    assert report.write_attempted is False
    assert report.write_blocked_reason
    assert writer.calls == []


# ---------- idempotency ----------

def test_already_synced_pages_skipped_on_re_run(tmp_path: Path) -> None:
    mem, pack, _ = _full_pipeline(tmp_path)
    writer1 = ScriptedNotionWriter()
    e1 = NotionSyncExecutor(memory=mem, writer=writer1, database_id="db1")
    report1 = e1.run(pack.client_slug, mode=SyncMode.WRITE, confirmed=True)
    e1.persist_report(report1)
    assert report1.stats.created > 0

    writer2 = ScriptedNotionWriter()
    e2 = NotionSyncExecutor(memory=mem, writer=writer2, database_id="db1")
    report2 = e2.run(pack.client_slug, mode=SyncMode.WRITE, confirmed=True)
    # Second run: zero new creates.
    assert report2.stats.created == 0
    assert report2.stats.skipped_already_synced == report1.stats.created
    assert writer2.calls == []


def test_idempotency_index_persists(tmp_path: Path) -> None:
    mem, pack, _ = _full_pipeline(tmp_path)
    executor = NotionSyncExecutor(
        memory=mem, writer=ScriptedNotionWriter(), database_id="db1"
    )
    executor.run(pack.client_slug, mode=SyncMode.WRITE, confirmed=True)
    raw = mem.get(
        pack.client_slug, NOTION_SYNCED_PAGES_KIND, NOTION_SYNCED_PAGES_SINGLETON_ID
    )
    idx = NotionSyncedPagesIndex.model_validate(raw)
    assert len(idx.entries) > 0


# ---------- failure handling ----------

def test_writer_error_records_failed_outcome(tmp_path: Path) -> None:
    mem, pack, _ = _full_pipeline(tmp_path)
    first_task = pack.tasks[0]
    writer = ScriptedNotionWriter(
        errors_for={first_task.task_id: RuntimeError("synthetic")}
    )
    executor = NotionSyncExecutor(memory=mem, writer=writer, database_id="db1")
    report = executor.run(pack.client_slug, mode=SyncMode.WRITE, confirmed=True)
    failed = [r for r in report.records if r.outcome is SyncedRecordOutcome.FAILED]
    assert any(r.task_id == first_task.task_id for r in failed)
    assert report.stats.failed >= 1


def test_refusing_writer_records_skipped_refused(tmp_path: Path) -> None:
    """With --write --confirm but RefusingNotionWriter (e.g. SDK
    not installed), the executor must NOT crash."""
    mem, pack, _ = _full_pipeline(tmp_path)
    executor = NotionSyncExecutor(
        memory=mem, writer=RefusingNotionWriter(), database_id="db1"
    )
    report = executor.run(pack.client_slug, mode=SyncMode.WRITE, confirmed=True)
    assert report.stats.created == 0
    assert report.stats.failed == 0
    assert report.stats.skipped_refused > 0


# ---------- audit trail ----------

def test_audit_records_started_record_and_finished(tmp_path: Path) -> None:
    mem, pack, _ = _full_pipeline(tmp_path)
    executor = NotionSyncExecutor(
        memory=mem, writer=ScriptedNotionWriter(), database_id="db1"
    )
    executor.run(pack.client_slug, mode=SyncMode.WRITE, confirmed=True)
    events = mem.read_audit_events(pack.client_slug)
    actions = [
        e.payload.get("notion_sync", {}).get("action")
        for e in events
        if "notion_sync" in e.payload
    ]
    assert "started" in actions
    assert "finished" in actions
    assert "record" in actions
    from core.contracts import verify_chain
    assert verify_chain(events) == []


# ---------- persistence ----------

def test_persist_report_writes_to_memory(tmp_path: Path) -> None:
    mem, pack, _ = _full_pipeline(tmp_path)
    executor = NotionSyncExecutor(
        memory=mem, writer=ScriptedNotionWriter(), database_id="db1"
    )
    report = executor.run(pack.client_slug, mode=SyncMode.WRITE, confirmed=True)
    executor.persist_report(report)
    assert mem.exists(pack.client_slug, NOTION_SYNC_REPORT_KIND, REPORT_SINGLETON_ID)
    raw = mem.get(pack.client_slug, NOTION_SYNC_REPORT_KIND, REPORT_SINGLETON_ID)
    assert raw["report_id"] == report.report_id


# ---------- safety: only create_page ----------

def test_writer_only_uses_create_page(tmp_path: Path) -> None:
    """The executor must NEVER call update_page / delete_page /
    archive_page. ScriptedNotionWriter has no such methods, so a
    call would raise AttributeError."""
    mem, pack, _ = _full_pipeline(tmp_path)
    writer = ScriptedNotionWriter()
    executor = NotionSyncExecutor(memory=mem, writer=writer, database_id="db1")
    executor.run(pack.client_slug, mode=SyncMode.WRITE, confirmed=True)
    # Sanity: writer surface area is exactly create_page.
    assert not hasattr(writer, "update_page")
    assert not hasattr(writer, "delete_page")
    assert not hasattr(writer, "archive_page")


def test_no_status_advanced_in_records(tmp_path: Path) -> None:
    """The executor must NEVER produce a record outcome that
    advances a blocked task to ready / approved / done. Only
    created / skipped_* / failed are emitted."""
    mem, pack, _ = _full_pipeline(tmp_path, risky=True)
    executor = NotionSyncExecutor(
        memory=mem, writer=ScriptedNotionWriter(), database_id="db1"
    )
    report = executor.run(pack.client_slug, mode=SyncMode.WRITE, confirmed=True)
    allowed = {o.value for o in SyncedRecordOutcome}
    advance_states = {"ready", "approved", "done"}
    for r in report.records:
        assert r.outcome.value in allowed
        assert r.outcome.value not in advance_states
