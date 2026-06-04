"""CLI tests for ``mkt ads-analyze``."""

from __future__ import annotations

import io
import json
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from cli.main import main
from core.analytics.models import (
    METRICS_SNAPSHOT_KIND,
    SINGLETON_ID,
    MetricRow,
    MetricSource,
    MetricsSnapshot,
)
from core.memory import JsonFileMemory


def _run(argv: list[str]) -> tuple[int, str]:
    out = io.StringIO()
    code = main(argv, out=out)
    return code, out.getvalue()


def _seed_snapshot(root: Path, *, client: str = "acme") -> None:
    mem = JsonFileMemory(root)
    now = datetime(2026, 6, 4, tzinfo=UTC)
    rows = []
    for metric, value in (
        ("impressions", 2000.0), ("clicks", 80.0),
        ("cost", 120.0), ("conversions", 0.0),
        ("conversions_value", 0.0),
    ):
        rows.append(MetricRow(
            source=MetricSource.GOOGLE_ADS,
            event_date=date(2026, 5, 15),
            channel="google_ads",
            content_ref="campaign:1::ad_group:100",
            dimension="Brand / Wasteful",
            metric_name=metric,
            value=value,
        ))
    snap = MetricsSnapshot(
        client_slug=client, rows=rows,
        created_at=now, updated_at=now,
    )
    mem.put(client, METRICS_SNAPSHOT_KIND, SINGLETON_ID,
            snap.model_dump(mode="json"))


def test_ads_analyze_happy_path(tmp_path: Path) -> None:
    _seed_snapshot(tmp_path / "mem")
    code, stdout = _run([
        "ads-analyze",
        "--client", "acme",
        "--root", str(tmp_path / "mem"),
        "--outputs-dir", str(tmp_path / "out"),
    ])
    assert code == 0, stdout
    payload = json.loads(stdout)
    assert payload["client_slug"] == "acme"
    assert payload["contract_version"] == "google-ads-insight-pack.v1"
    assert payload["stats"]["total_insights"] >= 1
    assert Path(payload["markdown_path"]).exists()
    assert Path(payload["json_path"]).exists()
    md = Path(payload["markdown_path"]).read_text(encoding="utf-8")
    assert "Google Ads Insight Pack" in md
    assert "Read-only" in md


def test_ads_analyze_exit_2_when_no_snapshot(tmp_path: Path) -> None:
    code, stdout = _run([
        "ads-analyze",
        "--client", "acme",
        "--root", str(tmp_path / "mem"),
        "--outputs-dir", str(tmp_path / "out"),
    ])
    assert code == 2
    assert "no MetricsSnapshot" in stdout


def test_ads_analyze_missing_client_arg(tmp_path: Path) -> None:
    with pytest.raises(SystemExit) as exc:
        _run([
            "ads-analyze",
            "--root", str(tmp_path / "mem"),
        ])
    assert exc.value.code == 2


def test_ads_analyze_writes_audit(tmp_path: Path) -> None:
    _seed_snapshot(tmp_path / "mem")
    code, _ = _run([
        "ads-analyze",
        "--client", "acme",
        "--root", str(tmp_path / "mem"),
        "--outputs-dir", str(tmp_path / "out"),
    ])
    assert code == 0
    audit_root = tmp_path / "mem" / "acme" / "audit"
    assert audit_root.exists()
    content = "\n".join(
        f.read_text(encoding="utf-8") for f in audit_root.glob("*.jsonl")
    )
    assert "google_ads_insight_pack" in content
    assert "analyzed" in content
