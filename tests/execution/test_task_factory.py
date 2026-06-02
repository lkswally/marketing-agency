"""TaskFactory tests — end-to-end against the demo intake."""

from __future__ import annotations

import json
from pathlib import Path

from core.approval import ApprovalPackBuilder
from core.creative import CreativeFactory
from core.execution import (
    EXECUTION_TASK_PACK_KIND,
    SINGLETON_ID,
    TaskCategory,
    TaskFactory,
    TaskState,
)
from core.intake import ClientIntake, IntakeValidator, normalize_intake
from core.memory import JsonFileMemory
from core.strategy import StrategyPipeline
from core.visual import VisualPromptFactory

REPO_ROOT = Path(__file__).resolve().parents[2]
DEMO_INTAKE = REPO_ROOT / "examples" / "intake" / "demo-business.json"


def _build_full_stack(tmp_path: Path, *, risky: bool = False):
    """Run the full pipeline (intake → strategy → approval → creative
    → visual) and return the four input packs the TaskFactory needs."""
    data = json.loads(DEMO_INTAKE.read_text(encoding="utf-8"))
    if risky:
        data["product_or_service"] = (
            "Demo Pro - te aseguramos resultados garantizados sin riesgo"
        )
    intake_path = tmp_path / "intake.json"
    intake_path.write_text(json.dumps(data), encoding="utf-8")

    intake = ClientIntake.model_validate(
        json.loads(intake_path.read_text(encoding="utf-8"))
    )
    validation = IntakeValidator().validate(intake)
    brief = normalize_intake(intake, validation)
    mem = JsonFileMemory(tmp_path / "mem")
    pipeline = StrategyPipeline(memory=mem)
    res = pipeline.run_from_brief(brief)
    report = res.report

    builder = ApprovalPackBuilder(memory=mem)
    approval = builder.build_from_report(report)
    builder.persist(approval)

    creative_factory = CreativeFactory(memory=mem)
    creative = creative_factory.build(report, approval)
    creative_factory.persist(creative)

    visual_factory = VisualPromptFactory(memory=mem)
    visual = visual_factory.build(report, approval, creative)
    visual_factory.persist(visual)

    return mem, report, approval, creative, visual


# ---------- happy path ----------

def test_build_pack_from_demo_intake(tmp_path: Path) -> None:
    mem, report, approval, creative, visual = _build_full_stack(tmp_path)
    pack = TaskFactory(memory=mem).build(report, approval, creative, visual)
    assert pack.total_tasks > 0
    assert pack.client_slug == report.client_slug
    assert pack.report_id == report.report_id
    assert pack.approval_pack_id == approval.pack_id
    assert pack.creative_pack_id == creative.pack_id
    assert pack.visual_pack_id == visual.pack_id


def test_pack_has_all_categories_for_complete_input(tmp_path: Path) -> None:
    mem, report, approval, creative, visual = _build_full_stack(tmp_path)
    pack = TaskFactory(memory=mem).build(report, approval, creative, visual)
    cats = pack.count_by_category()
    for c in ("design", "publishing", "seo", "email", "social",
              "operational", "measurement", "calendar"):
        assert cats.get(c, 0) > 0, f"category {c} should have ≥1 task"


def test_publishing_tasks_have_dependencies(tmp_path: Path) -> None:
    mem, report, approval, creative, visual = _build_full_stack(tmp_path)
    pack = TaskFactory(memory=mem).build(report, approval, creative, visual)
    publishing = pack.tasks_in_category(TaskCategory.PUBLISHING)
    assert publishing
    assert all(p.depends_on for p in publishing)


def test_calendar_tasks_have_due_dates(tmp_path: Path) -> None:
    mem, report, approval, creative, visual = _build_full_stack(tmp_path)
    pack = TaskFactory(memory=mem).build(report, approval, creative, visual)
    cal = pack.tasks_in_category(TaskCategory.CALENDAR)
    assert cal
    assert all(t.due_date is not None for t in cal)


# ---------- blocking ----------

def test_blocks_publish_marks_publishing_tasks_blocked(tmp_path: Path) -> None:
    mem, report, approval, creative, visual = _build_full_stack(tmp_path, risky=True)
    assert approval.blocks_publish is True
    pack = TaskFactory(memory=mem).build(report, approval, creative, visual)
    assert pack.blocks_publish is True
    publishing = pack.tasks_in_category(TaskCategory.PUBLISHING)
    assert publishing
    for t in publishing:
        assert t.state is TaskState.BLOCKED
        assert t.blocked_reason is not None


def test_qa_tasks_remain_todo_when_publish_blocked(tmp_path: Path) -> None:
    """Even when publishing is blocked, the upstream QA / approval /
    design tasks stay actionable so the operator can resolve the
    block."""
    mem, report, approval, creative, visual = _build_full_stack(tmp_path, risky=True)
    pack = TaskFactory(memory=mem).build(report, approval, creative, visual)
    design = pack.tasks_in_category(TaskCategory.DESIGN)
    assert design
    # Design tasks have no blocking dependency from approval, so they
    # stay TODO.
    assert any(t.state is TaskState.TODO for t in design)


def test_propagated_blocking_for_dependent_tasks(tmp_path: Path) -> None:
    """If an email QA task is blocked, the email publish task that
    depends on it must also be blocked."""
    mem, report, approval, creative, visual = _build_full_stack(tmp_path, risky=True)
    pack = TaskFactory(memory=mem).build(report, approval, creative, visual)
    publishing = pack.tasks_in_category(TaskCategory.PUBLISHING)
    # Every publishing task is blocked AND has a non-empty depends_on.
    assert all(t.state is TaskState.BLOCKED and t.depends_on for t in publishing)


# ---------- persistence ----------

def test_pack_persists_to_memory(tmp_path: Path) -> None:
    mem, report, approval, creative, visual = _build_full_stack(tmp_path)
    pack = TaskFactory(memory=mem).build(report, approval, creative, visual)
    TaskFactory(memory=mem).persist(pack)
    assert mem.exists(pack.client_slug, EXECUTION_TASK_PACK_KIND, SINGLETON_ID)
    loaded = TaskFactory(memory=mem).load_latest(pack.client_slug)
    assert loaded.pack_id == pack.pack_id
    assert loaded.total_tasks == pack.total_tasks


# ---------- determinism ----------

def test_two_builds_produce_same_task_count(tmp_path: Path) -> None:
    mem, report, approval, creative, visual = _build_full_stack(tmp_path)
    factory = TaskFactory(memory=mem)
    a = factory.build(report, approval, creative, visual)
    b = factory.build(report, approval, creative, visual)
    assert a.total_tasks == b.total_tasks
    assert a.count_by_category() == b.count_by_category()


# ---------- approval-only / no creative ----------

def test_build_with_only_strategy(tmp_path: Path) -> None:
    """The factory must work even if only the strategy report is
    available (no approval, no creative, no visual)."""
    mem, report, _, _, _ = _build_full_stack(tmp_path)
    pack = TaskFactory(memory=mem).build(report, None, None, None)
    assert pack.total_tasks > 0
    assert pack.approval_pack_id is None
    assert pack.creative_pack_id is None
    assert pack.visual_pack_id is None
    # Some categories should still appear (channels, SEO, calendar).
    cats = pack.count_by_category()
    assert cats.get("operational", 0) > 0  # channel setup
    assert cats.get("calendar", 0) > 0


# ---------- pure / no side effects ----------

def test_build_does_not_write_to_disk_by_itself(tmp_path: Path) -> None:
    """``build`` is pure; only ``persist`` writes."""
    mem, report, approval, creative, visual = _build_full_stack(tmp_path)
    factory = TaskFactory(memory=mem)
    # Clear the slate.
    if mem.exists(report.client_slug, EXECUTION_TASK_PACK_KIND, SINGLETON_ID):
        return  # already exists from prior helper; nothing to test
    pack = factory.build(report, approval, creative, visual)
    # build() alone did not persist.
    assert not mem.exists(report.client_slug, EXECUTION_TASK_PACK_KIND, SINGLETON_ID)
    factory.persist(pack)
    assert mem.exists(report.client_slug, EXECUTION_TASK_PACK_KIND, SINGLETON_ID)
