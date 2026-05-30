"""CLI tests for `mkt build-creatives`."""

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


def _setup_strategy(tmp_path: Path, *, audit: bool = True) -> Path:
    """Helper: run strategy (+ optional audit) and return memory root."""
    root = tmp_path / "mem"
    out_dir = tmp_path / "out"
    argv = [
        "run-strategy",
        "--brief", str(DEMO_BRIEF),
        "--root", str(root),
        "--outputs-dir", str(out_dir),
    ]
    if audit:
        argv.append("--audit")
    code, _ = _run(argv)
    assert code == 0
    return root


# ---------- happy path ----------

def test_build_creatives_after_strategy_and_audit(tmp_path: Path) -> None:
    root = _setup_strategy(tmp_path, audit=True)
    code, text = _run(
        [
            "build-creatives",
            "--client", "demo-saas",
            "--root", str(root),
            "--outputs-dir", str(tmp_path / "out"),
        ]
    )
    assert code == 0
    payload = json.loads(text)
    assert payload["client_slug"] == "demo-saas"
    assert payload["total_assets"] > 0
    assert payload["rule_set_id"] == "default-templates.v1"

    # Disk side effects.
    md_path = Path(payload["markdown_path"])
    json_path = Path(payload["json_path"])
    assert md_path.exists()
    assert json_path.exists()
    text_md = md_path.read_text(encoding="utf-8")
    assert text_md.startswith("# Creative Asset Pack")

    # Persisted in memory.
    assert (root / "demo-saas" / "creative_asset_pack" / "current.json").exists()


def test_build_creatives_without_audit_works_but_state_is_needs_review(
    tmp_path: Path,
) -> None:
    """Running build-creatives without a prior audit pins state to needs_review."""
    root = _setup_strategy(tmp_path, audit=False)
    code, text = _run(
        [
            "build-creatives",
            "--client", "demo-saas",
            "--root", str(root),
            "--outputs-dir", str(tmp_path / "out"),
        ]
    )
    assert code == 0
    payload = json.loads(text)
    assert payload["derived_overall_state"] == "needs_review"
    assert payload["count_by_state"]["needs_review"] == payload["total_assets"]
    assert payload["count_by_state"]["draft"] == 0


# ---------- missing report ----------

def test_build_creatives_without_strategy_fails(tmp_path: Path) -> None:
    code, text = _run(
        [
            "build-creatives",
            "--client", "demo-saas",
            "--root", str(tmp_path / "empty"),
            "--outputs-dir", str(tmp_path / "out"),
        ]
    )
    assert code == 2
    assert "no CampaignStrategyReport" in text


# ---------- require-approval flag ----------

def test_require_approval_passes_when_clean(tmp_path: Path) -> None:
    root = _setup_strategy(tmp_path, audit=True)
    code, _ = _run(
        [
            "build-creatives",
            "--client", "demo-saas",
            "--root", str(root),
            "--outputs-dir", str(tmp_path / "out"),
            "--require-approval",
        ]
    )
    assert code == 0


def test_require_approval_blocks_when_pack_blocks_publish(tmp_path: Path) -> None:
    """Inject a risky claim, persist the corresponding strategy + approval pack,
    then verify --require-approval refuses to build."""
    # We need a customised brief whose strategy template produces risky text
    # in the value_proposition.headline. Simulate by manually overwriting
    # the persisted strategy report after a clean run.
    root = _setup_strategy(tmp_path, audit=True)

    # Mutate the persisted report to inject a risky claim, then re-audit.
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

    # Rebuild the approval pack so blocks_publish reflects the new text.
    builder = ApprovalPackBuilder(memory=mem)
    risky_ap = builder.build_from_report(report)
    builder.persist(risky_ap)
    assert risky_ap.blocks_publish is True

    code, text = _run(
        [
            "build-creatives",
            "--client", "demo-saas",
            "--root", str(root),
            "--outputs-dir", str(tmp_path / "out"),
            "--require-approval",
        ]
    )
    assert code == 3
    assert "blocks publish" in text


# ---------- audit trail invariants ----------

def test_audit_trail_records_creative_pack_creation(tmp_path: Path) -> None:
    root = _setup_strategy(tmp_path, audit=True)
    _run(
        [
            "build-creatives",
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
        e.payload.get("creative_pack", {}).get("action")
        for e in events
        if "creative_pack" in e.payload
    ]
    assert "created" in actions
    assert verify_chain(events) == []
