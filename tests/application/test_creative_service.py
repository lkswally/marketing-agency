"""Tests for the Creative Asset Pack application service
(architecture/application-service-boundary)."""

from __future__ import annotations

import json
from pathlib import Path

from core.application import OperationContext
from core.application.result import ErrorCode
from core.application.services.creative import build_creative_pack
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

def test_build_without_approval(tmp_path: Path) -> None:
    report = _seed_report(tmp_path)
    ctx = _ctx(tmp_path, report.client_slug)
    result = build_creative_pack(ctx)
    assert result.ok
    assert len(result.artifacts) == 2
    assert result.data.client_slug == report.client_slug
    assert result.data.report_id == report.report_id


def test_json_and_markdown_written(tmp_path: Path) -> None:
    report = _seed_report(tmp_path)
    ctx = _ctx(tmp_path, report.client_slug)
    result = build_creative_pack(ctx)
    md_path = tmp_path / "out" / "creative-pack.md"
    json_path = tmp_path / "out" / "creative-pack.json"
    assert md_path.exists()
    assert json_path.exists()
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["client_slug"] == report.client_slug
    paths = {str(a.path) for a in result.artifacts}
    assert str(md_path) in paths
    assert str(json_path) in paths


def test_persist_writes_audit_event(tmp_path: Path) -> None:
    report = _seed_report(tmp_path)
    ctx = _ctx(tmp_path, report.client_slug)
    build_creative_pack(ctx)
    mem = JsonFileMemory(tmp_path / "mem")
    events = mem.read_audit_events(report.client_slug)
    creative_events = [e for e in events if "creative_pack" in e.payload]
    assert len(creative_events) == 1
    assert creative_events[0].payload["creative_pack"]["action"] == "created"


# ---------- error mapping ----------

def test_missing_report_returns_not_found(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path, "no-such-client")
    result = build_creative_pack(ctx)
    assert not result.ok
    assert result.error.code is ErrorCode.NOT_FOUND


def test_require_approval_blocks_when_pack_blocks_publish(tmp_path: Path) -> None:
    report = _seed_report(tmp_path)
    mem = JsonFileMemory(tmp_path / "mem")
    builder = ApprovalPackBuilder(mem)
    pack = builder.build_from_report(report)
    # Force a blocking state without going through the full claim-audit
    # rule engine — this mirrors the existing CLI test's own approach.
    pack = pack.model_copy(update={"blocks_publish": True})
    mem.put(report.client_slug, "approval_pack", pack.pack_id, pack.model_dump(mode="json"))

    ctx = _ctx(tmp_path, report.client_slug)
    result = build_creative_pack(ctx, require_approval=True)
    assert not result.ok
    assert result.error.code is ErrorCode.POLICY_BLOCKED
    # This gate runs BEFORE the factory does any work — no side effects
    # to report, unlike intake's --strict (which blocks AFTER persisting).
    assert result.artifacts == []
    assert result.audit_event_id is None
    assert not mem.exists(report.client_slug, "creative_asset_pack", "current")


def test_require_approval_passes_when_clean(tmp_path: Path) -> None:
    report = _seed_report(tmp_path)
    mem = JsonFileMemory(tmp_path / "mem")
    builder = ApprovalPackBuilder(mem)
    pack = builder.build_from_report(report)
    builder.persist(pack)
    approved = builder.approve(report.client_slug, pack.pack_id, reviewer="qa")
    assert approved.blocks_publish is False

    ctx = _ctx(tmp_path, report.client_slug)
    result = build_creative_pack(ctx, require_approval=True)
    assert result.ok


# ---------- tenant isolation ----------

def test_two_clients_do_not_cross_contaminate(tmp_path: Path) -> None:
    """A strategy report seeded only for ``report_a.client_slug`` must not
    be visible when building the pack for an unrelated client_slug under
    the same memory root."""
    report_a = _seed_report(tmp_path)
    ctx_a = _ctx(tmp_path, report_a.client_slug)
    result_a = build_creative_pack(ctx_a)
    assert result_a.ok

    ctx_b = _ctx(tmp_path, "totally-different-client")
    result_b = build_creative_pack(ctx_b)
    assert not result_b.ok
    assert result_b.error.code is ErrorCode.NOT_FOUND


def test_root_scoping_uses_ctx_root_not_a_global(tmp_path: Path) -> None:
    """A second OperationContext pointed at a DIFFERENT `root` (same
    client_slug) must not see data seeded under the first root — proves
    the service never falls back to a process-global memory root."""
    report = _seed_report(tmp_path)
    other_root = tmp_path / "other-mem"
    ctx_other_root = OperationContext(
        client_slug=report.client_slug, root=other_root, outputs_root=tmp_path / "out2",
    )
    result = build_creative_pack(ctx_other_root)
    assert not result.ok
    assert result.error.code is ErrorCode.NOT_FOUND
