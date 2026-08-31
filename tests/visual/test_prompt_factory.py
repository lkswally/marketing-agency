"""VisualPromptFactory tests — state derivation, variants, persistence."""

from __future__ import annotations

from pathlib import Path

import pytest

from core.approval import ApprovalPackBuilder
from core.approval.models import ApprovalPack
from core.contracts import verify_chain
from core.creative import CreativeFactory
from core.creative.models import CreativeAssetState
from core.memory import JsonFileMemory
from core.strategy import StrategyPipeline
from core.visual import (
    SINGLETON_ID,
    VISUAL_PACK_KIND,
    VisualDirectionPack,
    VisualPromptFactory,
    build_and_persist,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
DEMO_BRIEF = REPO_ROOT / "examples" / "clients" / "demo-saas" / "brief.json"


@pytest.fixture
def mem(tmp_path: Path) -> JsonFileMemory:
    return JsonFileMemory(tmp_path)


@pytest.fixture
def demo_report(mem: JsonFileMemory):
    return StrategyPipeline(memory=mem).run_from_path(DEMO_BRIEF).report


@pytest.fixture
def clean_pack(mem: JsonFileMemory, demo_report) -> ApprovalPack:
    builder = ApprovalPackBuilder(memory=mem)
    pack = builder.build_from_report(demo_report)
    builder.persist(pack)
    return pack


@pytest.fixture
def creative_pack(mem: JsonFileMemory, demo_report, clean_pack):
    return CreativeFactory(memory=mem).build(demo_report, clean_pack)


# ---------- basic shape ----------

def test_build_returns_valid_pack(mem: JsonFileMemory, demo_report) -> None:
    pack = VisualPromptFactory(memory=mem).build(demo_report, None, None)
    assert isinstance(pack, VisualDirectionPack)
    assert pack.client_slug == demo_report.client_slug
    assert pack.contract_version == "visual-direction-pack.v1"


def test_pack_has_eleven_directions(mem: JsonFileMemory, demo_report) -> None:
    pack = VisualPromptFactory(memory=mem).build(demo_report, None, None)
    assert pack.total_directions == 11


def test_pack_has_twenty_two_variants(mem: JsonFileMemory, demo_report) -> None:
    pack = VisualPromptFactory(memory=mem).build(demo_report, None, None)
    # 11 directions × 2 variants each.
    assert pack.total_prompt_variants == 22


def test_every_direction_has_two_variants_a_and_b(
    mem: JsonFileMemory, demo_report
) -> None:
    pack = VisualPromptFactory(memory=mem).build(demo_report, None, None)
    for d in pack.directions:
        assert len(d.prompt_variants) == 2
        ids = {v.variant_id for v in d.prompt_variants}
        assert ids == {"A", "B"}


def test_style_guide_has_palettes(mem: JsonFileMemory, demo_report) -> None:
    pack = VisualPromptFactory(memory=mem).build(demo_report, None, None)
    assert pack.style_guide.palette_primary
    assert pack.style_guide.overall_mood


def test_global_risks_are_populated(mem: JsonFileMemory, demo_report) -> None:
    pack = VisualPromptFactory(memory=mem).build(demo_report, None, None)
    assert len(pack.global_visual_risks) >= 3
    cats = {r.category for r in pack.global_visual_risks}
    assert "stock_cliche" in cats
    assert "accessibility" in cats


def test_pack_provenance_references(
    mem: JsonFileMemory, demo_report, clean_pack, creative_pack
) -> None:
    pack = VisualPromptFactory(memory=mem).build(demo_report, clean_pack, creative_pack)
    assert pack.report_id == demo_report.report_id
    assert pack.approval_pack_id == clean_pack.pack_id
    assert pack.creative_pack_id == creative_pack.pack_id


def test_pack_provenance_optional_when_inputs_missing(
    mem: JsonFileMemory, demo_report
) -> None:
    pack = VisualPromptFactory(memory=mem).build(demo_report, None, None)
    assert pack.approval_pack_id is None
    assert pack.creative_pack_id is None


# ---------- state derivation ----------

def test_state_default_when_no_approval_is_needs_review(
    mem: JsonFileMemory, demo_report
) -> None:
    pack = VisualPromptFactory(memory=mem).build(demo_report, None, None)
    assert pack.derived_overall_state is CreativeAssetState.NEEDS_REVIEW
    for d in pack.directions:
        assert d.state is CreativeAssetState.NEEDS_REVIEW


def test_state_with_clean_approval_is_draft(
    mem: JsonFileMemory, demo_report, clean_pack
) -> None:
    pack = VisualPromptFactory(memory=mem).build(demo_report, clean_pack, None)
    assert pack.derived_overall_state is CreativeAssetState.DRAFT
    assert pack.blocks_publish is False
    for d in pack.directions:
        assert d.state is CreativeAssetState.DRAFT


def test_state_with_blocking_pack_is_blocked(
    mem: JsonFileMemory, demo_report
) -> None:
    risky = demo_report.model_copy(deep=True)
    risky.value_proposition.headline = (
        "Te aseguramos resultados garantizados sin riesgo"
    )
    builder = ApprovalPackBuilder(memory=mem)
    blocking = builder.build_from_report(risky)
    assert blocking.blocks_publish is True
    pack = VisualPromptFactory(memory=mem).build(risky, blocking, None)
    assert pack.derived_overall_state is CreativeAssetState.BLOCKED
    for d in pack.directions:
        assert d.state is CreativeAssetState.BLOCKED


def test_state_with_approved_pack_is_ready(
    mem: JsonFileMemory, demo_report, clean_pack
) -> None:
    builder = ApprovalPackBuilder(memory=mem)
    approved = builder.approve(
        demo_report.client_slug, clean_pack.pack_id, reviewer="lucas",
    )
    pack = VisualPromptFactory(memory=mem).build(demo_report, approved, None)
    assert pack.derived_overall_state is CreativeAssetState.READY_FOR_PUBLISH
    assert pack.blocks_publish is False


def test_risky_pack_also_blocks(mem: JsonFileMemory, demo_report) -> None:
    risky = demo_report.model_copy(deep=True)
    risky.value_proposition.headline = "Somos los mejores del mercado"
    builder = ApprovalPackBuilder(memory=mem)
    risky_pack = builder.build_from_report(risky)
    assert risky_pack.blocks_publish is True
    pack = VisualPromptFactory(memory=mem).build(risky, risky_pack, None)
    assert pack.derived_overall_state is CreativeAssetState.BLOCKED


# ---------- cardinal MKT-3C/3D rule: never published ----------

def test_no_direction_is_ever_published(
    mem: JsonFileMemory, demo_report, clean_pack
) -> None:
    builder = ApprovalPackBuilder(memory=mem)
    approved = builder.approve(
        demo_report.client_slug, clean_pack.pack_id, reviewer="x",
    )
    pack = VisualPromptFactory(memory=mem).build(demo_report, approved, None)
    values = {s.value for s in CreativeAssetState}
    assert "published" not in values
    for d in pack.directions:
        assert d.state is CreativeAssetState.READY_FOR_PUBLISH
        assert d.state.value != "published"


# ---------- variants carry 12 fields per the user spec ----------

def test_every_variant_carries_12_fields(mem: JsonFileMemory, demo_report) -> None:
    pack = VisualPromptFactory(memory=mem).build(demo_report, None, None)
    sample = pack.directions[0].prompt_variants[0]
    # All 12 user-spec fields must be populated.
    assert sample.objective
    assert sample.target_audience
    assert sample.visual_style
    assert sample.emotional_tone
    assert sample.composition
    assert sample.in_image_text  # list, but non-empty by construction
    assert sample.visual_elements
    assert sample.suggested_colors
    assert sample.aspect_ratio
    assert sample.restrictions
    assert sample.negative_prompt
    assert sample.intended_use
    # Plus the ready-to-paste assembled prompt.
    assert sample.full_prompt_text


def test_full_prompt_contains_objective_marker(
    mem: JsonFileMemory, demo_report
) -> None:
    pack = VisualPromptFactory(memory=mem).build(demo_report, None, None)
    for d in pack.directions:
        for v in d.prompt_variants:
            assert "Objective:" in v.full_prompt_text
            assert "Aspect ratio:" in v.full_prompt_text


# ---------- persistence ----------

def test_persist_writes_to_memory(mem: JsonFileMemory, demo_report) -> None:
    factory = VisualPromptFactory(memory=mem)
    pack = factory.build(demo_report, None, None)
    factory.persist(pack)
    assert mem.exists(demo_report.client_slug, VISUAL_PACK_KIND, SINGLETON_ID)


def test_persist_emits_audit_event(mem: JsonFileMemory, demo_report) -> None:
    factory = VisualPromptFactory(memory=mem)
    factory.persist(factory.build(demo_report, None, None))
    events = mem.read_audit_events(demo_report.client_slug)
    notes = [e for e in events if e.event_type.value == "note"]
    assert any("visual_pack" in e.payload for e in notes)
    assert verify_chain(events) == []


def test_persist_then_load_returns_same_pack(
    mem: JsonFileMemory, demo_report
) -> None:
    factory = VisualPromptFactory(memory=mem)
    saved = factory.build(demo_report, None, None)
    factory.persist(saved)
    loaded = factory.load(demo_report.client_slug)
    assert loaded.pack_id == saved.pack_id


def test_re_persisting_emits_updated_event(
    mem: JsonFileMemory, demo_report
) -> None:
    factory = VisualPromptFactory(memory=mem)
    factory.persist(factory.build(demo_report, None, None))
    factory.persist(factory.build(demo_report, None, None))
    events = mem.read_audit_events(demo_report.client_slug)
    actions = [
        e.payload["visual_pack"]["action"]
        for e in events
        if "visual_pack" in e.payload
    ]
    assert "created" in actions
    assert "updated" in actions


def test_build_and_persist_helper(mem: JsonFileMemory, demo_report) -> None:
    pack = build_and_persist(mem, demo_report, None, None)
    assert mem.exists(demo_report.client_slug, VISUAL_PACK_KIND, SINGLETON_ID)
    assert pack.total_directions == 11


# ---------- creative pack integration ----------

def test_directions_reference_creative_asset_dates(
    mem: JsonFileMemory, demo_report, clean_pack, creative_pack
) -> None:
    pack = VisualPromptFactory(memory=mem).build(demo_report, clean_pack, creative_pack)
    # At least some piece types should have a scheduled date from the creative pack.
    scheduled_count = sum(1 for d in pack.directions if d.scheduled_for is not None)
    assert scheduled_count > 0


def test_directions_reference_creative_asset_ids(
    mem: JsonFileMemory, demo_report, clean_pack, creative_pack
) -> None:
    pack = VisualPromptFactory(memory=mem).build(demo_report, clean_pack, creative_pack)
    assert any(d.source_creative_asset_id for d in pack.directions)


# ---------- determinism ----------

def test_pack_is_deterministic_on_same_inputs(
    mem: JsonFileMemory, demo_report, clean_pack
) -> None:
    f = VisualPromptFactory(memory=mem)
    a = f.build(demo_report, clean_pack, None)
    b = f.build(demo_report, clean_pack, None)
    # Same prompt text per variant.
    for da, db in zip(a.directions, b.directions, strict=True):
        for va, vb in zip(da.prompt_variants, db.prompt_variants, strict=True):
            assert va.full_prompt_text == vb.full_prompt_text


# ---------- checklist propagation ----------

def test_per_direction_checklist_present(
    mem: JsonFileMemory, demo_report
) -> None:
    pack = VisualPromptFactory(memory=mem).build(demo_report, None, None)
    for d in pack.directions:
        assert d.checklist
        cats = {it.category for it in d.checklist}
        assert "composition" in cats
        assert "format" in cats


def test_blocking_pack_includes_blocker_item(
    mem: JsonFileMemory, demo_report
) -> None:
    risky = demo_report.model_copy(deep=True)
    risky.value_proposition.headline = (
        "Te aseguramos resultados garantizados sin riesgo"
    )
    builder = ApprovalPackBuilder(memory=mem)
    blocking = builder.build_from_report(risky)
    pack = VisualPromptFactory(memory=mem).build(risky, blocking, None)
    for d in pack.directions:
        severities = {it.severity for it in d.checklist}
        assert "blocker" in severities
