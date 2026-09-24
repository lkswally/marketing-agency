"""Tests for the metrics ingestion + analysis application services
(architecture/application-service-boundary, batch 2)."""

from __future__ import annotations

import json
from pathlib import Path

from core.application import OperationContext
from core.application.result import ErrorCode
from core.application.services.metrics import analyze_metrics, import_metrics
from core.memory import JsonFileMemory

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES = REPO_ROOT / "tests" / "fixtures" / "analytics"


def _ctx(tmp_path: Path, client: str = "acme") -> OperationContext:
    return OperationContext(
        client_slug=client, root=tmp_path / "mem", outputs_root=tmp_path / "out",
    )


# ---------- import_metrics: happy path ----------

def test_import_valid_csv_succeeds(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    result = import_metrics(ctx, source="ga4", file_path=FIXTURES / "ga4_demo.csv")
    assert result.ok
    assert result.data["report"].source.value == "ga4"
    assert result.data["report"].rows_imported > 0
    assert len(result.artifacts) == 2


def test_import_writes_md_and_json(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    result = import_metrics(ctx, source="ga4", file_path=FIXTURES / "ga4_demo.csv")
    md_path = tmp_path / "out" / "analytics-import-report.md"
    json_path = tmp_path / "out" / "analytics-import-report.json"
    assert md_path.exists()
    assert json_path.exists()
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["client_slug"] == "acme"
    paths = {str(a.path) for a in result.artifacts}
    assert str(md_path) in paths
    assert str(json_path) in paths


# ---------- import_metrics: persistence + audit ----------

def test_import_persists_snapshot(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    import_metrics(ctx, source="ga4", file_path=FIXTURES / "ga4_demo.csv")
    mem = JsonFileMemory(tmp_path / "mem")
    assert mem.exists("acme", "metrics_snapshot", "current")
    assert mem.exists("acme", "analytics_import_report", "current")


def test_import_writes_audit_event(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    import_metrics(ctx, source="ga4", file_path=FIXTURES / "ga4_demo.csv")
    mem = JsonFileMemory(tmp_path / "mem")
    events = mem.read_audit_events("acme")
    import_events = [e for e in events if "analytics_import" in e.payload]
    assert len(import_events) == 1
    assert import_events[0].payload["analytics_import"]["action"] == "imported"


# ---------- import_metrics: error mapping ----------

def test_import_unsupported_extension_rejected(tmp_path: Path) -> None:
    bad = tmp_path / "data.txt"
    bad.write_text("x", encoding="utf-8")
    ctx = _ctx(tmp_path)
    result = import_metrics(ctx, source="ga4", file_path=bad)
    assert not result.ok
    assert result.error.code is ErrorCode.INVALID_INPUT
    assert "unsupported" in result.error.message


def test_import_invalid_source_rejected(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    result = import_metrics(ctx, source="not-a-real-source", file_path=FIXTURES / "ga4_demo.csv")
    assert not result.ok
    assert result.error.code is ErrorCode.INVALID_INPUT


def test_import_malformed_period_date_rejected(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    result = import_metrics(
        ctx, source="ga4", file_path=FIXTURES / "ga4_demo.csv", period_start="not-a-date",
    )
    assert not result.ok
    assert result.error.code is ErrorCode.INVALID_INPUT


# ---------- import_metrics: tenant/root isolation ----------

def test_import_two_clients_do_not_cross_contaminate(tmp_path: Path) -> None:
    ctx_a = _ctx(tmp_path, "acme")
    ctx_b = _ctx(tmp_path, "other-client")
    import_metrics(ctx_a, source="ga4", file_path=FIXTURES / "ga4_demo.csv")

    mem = JsonFileMemory(tmp_path / "mem")
    assert mem.exists("acme", "metrics_snapshot", "current")
    assert not mem.exists("other-client", "metrics_snapshot", "current")

    result_b = analyze_metrics(ctx_b)
    assert not result_b.ok
    assert result_b.error.code is ErrorCode.NOT_FOUND


# ---------- analyze_metrics: happy path ----------

def _import_all(tmp_path: Path, client: str = "acme") -> None:
    for fixture, source in [
        ("ga4_demo.csv", "ga4"),
        ("sc_demo.csv", "search_console"),
        ("social_demo.csv", "social"),
        ("email_demo.csv", "email"),
    ]:
        ctx = _ctx(tmp_path, client)
        result = import_metrics(ctx, source=source, file_path=FIXTURES / fixture)
        assert result.ok


def test_analyze_after_imports_succeeds(tmp_path: Path) -> None:
    _import_all(tmp_path)
    ctx = _ctx(tmp_path)
    result = analyze_metrics(ctx)
    assert result.ok
    assert result.data.best_channel
    assert len(result.data.recommendations) > 0


def test_analyze_persists_and_writes(tmp_path: Path) -> None:
    _import_all(tmp_path)
    ctx = _ctx(tmp_path)
    result = analyze_metrics(ctx)
    mem = JsonFileMemory(tmp_path / "mem")
    assert mem.exists("acme", "optimization_recommendation_pack", "current")
    md_path = tmp_path / "out" / "analytics-recommendations.md"
    json_path = tmp_path / "out" / "analytics-recommendations.json"
    assert md_path.exists()
    assert json_path.exists()
    assert len(result.artifacts) == 2


def test_analyze_writes_audit_event(tmp_path: Path) -> None:
    _import_all(tmp_path)
    ctx = _ctx(tmp_path)
    analyze_metrics(ctx)
    mem = JsonFileMemory(tmp_path / "mem")
    events = mem.read_audit_events("acme")
    analysis_events = [e for e in events if "analytics_analysis" in e.payload]
    assert len(analysis_events) == 1
    assert analysis_events[0].payload["analytics_analysis"]["action"] == "analyzed"


# ---------- analyze_metrics: error mapping ----------

def test_analyze_missing_snapshot_returns_not_found(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path, "ghost")
    result = analyze_metrics(ctx)
    assert not result.ok
    assert result.error.code is ErrorCode.NOT_FOUND
    assert "MetricsSnapshot" in result.error.message
