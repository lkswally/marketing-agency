"""Skill spec — Pydantic contract ``skill-spec.v1``.

Promotes the markdown-frontmatter format from MKT-1E to a Pydantic contract.

Skills are atomic capabilities composed by agents. Their input/output entries
in the v1 specs use single-key dicts (``{sample_texts: list[str]}``) — a
shape too loose to model tightly. We store them as raw dicts and validate
only that they are dicts (or strings, since some specs use a bare type name).
"""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import Field, field_validator

from core.domain.base import DomainModel

SKILL_SPEC_VERSION = "skill-spec.v1"

_SKILL_ID_RE = re.compile(r"^[a-z][a-z0-9-]*$")
_AGENT_ID_RE = re.compile(r"^[a-z][a-z0-9-]*$")


class SkillSpec(DomainModel):
    """A skill spec loaded from ``skills/<skill_id>.md``."""

    skill_id: str = Field(min_length=1)
    version: int = Field(ge=1)
    spec_version: Literal["skill-spec.v1"] = SKILL_SPEC_VERSION
    status: Literal["spec_only", "implemented"]
    deterministic: bool | Literal["partial"] = False
    external_dependencies: list[str] = Field(default_factory=list)
    inputs: list[Any] = Field(default_factory=list)
    outputs: list[Any] = Field(default_factory=list)
    used_by: list[str] = Field(default_factory=list)

    @field_validator("skill_id")
    @classmethod
    def _skill_id_shape(cls, v: str) -> str:
        if not _SKILL_ID_RE.match(v):
            raise ValueError(
                f"invalid skill_id {v!r}: must match [a-z][a-z0-9-]*"
            )
        return v

    @field_validator("used_by")
    @classmethod
    def _used_by_shape(cls, v: list[str]) -> list[str]:
        for a in v:
            if not _AGENT_ID_RE.match(a):
                raise ValueError(
                    f"invalid agent id {a!r} in used_by: must match [a-z][a-z0-9-]*"
                )
        if len(v) != len(set(v)):
            raise ValueError("duplicate agent ids in used_by")
        return v

    @field_validator("inputs", "outputs")
    @classmethod
    def _io_shape(cls, v: list[Any]) -> list[Any]:
        # We allow either dicts (the common form) or bare strings, but
        # reject anything else to catch obvious typos.
        for i, entry in enumerate(v):
            if not isinstance(entry, dict | str):
                raise ValueError(
                    f"entry [{i}] must be a dict or a string, got {type(entry).__name__}"
                )
        return v
