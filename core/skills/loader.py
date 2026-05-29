"""Skill spec loader."""

from __future__ import annotations

from pathlib import Path

import yaml

from .spec import SkillSpec

DEFAULT_SKILLS_DIR = Path("skills")


class SkillLoadError(Exception):
    """Raised when a skill markdown spec cannot be parsed or validated."""

    def __init__(self, path: Path, message: str) -> None:
        self.path = path
        super().__init__(f"{path}: {message}")


def _extract_frontmatter(text: str) -> str | None:
    if not text.startswith("---"):
        return None
    end = text.find("\n---", 3)
    if end == -1:
        return None
    return text[3:end].strip()


def load_skill(path: Path) -> SkillSpec:
    """Load and validate a single skill spec."""
    if not path.exists():
        raise SkillLoadError(path, "file does not exist")
    text = path.read_text(encoding="utf-8")
    raw_fm = _extract_frontmatter(text)
    if raw_fm is None:
        raise SkillLoadError(path, "missing YAML frontmatter")
    try:
        data = yaml.safe_load(raw_fm)
    except yaml.YAMLError as e:
        raise SkillLoadError(path, f"YAML parse error: {e}") from e
    if not isinstance(data, dict):
        raise SkillLoadError(path, "frontmatter must be a mapping")
    try:
        return SkillSpec.model_validate(data)
    except Exception as e:
        raise SkillLoadError(path, f"validation error: {e}") from e


def load_all_skills(root: Path | str = DEFAULT_SKILLS_DIR) -> list[SkillSpec]:
    """Load every ``*.md`` skill spec under ``root`` in sorted order."""
    root_path = Path(root)
    if not root_path.exists():
        return []
    out: list[SkillSpec] = []
    for p in sorted(root_path.glob("*.md")):
        out.append(load_skill(p))
    return out
