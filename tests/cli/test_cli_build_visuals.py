"""CLI tests for `mkt build-visuals`."""

from __future__ import annotations

import io
import json
from pathlib import Path

from cli.main import main

REPO_ROOT = Path(__file__).resolve().parents[2]
DEMO_BRIEF = REPO_ROOT / "examples" / "clients" / "demo-saas" / "brief.json"


def _run(argv: list[str]) -> tuple[int, str]:
    out = io.StringIO()
    code = main(argv, out=out)
    return code, out.getvalue()


def _setup_full_chain(tmp_path: Path) -> Path:
    """Run strategy + audit + creatives, return memory root."""
    root = tmp_path / "mem"
    out_dir = tmp_path / "out"
    code, _ = _run(
        [
            "run-strategy",
            "--brief", str(DEMO_BRIEF),
            "--root", str(root),
            "--outputs-dir", str(out_dir),
            "--audit",
        ]
    )
    assert code == 0
    code, _ = _run(
        [
            "build-creatives",
            "--client", "demo-saas",
            "--root", str(root),
            "--outputs-dir", str(out_dir),
        ]
    )
    assert code == 0
    return root


# ---------- happy path ----------

def test_build_visuals_full_chain(tmp_path: Path) -> None:
    root = _setup_full_chain(tmp_path)
    code, text = _run(
        [
            "build-visuals",
            "--client", "demo-saas",
            "--root", str(root),
            "--outputs-dir", str(tmp_path / "out"),
        ]
    )
    assert code == 0
    payload = json.loads(text)
    assert payload["client_slug"] == "demo-saas"
    assert payload["total_directions"] == 11
    assert payload["total_prompt_variants"] == 22
    assert payload["derived_overall_state"] in {"draft", "needs_review", "ready_for_publish", "blocked"}
    assert payload["rule_set_id"] == "default-visual-rules.v1"

    # Disk side effects.
    md_path = Path(payload["markdown_path"])
    json_path = Path(payload["json_path"])
    assert md_path.exists()
    assert json_path.exists()
    text_md = md_path.read_text(encoding="utf-8")
    assert text_md.startswith("# Visual Direction Pack")

    # Memory persistence.
    assert (root / "demo-saas" / "visual_direction_pack" / "current.json").exists()


def test_build_visuals_without_creative_pack_works(tmp_path: Path) -> None:
    """Visuals can be built from only strategy + approval (no creative pack)."""
    root = tmp_path / "mem"
    out_dir = tmp_path / "out"
    # Only strategy + audit, NOT build-creatives.
    _run(
        [
            "run-strategy",
            "--brief", str(DEMO_BRIEF),
            "--root", str(root),
            "--outputs-dir", str(out_dir),
            "--audit",
        ]
    )
    code, text = _run(
        [
            "build-visuals",
            "--client", "demo-saas",
            "--root", str(root),
            "--outputs-dir", str(tmp_path / "out"),
        ]
    )
    assert code == 0
    payload = json.loads(text)
    assert payload["creative_pack_id"] is None
    assert payload["total_directions"] == 11


def test_build_visuals_without_approval_pack_is_needs_review(tmp_path: Path) -> None:
    """No approval pack → state defaults to needs_review per ADR 0012."""
    root = tmp_path / "mem"
    out_dir = tmp_path / "out"
    _run(
        [
            "run-strategy",
            "--brief", str(DEMO_BRIEF),
            "--root", str(root),
            "--outputs-dir", str(out_dir),
        ]
    )
    code, text = _run(
        [
            "build-visuals",
            "--client", "demo-saas",
            "--root", str(root),
            "--outputs-dir", str(tmp_path / "out"),
        ]
    )
    assert code == 0
    payload = json.loads(text)
    assert payload["derived_overall_state"] == "needs_review"
    assert payload["approval_pack_id"] is None


# ---------- missing report ----------

def test_build_visuals_without_strategy_fails(tmp_path: Path) -> None:
    code, text = _run(
        [
            "build-visuals",
            "--client", "demo-saas",
            "--root", str(tmp_path / "empty"),
            "--outputs-dir", str(tmp_path / "out"),
        ]
    )
    assert code == 2
    assert "no CampaignStrategyReport" in text


# ---------- require-approval ----------

def test_require_approval_blocks_when_pack_blocks_publish(tmp_path: Path) -> None:
    root = _setup_full_chain(tmp_path)

    from core.approval import ApprovalPackBuilder
    from core.memory import JsonFileMemory
    from core.strategy import REPORT_KIND, SINGLETON_ID, CampaignStrategyReport

    mem = JsonFileMemory(root)
    raw = mem.get("demo-saas", REPORT_KIND, SINGLETON_ID)
    report = CampaignStrategyReport.model_validate(raw)
    report.value_proposition.headline = (
        "Te aseguramos resultados garantizados sin riesgo"
    )
    mem.put("demo-saas", REPORT_KIND, SINGLETON_ID, report.model_dump(mode="json"))
    builder = ApprovalPackBuilder(memory=mem)
    risky_ap = builder.build_from_report(report)
    builder.persist(risky_ap)
    assert risky_ap.blocks_publish is True

    code, text = _run(
        [
            "build-visuals",
            "--client", "demo-saas",
            "--root", str(root),
            "--outputs-dir", str(tmp_path / "out"),
            "--require-approval",
        ]
    )
    assert code == 3
    assert "blocks publish" in text


# ---------- audit trail ----------

def test_audit_trail_records_visual_pack(tmp_path: Path) -> None:
    root = _setup_full_chain(tmp_path)
    _run(
        [
            "build-visuals",
            "--client", "demo-saas",
            "--root", str(root),
            "--outputs-dir", str(tmp_path / "out"),
        ]
    )
    from core.contracts import verify_chain
    from core.memory import JsonFileMemory

    mem = JsonFileMemory(root)
    events = mem.read_audit_events("demo-saas")
    actions = [
        e.payload.get("visual_pack", {}).get("action")
        for e in events
        if "visual_pack" in e.payload
    ]
    assert "created" in actions
    assert verify_chain(events) == []
