"""Tests for JsonFileMemory entity CRUD + multi-tenant isolation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.memory import EngramMemory, EntityNotFound, JsonFileMemory


@pytest.fixture
def mem(tmp_path: Path) -> JsonFileMemory:
    return JsonFileMemory(tmp_path)


# ---------- CRUD round-trip ----------

def test_put_then_get(mem: JsonFileMemory) -> None:
    mem.put("demo-co", "client", "c1", {"slug": "demo-co", "name": "Demo Co."})
    got = mem.get("demo-co", "client", "c1")
    assert got == {"slug": "demo-co", "name": "Demo Co."}


def test_put_overwrites(mem: JsonFileMemory) -> None:
    mem.put("demo-co", "client", "c1", {"slug": "demo-co", "name": "v1"})
    mem.put("demo-co", "client", "c1", {"slug": "demo-co", "name": "v2"})
    assert mem.get("demo-co", "client", "c1")["name"] == "v2"


def test_get_missing_raises(mem: JsonFileMemory) -> None:
    with pytest.raises(EntityNotFound) as exc:
        mem.get("demo-co", "client", "nope")
    assert exc.value.entity_id == "nope"


def test_delete_then_get_raises(mem: JsonFileMemory) -> None:
    mem.put("demo-co", "client", "c1", {"slug": "demo-co", "name": "X"})
    mem.delete("demo-co", "client", "c1")
    with pytest.raises(EntityNotFound):
        mem.get("demo-co", "client", "c1")


def test_delete_missing_raises(mem: JsonFileMemory) -> None:
    with pytest.raises(EntityNotFound):
        mem.delete("demo-co", "client", "nope")


def test_exists(mem: JsonFileMemory) -> None:
    assert mem.exists("demo-co", "client", "c1") is False
    mem.put("demo-co", "client", "c1", {"slug": "demo-co", "name": "X"})
    assert mem.exists("demo-co", "client", "c1") is True


# ---------- list ----------

def test_list_empty(mem: JsonFileMemory) -> None:
    assert mem.list("demo-co", "client") == []


def test_list_returns_stable_sorted_order(mem: JsonFileMemory) -> None:
    mem.put("demo-co", "campaign", "z", {"id": "z"})
    mem.put("demo-co", "campaign", "a", {"id": "a"})
    mem.put("demo-co", "campaign", "m", {"id": "m"})
    out = mem.list("demo-co", "campaign")
    assert [e["id"] for e in out] == ["a", "m", "z"]


# ---------- multi-tenant isolation ----------

def test_clients_are_isolated(mem: JsonFileMemory) -> None:
    mem.put("acme", "client", "c1", {"slug": "acme", "name": "Acme"})
    mem.put("demo-co", "client", "c1", {"slug": "demo-co", "name": "Demo"})
    assert mem.get("acme", "client", "c1")["name"] == "Acme"
    assert mem.get("demo-co", "client", "c1")["name"] == "Demo"
    assert mem.list("acme", "client")[0]["name"] == "Acme"
    assert mem.list("demo-co", "client")[0]["name"] == "Demo"


# ---------- _meta.json ----------

def test_meta_file_written_on_first_put(mem: JsonFileMemory, tmp_path: Path) -> None:
    mem.put("demo-co", "client", "c1", {"slug": "demo-co", "name": "X"})
    meta = tmp_path / "demo-co" / "_meta.json"
    assert meta.exists()
    payload = json.loads(meta.read_text())
    assert payload["contract_version"] == "memory.v1"
    assert payload["client_slug"] == "demo-co"


def test_meta_not_rewritten_on_subsequent_put(mem: JsonFileMemory, tmp_path: Path) -> None:
    mem.put("demo-co", "client", "c1", {"slug": "demo-co", "name": "X"})
    meta = tmp_path / "demo-co" / "_meta.json"
    mtime = meta.stat().st_mtime_ns
    mem.put("demo-co", "client", "c2", {"slug": "demo-co", "name": "Y"})
    assert meta.stat().st_mtime_ns == mtime


# ---------- slug + kind + id validation ----------

def test_invalid_slug_rejected(mem: JsonFileMemory) -> None:
    with pytest.raises(ValueError):
        mem.put("Bad Slug", "client", "c1", {})


def test_reserved_slug_rejected(mem: JsonFileMemory) -> None:
    with pytest.raises(ValueError):
        mem.put("_shared", "client", "c1", {})


def test_invalid_kind_rejected(mem: JsonFileMemory) -> None:
    with pytest.raises(ValueError):
        mem.put("demo-co", "Invalid Kind!", "c1", {})


def test_traversal_via_kind_blocked(mem: JsonFileMemory) -> None:
    # ".." or path separators must be rejected at the kind validator.
    with pytest.raises(ValueError):
        mem.put("demo-co", "../etc", "c1", {})


def test_traversal_via_id_blocked(mem: JsonFileMemory) -> None:
    with pytest.raises(ValueError):
        mem.put("demo-co", "client", "../etc/passwd", {})


def test_invalid_id_rejected(mem: JsonFileMemory) -> None:
    with pytest.raises(ValueError):
        mem.put("demo-co", "client", "has space", {})


# ---------- atomic writes ----------

def test_no_tmp_file_left_after_put(mem: JsonFileMemory, tmp_path: Path) -> None:
    mem.put("demo-co", "client", "c1", {"slug": "demo-co", "name": "X"})
    leftovers = list((tmp_path / "demo-co" / "client").glob("*.tmp"))
    assert leftovers == []


# ---------- EngramMemory scaffolding ----------

def test_engram_memory_raises_not_implemented() -> None:
    eng = EngramMemory()
    with pytest.raises(NotImplementedError):
        eng.put("demo-co", "client", "c1", {})
    with pytest.raises(NotImplementedError):
        eng.get("demo-co", "client", "c1")
    with pytest.raises(NotImplementedError):
        eng.list("demo-co", "client")
    with pytest.raises(NotImplementedError):
        eng.exists("demo-co", "client", "c1")
    with pytest.raises(NotImplementedError):
        eng.delete("demo-co", "client", "c1")
    with pytest.raises(NotImplementedError):
        eng.last_audit_hash("demo-co")
