"""MKT workflow specs + loader + linter.

Contract: ``workflow-spec.v1`` (see ``docs/workflows/overview.md`` and
``core/workflows/spec.py``).
"""

from __future__ import annotations

from .linter import (
    DEFAULT_AGENTS_DIR,
    DEFAULT_SKILLS_DIR,
    DEFAULT_WORKFLOWS_DIR,
    LintFinding,
    Severity,
    lint_agent_file,
    lint_all,
    lint_skill_file,
    lint_workflow_spec,
)
from .loader import WorkflowLoadError, load_all_workflows, load_workflow
from .spec import (
    WORKFLOW_SPEC_VERSION,
    ApprovalSpec,
    PhaseSpec,
    WorkflowSpec,
)

__all__ = [
    "WORKFLOW_SPEC_VERSION",
    "WorkflowSpec",
    "PhaseSpec",
    "ApprovalSpec",
    "load_workflow",
    "load_all_workflows",
    "WorkflowLoadError",
    "lint_all",
    "lint_workflow_spec",
    "lint_agent_file",
    "lint_skill_file",
    "LintFinding",
    "Severity",
    "DEFAULT_WORKFLOWS_DIR",
    "DEFAULT_AGENTS_DIR",
    "DEFAULT_SKILLS_DIR",
]
