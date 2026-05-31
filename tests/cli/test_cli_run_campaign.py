"""CLI tests for `mkt run-campaign`."""

from __future__ import annotations

import io
import json
from pathlib import Path

from cli.main import main

REPO_ROOT = Path(__file__).resolve().parents[2]
DEMO_INTAKE = REPO_ROOT / "examples" / "intake" / "demo-business.json"


def _run(argv: list[str]) -> tuple[int, str]:
    out = io.StringIO()
    code = main(argv, out=out)
    return code, out.getvalue()


def test_run_campaign_demo_succeeds(tmp_path: Path) -> None:
    code, text = _run(
        [
            "run-campaign",
            "--intake", str(DEMO_INTAKE),
            "--root", str(tmp_path / "mem"),
            "--outputs-dir", str(tmp_path / "out"),
        ]
    )
    assert code == 0
    payload = json.loads(text)
    assert payload["client_slug"] == "acme-bootstrapped"
    assert payload["is_complete"] is True
    assert payload["overall_state"] == "draft"
    assert payload["blocks_publish"] is False
    assert payload["report_id"]
    assert payload["approval_pack_id"]
    assert payload["creative_pack_id"]
    assert payload["visual_pack_id"]
    assert payload["stage_counts"]["succeeded"] == 6


def test_run_campaign_writes_expected_files(tmp_path: Path) -> None:
    code, text = _run(
        [
            "run-campaign",
            "--intake", str(DEMO_INTAKE),
            "--root", str(tmp_path / "mem"),
            "--outputs-dir", str(tmp_path / "out"),
        ]
    )
    assert code == 0
    payload = json.loads(text)
    client_out = Path(payload["outputs_dir"])
    expected = [
        "intake.json",
        "intake-summary.md",
        "brief.json",
        "campaign-strategy.md",
        "approval-pack.md",
        "approval-pack.json",
        "creative-pack.md",
        "creative-pack.json",
        "visual-direction-pack.md",
        "visual-direction-pack.json",
        "campaign-final-summary.md",
        "campaign-final-summary.json",
    ]
    for name in expected:
        assert (client_out / name).exists(), f"missing output: {name}"


def test_run_campaign_missing_intake_fails(tmp_path: Path) -> None:
    code, text = _run(
        [
            "run-campaign",
            "--intake", str(tmp_path / "nope.json"),
            "--root", str(tmp_path / "mem"),
            "--outputs-dir", str(tmp_path / "out"),
        ]
    )
    assert code == 2
    assert "not found" in text


def test_run_campaign_strict_blocks_on_critical(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text(
        json.dumps({"schema_version": "client-intake.v1", "client_name": "Acme"}),
        encoding="utf-8",
    )
    code, text = _run(
        [
            "run-campaign",
            "--intake", str(bad),
            "--root", str(tmp_path / "mem"),
            "--outputs-dir", str(tmp_path / "out"),
            "--strict",
        ]
    )
    assert code == 4
    assert "strict" in text.lower() or "critical" in text.lower()


def test_run_campaign_require_approval_blocks_when_risky(tmp_path: Path) -> None:
    data = json.loads(DEMO_INTAKE.read_text(encoding="utf-8"))
    data["product_or_service"] = (
        "Demo Pro — te aseguramos resultados garantizados sin riesgo"
    )
    risky = tmp_path / "risky.json"
    risky.write_text(json.dumps(data), encoding="utf-8")
    code, text = _run(
        [
            "run-campaign",
            "--intake", str(risky),
            "--root", str(tmp_path / "mem"),
            "--outputs-dir", str(tmp_path / "out"),
            "--require-approval",
        ]
    )
    assert code == 3
    assert "blocks publish" in text


def test_run_campaign_stop_on_blocked_exits_zero(tmp_path: Path) -> None:
    data = json.loads(DEMO_INTAKE.read_text(encoding="utf-8"))
    data["product_or_service"] = (
        "Demo Pro — te aseguramos resultados garantizados sin riesgo"
    )
    risky = tmp_path / "risky.json"
    risky.write_text(json.dumps(data), encoding="utf-8")
    code, text = _run(
        [
            "run-campaign",
            "--intake", str(risky),
            "--root", str(tmp_path / "mem"),
            "--outputs-dir", str(tmp_path / "out"),
            "--stop-on-blocked",
        ]
    )
    assert code == 0
    payload = json.loads(text)
    assert payload["blocks_publish"] is True
    assert payload["stage_counts"]["skipped"] == 2


def test_audit_trail_records_pipeline_run(tmp_path: Path) -> None:
    _run(
        [
            "run-campaign",
            "--intake", str(DEMO_INTAKE),
            "--root", str(tmp_path / "mem"),
            "--outputs-dir", str(tmp_path / "out"),
        ]
    )
    from core.contracts import verify_chain
    from core.memory import JsonFileMemory

    mem = JsonFileMemory(tmp_path / "mem")
    events = mem.read_audit_events("acme-bootstrapped")
    actions = [
        e.payload.get("campaign_pipeline", {}).get("action")
        for e in events
        if "campaign_pipeline" in e.payload
    ]
    assert "started" in actions
    assert "finished" in actions
    assert verify_chain(events) == []
