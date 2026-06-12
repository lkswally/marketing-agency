"""Safety: verify .gitignore protects client data from accidental git-add.

These tests call `git check-ignore` so they require a git repository.
They run on all platforms (no Windows-specific path escaping needed because
subprocess receives a list, not a shell string).
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


def _git_check_ignore(path: str) -> bool:
    """Return True iff git considers path to be ignored."""
    result = subprocess.run(
        ["git", "check-ignore", "-q", path],
        cwd=str(REPO_ROOT),
        capture_output=True,
    )
    return result.returncode == 0


@pytest.mark.parametrize("path", [
    "data/lexia",
    "data/acme",
    "data/testclient",
    "data/real-corp",
    "data/lexia/approval_pack/current.json",
    "data/lexia/audit/2026-06-01.jsonl",
])
def test_client_data_is_ignored(path):
    assert _git_check_ignore(path), f"Expected {path!r} to be gitignored"


@pytest.mark.parametrize("path", [
    "outputs/lexia",
    "outputs/acme/campaign-strategy.md",
])
def test_outputs_are_ignored(path):
    assert _git_check_ignore(path), f"Expected {path!r} to be gitignored"


def test_data_clients_gitkeep_is_tracked():
    assert not _git_check_ignore("data/clients/.gitkeep"), (
        "data/clients/.gitkeep must NOT be gitignored — it's a tracked placeholder"
    )


def test_outputs_gitkeep_is_tracked():
    assert not _git_check_ignore("outputs/.gitkeep"), (
        "outputs/.gitkeep must NOT be gitignored — it's a tracked placeholder"
    )
