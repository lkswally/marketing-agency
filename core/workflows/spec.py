"""Workflow specs — Pydantic contract ``workflow-spec.v1``.

A workflow spec is the YAML artifact in ``workflows/`` describing how a
marketing motion runs. MKT-1E declared the format in prose; MKT-2A pins it
to a Pydantic model so the dispatcher can refuse malformed inputs.
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import Field, field_validator, model_validator

from core.domain.base import DomainModel

WORKFLOW_SPEC_VERSION = "workflow-spec.v1"

# Identifier rules (mirror what MKT-1E documents).
_WORKFLOW_ID_RE = re.compile(r"^W[0-9]+_[a-z0-9_]+$")
_PHASE_ID_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_AGENT_ID_RE = re.compile(r"^[a-z][a-z0-9-]*$")
# Phase gates: g_<noun>_<verb_past>. Two underscore-separated segments at
# minimum after the ``g_`` prefix.
_GATE_NAME_RE = re.compile(r"^g_[a-z0-9]+(?:_[a-z0-9]+)+$")


class ApprovalSpec(DomainModel):
    """Approval Center coupling for a workflow."""

    state_machine: Literal["standard"] = "standard"
    human_required_at: list[str] = Field(default_factory=list)


class PhaseSpec(DomainModel):
    """A single phase in a workflow."""

    id: str = Field(min_length=1, max_length=64)
    agents: list[str] = Field(min_length=1)
    gates_required_before: list[str] = Field(default_factory=list)
    gates_produced: list[str] = Field(default_factory=list)
    outputs: list[str] = Field(default_factory=list)
    description: str | None = None

    @field_validator("id")
    @classmethod
    def _phase_id_shape(cls, v: str) -> str:
        if not _PHASE_ID_RE.match(v):
            raise ValueError(f"invalid phase id {v!r}: must match [a-z][a-z0-9_]*")
        return v

    @field_validator("agents")
    @classmethod
    def _agents_shape(cls, v: list[str]) -> list[str]:
        for a in v:
            if not _AGENT_ID_RE.match(a):
                raise ValueError(f"invalid agent id {a!r}: must match [a-z][a-z0-9-]*")
        if len(v) != len(set(v)):
            raise ValueError("duplicate agent ids in phase.agents")
        return v

    @field_validator("gates_required_before", "gates_produced")
    @classmethod
    def _gate_names(cls, v: list[str]) -> list[str]:
        for g in v:
            if not _GATE_NAME_RE.match(g):
                raise ValueError(
                    f"invalid gate name {g!r}: must match g_<noun>_<verb_past> "
                    "(lowercase, underscore-separated)"
                )
        return v


class WorkflowSpec(DomainModel):
    """A workflow spec loaded from ``workflows/<id>.yaml``."""

    workflow_id: str = Field(min_length=1)
    version: int = Field(ge=1)
    spec_version: Literal["workflow-spec.v1"] = WORKFLOW_SPEC_VERSION
    description: str = Field(min_length=1)
    phases: list[PhaseSpec] = Field(min_length=1)
    approval: ApprovalSpec | None = None
    notes: list[str] = Field(default_factory=list)

    @field_validator("workflow_id")
    @classmethod
    def _workflow_id_shape(cls, v: str) -> str:
        if not _WORKFLOW_ID_RE.match(v):
            raise ValueError(
                f"invalid workflow_id {v!r}: must match W<N>_<snake_name>"
            )
        return v

    @model_validator(mode="after")
    def _unique_phase_ids(self) -> WorkflowSpec:
        ids = [p.id for p in self.phases]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate phase ids in workflow")
        return self

    @model_validator(mode="after")
    def _human_required_phases_exist(self) -> WorkflowSpec:
        if self.approval is None:
            return self
        phase_ids = {p.id for p in self.phases}
        unknown = [
            ph
            for ph in self.approval.human_required_at
            if ph not in phase_ids
        ]
        if unknown:
            raise ValueError(
                f"approval.human_required_at references unknown phases: {unknown}"
            )
        return self

    # -------- helpers --------

    @property
    def all_phase_ids(self) -> list[str]:
        return [p.id for p in self.phases]

    @property
    def all_agents(self) -> list[str]:
        seen: list[str] = []
        for p in self.phases:
            for a in p.agents:
                if a not in seen:
                    seen.append(a)
        return seen

    @property
    def gates_consumed(self) -> set[str]:
        out: set[str] = set()
        for p in self.phases:
            out.update(p.gates_required_before)
        return out

    @property
    def gates_emitted(self) -> set[str]:
        out: set[str] = set()
        for p in self.phases:
            out.update(p.gates_produced)
        return out
