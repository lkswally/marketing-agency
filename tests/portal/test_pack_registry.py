"""Tests for the portal pack registry."""

from __future__ import annotations

from portal.pack_registry import (
    PORTAL_PACK_REGISTRY,
    PortalPackSpec,
    iter_pack_specs,
)


def test_registry_has_14_entries() -> None:
    assert len(PORTAL_PACK_REGISTRY) == 14


def test_registry_is_sorted_by_order() -> None:
    seq = [s.order for s in iter_pack_specs()]
    assert seq == sorted(seq)
    assert seq == list(range(1, 15))


def test_registry_kinds_unique() -> None:
    kinds = [s.kind for s in PORTAL_PACK_REGISTRY]
    # The ATLAS bridge spec uses kind=atlas_handoff_brief — it
    # should still be unique within the registry.
    assert len(set(kinds)) == len(kinds)


def test_registry_required_packs_present() -> None:
    required = {s.kind for s in PORTAL_PACK_REGISTRY if not s.optional}
    # Strategy / approval / creative / visual are mandatory for any
    # campaign to be considered ready.
    assert "campaign_strategy_report" in required
    assert "approval_pack" in required
    assert "creative_asset_pack" in required
    assert "visual_direction_pack" in required


def test_registry_blockable_packs_have_field() -> None:
    blockables = [
        s for s in PORTAL_PACK_REGISTRY if s.blocks_publish_field
    ]
    # Every blockable pack uses the same field name.
    for s in blockables:
        assert s.blocks_publish_field == "blocks_publish"


def test_registry_titles_are_unique() -> None:
    titles = [s.title for s in PORTAL_PACK_REGISTRY]
    assert len(set(titles)) == len(titles)


def test_spec_is_frozen() -> None:
    spec = PORTAL_PACK_REGISTRY[0]
    try:
        spec.order = 999  # type: ignore[misc]
    except Exception:
        return
    raise AssertionError("PortalPackSpec should be frozen")


def test_spec_dataclass_fields() -> None:
    fields = set(PortalPackSpec.__dataclass_fields__.keys())
    assert fields == {
        "order", "kind", "singleton_id", "title",
        "markdown_filenames", "blocks_publish_field",
        "optional", "description",
        "extra_singleton_ids",  # MKT-9B
    }
