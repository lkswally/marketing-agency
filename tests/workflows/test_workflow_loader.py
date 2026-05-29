"""Loader tests — must successfully parse all 6 real workflows in the repo."""

from __future__ import annotations

from pathlib import Path

import pytest

from core.workflows import (
    WorkflowLoadError,
    WorkflowSpec,
    load_all_workflows,
    load_workflow,
)

# The repo's own workflows directory.
REPO_WORKFLOWS_DIR = Path(__file__).resolve().parents[2] / "workflows"


def test_load_all_real_workflows() -> None:
    specs = load_all_workflows(REPO_WORKFLOWS_DIR)
    ids = {s.workflow_id for s in specs}
    expected = {
        "W1_intake_to_strategy",
        "W2_keyword_and_competitor_research",
        "W3_campaign_builder",
        "W4_creative_factory_draft",
        "W5_claim_audit_and_approval",
        "W6_report_summary",
    }
    assert expected.issubset(ids)


def test_each_workflow_is_v1() -> None:
    for s in load_all_workflows(REPO_WORKFLOWS_DIR):
        assert s.spec_version == "workflow-spec.v1"
        assert s.version >= 1
        assert s.phases, f"{s.workflow_id} has no phases"


def test_load_workflow_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(WorkflowLoadError):
        load_workflow(tmp_path / "nope.yaml")


def test_load_workflow_invalid_yaml_raises(tmp_path: Path) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text(": not yaml :\nthis-is::broken: [\n", encoding="utf-8")
    with pytest.raises(WorkflowLoadError):
        load_workflow(bad)


def test_load_workflow_invalid_schema_raises(tmp_path: Path) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "workflow_id: bad\nversion: 1\nspec_version: workflow-spec.v1\n"
        "description: x\nphases:\n  - id: x\n    agents: [a]\n",
        encoding="utf-8",
    )
    with pytest.raises(WorkflowLoadError):
        load_workflow(bad)


def test_load_all_empty_dir_returns_empty(tmp_path: Path) -> None:
    assert load_all_workflows(tmp_path) == []


def test_w1_specific_gates_emitted() -> None:
    specs = load_all_workflows(REPO_WORKFLOWS_DIR)
    by_id = {s.workflow_id: s for s in specs}
    w1: WorkflowSpec = by_id["W1_intake_to_strategy"]
    emitted = w1.gates_emitted
    assert "g_brief_captured" in emitted
    assert "g_positioning_drafted" in emitted
