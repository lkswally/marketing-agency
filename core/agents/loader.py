"""Agent spec loader.

Parses ``agents/<agent_id>.md`` files: YAML frontmatter + markdown body.
Frontmatter is validated against :class:`AgentSpec`.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from .spec import AgentSpec

DEFAULT_AGENTS_DIR = Path("agents")


class AgentLoadError(Exception):
    """Raised when an agent markdown spec cannot be parsed or validated."""

    def __init__(self, path: Path, message: str) -> None:
        self.path = path
        super().__init__(f"{path}: {message}")


def _extract_frontmatter(text: str) -> str | None:
    """Return the YAML frontmatter block of a markdown file, or ``None``."""
    if not text.startswith("---"):
        return None
    end = text.find("\n---", 3)
    if end == -1:
        return None
    return text[3:end].strip()


def load_agent(path: Path) -> AgentSpec:
    """Load and validate a single agent spec from a markdown file."""
    if not path.exists():
        raise AgentLoadError(path, "file does not exist")
    text = path.read_text(encoding="utf-8")
    raw_fm = _extract_frontmatter(text)
    if raw_fm is None:
        raise AgentLoadError(path, "missing YAML frontmatter")
    try:
        data = yaml.safe_load(raw_fm)
    except yaml.YAMLError as e:
        raise AgentLoadError(path, f"YAML parse error: {e}") from e
    if not isinstance(data, dict):
        raise AgentLoadError(path, "frontmatter must be a mapping")
    try:
        return AgentSpec.model_validate(data)
    except Exception as e:
        raise AgentLoadError(path, f"validation error: {e}") from e


def load_all_agents(root: Path | str = DEFAULT_AGENTS_DIR) -> list[AgentSpec]:
    """Load every ``*.md`` agent spec under ``root`` in sorted order."""
    root_path = Path(root)
    if not root_path.exists():
        return []
    out: list[AgentSpec] = []
    for p in sorted(root_path.glob("*.md")):
        out.append(load_agent(p))
    return out
