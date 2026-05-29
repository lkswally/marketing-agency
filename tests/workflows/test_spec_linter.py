"""Spec linter tests — synthetic cases for each rule + sanity over the real repo."""

from __future__ import annotations

from pathlib import Path

from core.workflows import (
    WorkflowSpec,
    lint_agent_file,
    lint_all,
    lint_skill_file,
    lint_workflow_spec,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


# ---------- workflow linter ----------

def _build_spec(agents: list[str], gates_before: list[str] | None = None,
                gates_produced: list[str] | None = None) -> WorkflowSpec:
    return WorkflowSpec.model_validate(
        {
            "workflow_id": "W9_synthetic",
            "version": 1,
            "spec_version": "workflow-spec.v1",
            "description": "synthetic",
            "phases": [
                {
                    "id": "p1",
                    "agents": agents,
                    "gates_required_before": gates_before or [],
                    "gates_produced": gates_produced or [],
                }
            ],
        }
    )


def test_workflow_lint_flags_unknown_agent() -> None:
    spec = _build_spec(agents=["does-not-exist"])
    findings = lint_workflow_spec(spec, known_agents={"copywriter"})
    rules = {f.rule for f in findings}
    assert "workflow_unknown_agent" in rules


def test_workflow_lint_passes_when_agent_known() -> None:
    spec = _build_spec(agents=["copywriter"])
    findings = lint_workflow_spec(spec, known_agents={"copywriter"})
    assert findings == []


def test_workflow_lint_warns_on_gate_consumed_not_produced() -> None:
    # Gate is produced by the same workflow but at a later phase → warning.
    spec = WorkflowSpec.model_validate(
        {
            "workflow_id": "W9_synthetic",
            "version": 1,
            "spec_version": "workflow-spec.v1",
            "description": "x",
            "phases": [
                {
                    "id": "p1",
                    "agents": ["a"],
                    "gates_required_before": ["g_brief_captured"],
                    "gates_produced": [],
                },
                {
                    "id": "p2",
                    "agents": ["a"],
                    "gates_required_before": [],
                    "gates_produced": ["g_brief_captured"],
                },
            ],
        }
    )
    findings = lint_workflow_spec(spec, known_agents={"a"})
    rules = {f.rule for f in findings}
    assert "gate_consumed_before_produced" in rules


def test_workflow_lint_allows_cross_workflow_gate() -> None:
    # Gate is not produced anywhere in this workflow → assumed cross-workflow,
    # no finding.
    spec = _build_spec(
        agents=["a"], gates_before=["g_brief_captured"], gates_produced=[]
    )
    findings = lint_workflow_spec(spec, known_agents={"a"})
    assert findings == []


# ---------- agent linter ----------

def test_agent_lint_missing_frontmatter(tmp_path: Path) -> None:
    p = tmp_path / "bad.md"
    p.write_text("# no frontmatter here\n", encoding="utf-8")
    findings = lint_agent_file(p, known_skills=set())
    assert any(f.rule == "agent_missing_frontmatter" for f in findings)


def test_agent_lint_missing_field(tmp_path: Path) -> None:
    p = tmp_path / "x.md"
    p.write_text(
        "---\nagent_id: x\nversion: 1\nspec_version: agent-spec.v1\n---\nbody\n",
        encoding="utf-8",
    )
    findings = lint_agent_file(p, known_skills=set())
    assert any(
        f.rule == "agent_missing_field" and "status" in f.message for f in findings
    )


def test_agent_lint_invalid_status(tmp_path: Path) -> None:
    p = tmp_path / "x.md"
    p.write_text(
        "---\nagent_id: x\nversion: 1\nspec_version: agent-spec.v1\nstatus: vibing\n---\nbody\n",
        encoding="utf-8",
    )
    findings = lint_agent_file(p, known_skills=set())
    assert any(f.rule == "agent_invalid_status" for f in findings)


def test_agent_lint_unknown_skill(tmp_path: Path) -> None:
    p = tmp_path / "x.md"
    p.write_text(
        "---\nagent_id: x\nversion: 1\nspec_version: agent-spec.v1\nstatus: spec_only\nskills: [made-up]\n---\nbody\n",
        encoding="utf-8",
    )
    findings = lint_agent_file(p, known_skills=set())
    assert any(f.rule == "agent_skill_not_found" for f in findings)


def test_agent_lint_known_skill_ok(tmp_path: Path) -> None:
    p = tmp_path / "x.md"
    p.write_text(
        "---\nagent_id: x\nversion: 1\nspec_version: agent-spec.v1\nstatus: spec_only\nskills: [real-skill]\n---\nbody\n",
        encoding="utf-8",
    )
    findings = lint_agent_file(p, known_skills={"real-skill"})
    # No skill-related error; may still be empty.
    assert not any(f.rule == "agent_skill_not_found" for f in findings)


# ---------- skill linter ----------

def test_skill_lint_missing_frontmatter(tmp_path: Path) -> None:
    p = tmp_path / "bad.md"
    p.write_text("body\n", encoding="utf-8")
    findings = lint_skill_file(p)
    assert any(f.rule == "skill_missing_frontmatter" for f in findings)


def test_skill_lint_invalid_status(tmp_path: Path) -> None:
    p = tmp_path / "x.md"
    p.write_text(
        "---\nskill_id: x\nversion: 1\nspec_version: skill-spec.v1\nstatus: experimental\n---\nbody\n",
        encoding="utf-8",
    )
    findings = lint_skill_file(p)
    assert any(f.rule == "skill_invalid_status" for f in findings)


# ---------- lint_all over the real repo ----------

def test_lint_all_on_real_repo_has_no_errors() -> None:
    findings = lint_all(
        workflows_dir=REPO_ROOT / "workflows",
        agents_dir=REPO_ROOT / "agents",
        skills_dir=REPO_ROOT / "skills",
    )
    errors = [f for f in findings if f.severity == "error"]
    assert errors == [], f"unexpected lint errors: {errors}"


def test_lint_all_handles_missing_dirs(tmp_path: Path) -> None:
    findings = lint_all(
        workflows_dir=tmp_path / "wf",
        agents_dir=tmp_path / "ag",
        skills_dir=tmp_path / "sk",
    )
    assert findings == []
