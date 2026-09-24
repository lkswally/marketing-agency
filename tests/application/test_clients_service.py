"""Tests for the client directory read service (Web Foundation)."""

from __future__ import annotations

from pathlib import Path

from core.application.services.clients import list_clients


def test_empty_root_returns_empty_list(tmp_path: Path) -> None:
    result = list_clients(root=tmp_path / "mem")
    assert result.ok
    assert result.data == []


def test_one_client_in_memory_root(tmp_path: Path) -> None:
    (tmp_path / "mem" / "acme").mkdir(parents=True)
    result = list_clients(root=tmp_path / "mem")
    assert result.ok
    assert len(result.data) == 1
    summary = result.data[0]
    assert summary.client_slug == "acme"
    assert summary.has_memory_data is True
    assert summary.has_outputs is False


def test_multiple_clients_sorted_alphabetically(tmp_path: Path) -> None:
    for slug in ("zeta", "acme", "mid-co"):
        (tmp_path / "mem" / slug).mkdir(parents=True)
    result = list_clients(root=tmp_path / "mem")
    slugs = [s.client_slug for s in result.data]
    assert slugs == ["acme", "mid-co", "zeta"]


def test_union_of_memory_and_outputs_roots(tmp_path: Path) -> None:
    (tmp_path / "mem" / "only-mem").mkdir(parents=True)
    (tmp_path / "out" / "only-out").mkdir(parents=True)
    (tmp_path / "mem" / "both").mkdir(parents=True)
    (tmp_path / "out" / "both").mkdir(parents=True)

    result = list_clients(root=tmp_path / "mem", outputs_root=tmp_path / "out")
    by_slug = {s.client_slug: s for s in result.data}
    assert set(by_slug) == {"only-mem", "only-out", "both"}
    assert by_slug["only-mem"].has_memory_data is True
    assert by_slug["only-mem"].has_outputs is False
    assert by_slug["only-out"].has_memory_data is False
    assert by_slug["only-out"].has_outputs is True
    assert by_slug["both"].has_memory_data is True
    assert by_slug["both"].has_outputs is True


def test_outputs_root_none_is_ignored(tmp_path: Path) -> None:
    (tmp_path / "mem" / "acme").mkdir(parents=True)
    result = list_clients(root=tmp_path / "mem", outputs_root=None)
    assert result.ok
    assert [s.client_slug for s in result.data] == ["acme"]


def test_missing_roots_tolerated_not_an_error(tmp_path: Path) -> None:
    result = list_clients(
        root=tmp_path / "does-not-exist", outputs_root=tmp_path / "also-missing",
    )
    assert result.ok
    assert result.data == []


# ---------- tenant/path safety ----------

def test_reserved_shared_dir_never_listed_as_a_client(tmp_path: Path) -> None:
    (tmp_path / "mem" / "_shared").mkdir(parents=True)
    (tmp_path / "mem" / "acme").mkdir(parents=True)
    result = list_clients(root=tmp_path / "mem")
    assert [s.client_slug for s in result.data] == ["acme"]


def test_no_raw_filesystem_paths_in_result(tmp_path: Path) -> None:
    """Summaries must never leak the absolute root path — only the
    slug and two booleans, as documented."""
    (tmp_path / "mem" / "acme").mkdir(parents=True)
    result = list_clients(root=tmp_path / "mem")
    summary = result.data[0]
    assert set(summary.model_dump().keys()) == {
        "client_slug", "has_memory_data", "has_outputs",
    }


# ---------- malformed / unrelated entries ignored ----------

def test_files_at_root_level_are_ignored_not_listed_as_clients(tmp_path: Path) -> None:
    root = tmp_path / "mem"
    root.mkdir(parents=True)
    (root / "acme").mkdir()
    (root / "stray-file.json").write_text("{}", encoding="utf-8")
    result = list_clients(root=root)
    assert [s.client_slug for s in result.data] == ["acme"]


def test_meta_prefixed_directories_are_ignored(tmp_path: Path) -> None:
    root = tmp_path / "mem"
    root.mkdir(parents=True)
    (root / "acme").mkdir()
    (root / "_meta_something").mkdir()
    result = list_clients(root=root)
    assert [s.client_slug for s in result.data] == ["acme"]
