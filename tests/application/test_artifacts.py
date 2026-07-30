"""Tests for the centralized artifact writer (MKT-11A)."""

from __future__ import annotations

from pathlib import Path

from core.application.artifacts import (
    ArtifactWriteError,
    OutputLayout,
    check_path_allowed,
    resolve_output_dir,
    write_artifacts,
)
from core.application.result import ErrorCode


def test_resolve_output_dir_flat(tmp_path: Path) -> None:
    d = resolve_output_dir(
        outputs_root=tmp_path / "out", client_slug="acme", layout=OutputLayout.FLAT,
    )
    assert d == tmp_path / "out"


def test_resolve_output_dir_per_client(tmp_path: Path) -> None:
    d = resolve_output_dir(
        outputs_root=tmp_path / "out", client_slug="acme", layout=OutputLayout.PER_CLIENT,
    )
    assert d == tmp_path / "out" / "acme"


def test_check_path_allowed_inside_root(tmp_path: Path) -> None:
    root = tmp_path / "out"
    assert check_path_allowed(path=root / "x.md", outputs_root=root) is True


def test_check_path_allowed_escapes_root(tmp_path: Path) -> None:
    root = tmp_path / "out"
    escaped = tmp_path / "elsewhere" / "x.md"
    assert check_path_allowed(path=escaped, outputs_root=root) is False


# ---------- write_artifacts: happy path ----------

def test_write_artifacts_creates_dir_and_files(tmp_path: Path) -> None:
    artifacts, err = write_artifacts(
        outputs_root=tmp_path / "out",
        client_slug="acme",
        layout=OutputLayout.FLAT,
        files={"a.md": "# hi", "a.json": '{"x": 1}'},
        overwrite=False,
        dry_run=False,
    )
    assert err is None
    assert len(artifacts) == 2
    assert (tmp_path / "out" / "a.md").read_text(encoding="utf-8") == "# hi"
    assert (tmp_path / "out" / "a.json").read_text(encoding="utf-8") == '{"x": 1}'
    assert all(not a.would_write for a in artifacts)


def test_write_artifacts_per_client_layout(tmp_path: Path) -> None:
    artifacts, err = write_artifacts(
        outputs_root=tmp_path / "out",
        client_slug="acme",
        layout=OutputLayout.PER_CLIENT,
        files={"a.md": "hi"},
        overwrite=False,
        dry_run=False,
    )
    assert err is None
    assert (tmp_path / "out" / "acme" / "a.md").exists()


# ---------- overwrite ----------

def test_write_artifacts_overwrite_false_blocks_existing(tmp_path: Path) -> None:
    write_artifacts(
        outputs_root=tmp_path / "out", client_slug="acme", layout=OutputLayout.FLAT,
        files={"a.md": "v1"}, overwrite=False, dry_run=False,
    )
    artifacts, err = write_artifacts(
        outputs_root=tmp_path / "out", client_slug="acme", layout=OutputLayout.FLAT,
        files={"a.md": "v2"}, overwrite=False, dry_run=False,
    )
    assert artifacts == []
    assert err is not None
    assert err.code is ErrorCode.ALREADY_EXISTS
    assert (tmp_path / "out" / "a.md").read_text(encoding="utf-8") == "v1"


def test_write_artifacts_overwrite_true_replaces(tmp_path: Path) -> None:
    write_artifacts(
        outputs_root=tmp_path / "out", client_slug="acme", layout=OutputLayout.FLAT,
        files={"a.md": "v1"}, overwrite=False, dry_run=False,
    )
    artifacts, err = write_artifacts(
        outputs_root=tmp_path / "out", client_slug="acme", layout=OutputLayout.FLAT,
        files={"a.md": "v2"}, overwrite=True, dry_run=False,
    )
    assert err is None
    assert len(artifacts) == 1
    assert (tmp_path / "out" / "a.md").read_text(encoding="utf-8") == "v2"


# ---------- dry-run ----------

def test_write_artifacts_dry_run_does_not_touch_disk(tmp_path: Path) -> None:
    artifacts, err = write_artifacts(
        outputs_root=tmp_path / "out", client_slug="acme", layout=OutputLayout.FLAT,
        files={"a.md": "hi"}, overwrite=False, dry_run=True,
    )
    assert err is None
    assert len(artifacts) == 1
    assert artifacts[0].would_write is True
    assert not (tmp_path / "out").exists()


def test_write_artifacts_dry_run_ignores_overwrite_conflicts(tmp_path: Path) -> None:
    write_artifacts(
        outputs_root=tmp_path / "out", client_slug="acme", layout=OutputLayout.FLAT,
        files={"a.md": "v1"}, overwrite=False, dry_run=False,
    )
    artifacts, err = write_artifacts(
        outputs_root=tmp_path / "out", client_slug="acme", layout=OutputLayout.FLAT,
        files={"a.md": "v2"}, overwrite=False, dry_run=True,
    )
    assert err is None
    assert artifacts[0].would_write is True
    # Original file untouched.
    assert (tmp_path / "out" / "a.md").read_text(encoding="utf-8") == "v1"


# ---------- path traversal ----------

def test_write_artifacts_rejects_path_escaping_root(tmp_path: Path) -> None:
    outputs_root = tmp_path / "out"
    artifacts, err = write_artifacts(
        outputs_root=outputs_root,
        client_slug="acme",
        layout=OutputLayout.PER_CLIENT,
        files={"../../escape.md": "pwned"},
        overwrite=False,
        dry_run=False,
    )
    assert artifacts == []
    assert err is not None
    assert err.code is ErrorCode.PATH_NOT_ALLOWED
    assert not (tmp_path / "escape.md").exists()


def test_write_artifacts_rejects_traversal_even_in_dry_run(tmp_path: Path) -> None:
    outputs_root = tmp_path / "out"
    artifacts, err = write_artifacts(
        outputs_root=outputs_root,
        client_slug="acme",
        layout=OutputLayout.FLAT,
        files={"../escape.md": "pwned"},
        overwrite=False,
        dry_run=True,
    )
    assert artifacts == []
    assert err is not None
    assert err.code is ErrorCode.PATH_NOT_ALLOWED


# ---------- programmer error ----------

def test_write_artifacts_empty_filename_raises() -> None:
    import pytest

    with pytest.raises(ArtifactWriteError):
        write_artifacts(
            outputs_root=Path("out"), client_slug="acme", layout=OutputLayout.FLAT,
            files={"": "x"}, overwrite=False, dry_run=False,
        )
