"""Tests for the Campaign Execution Task Pack application service
(architecture/application-service-boundary)."""

from __future__ import annotations

import json
from pathlib import Path

from core.application import OperationContext
from core.application.result import ErrorCode
from core.application.services.tasks import build_task_pack
from core.memory import JsonFileMemory
from core.strategy import StrategyPipeline

REPO_ROOT = Path(__file__).resolve().parents[2]
DEMO_BRIEF = REPO_ROOT / "examples" / "clients" / "demo-saas" / "brief.json"


def _ctx(tmp_path: Path, client: str = "demo-saas") -> OperationContext:
    return OperationContext(
        client_slug=client, root=tmp_path / "mem", outputs_root=tmp_path / "out",
    )


def _seed_report(tmp_path: Path):
    mem = JsonFileMemory(tmp_path / "mem")
    return StrategyPipeline(memory=mem).run_from_path(DEMO_BRIEF).report


# ---------- happy path ----------

def test_build_from_report_only(tmp_path: Path) -> None:
    report = _seed_report(tmp_path)
    ctx = _ctx(tmp_path, report.client_slug)
    result = build_task_pack(ctx)
    assert result.ok
    assert result.data.client_slug == report.client_slug
    assert result.data.report_id == report.report_id
    assert result.data.total_tasks > 0


def test_writes_three_files(tmp_path: Path) -> None:
    report = _seed_report(tmp_path)
    ctx = _ctx(tmp_path, report.client_slug)
    result = build_task_pack(ctx)
    assert len(result.artifacts) == 3
    md_path = tmp_path / "out" / "campaign-execution-tasks.md"
    json_path = tmp_path / "out" / "campaign-execution-tasks.json"
    notion_path = tmp_path / "out" / "notion-task-payload.json"
    assert md_path.exists()
    assert json_path.exists()
    assert notion_path.exists()
    notion_payload = json.loads(notion_path.read_text(encoding="utf-8"))
    assert isinstance(notion_payload, (dict, list))


def test_persists_pack(tmp_path: Path) -> None:
    report = _seed_report(tmp_path)
    ctx = _ctx(tmp_path, report.client_slug)
    result = build_task_pack(ctx)
    mem = JsonFileMemory(tmp_path / "mem")
    from core.execution import EXECUTION_TASK_PACK_KIND, SINGLETON_ID

    stored = mem.get(report.client_slug, EXECUTION_TASK_PACK_KIND, SINGLETON_ID)
    assert stored["pack_id"] == result.data.pack_id


def test_records_audit_event(tmp_path: Path) -> None:
    report = _seed_report(tmp_path)
    ctx = _ctx(tmp_path, report.client_slug)
    build_task_pack(ctx)
    mem = JsonFileMemory(tmp_path / "mem")
    events = mem.read_audit_events(report.client_slug)
    task_events = [e for e in events if "execution_task_pack" in e.payload]
    assert len(task_events) == 1
    assert task_events[0].payload["execution_task_pack"]["action"] == "built"


# ---------- error mapping ----------

def test_missing_report_returns_not_found(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path, "no-such-client")
    result = build_task_pack(ctx)
    assert not result.ok
    assert result.error.code is ErrorCode.NOT_FOUND


# ---------- ads-bridge opt-in (no pack present -> no-op, not an error) ----------

def test_include_ads_bridge_without_bridge_pack_is_a_noop(tmp_path: Path) -> None:
    report = _seed_report(tmp_path)
    ctx = _ctx(tmp_path, report.client_slug)
    result = build_task_pack(ctx, include_ads_bridge=True)
    assert result.ok


# ---------- tenant isolation ----------

def test_two_clients_do_not_cross_contaminate(tmp_path: Path) -> None:
    report_a = _seed_report(tmp_path)
    ctx_a = _ctx(tmp_path, report_a.client_slug)
    assert build_task_pack(ctx_a).ok

    ctx_b = _ctx(tmp_path, "totally-different-client")
    result_b = build_task_pack(ctx_b)
    assert not result_b.ok
    assert result_b.error.code is ErrorCode.NOT_FOUND
