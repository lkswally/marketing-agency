"""Tests for referential_integrity helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from core.memory import (
    ALL_KINDS,
    REFERENCE_MAP,
    JsonFileMemory,
    check_client_integrity,
    find_missing_references,
)

SLUG = "demo-co"


@pytest.fixture
def mem(tmp_path: Path) -> JsonFileMemory:
    return JsonFileMemory(tmp_path)


# ---------- kinds without rules ----------

def test_kind_without_rules_returns_no_issues(mem: JsonFileMemory) -> None:
    # ``channel`` has no outbound references in REFERENCE_MAP.
    assert "channel" not in REFERENCE_MAP
    issues = find_missing_references(
        mem, SLUG, "channel", {"id": "ch1", "label": "x"}
    )
    assert issues == []


# ---------- single id reference ----------

def test_persona_requires_existing_audience(mem: JsonFileMemory) -> None:
    persona = {"id": "p1", "audience_id": "a-missing", "archetype_name": "X"}
    issues = find_missing_references(mem, SLUG, "persona", persona)
    assert len(issues) == 1
    assert issues[0].target_kind == "audience"
    assert issues[0].target_id == "a-missing"
    assert issues[0].reason == "missing"


def test_persona_with_existing_audience_is_ok(mem: JsonFileMemory) -> None:
    mem.put(SLUG, "audience", "a1", {"id": "a1", "label": "x"})
    persona = {"id": "p1", "audience_id": "a1", "archetype_name": "X"}
    assert find_missing_references(mem, SLUG, "persona", persona) == []


def test_persona_with_empty_required_field_flagged(mem: JsonFileMemory) -> None:
    persona = {"id": "p1", "audience_id": "", "archetype_name": "X"}
    issues = find_missing_references(mem, SLUG, "persona", persona)
    assert len(issues) == 1
    assert issues[0].reason == "required_field_empty"


# ---------- list reference ----------

def test_campaign_audience_ids_partially_missing(mem: JsonFileMemory) -> None:
    mem.put(SLUG, "audience", "a1", {"id": "a1"})
    campaign = {
        "id": "camp1",
        "audience_ids": ["a1", "a-missing"],
        "channel_ids": [],
        "asset_ids": [],
        "offer_ids": [],
    }
    issues = find_missing_references(mem, SLUG, "campaign", campaign)
    assert len(issues) == 1
    assert issues[0].field_path == "audience_ids[1]"
    assert issues[0].target_id == "a-missing"


def test_campaign_empty_optional_id_list_is_ok(mem: JsonFileMemory) -> None:
    campaign = {
        "id": "c1",
        "audience_ids": [],
        "channel_ids": [],
        "asset_ids": [],
        "offer_ids": [],
    }
    assert find_missing_references(mem, SLUG, "campaign", campaign) == []


def test_campaign_with_all_refs_resolved(mem: JsonFileMemory) -> None:
    mem.put(SLUG, "audience", "a1", {"id": "a1"})
    mem.put(SLUG, "channel", "ch1", {"id": "ch1"})
    mem.put(SLUG, "asset", "as1", {"id": "as1"})
    mem.put(SLUG, "offer", "of1", {"id": "of1"})
    mem.put(SLUG, "brief", "br1", {"id": "br1"})
    campaign = {
        "id": "camp1",
        "brief_id": "br1",
        "audience_ids": ["a1"],
        "channel_ids": ["ch1"],
        "asset_ids": ["as1"],
        "offer_ids": ["of1"],
    }
    assert find_missing_references(mem, SLUG, "campaign", campaign) == []


def test_optional_single_id_missing_is_not_flagged(mem: JsonFileMemory) -> None:
    # Campaign.brief_id is optional; absence is fine.
    campaign = {
        "id": "camp1",
        "audience_ids": [],
        "channel_ids": [],
        "asset_ids": [],
        "offer_ids": [],
    }
    assert find_missing_references(mem, SLUG, "campaign", campaign) == []


def test_optional_single_id_dangling_is_flagged(mem: JsonFileMemory) -> None:
    # If brief_id is provided but does not resolve, flag it.
    campaign = {
        "id": "camp1",
        "brief_id": "br-missing",
        "audience_ids": [],
        "channel_ids": [],
        "asset_ids": [],
        "offer_ids": [],
    }
    issues = find_missing_references(mem, SLUG, "campaign", campaign)
    assert len(issues) == 1
    assert issues[0].field_path == "brief_id"
    assert issues[0].target_id == "br-missing"


# ---------- empty id in list ----------

def test_empty_id_in_list_flagged_as_empty_id(mem: JsonFileMemory) -> None:
    campaign = {
        "id": "c1",
        "audience_ids": ["", "a-missing"],
        "channel_ids": [],
        "asset_ids": [],
        "offer_ids": [],
    }
    issues = find_missing_references(mem, SLUG, "campaign", campaign)
    reasons = {(i.field_path, i.reason) for i in issues}
    assert ("audience_ids[0]", "empty_id") in reasons
    assert ("audience_ids[1]", "missing") in reasons


# ---------- client source uses slug as fallback id ----------

def test_client_uses_slug_as_source_id(mem: JsonFileMemory) -> None:
    client = {"slug": "demo-co", "name": "Demo", "brand_id": "b-missing"}
    issues = find_missing_references(mem, SLUG, "client", client)
    assert len(issues) == 1
    assert issues[0].source_id == "demo-co"


# ---------- check_client_integrity ----------

def test_check_client_integrity_aggregates(mem: JsonFileMemory) -> None:
    mem.put(SLUG, "persona", "p1", {"id": "p1", "audience_id": "a-missing"})
    mem.put(SLUG, "claim", "cl1", {"id": "cl1", "evidence_ids": ["ev-missing"]})
    issues = check_client_integrity(mem, SLUG)
    assert len(issues) == 2
    target_kinds = sorted(i.target_kind for i in issues)
    assert target_kinds == ["audience", "evidence"]


def test_check_client_integrity_clean_returns_empty(mem: JsonFileMemory) -> None:
    mem.put(SLUG, "audience", "a1", {"id": "a1"})
    mem.put(SLUG, "persona", "p1", {"id": "p1", "audience_id": "a1"})
    assert check_client_integrity(mem, SLUG) == []


def test_check_client_integrity_visits_all_known_kinds(mem: JsonFileMemory) -> None:
    # Sanity: every kind in REFERENCE_MAP also appears in ALL_KINDS, otherwise
    # check_client_integrity would silently skip its entities.
    for kind in REFERENCE_MAP:
        assert kind in ALL_KINDS, f"{kind} missing from ALL_KINDS"
