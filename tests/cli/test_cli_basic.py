"""CLI smoke tests — invoke main() directly with explicit argv + StringIO."""

from __future__ import annotations

import io
import json
from pathlib import Path

from cli.main import main

REPO_ROOT = Path(__file__).resolve().parents[2]
REPO_WORKFLOWS = REPO_ROOT / "workflows"
REPO_AGENTS = REPO_ROOT / "agents"
REPO_SKILLS = REPO_ROOT / "skills"


def _run(argv: list[str]) -> tuple[int, str]:
    out = io.StringIO()
    code = main(argv, out=out)
    return code, out.getvalue()


# ---------- list-workflows ----------

def test_list_workflows_lists_six(_=None) -> None:
    code, text = _run(["list-workflows", "--workflows-dir", str(REPO_WORKFLOWS)])
    assert code == 0
    for expected in [
        "W1_intake_to_strategy",
        "W2_keyword_and_competitor_research",
        "W3_campaign_builder",
        "W4_creative_factory_draft",
        "W5_claim_audit_and_approval",
        "W6_report_summary",
    ]:
        assert expected in text


def test_list_workflows_empty_dir(tmp_path: Path) -> None:
    code, text = _run(["list-workflows", "--workflows-dir", str(tmp_path)])
    assert code == 0
    assert "no workflows found" in text


# ---------- validate-specs ----------

def test_validate_specs_on_real_repo_has_no_errors() -> None:
    code, text = _run(
        [
            "validate-specs",
            "--workflows-dir", str(REPO_WORKFLOWS),
            "--agents-dir", str(REPO_AGENTS),
            "--skills-dir", str(REPO_SKILLS),
        ]
    )
    assert code == 0
    assert "0 error(s)" in text


# ---------- memory inspect ----------

def test_memory_inspect_empty_root(tmp_path: Path) -> None:
    code, text = _run(["memory", "inspect", "--root", str(tmp_path / "nope")])
    assert code == 0
    assert "no memory root" in text


def test_memory_inspect_no_clients(tmp_path: Path) -> None:
    tmp_path.mkdir(exist_ok=True)
    code, text = _run(["memory", "inspect", "--root", str(tmp_path)])
    assert code == 0
    assert "no clients persisted" in text


def test_memory_inspect_lists_clients(tmp_path: Path) -> None:
    (tmp_path / "demo-co").mkdir()
    (tmp_path / "acme").mkdir()
    code, text = _run(["memory", "inspect", "--root", str(tmp_path)])
    assert code == 0
    assert "demo-co" in text
    assert "acme" in text


# ---------- run-mock ----------

def test_run_mock_w1_succeeds(tmp_path: Path) -> None:
    code, text = _run(
        [
            "run-mock",
            "W1_intake_to_strategy",
            "--client", "default",
            "--workflows-dir", str(REPO_WORKFLOWS),
            "--root", str(tmp_path),
        ]
    )
    assert code == 0
    payload = json.loads(text)
    assert payload["status"] == "succeeded"
    assert payload["workflow_name"] == "W1_intake_to_strategy"

    # Side effects on disk:
    assert (tmp_path / "default" / "_meta.json").exists()
    assert (tmp_path / "default" / "envelope").exists()
    assert (tmp_path / "default" / "workflow_run").exists()
    audit_files = list((tmp_path / "default" / "audit").glob("*.jsonl"))
    assert audit_files, "audit JSONL should exist after run-mock"


def test_run_mock_unknown_workflow_fails(tmp_path: Path) -> None:
    code, text = _run(
        [
            "run-mock",
            "Wnope",
            "--client", "default",
            "--workflows-dir", str(REPO_WORKFLOWS),
            "--root", str(tmp_path),
        ]
    )
    assert code == 2
    assert "not found" in text


def test_run_mock_then_inspect_shows_kinds(tmp_path: Path) -> None:
    _run(
        [
            "run-mock",
            "W1_intake_to_strategy",
            "--client", "default",
            "--workflows-dir", str(REPO_WORKFLOWS),
            "--root", str(tmp_path),
        ]
    )
    code, text = _run(
        ["memory", "inspect", "--client", "default", "--root", str(tmp_path)]
    )
    assert code == 0
    assert "envelope/" in text
    assert "workflow_run/" in text
    assert "audit/" in text
