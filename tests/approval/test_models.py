"""Pydantic validation tests for approval models."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from core.approval import (
    APPROVAL_PACK_VERSION,
    ApprovalChecklistItem,
    ApprovalDecision,
    ApprovalPack,
    ApprovalState,
    ClaimCategory,
    ClaimDetection,
    ClaimRule,
)
from core.domain.enums import ClaimSeverity, ClaimVerdict


def _now() -> datetime:
    return datetime(2026, 5, 30, 12, 0, tzinfo=UTC)


def _minimal_pack(**overrides) -> dict:
    base = {
        "contract_version": APPROVAL_PACK_VERSION,
        "pack_id": "p1",
        "client_slug": "demo-saas",
        "report_id": "r1",
        "report_contract_version": "campaign-strategy.v1",
        "state": "draft",
        "detections": [],
        "overall_severity": "safe",
        "blocks_publish": False,
        "checklist": [],
        "created_at": _now().isoformat(),
        "updated_at": _now().isoformat(),
        "rule_set_id": "default-rules.v1",
    }
    base.update(overrides)
    return base


# ---------- ApprovalPack ----------

def test_minimal_pack_validates() -> None:
    pack = ApprovalPack.model_validate(_minimal_pack())
    assert pack.contract_version == APPROVAL_PACK_VERSION
    assert pack.state is ApprovalState.DRAFT
    assert pack.is_terminal is False


def test_pack_round_trip_json() -> None:
    pack = ApprovalPack.model_validate(_minimal_pack())
    reloaded = ApprovalPack.from_json(pack.to_json())
    assert reloaded.model_dump() == pack.model_dump()


def test_pack_rejects_naive_timestamp() -> None:
    data = _minimal_pack(created_at="2026-05-30T12:00:00")
    with pytest.raises(ValidationError):
        ApprovalPack.model_validate(data)


def test_pack_rejects_bad_slug() -> None:
    data = _minimal_pack(client_slug="Bad Slug")
    with pytest.raises(ValidationError):
        ApprovalPack.model_validate(data)


def test_pack_spec_version_pinned() -> None:
    data = _minimal_pack(contract_version="approval-pack.v2")
    with pytest.raises(ValidationError):
        ApprovalPack.model_validate(data)


def test_pack_is_terminal_states() -> None:
    for state in ["approved", "rejected"]:
        pack = ApprovalPack.model_validate(_minimal_pack(state=state))
        assert pack.is_terminal is True
    for state in ["draft", "needs_review"]:
        pack = ApprovalPack.model_validate(_minimal_pack(state=state))
        assert pack.is_terminal is False


def test_pack_extra_field_rejected() -> None:
    data = _minimal_pack()
    data["rogue"] = "no"
    with pytest.raises(ValidationError):
        ApprovalPack.model_validate(data)


# ---------- Severity / category helpers ----------

def test_pack_count_by_severity_with_detections() -> None:
    detections = [
        ClaimDetection(
            rule_id="r1",
            rule_description="x",
            category=ClaimCategory.SUPERLATIVE,
            severity=ClaimSeverity.RISKY,
            text_span="somos los mejores",
            located_in="value_proposition.headline",
        ),
        ClaimDetection(
            rule_id="r2",
            rule_description="x",
            category=ClaimCategory.SUPERLATIVE,
            severity=ClaimSeverity.RISKY,
            text_span="lider absoluto",
            located_in="email_sequence.emails[0].body",
        ),
        ClaimDetection(
            rule_id="r3",
            rule_description="x",
            category=ClaimCategory.ARTIFICIAL_URGENCY,
            severity=ClaimSeverity.CAVEAT,
            text_span="solo hoy",
            located_in="email_sequence.emails[0].subject",
        ),
    ]
    pack = ApprovalPack.model_validate(_minimal_pack(detections=[d.model_dump(mode="json") for d in detections]))
    counts_sev = pack.count_by_severity()
    assert counts_sev["risky"] == 2
    assert counts_sev["caveat"] == 1
    assert counts_sev["safe"] == 0
    counts_cat = pack.count_by_category()
    assert counts_cat["superlative"] == 2
    assert counts_cat["artificial_urgency"] == 1
    assert pack.total_detections == 3
    assert pack.human_review_required_count == 3


# ---------- ClaimRule ----------

def test_claim_rule_validates() -> None:
    rule = ClaimRule(
        rule_id="r.x",
        category=ClaimCategory.SUPERLATIVE,
        default_severity=ClaimSeverity.RISKY,
        description="example",
        pattern=r"\btest\b",
    )
    assert rule.requires_human_review is True


def test_claim_rule_rejects_empty_pattern() -> None:
    with pytest.raises(ValidationError):
        ClaimRule(
            rule_id="r.x",
            category=ClaimCategory.SUPERLATIVE,
            default_severity=ClaimSeverity.RISKY,
            description="x",
            pattern="",
        )


def test_claim_rule_rejects_empty_description() -> None:
    with pytest.raises(ValidationError):
        ClaimRule(
            rule_id="r.x",
            category=ClaimCategory.SUPERLATIVE,
            default_severity=ClaimSeverity.RISKY,
            description="",
            pattern="x",
        )


# ---------- ClaimDetection ----------

def test_detection_default_verdict() -> None:
    d = ClaimDetection(
        rule_id="r",
        rule_description="x",
        category=ClaimCategory.SUPERLATIVE,
        severity=ClaimSeverity.RISKY,
        text_span="x",
        located_in="here",
    )
    assert d.verdict is ClaimVerdict.UNVERIFIED


def test_detection_requires_text_span() -> None:
    with pytest.raises(ValidationError):
        ClaimDetection(
            rule_id="r",
            rule_description="x",
            category=ClaimCategory.SUPERLATIVE,
            severity=ClaimSeverity.RISKY,
            text_span="",
            located_in="here",
        )


# ---------- ApprovalChecklistItem ----------

def test_checklist_item_severity_pinned() -> None:
    with pytest.raises(ValidationError):
        ApprovalChecklistItem(
            title="x",
            severity="vibes",  # type: ignore[arg-type]
            category="claims",
        )


def test_checklist_item_category_pinned() -> None:
    with pytest.raises(ValidationError):
        ApprovalChecklistItem(
            title="x",
            severity="must",
            category="random",  # type: ignore[arg-type]
        )


# ---------- ApprovalDecision ----------

def test_decision_requires_tz() -> None:
    with pytest.raises(ValidationError):
        ApprovalDecision(
            reviewer="lucas",
            decided_at=datetime(2026, 5, 30, 12),  # naive
        )


def test_decision_reviewer_required() -> None:
    with pytest.raises(ValidationError):
        ApprovalDecision(reviewer="", decided_at=_now())
