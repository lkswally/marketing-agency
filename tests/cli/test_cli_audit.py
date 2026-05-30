"""CLI tests for `mkt audit-strategy` + `mkt run-strategy --audit`."""

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


# ---------- run-strategy --audit ----------

def test_run_strategy_with_audit_emits_pack(tmp_path: Path) -> None:
    code, text = _run(
        [
            "run-strategy",
            "--brief", str(DEMO_BRIEF),
            "--root", str(tmp_path / "mem"),
            "--outputs-dir", str(tmp_path / "out"),
            "--audit",
        ]
    )
    assert code == 0
    payload = json.loads(text)
    assert payload["status"] == "succeeded"
    assert "approval_pack" in payload
    pack = payload["approval_pack"]
    assert pack["client_slug"] == "demo-saas"
    assert pack["state"] == "draft"
    assert pack["overall_severity"] in {"safe", "caveat", "risky", "unsafe"}
    # Disk side effects.
    assert (tmp_path / "out" / "approval-pack.md").exists()
    assert (tmp_path / "mem" / "demo-saas" / "approval_pack").exists()


def test_run_strategy_without_audit_no_pack(tmp_path: Path) -> None:
    code, text = _run(
        [
            "run-strategy",
            "--brief", str(DEMO_BRIEF),
            "--root", str(tmp_path / "mem"),
            "--outputs-dir", str(tmp_path / "out"),
        ]
    )
    assert code == 0
    payload = json.loads(text)
    assert "approval_pack" not in payload
    assert not (tmp_path / "out" / "approval-pack.md").exists()


# ---------- audit-strategy ----------

def test_audit_strategy_after_run_succeeds(tmp_path: Path) -> None:
    # 1. Run strategy first.
    _run(
        [
            "run-strategy",
            "--brief", str(DEMO_BRIEF),
            "--root", str(tmp_path / "mem"),
            "--outputs-dir", str(tmp_path / "out"),
        ]
    )
    # 2. Audit it.
    code, text = _run(
        [
            "audit-strategy",
            "--client", "demo-saas",
            "--root", str(tmp_path / "mem"),
            "--outputs-dir", str(tmp_path / "out"),
        ]
    )
    assert code == 0
    payload = json.loads(text)
    assert payload["client_slug"] == "demo-saas"
    assert payload["state"] == "draft"
    md_path = Path(payload["pack_markdown_path"])
    assert md_path.exists()
    text_md = md_path.read_text(encoding="utf-8")
    assert "Approval Pack" in text_md


def test_audit_strategy_without_prior_run_fails(tmp_path: Path) -> None:
    code, text = _run(
        [
            "audit-strategy",
            "--client", "demo-saas",
            "--root", str(tmp_path / "empty"),
            "--outputs-dir", str(tmp_path / "out"),
        ]
    )
    assert code == 2
    assert "no CampaignStrategyReport" in text


def test_audit_strategy_returns_rule_set_id(tmp_path: Path) -> None:
    _run(
        [
            "run-strategy",
            "--brief", str(DEMO_BRIEF),
            "--root", str(tmp_path / "mem"),
            "--outputs-dir", str(tmp_path / "out"),
        ]
    )
    code, text = _run(
        [
            "audit-strategy",
            "--client", "demo-saas",
            "--root", str(tmp_path / "mem"),
            "--outputs-dir", str(tmp_path / "out"),
        ]
    )
    assert code == 0
    payload = json.loads(text)
    assert payload["rule_set_id"] == "default-rules.v1"
