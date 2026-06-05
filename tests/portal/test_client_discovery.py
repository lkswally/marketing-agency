"""Tests for portal.client_discovery — pure filesystem walks."""

from __future__ import annotations

from pathlib import Path

from portal.client_discovery import discover_clients, list_outputs_files


def test_discover_clients_returns_empty_when_roots_missing(tmp_path: Path) -> None:
    out = discover_clients(
        root=tmp_path / "does-not-exist",
        outputs_dir=tmp_path / "also-missing",
    )
    assert out == []


def test_discover_clients_union(tmp_path: Path) -> None:
    root = tmp_path / "data"
    outputs = tmp_path / "outputs"
    (root / "acme" / "strategy").mkdir(parents=True)
    (root / "beta" / "strategy").mkdir(parents=True)
    (outputs / "acme").mkdir(parents=True)
    (outputs / "gamma").mkdir(parents=True)
    assert discover_clients(root=root, outputs_dir=outputs) == [
        "acme", "beta", "gamma",
    ]


def test_discover_clients_skips_reserved(tmp_path: Path) -> None:
    root = tmp_path / "data"
    (root / "_shared").mkdir(parents=True)
    (root / "acme").mkdir(parents=True)
    assert discover_clients(root=root, outputs_dir=None) == ["acme"]


def test_discover_clients_skips_files(tmp_path: Path) -> None:
    root = tmp_path / "data"
    root.mkdir()
    (root / "notes.txt").write_text("ignore me", encoding="utf-8")
    (root / "acme").mkdir()
    assert discover_clients(root=root, outputs_dir=None) == ["acme"]


def test_list_outputs_files_filters_md_and_json(tmp_path: Path) -> None:
    base = tmp_path / "outputs" / "acme"
    base.mkdir(parents=True)
    (base / "a.md").write_text("x", encoding="utf-8")
    (base / "b.json").write_text("{}", encoding="utf-8")
    (base / "c.txt").write_text("nope", encoding="utf-8")
    (base / "sub").mkdir()  # directories ignored
    files = list_outputs_files(outputs_dir=tmp_path / "outputs", client_slug="acme")
    names = sorted(p.name for p in files)
    assert names == ["a.md", "b.json"]


def test_list_outputs_files_handles_missing_dir(tmp_path: Path) -> None:
    out = list_outputs_files(outputs_dir=tmp_path / "outputs", client_slug="ghost")
    assert out == []
