"""Agent loader tests — must successfully parse all 16 real agent specs."""

from __future__ import annotations

from pathlib import Path

import pytest

from core.agents import AgentLoadError, load_agent, load_all_agents

REPO_AGENTS_DIR = Path(__file__).resolve().parents[2] / "agents"


def test_load_all_real_agents() -> None:
    specs = load_all_agents(REPO_AGENTS_DIR)
    ids = {s.agent_id for s in specs}
    expected = {
        "mkt-orchestrator",
        "brand-strategist",
        "audience-researcher",
        "keyword-intelligence-agent",
        "competitor-benchmark-agent",
        "channel-advisor-agent",
        "paid-ads-strategist",
        "seo-content-planner",
        "copywriter",
        "creative-director",
        "reels-scriptwriter",
        "compliance-auditor",
        "approval-manager",
        "analytics-agent",
        "optimizer-agent",
        "n8n-automation-planner",
    }
    assert expected.issubset(ids)
    assert len(specs) == 16


def test_all_real_agents_are_spec_only() -> None:
    for spec in load_all_agents(REPO_AGENTS_DIR):
        assert spec.status == "spec_only", spec.agent_id


def test_load_agent_missing_raises(tmp_path: Path) -> None:
    with pytest.raises(AgentLoadError):
        load_agent(tmp_path / "nope.md")


def test_load_agent_no_frontmatter_raises(tmp_path: Path) -> None:
    p = tmp_path / "x.md"
    p.write_text("just body, no frontmatter\n", encoding="utf-8")
    with pytest.raises(AgentLoadError):
        load_agent(p)


def test_load_agent_invalid_yaml_raises(tmp_path: Path) -> None:
    p = tmp_path / "x.md"
    p.write_text("---\nthis:::: not valid: [\n---\n", encoding="utf-8")
    with pytest.raises(AgentLoadError):
        load_agent(p)


def test_load_agent_validation_error_raises(tmp_path: Path) -> None:
    p = tmp_path / "x.md"
    p.write_text(
        "---\nagent_id: X\nversion: 1\nspec_version: agent-spec.v1\nstatus: spec_only\n---\nbody\n",
        encoding="utf-8",
    )
    with pytest.raises(AgentLoadError):
        load_agent(p)


def test_load_all_empty_dir_returns_empty(tmp_path: Path) -> None:
    assert load_all_agents(tmp_path) == []


def test_compliance_auditor_uses_opus() -> None:
    specs = {s.agent_id: s for s in load_all_agents(REPO_AGENTS_DIR)}
    assert specs["compliance-auditor"].default_model == "opus"
