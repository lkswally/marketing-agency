"""ApprovalPackBuilder tests — build, persist, transitions, audit events."""

from __future__ import annotations

from pathlib import Path

import pytest

from core.approval import (
    APPROVAL_PACK_KIND,
    SINGLETON_ID,
    ApprovalPackBuilder,
    ApprovalState,
    ApprovalStateError,
    ClaimCategory,
    audit_and_persist,
)
from core.contracts import verify_chain
from core.domain.enums import ClaimSeverity
from core.memory import JsonFileMemory
from core.strategy import StrategyPipeline

REPO_ROOT = Path(__file__).resolve().parents[2]
DEMO_BRIEF = REPO_ROOT / "examples" / "clients" / "demo-saas" / "brief.json"


@pytest.fixture
def mem(tmp_path: Path) -> JsonFileMemory:
    return JsonFileMemory(tmp_path)


@pytest.fixture
def demo_report(mem: JsonFileMemory):
    pipeline = StrategyPipeline(memory=mem)
    return pipeline.run_from_path(DEMO_BRIEF).report


# ---------- build_from_report ----------

def test_build_pack_from_demo_report(mem: JsonFileMemory, demo_report) -> None:
    builder = ApprovalPackBuilder(memory=mem)
    pack = builder.build_from_report(demo_report)
    assert pack.client_slug == demo_report.client_slug
    assert pack.report_id == demo_report.report_id
    assert pack.report_contract_version == demo_report.contract_version
    assert pack.state is ApprovalState.DRAFT
    # Demo report is clean → safe + no blocks.
    assert pack.overall_severity is ClaimSeverity.SAFE
    assert pack.blocks_publish is False
    assert pack.rule_set_id == "default-rules.v1"


def test_pack_has_structural_checklist(mem: JsonFileMemory, demo_report) -> None:
    builder = ApprovalPackBuilder(memory=mem)
    pack = builder.build_from_report(demo_report)
    # Two structural items always present, regardless of detections.
    assert len(pack.checklist) >= 2


def test_pack_blocks_publish_with_risky_text(
    mem: JsonFileMemory, demo_report
) -> None:
    # Inject risky claim into the report and re-audit.
    risky = demo_report.model_copy(deep=True)
    risky.value_proposition.headline = (
        "Te aseguramos resultados garantizados sin riesgo"
    )
    builder = ApprovalPackBuilder(memory=mem)
    pack = builder.build_from_report(risky)
    assert pack.overall_severity is ClaimSeverity.UNSAFE
    assert pack.blocks_publish is True
    # Checklist must include at least one blocker.
    severities = {item.severity for item in pack.checklist}
    assert "blocker" in severities


def test_pack_blocks_publish_with_risky_only(
    mem: JsonFileMemory, demo_report
) -> None:
    risky = demo_report.model_copy(deep=True)
    risky.value_proposition.headline = "Somos los mejores del mercado"
    builder = ApprovalPackBuilder(memory=mem)
    pack = builder.build_from_report(risky)
    # Superlative is RISKY, not UNSAFE — still blocks publish on a draft.
    assert pack.overall_severity is ClaimSeverity.RISKY
    assert pack.blocks_publish is True


def test_pack_caveat_only_does_not_block(mem: JsonFileMemory, demo_report) -> None:
    caveat = demo_report.model_copy(deep=True)
    caveat.email_sequence.emails[0].subject = "Solo hoy: revisalo"
    builder = ApprovalPackBuilder(memory=mem)
    pack = builder.build_from_report(caveat)
    # caveat-only does not block publish.
    assert pack.overall_severity is ClaimSeverity.CAVEAT
    assert pack.blocks_publish is False


# ---------- persistence ----------

def test_persist_writes_to_memory(mem: JsonFileMemory, demo_report) -> None:
    # MKT-11E: persisted at <pack_id>.json, not the "current" singleton.
    builder = ApprovalPackBuilder(memory=mem)
    pack = builder.build_from_report(demo_report)
    builder.persist(pack)
    assert mem.exists(demo_report.client_slug, APPROVAL_PACK_KIND, pack.pack_id)
    assert not mem.exists(demo_report.client_slug, APPROVAL_PACK_KIND, SINGLETON_ID)
    raw = mem.get(demo_report.client_slug, APPROVAL_PACK_KIND, pack.pack_id)
    assert raw["pack_id"] == pack.pack_id


def test_persist_emits_audit_event(mem: JsonFileMemory, demo_report) -> None:
    builder = ApprovalPackBuilder(memory=mem)
    pack = builder.build_from_report(demo_report)
    builder.persist(pack)
    events = mem.read_audit_events(demo_report.client_slug)
    notes = [e for e in events if e.event_type.value == "note"]
    assert any("approval_pack" in e.payload for e in notes)
    # Chain remains valid.
    assert verify_chain(events) == []


def test_load_returns_persisted_pack(mem: JsonFileMemory, demo_report) -> None:
    builder = ApprovalPackBuilder(memory=mem)
    saved = builder.build_from_report(demo_report)
    builder.persist(saved)
    loaded = builder.load(demo_report.client_slug, saved.pack_id)
    assert loaded.pack_id == saved.pack_id


# ---------- transitions ----------

def test_submit_for_review_succeeds_on_draft(
    mem: JsonFileMemory, demo_report
) -> None:
    builder = ApprovalPackBuilder(memory=mem)
    pack = builder.build_from_report(demo_report)
    builder.persist(pack)
    submitted = builder.submit_for_review(demo_report.client_slug, pack.pack_id)
    assert submitted.state is ApprovalState.NEEDS_REVIEW
    assert submitted.updated_at >= pack.created_at


def test_cannot_submit_twice(mem: JsonFileMemory, demo_report) -> None:
    builder = ApprovalPackBuilder(memory=mem)
    pack = builder.build_from_report(demo_report)
    builder.persist(pack)
    builder.submit_for_review(demo_report.client_slug, pack.pack_id)
    with pytest.raises(ApprovalStateError):
        builder.submit_for_review(demo_report.client_slug, pack.pack_id)


def test_approve_records_decision(mem: JsonFileMemory, demo_report) -> None:
    builder = ApprovalPackBuilder(memory=mem)
    pack = builder.build_from_report(demo_report)
    builder.persist(pack)
    approved = builder.approve(
        demo_report.client_slug, pack.pack_id, reviewer="lucas", notes="OK"
    )
    assert approved.state is ApprovalState.APPROVED
    assert approved.decision is not None
    assert approved.decision.reviewer == "lucas"
    assert approved.decision.notes == "OK"
    # Approved packs never block publish (policy D-10.x).
    assert approved.blocks_publish is False


def test_reject_records_decision(mem: JsonFileMemory, demo_report) -> None:
    builder = ApprovalPackBuilder(memory=mem)
    pack = builder.build_from_report(demo_report)
    builder.persist(pack)
    rejected = builder.reject(
        demo_report.client_slug, pack.pack_id, reviewer="lucas", notes="no"
    )
    assert rejected.state is ApprovalState.REJECTED
    assert rejected.decision is not None
    # Rejected packs always block publish.
    assert rejected.blocks_publish is True


def test_cannot_approve_after_reject(mem: JsonFileMemory, demo_report) -> None:
    builder = ApprovalPackBuilder(memory=mem)
    pack = builder.build_from_report(demo_report)
    builder.persist(pack)
    builder.reject(demo_report.client_slug, pack.pack_id, reviewer="r")
    with pytest.raises(ApprovalStateError):
        builder.approve(demo_report.client_slug, pack.pack_id, reviewer="r")


def test_cannot_reject_after_approve(mem: JsonFileMemory, demo_report) -> None:
    builder = ApprovalPackBuilder(memory=mem)
    pack = builder.build_from_report(demo_report)
    builder.persist(pack)
    builder.approve(demo_report.client_slug, pack.pack_id, reviewer="r")
    with pytest.raises(ApprovalStateError):
        builder.reject(demo_report.client_slug, pack.pack_id, reviewer="r")


def test_transitions_emit_audit_events(
    mem: JsonFileMemory, demo_report
) -> None:
    builder = ApprovalPackBuilder(memory=mem)
    pack = builder.build_from_report(demo_report)
    builder.persist(pack)
    builder.submit_for_review(demo_report.client_slug, pack.pack_id)
    builder.approve(demo_report.client_slug, pack.pack_id, reviewer="lucas")
    events = mem.read_audit_events(demo_report.client_slug)
    # 3 approval-pack events (created, submitted, approved) + the workflow events.
    pack_events = [
        e for e in events if e.payload.get("approval_pack")
    ]
    actions = [e.payload["approval_pack"]["action"] for e in pack_events]
    assert "created" in actions
    assert "submitted" in actions
    assert "approved" in actions
    # Audit chain still valid after all transitions.
    assert verify_chain(events) == []


# ---------- convenience helper ----------

def test_audit_and_persist_returns_persisted(
    mem: JsonFileMemory, demo_report
) -> None:
    pack = audit_and_persist(mem, demo_report)
    assert pack.state is ApprovalState.DRAFT
    assert mem.exists(demo_report.client_slug, APPROVAL_PACK_KIND, pack.pack_id)


# ---------- count helpers ----------

def test_count_by_category_with_injected_claims(
    mem: JsonFileMemory, demo_report
) -> None:
    risky = demo_report.model_copy(deep=True)
    risky.value_proposition.headline = "Somos los mejores"
    risky.email_sequence.emails[0].subject = "Solo hoy"
    builder = ApprovalPackBuilder(memory=mem)
    pack = builder.build_from_report(risky)
    counts = pack.count_by_category()
    assert counts.get(ClaimCategory.SUPERLATIVE.value, 0) >= 1
    assert counts.get(ClaimCategory.ARTIFICIAL_URGENCY.value, 0) >= 1
