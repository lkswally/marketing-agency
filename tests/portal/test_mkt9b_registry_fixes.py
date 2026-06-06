"""MKT-9B regression tests for the portal registry fixes.

After the LEXIA Alpha Pilot we discovered the portal reported
``Campaign strategy`` and ``n8n execution plan`` as MISSING even
though both packs were persisted. Root cause: the registry used
the wrong ``kind`` values. These tests pin the correct values so
the bug cannot regress.
"""

from __future__ import annotations

from portal.pack_registry import PORTAL_PACK_REGISTRY


def test_strategy_spec_uses_runtime_kind() -> None:
    """Pin: the strategy spec must point at the real persisted kind
    (``campaign_strategy_report``), NOT the legacy ``strategy``."""
    spec = next(s for s in PORTAL_PACK_REGISTRY if s.title == "Campaign strategy")
    assert spec.kind == "campaign_strategy_report"


def test_n8n_spec_uses_runtime_kind() -> None:
    """Pin: the n8n spec must point at ``n8n_execution_payload``
    — the kind the pipeline actually writes."""
    spec = next(s for s in PORTAL_PACK_REGISTRY if s.title == "n8n execution plan")
    assert spec.kind == "n8n_execution_payload"


def test_no_spec_uses_stale_kinds() -> None:
    """Guard against future drift: neither ``strategy`` nor
    ``n8n_execution_plan`` should ever appear as a kind again."""
    forbidden = {"strategy", "n8n_execution_plan"}
    for s in PORTAL_PACK_REGISTRY:
        assert s.kind not in forbidden, (
            f"Spec {s.title!r} still uses the stale kind {s.kind!r}"
        )


def test_atlas_spec_probes_per_kind_singletons() -> None:
    """Pin: the ATLAS spec must declare the three kind singletons
    (``landing`` / ``branding`` / ``page_design``) so the loader
    can find any of them after MKT-9B's per-kind persistence."""
    spec = next(
        s for s in PORTAL_PACK_REGISTRY if s.kind == "atlas_handoff_brief"
    )
    assert set(spec.extra_singleton_ids) >= {
        "landing", "branding", "page_design",
    }
