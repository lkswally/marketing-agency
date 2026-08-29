"""Tests for the SEO application service (MKT-11A)."""

from __future__ import annotations

import json
from pathlib import Path

from core.application import OperationContext
from core.application.result import ErrorCode
from core.application.services.seo import build_seo_report
from core.memory import JsonFileMemory


def _ctx(tmp_path: Path, client: str = "acme") -> OperationContext:
    return OperationContext(
        client_slug=client, root=tmp_path / "mem", outputs_root=tmp_path / "out",
    )


# ---------- happy path ----------

def test_build_no_evidence(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    result = build_seo_report(ctx)
    assert result.ok
    assert len(result.artifacts) == 2
    assert result.data.client_slug == "acme"
    assert len(result.data.missing_evidence) > 0


def test_json_and_markdown_written(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    result = build_seo_report(ctx)
    md_path = tmp_path / "out" / "seo-intelligence-report.md"
    json_path = tmp_path / "out" / "seo-intelligence-report.json"
    assert md_path.exists()
    assert json_path.exists()
    assert "SEO Intelligence Report" in md_path.read_text(encoding="utf-8")
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["client_slug"] == "acme"
    paths = {str(a.path) for a in result.artifacts}
    assert str(md_path) in paths
    assert str(json_path) in paths


# ---------- audit trail ----------

def test_persist_writes_audit_event(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    build_seo_report(ctx)
    mem = JsonFileMemory(tmp_path / "mem")
    events = mem.read_audit_events("acme")
    assert len(events) == 1
    assert events[0].payload["seo_intelligence_report_pack"]["action"] == "built"


# ---------- dry-run ----------

def test_dry_run_does_not_persist_or_write(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    result = build_seo_report(ctx, dry_run=True)
    assert result.ok
    assert all(a.would_write for a in result.artifacts)
    assert not (tmp_path / "out").exists()
    assert not (tmp_path / "mem").exists()


# ---------- overwrite ----------

def test_overwrite_false_blocks_second_run(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    r1 = build_seo_report(ctx)
    assert r1.ok
    r2 = build_seo_report(ctx)
    assert not r2.ok
    assert r2.error.code is ErrorCode.ALREADY_EXISTS


def test_overwrite_true_replaces(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    build_seo_report(ctx)
    r2 = build_seo_report(ctx, overwrite=True)
    assert r2.ok


# ---------- multi-tenant isolation ----------

def test_multi_tenant_isolation(tmp_path: Path) -> None:
    # Memory is per-tenant even though this service's FLAT output layout
    # shares one outputs_root — mirrored from the pre-11A CLI behaviour
    # (see docs/MKT-11A-Application-Services-Inventory.md, F-1). Use
    # overwrite=True on the second call so the shared-file collision
    # doesn't mask the thing this test actually checks: memory isolation.
    ctx_acme = _ctx(tmp_path, "acme")
    ctx_other = _ctx(tmp_path, "other-client")
    r1 = build_seo_report(ctx_acme)
    r2 = build_seo_report(ctx_other, overwrite=True)
    assert r1.ok and r2.ok
    mem = JsonFileMemory(tmp_path / "mem")
    acme_pack = mem.get("acme", "seo_intelligence_report_pack", "current")
    other_pack = mem.get("other-client", "seo_intelligence_report_pack", "current")
    assert acme_pack["client_slug"] == "acme"
    assert other_pack["client_slug"] == "other-client"
    assert acme_pack["report_id"] != other_pack["report_id"]


# ---------- determinism ----------

def test_determinism(tmp_path: Path) -> None:
    ctx1 = _ctx(tmp_path, "acme")
    ctx2 = OperationContext(
        client_slug="acme", root=tmp_path / "mem2", outputs_root=tmp_path / "out2",
    )
    r1 = build_seo_report(ctx1)
    r2 = build_seo_report(ctx2)
    assert r1.data.executive_summary.facts_count == r2.data.executive_summary.facts_count
    assert len(r1.data.missing_evidence) == len(r2.data.missing_evidence)


# ---------- errors ----------

def test_invalid_input_file_missing(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    result = build_seo_report(ctx, input_path=str(tmp_path / "nope.json"))
    assert not result.ok
    assert result.error.code is ErrorCode.INVALID_INPUT


def test_invalid_input_file_malformed(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    ctx = _ctx(tmp_path)
    result = build_seo_report(ctx, input_path=str(bad))
    assert not result.ok
    assert result.error.code is ErrorCode.INVALID_INPUT


def test_invalid_start_date(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    result = build_seo_report(ctx, start_date="not-a-date")
    assert not result.ok
    assert result.error.code is ErrorCode.INVALID_INPUT


# ---------- path traversal ----------

def test_artifact_paths_stay_inside_outputs_root(tmp_path: Path) -> None:
    """This service always uses fixed, safe filenames — the path-escape
    scenario itself (crafted filenames) is exercised directly against
    the writer in test_artifacts.py. Here we just pin that every
    artifact this service produces resolves under its own outputs_root."""
    ctx = _ctx(tmp_path)
    result = build_seo_report(ctx)
    out_root_resolved = (tmp_path / "out").resolve()
    for artifact in result.artifacts:
        artifact.path.resolve().relative_to(out_root_resolved)  # raises if outside
