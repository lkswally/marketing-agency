"""Spec linter — pure structural checks over workflows / agents / skills.

The linter does NOT execute anything and does NOT modify any file. It reads
the filesystem to discover known agent/skill ids, parses YAML frontmatter
from agent/skill markdown files, and aggregates findings.

Output is a flat ``list[LintFinding]`` with severities ``error`` / ``warning``.
A caller is responsible for deciding what to do with warnings.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import yaml

from .loader import WorkflowLoadError, load_workflow
from .spec import WorkflowSpec

DEFAULT_AGENTS_DIR = Path("agents")
DEFAULT_SKILLS_DIR = Path("skills")
DEFAULT_WORKFLOWS_DIR = Path("workflows")

Severity = Literal["error", "warning"]


@dataclass(frozen=True)
class LintFinding:
    """A single lint result."""

    severity: Severity
    rule: str
    target: str  # path or id
    message: str


def _read_frontmatter(md_path: Path) -> dict | None:
    """Extract YAML frontmatter from a markdown file.

    Returns ``None`` if the file does not start with ``---`` or the
    frontmatter cannot be parsed.
    """
    if not md_path.exists():
        return None
    text = md_path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return None
    # Frontmatter ends at the next ``---`` line.
    end = text.find("\n---", 3)
    if end == -1:
        return None
    raw = text[3:end].strip()
    try:
        data = yaml.safe_load(raw)
    except yaml.YAMLError:
        return None
    return data if isinstance(data, dict) else None


def _scan_ids(directory: Path, expected_id_key: str) -> dict[str, dict]:
    """Discover all specs under ``directory``.

    Returns a mapping ``{id: frontmatter_dict}``. Files without
    parseable frontmatter or without the expected id key are skipped
    silently (lint_agent / lint_skill report those cases when called
    directly).
    """
    out: dict[str, dict] = {}
    if not directory.exists():
        return out
    for p in sorted(directory.glob("*.md")):
        fm = _read_frontmatter(p)
        if not fm:
            continue
        ident = fm.get(expected_id_key)
        if isinstance(ident, str):
            out[ident] = fm
    return out


# -------- per-target linters --------

def lint_workflow_spec(
    spec: WorkflowSpec,
    *,
    known_agents: set[str],
) -> list[LintFinding]:
    """Structural checks on a loaded :class:`WorkflowSpec`."""
    findings: list[LintFinding] = []
    target = spec.workflow_id

    # 1. every agent referenced must exist
    for phase in spec.phases:
        for agent_id in phase.agents:
            if agent_id not in known_agents:
                findings.append(
                    LintFinding(
                        severity="error",
                        rule="workflow_unknown_agent",
                        target=f"{target}.{phase.id}",
                        message=f"agent {agent_id!r} not found under agents/",
                    )
                )

    # 2. every consumed gate within the workflow must be produced by an
    #    earlier phase. Cross-workflow consumption (a gate produced by
    #    another workflow) is allowed and is NOT flagged.
    produced_so_far: set[str] = set()
    for phase in spec.phases:
        for gate in phase.gates_required_before:
            if gate not in produced_so_far and not _looks_externally_produced(
                gate, spec
            ):
                findings.append(
                    LintFinding(
                        severity="warning",
                        rule="gate_consumed_before_produced",
                        target=f"{target}.{phase.id}",
                        message=(
                            f"gate {gate!r} is consumed but not produced earlier "
                            "in this workflow (may be cross-workflow)"
                        ),
                    )
                )
        produced_so_far.update(phase.gates_produced)

    return findings


def _looks_externally_produced(gate: str, spec: WorkflowSpec) -> bool:
    """Best-effort heuristic: a gate that this workflow never emits anywhere.

    Cross-workflow gates are legitimate; this helper suppresses the warning
    when the gate is clearly not "this workflow's job".
    """
    return gate not in spec.gates_emitted


def lint_agent_file(
    path: Path,
    *,
    known_skills: set[str],
) -> list[LintFinding]:
    """Structural checks on an agent markdown spec."""
    findings: list[LintFinding] = []
    fm = _read_frontmatter(path)
    target = str(path)

    if fm is None:
        findings.append(
            LintFinding(
                severity="error",
                rule="agent_missing_frontmatter",
                target=target,
                message="agent spec must start with YAML frontmatter",
            )
        )
        return findings

    required = ["agent_id", "version", "spec_version", "status"]
    for key in required:
        if key not in fm:
            findings.append(
                LintFinding(
                    severity="error",
                    rule="agent_missing_field",
                    target=target,
                    message=f"missing frontmatter field {key!r}",
                )
            )

    status = fm.get("status")
    if status not in (None, "spec_only", "implemented"):
        findings.append(
            LintFinding(
                severity="error",
                rule="agent_invalid_status",
                target=target,
                message=f"status must be 'spec_only' or 'implemented' (got {status!r})",
            )
        )

    spec_version = fm.get("spec_version")
    if spec_version not in (None, "agent-spec.v1"):
        findings.append(
            LintFinding(
                severity="warning",
                rule="agent_unknown_spec_version",
                target=target,
                message=f"unrecognized spec_version {spec_version!r}",
            )
        )

    skills = fm.get("skills", [])
    if isinstance(skills, list):
        for s in skills:
            if isinstance(s, str) and s not in known_skills:
                findings.append(
                    LintFinding(
                        severity="error",
                        rule="agent_skill_not_found",
                        target=target,
                        message=f"agent references skill {s!r} which is not under skills/",
                    )
                )

    return findings


def lint_skill_file(path: Path) -> list[LintFinding]:
    """Structural checks on a skill markdown spec."""
    findings: list[LintFinding] = []
    fm = _read_frontmatter(path)
    target = str(path)

    if fm is None:
        findings.append(
            LintFinding(
                severity="error",
                rule="skill_missing_frontmatter",
                target=target,
                message="skill spec must start with YAML frontmatter",
            )
        )
        return findings

    required = ["skill_id", "version", "spec_version", "status"]
    for key in required:
        if key not in fm:
            findings.append(
                LintFinding(
                    severity="error",
                    rule="skill_missing_field",
                    target=target,
                    message=f"missing frontmatter field {key!r}",
                )
            )

    status = fm.get("status")
    if status not in (None, "spec_only", "implemented"):
        findings.append(
            LintFinding(
                severity="error",
                rule="skill_invalid_status",
                target=target,
                message=f"status must be 'spec_only' or 'implemented' (got {status!r})",
            )
        )

    return findings


# -------- orchestrator --------

def lint_all(
    *,
    workflows_dir: Path | str = DEFAULT_WORKFLOWS_DIR,
    agents_dir: Path | str = DEFAULT_AGENTS_DIR,
    skills_dir: Path | str = DEFAULT_SKILLS_DIR,
) -> list[LintFinding]:
    """Run every linter and aggregate findings."""
    workflows_dir = Path(workflows_dir)
    agents_dir = Path(agents_dir)
    skills_dir = Path(skills_dir)

    known_agents_map = _scan_ids(agents_dir, "agent_id")
    known_skills_map = _scan_ids(skills_dir, "skill_id")
    known_agents = set(known_agents_map.keys())
    known_skills = set(known_skills_map.keys())

    findings: list[LintFinding] = []

    # Workflows
    if workflows_dir.exists():
        for p in sorted(workflows_dir.glob("*.yaml")):
            try:
                spec = load_workflow(p)
            except WorkflowLoadError as e:
                findings.append(
                    LintFinding(
                        severity="error",
                        rule="workflow_invalid",
                        target=str(p),
                        message=str(e),
                    )
                )
                continue
            findings.extend(
                lint_workflow_spec(spec, known_agents=known_agents)
            )

    # Agents
    if agents_dir.exists():
        for p in sorted(agents_dir.glob("*.md")):
            findings.extend(lint_agent_file(p, known_skills=known_skills))

    # Skills
    if skills_dir.exists():
        for p in sorted(skills_dir.glob("*.md")):
            findings.extend(lint_skill_file(p))

    return findings
