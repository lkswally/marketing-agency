"""CLI tests for ``mkt ads-feedback``."""

from __future__ import annotations

import io
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from cli.main import main
from core.ads_analysis import (
    AdsInsightAction,
    AdsInsightKind,
    AdsInsightSeverity,
    AdsInsightStats,
    GoogleAdsInsight,
    GoogleAdsInsightPack,
)
from core.ads_analysis.models import GOOGLE_ADS_INSIGHT_PACK_KIND
from core.memory import JsonFileMemory


def _run(argv: list[str]) -> tuple[int, str]:
    out = io.StringIO()
    code = main(argv, out=out)
    return code, out.getvalue()


def _seed_insight_pack(root: Path, *, client: str = "acme") -> None:
    mem = JsonFileMemory(root)
    insight = GoogleAdsInsight(
        kind=AdsInsightKind.HIGH_SPEND_ZERO_CONV,
        severity=AdsInsightSeverity.HIGH,
        suggested_action=AdsInsightAction.PAUSE_CANDIDATE,
        title="High spend zero conv",
        rationale="Spent $120 with 0 conversions.",
        content_ref="campaign:42::ad_group:100",
        campaign_id="42",
        ad_group_id="100",
        dimension="Brand / Wasteful",
        evidence={"cost": 120.0, "conversions": 0.0},
        thresholds_used={"min_cost": 50.0},
    )
    pack = GoogleAdsInsightPack(
        client_slug=client,
        snapshot_id="snap-1",
        snapshot_contract_version="metrics-snapshot.v1",
        profiles=[],
        insights=[insight],
        stats=AdsInsightStats(
            total_insights=1,
            by_severity={"high": 1},
            by_kind={"high_spend_zero_conv": 1},
            by_action={"pause_candidate": 1},
            ad_groups_profiled=1,
            rows_analyzed=4,
        ),
        created_at=datetime(2026, 6, 4, tzinfo=UTC),
        rule_set_id="ads-analyzer.v1",
    )
    mem.put(client, GOOGLE_ADS_INSIGHT_PACK_KIND, "current",
            pack.model_dump(mode="json"))


def test_ads_feedback_happy_path(tmp_path: Path) -> None:
    _seed_insight_pack(tmp_path / "mem")
    code, stdout = _run([
        "ads-feedback",
        "--client", "acme",
        "--root", str(tmp_path / "mem"),
        "--outputs-dir", str(tmp_path / "out"),
    ])
    assert code == 0, stdout
    payload = json.loads(stdout)
    assert payload["client_slug"] == "acme"
    assert payload["contract_version"] == "ads-feedback-bridge-pack.v1"
    assert payload["stats"]["total_recommendations"] == 1
    assert payload["stats"]["total_campaign_adjustments"] == 1
    assert payload["stats"]["total_suggested_tasks"] == 2  # rec + measurement
    assert Path(payload["markdown_path"]).exists()
    assert Path(payload["json_path"]).exists()


def test_ads_feedback_exit_2_when_no_insight_pack(tmp_path: Path) -> None:
    code, stdout = _run([
        "ads-feedback",
        "--client", "acme",
        "--root", str(tmp_path / "mem"),
        "--outputs-dir", str(tmp_path / "out"),
    ])
    assert code == 2
    assert "no GoogleAdsInsightPack" in stdout


def test_ads_feedback_missing_client(tmp_path: Path) -> None:
    with pytest.raises(SystemExit) as exc:
        _run([
            "ads-feedback",
            "--root", str(tmp_path / "mem"),
        ])
    assert exc.value.code == 2


def test_ads_feedback_writes_audit(tmp_path: Path) -> None:
    _seed_insight_pack(tmp_path / "mem")
    code, _ = _run([
        "ads-feedback",
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
    assert "ads_feedback_bridge_pack" in content
    assert "bridged" in content
