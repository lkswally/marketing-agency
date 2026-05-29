"""Skill specs — Pydantic contract ``skill-spec.v1`` + loader."""

from __future__ import annotations

from .loader import (
    DEFAULT_SKILLS_DIR,
    SkillLoadError,
    load_all_skills,
    load_skill,
)
from .spec import SKILL_SPEC_VERSION, SkillSpec

__all__ = [
    "SKILL_SPEC_VERSION",
    "SkillSpec",
    "load_skill",
    "load_all_skills",
    "SkillLoadError",
    "DEFAULT_SKILLS_DIR",
]
