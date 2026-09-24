"""Tests for the Visual Direction Pack application service
(architecture/application-service-boundary)."""

from __future__ import annotations

import json
from pathlib import Path

from core.application import OperationContext
from core.application.result import ErrorCode
from core.application.services.creative import build_creative_pack
from core.application.services.visual import build_visual_pack
from core.approval import ApprovalPackBuilder
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

def test_build_without_creative_pack(tmp_path: Path) -> None:
    report = _seed_report(tmp_path)
    ctx = _ctx(tmp_path, report.client_slug)
    result = build_visual_pack(ctx)
    assert result.ok
    assert len(result.artifacts) == 2
    assert result.data.client_slug == report.client_slug
    assert result.data.creative_pack_id is None


def test_build_with_creative_pack(tmp_path: Path) -> None:
    report = _seed_report(tmp_path)
    ctx = _ctx(tmp_path, report.client_slug)
    creative_result = build_creative_pack(ctx)
    assert creative_result.ok

    result = build_visual_pack(ctx)
    assert result.ok
    assert result.data.creative_pack_id == creative_result.data.pack_id


def test_json_and_markdown_written(tmp_path: Path) -> None:
    report = _seed_report(tmp_path)
    ctx = _ctx(tmp_path, report.client_slug)
    build_visual_pack(ctx)
    md_path = tmp_path / "out" / "visual-direction-pack.md"
    json_path = tmp_path / "out" / "visual-direction-pack.json"
    assert md_path.exists()
    assert json_path.exists()
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["client_slug"] == report.client_slug


def test_persist_writes_audit_event(tmp_path: Path) -> None:
    report = _seed_report(tmp_path)
    ctx = _ctx(tmp_path, report.client_slug)
    build_visual_pack(ctx)
    mem = JsonFileMemory(tmp_path / "mem")
    events = mem.read_audit_events(report.client_slug)
    visual_events = [e for e in events if "visual_pack" in e.payload]
    assert len(visual_events) == 1
    assert visual_events[0].payload["visual_pack"]["action"] == "created"


# ---------- error mapping ----------

def test_missing_report_returns_not_found(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path, "no-such-client")
    result = build_visual_pack(ctx)
    assert not result.ok
    assert result.error.code is ErrorCode.NOT_FOUND


def test_require_approval_blocks_when_pack_blocks_publish(tmp_path: Path) -> None:
    report = _seed_report(tmp_path)
    mem = JsonFileMemory(tmp_path / "mem")
    builder = ApprovalPackBuilder(mem)
    pack = builder.build_from_report(report)
    pack = pack.model_copy(update={"blocks_publish": True})
    mem.put(report.client_slug, "approval_pack", pack.pack_id, pack.model_dump(mode="json"))

    ctx = _ctx(tmp_path, report.client_slug)
    result = build_visual_pack(ctx, require_approval=True)
    assert not result.ok
    assert result.error.code is ErrorCode.POLICY_BLOCKED
    assert result.artifacts == []
    assert result.audit_event_id is None
    assert not mem.exists(report.client_slug, "visual_direction_pack", "current")


# ---------- tenant isolation ----------

def test_two_clients_do_not_cross_contaminate(tmp_path: Path) -> None:
    report_a = _seed_report(tmp_path)
    ctx_a = _ctx(tmp_path, report_a.client_slug)
    assert build_visual_pack(ctx_a).ok

    ctx_b = _ctx(tmp_path, "totally-different-client")
    result_b = build_visual_pack(ctx_b)
    assert not result_b.ok
    assert result_b.error.code is ErrorCode.NOT_FOUND
