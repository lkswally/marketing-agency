"""Contract tests for ClaimAudit (claim-audit.v1)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from core.contracts import (
    ClaimAudit,
    ClaimAuditItem,
    ContractError,
    ContractErrorCode,
    EvidenceRef,
    validate_claim_audit,
    validate_claim_audit_strict,
)
from core.domain.enums import ClaimSeverity, ClaimVerdict

pytestmark = pytest.mark.contract


# ---------- Happy path ----------

def test_empty_audit_is_valid() -> None:
    a = ClaimAudit()
    assert a.contract_version == "claim-audit.v1"
    assert a.claims == []


def test_audit_with_items_round_trips() -> None:
    a = ClaimAudit(
        claims=[
            ClaimAuditItem(
                claim_id="c1",
                text="3x faster",
                severity=ClaimSeverity.CAVEAT,
                verdict=ClaimVerdict.PARTIAL,
                evidence_refs=[EvidenceRef(evidence_id="e1", trust_level=0.8)],
            )
        ],
        overall_severity=ClaimSeverity.CAVEAT,
        overall_verdict=ClaimVerdict.PARTIAL,
    )
    reloaded = ClaimAudit.from_json(a.to_json())
    assert reloaded.model_dump() == a.model_dump()


# ---------- Overall severity coherence ----------

def test_overall_severity_below_max_item_rejected() -> None:
    with pytest.raises(ValidationError):
        ClaimAudit(
            claims=[
                ClaimAuditItem(
                    claim_id="c1",
                    text="x",
                    severity=ClaimSeverity.UNSAFE,
                    verdict=ClaimVerdict.CONTRADICTED,
                )
            ],
            overall_severity=ClaimSeverity.SAFE,
            overall_verdict=ClaimVerdict.UNVERIFIED,
        )


def test_overall_severity_equal_to_max_is_ok() -> None:
    ClaimAudit(
        claims=[
            ClaimAuditItem(
                claim_id="c1",
                text="x",
                severity=ClaimSeverity.RISKY,
                verdict=ClaimVerdict.UNVERIFIED,
            )
        ],
        overall_severity=ClaimSeverity.RISKY,
        overall_verdict=ClaimVerdict.UNVERIFIED,
    )


def test_overall_severity_above_max_is_ok() -> None:
    ClaimAudit(
        claims=[
            ClaimAuditItem(
                claim_id="c1",
                text="x",
                severity=ClaimSeverity.SAFE,
                verdict=ClaimVerdict.VERIFIED,
            )
        ],
        overall_severity=ClaimSeverity.CAVEAT,
        overall_verdict=ClaimVerdict.VERIFIED,
    )


# ---------- blocks_emission policy ----------

@pytest.mark.parametrize(
    "severity,verdict,expected",
    [
        (ClaimSeverity.SAFE, ClaimVerdict.VERIFIED, False),
        (ClaimSeverity.CAVEAT, ClaimVerdict.PARTIAL, False),
        (ClaimSeverity.RISKY, ClaimVerdict.VERIFIED, False),
        (ClaimSeverity.RISKY, ClaimVerdict.UNVERIFIED, True),
        (ClaimSeverity.RISKY, ClaimVerdict.CONTRADICTED, True),
        (ClaimSeverity.UNSAFE, ClaimVerdict.VERIFIED, True),
        (ClaimSeverity.UNSAFE, ClaimVerdict.UNVERIFIED, True),
    ],
)
def test_blocks_emission_policy(
    severity: ClaimSeverity, verdict: ClaimVerdict, expected: bool
) -> None:
    audit = ClaimAudit(overall_severity=severity, overall_verdict=verdict)
    assert audit.blocks_emission is expected


# ---------- Validation errors ----------

def test_item_text_empty_rejected() -> None:
    ok, errs = validate_claim_audit(
        {
            "claims": [
                {
                    "claim_id": "c1",
                    "text": "",
                    "severity": "safe",
                    "verdict": "verified",
                }
            ]
        }
    )
    assert ok is False


def test_invalid_severity_rejected() -> None:
    ok, errs = validate_claim_audit(
        {
            "overall_severity": "nuclear",
            "overall_verdict": "verified",
        }
    )
    assert ok is False
    assert any(e.code is ContractErrorCode.INVALID_ENUM for e in errs)


def test_evidence_ref_trust_level_bounds() -> None:
    ok, errs = validate_claim_audit(
        {
            "claims": [
                {
                    "claim_id": "c1",
                    "text": "x",
                    "severity": "safe",
                    "verdict": "verified",
                    "evidence_refs": [{"evidence_id": "e1", "trust_level": 1.7}],
                }
            ]
        }
    )
    assert ok is False


def test_extra_field_rejected_on_item() -> None:
    ok, errs = validate_claim_audit(
        {
            "claims": [
                {
                    "claim_id": "c1",
                    "text": "x",
                    "severity": "safe",
                    "verdict": "verified",
                    "extra": "no",
                }
            ]
        }
    )
    assert ok is False
    assert any(e.code is ContractErrorCode.EXTRA_FIELD for e in errs)


def test_strict_returns_instance() -> None:
    a = validate_claim_audit_strict({})
    assert isinstance(a, ClaimAudit)


def test_strict_raises_on_invalid() -> None:
    with pytest.raises(ContractError):
        validate_claim_audit_strict({"overall_severity": "wat"})
