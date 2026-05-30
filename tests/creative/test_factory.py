"""CreativeFactory tests — state derivation, A/B variants, blocks_publish."""

from __future__ import annotations

from pathlib import Path

import pytest

from core.approval import ApprovalPackBuilder
from core.approval.models import ApprovalPack
from core.contracts import verify_chain
from core.creative import (
    CREATIVE_PACK_KIND,
    SINGLETON_ID,
    CreativeAssetPack,
    CreativeAssetState,
    CreativeFactory,
    build_and_persist,
)
from core.memory import JsonFileMemory
from core.strategy import StrategyPipeline

REPO_ROOT = Path(__file__).resolve().parents[2]
DEMO_BRIEF = REPO_ROOT / "examples" / "clients" / "demo-saas" / "brief.json"


@pytest.fixture
def mem(tmp_path: Path) -> JsonFileMemory:
    return JsonFileMemory(tmp_path)


@pytest.fixture
def demo_report(mem: JsonFileMemory):
    return StrategyPipeline(memory=mem).run_from_path(DEMO_BRIEF).report


@pytest.fixture
def clean_approval_pack(mem: JsonFileMemory, demo_report) -> ApprovalPack:
    builder = ApprovalPackBuilder(memory=mem)
    pack = builder.build_from_report(demo_report)
    builder.persist(pack)
    return pack


# ---------- factory builds a pack with the expected shape ----------

def test_build_returns_valid_pack(mem: JsonFileMemory, demo_report) -> None:
    factory = CreativeFactory(memory=mem)
    pack = factory.build(demo_report, None)
    assert isinstance(pack, CreativeAssetPack)
    assert pack.client_slug == demo_report.client_slug
    assert pack.report_id == demo_report.report_id
    assert pack.report_contract_version == demo_report.contract_version
    assert pack.contract_version == "creative-pack.v1"


def test_pack_has_assets_of_every_kind(mem: JsonFileMemory, demo_report) -> None:
    pack = CreativeFactory(memory=mem).build(demo_report, None)
    counts = pack.count_by_kind()
    assert counts["social_post"] > 0
    assert counts["email"] > 0
    assert counts["reels_script"] > 0
    assert counts["flyer_copy"] > 0
    assert counts["image_prompt"] > 0


def test_pack_counts_match_specs(mem: JsonFileMemory, demo_report) -> None:
    pack = CreativeFactory(memory=mem).build(demo_report, None)
    # 3 top channels × 2 posts per channel.
    assert len(pack.social_posts) == 6
    # MKT-3A demo brief produces 4 emails.
    assert len(pack.emails) == 4
    # 3 reels scripts from MKT-3A.
    assert len(pack.reels) == 3
    # Three default flyer formats.
    assert len(pack.flyers) == 3
    # 3 briefs from MKT-3A + 1 OOH bonus.
    assert len(pack.image_prompts) == 4


# ---------- variants ----------

def test_every_social_has_two_hook_and_two_cta_variants(
    mem: JsonFileMemory, demo_report
) -> None:
    pack = CreativeFactory(memory=mem).build(demo_report, None)
    for p in pack.social_posts:
        assert len(p.hook_variants) == 2
        assert {h.variant_id for h in p.hook_variants} == {"A", "B"}
        assert len(p.cta_variants) == 2
        assert {c.variant_id for c in p.cta_variants} == {"A", "B"}


def test_every_email_has_two_subject_variants(
    mem: JsonFileMemory, demo_report
) -> None:
    pack = CreativeFactory(memory=mem).build(demo_report, None)
    for e in pack.emails:
        assert len(e.subject_line_variants) == 2


def test_every_reels_has_two_hook_variants(mem: JsonFileMemory, demo_report) -> None:
    pack = CreativeFactory(memory=mem).build(demo_report, None)
    for r in pack.reels:
        assert len(r.hook_variants) == 2


def test_every_flyer_has_two_headline_variants(
    mem: JsonFileMemory, demo_report
) -> None:
    pack = CreativeFactory(memory=mem).build(demo_report, None)
    for f in pack.flyers:
        assert len(f.headline_variants) == 2


# ---------- state derivation rules ----------

def test_state_default_when_no_approval_pack_is_needs_review(
    mem: JsonFileMemory, demo_report
) -> None:
    pack = CreativeFactory(memory=mem).build(demo_report, None)
    # Conservative default: with no audit, everything is needs_review.
    assert pack.derived_overall_state is CreativeAssetState.NEEDS_REVIEW
    for asset_list in (pack.social_posts, pack.emails, pack.reels, pack.flyers, pack.image_prompts):
        for a in asset_list:
            assert a.state is CreativeAssetState.NEEDS_REVIEW


def test_state_with_clean_approval_pack_is_draft(
    mem: JsonFileMemory, demo_report, clean_approval_pack: ApprovalPack
) -> None:
    pack = CreativeFactory(memory=mem).build(demo_report, clean_approval_pack)
    assert pack.derived_overall_state is CreativeAssetState.DRAFT
    assert pack.blocks_publish is False
    for asset_list in (pack.social_posts, pack.emails, pack.reels, pack.flyers, pack.image_prompts):
        for a in asset_list:
            assert a.state is CreativeAssetState.DRAFT


def test_state_with_blocking_pack_is_blocked(
    mem: JsonFileMemory, demo_report
) -> None:
    """`blocks_publish=True` propagates to BLOCKED on every asset."""
    risky = demo_report.model_copy(deep=True)
    risky.value_proposition.headline = (
        "Te aseguramos resultados garantizados sin riesgo"
    )
    builder = ApprovalPackBuilder(memory=mem)
    blocking_pack = builder.build_from_report(risky)
    assert blocking_pack.blocks_publish is True

    pack = CreativeFactory(memory=mem).build(risky, blocking_pack)
    assert pack.derived_overall_state is CreativeAssetState.BLOCKED
    assert pack.blocks_publish is True
    for asset_list in (pack.social_posts, pack.emails, pack.reels, pack.flyers, pack.image_prompts):
        for a in asset_list:
            assert a.state is CreativeAssetState.BLOCKED


def test_state_with_approved_pack_is_ready_for_publish(
    mem: JsonFileMemory, demo_report, clean_approval_pack: ApprovalPack
) -> None:
    """Approved + non-blocking → ready_for_publish."""
    builder = ApprovalPackBuilder(memory=mem)
    approved = builder.approve(demo_report.client_slug, reviewer="lucas")
    pack = CreativeFactory(memory=mem).build(demo_report, approved)
    assert pack.derived_overall_state is CreativeAssetState.READY_FOR_PUBLISH
    assert pack.blocks_publish is False
    for a in pack.social_posts:
        assert a.state is CreativeAssetState.READY_FOR_PUBLISH


def test_risky_only_pack_propagates_blocked(
    mem: JsonFileMemory, demo_report
) -> None:
    """Risky-severity pack ALSO blocks publish (per ADR 0010 D-10.10)."""
    risky = demo_report.model_copy(deep=True)
    risky.value_proposition.headline = "Somos los mejores del mercado"
    builder = ApprovalPackBuilder(memory=mem)
    risky_pack = builder.build_from_report(risky)
    # Risky non-approved pack blocks publish.
    assert risky_pack.blocks_publish is True
    pack = CreativeFactory(memory=mem).build(risky, risky_pack)
    assert pack.derived_overall_state is CreativeAssetState.BLOCKED


def test_caveat_only_pack_keeps_draft(
    mem: JsonFileMemory, demo_report
) -> None:
    caveat = demo_report.model_copy(deep=True)
    caveat.email_sequence.emails[0].subject = "Solo hoy"
    builder = ApprovalPackBuilder(memory=mem)
    caveat_pack = builder.build_from_report(caveat)
    # Caveat does NOT block.
    assert caveat_pack.blocks_publish is False
    pack = CreativeFactory(memory=mem).build(caveat, caveat_pack)
    # State is draft (caveat severity, not approved yet).
    assert pack.derived_overall_state is CreativeAssetState.DRAFT


# ---------- the cardinal MKT-3C rule: never published ----------

def test_no_asset_is_ever_published(
    mem: JsonFileMemory, demo_report, clean_approval_pack: ApprovalPack
) -> None:
    """Even after approval, the terminal positive state is READY_FOR_PUBLISH."""
    builder = ApprovalPackBuilder(memory=mem)
    approved = builder.approve(demo_report.client_slug, reviewer="x")
    pack = CreativeFactory(memory=mem).build(demo_report, approved)
    # `published` is not part of the CreativeAssetState enum.
    values = {s.value for s in CreativeAssetState}
    assert "published" not in values
    for asset_list in (pack.social_posts, pack.emails, pack.reels, pack.flyers, pack.image_prompts):
        for a in asset_list:
            assert a.state.value != "published"
            assert a.state is CreativeAssetState.READY_FOR_PUBLISH


# ---------- persistence ----------

def test_persist_writes_to_memory(mem: JsonFileMemory, demo_report) -> None:
    factory = CreativeFactory(memory=mem)
    pack = factory.build(demo_report, None)
    factory.persist(pack)
    assert mem.exists(demo_report.client_slug, CREATIVE_PACK_KIND, SINGLETON_ID)
    raw = mem.get(demo_report.client_slug, CREATIVE_PACK_KIND, SINGLETON_ID)
    assert raw["pack_id"] == pack.pack_id


def test_persist_emits_audit_event(mem: JsonFileMemory, demo_report) -> None:
    factory = CreativeFactory(memory=mem)
    factory.persist(factory.build(demo_report, None))
    events = mem.read_audit_events(demo_report.client_slug)
    notes = [e for e in events if e.event_type.value == "note"]
    assert any("creative_pack" in e.payload for e in notes)
    assert verify_chain(events) == []


def test_persist_then_load_returns_same_pack(
    mem: JsonFileMemory, demo_report
) -> None:
    factory = CreativeFactory(memory=mem)
    saved = factory.build(demo_report, None)
    factory.persist(saved)
    loaded = factory.load(demo_report.client_slug)
    assert loaded.pack_id == saved.pack_id


def test_re_persisting_emits_updated_event(
    mem: JsonFileMemory, demo_report
) -> None:
    factory = CreativeFactory(memory=mem)
    factory.persist(factory.build(demo_report, None))
    factory.persist(factory.build(demo_report, None))
    events = mem.read_audit_events(demo_report.client_slug)
    actions = [
        e.payload["creative_pack"]["action"]
        for e in events
        if "creative_pack" in e.payload
    ]
    assert "created" in actions
    assert "updated" in actions


# ---------- references to upstream artifacts ----------

def test_pack_references_approval_pack_when_present(
    mem: JsonFileMemory, demo_report, clean_approval_pack: ApprovalPack
) -> None:
    pack = CreativeFactory(memory=mem).build(demo_report, clean_approval_pack)
    assert pack.approval_pack_id == clean_approval_pack.pack_id
    assert pack.approval_pack_contract_version == clean_approval_pack.contract_version


def test_pack_omits_approval_ref_when_absent(
    mem: JsonFileMemory, demo_report
) -> None:
    pack = CreativeFactory(memory=mem).build(demo_report, None)
    assert pack.approval_pack_id is None
    assert pack.approval_pack_contract_version is None


# ---------- convenience helper ----------

def test_build_and_persist_helper(mem: JsonFileMemory, demo_report) -> None:
    pack = build_and_persist(mem, demo_report, None)
    assert mem.exists(demo_report.client_slug, CREATIVE_PACK_KIND, SINGLETON_ID)
    assert pack.total_assets > 0


# ---------- scheduled dates ----------

def test_assets_carry_scheduled_for(mem: JsonFileMemory, demo_report) -> None:
    pack = CreativeFactory(memory=mem).build(demo_report, None)
    # Every email / social / reels / flyer gets a date.
    for asset_list in (pack.social_posts, pack.emails, pack.reels, pack.flyers):
        for a in asset_list:
            assert a.scheduled_for is not None


def test_image_prompts_do_not_carry_dates(mem: JsonFileMemory, demo_report) -> None:
    """Image prompts are reusable; they intentionally do not get a date."""
    pack = CreativeFactory(memory=mem).build(demo_report, None)
    # `scheduled_for` isn't even on ImagePromptAsset, so just verify it
    # round-trips.
    assert all(p.title for p in pack.image_prompts)
