"""Agent spec — Pydantic contract ``agent-spec.v1``.

Promotes the markdown-frontmatter format from MKT-1E to a versioned Pydantic
contract. The 16 agent files under ``agents/`` are validated against this
contract by the linter and (in future blocks) by the dispatcher before any
agent invocation.

The IO entry sub-models are intentionally permissive (``extra="allow"``) to
accept the small format variations the human-written specs already exhibit.
The top-level :class:`AgentSpec` retains ``extra="forbid"`` to catch typos
in the canonical fields.
"""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import ConfigDict, Field, field_validator

from core.domain.base import DomainModel

AGENT_SPEC_VERSION = "agent-spec.v1"

_AGENT_ID_RE = re.compile(r"^[a-z][a-z0-9-]*$")
_GATE_NAME_RE = re.compile(r"^g_[a-z0-9]+(?:_[a-z0-9]+)+$")
_SKILL_ID_RE = re.compile(r"^[a-z][a-z0-9-]*$")


class AgentIOEntry(DomainModel):
    """One entry in an agent's ``inputs`` or ``outputs`` list.

    Permissive: keeps any other keys the spec author wrote without rejecting
    them. ``kind`` and ``required`` are recognized canonical fields.
    """

    model_config = ConfigDict(extra="allow", str_strip_whitespace=True)

    kind: str | None = None
    required: bool | None = None


class AgentSpec(DomainModel):
    """An agent role spec loaded from ``agents/<agent_id>.md``."""

    agent_id: str = Field(min_length=1)
    version: int = Field(ge=1)
    spec_version: Literal["agent-spec.v1"] = AGENT_SPEC_VERSION
    role: str | None = None
    default_model: Literal["opus", "sonnet", "haiku"] = "sonnet"
    status: Literal["spec_only", "implemented"]
    phases: list[str] = Field(default_factory=list)
    inputs: list[AgentIOEntry] = Field(default_factory=list)
    outputs: list[AgentIOEntry] = Field(default_factory=list)
    consumed_gates: list[str] = Field(default_factory=list)
    produced_gates: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    needs_human_approval: bool = False
    risks: list[str] = Field(default_factory=list)
    # Limits accept either bare labels (str) or single-key dicts like
    # ``{max_audiences_per_run: 3}`` — both forms appear in the v1 specs.
    limits: list[Any] = Field(default_factory=list)

    @field_validator("agent_id")
    @classmethod
    def _agent_id_shape(cls, v: str) -> str:
        if not _AGENT_ID_RE.match(v):
            raise ValueError(
                f"invalid agent_id {v!r}: must match [a-z][a-z0-9-]*"
            )
        return v

    @field_validator("skills")
    @classmethod
    def _skills_shape(cls, v: list[str]) -> list[str]:
        for s in v:
            if not _SKILL_ID_RE.match(s):
                raise ValueError(
                    f"invalid skill id {s!r}: must match [a-z][a-z0-9-]*"
                )
        if len(v) != len(set(v)):
            raise ValueError("duplicate skill ids in agent.skills")
        return v

    @field_validator("consumed_gates", "produced_gates")
    @classmethod
    def _gate_names(cls, v: list[str]) -> list[str]:
        for g in v:
            if not _GATE_NAME_RE.match(g):
                raise ValueError(
                    f"invalid gate name {g!r}: must match g_<noun>_<verb_past>"
                )
        return v
