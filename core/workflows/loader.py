"""Workflow YAML loader.

Pure read-side: takes a path, returns a validated :class:`WorkflowSpec`.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from .spec import WorkflowSpec

# Default directory; callers may override.
DEFAULT_WORKFLOWS_DIR = Path("workflows")


class WorkflowLoadError(Exception):
    """Raised when a workflow YAML cannot be loaded or validated."""

    def __init__(self, path: Path, message: str) -> None:
        self.path = path
        super().__init__(f"{path}: {message}")


def load_workflow(path: Path) -> WorkflowSpec:
    """Load a single workflow YAML into a :class:`WorkflowSpec`."""
    if not path.exists():
        raise WorkflowLoadError(path, "file does not exist")
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        raise WorkflowLoadError(path, f"YAML parse error: {e}") from e
    if not isinstance(raw, dict):
        raise WorkflowLoadError(path, "top-level YAML must be a mapping")
    try:
        return WorkflowSpec.model_validate(raw)
    except Exception as e:
        raise WorkflowLoadError(path, f"validation error: {e}") from e


def load_all_workflows(
    root: Path | str = DEFAULT_WORKFLOWS_DIR,
) -> list[WorkflowSpec]:
    """Load every ``*.yaml`` file under ``root`` in sorted order."""
    root_path = Path(root)
    if not root_path.exists():
        return []
    out: list[WorkflowSpec] = []
    for p in sorted(root_path.glob("*.yaml")):
        out.append(load_workflow(p))
    return out
