"""Pydantic models for claim audit + approval pack.

Contract: ``approval-pack.v1``.

These models reuse ``ClaimSeverity`` / ``ClaimVerdict`` from the operational
contracts family (MKT-1C). The ``ApprovalPack`` is a higher-level artifact
that bundles a strategy report reference, the detected claims, an approval
state and a checklist — it is NOT the ``Approval`` entity from the formal
Approval Center spec (``docs/approval-center.md``), which has its own
state machine and lives in a future block.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import Field, field_validator

from core.domain.base import DomainModel, new_id, validate_slug
from core.domain.enums import ClaimSeverity, ClaimVerdict

APPROVAL_PACK_VERSION = "approval-pack.v1"


# ============ Enums ============

class ApprovalState(StrEnum):
    """Lifecycle of an :class:`ApprovalPack`.

    ``DRAFT`` → ``NEEDS_REVIEW`` → ``APPROVED`` | ``REJECTED``.

    The four states are intentionally simpler than the formal Approval
    Center state machine (``PROPOSED → IN_REVIEW → APPROVED | REJECTED |
    NEEDS_REVISION``). The mapping is documented in
    ``docs/runtime/claim-audit-approval-pack.md``.
    """

    DRAFT = "draft"
    NEEDS_REVIEW = "needs_review"
    APPROVED = "approved"
    REJECTED = "rejected"


_TERMINAL_STATES = frozenset({ApprovalState.APPROVED, ApprovalState.REJECTED})


class ClaimCategory(StrEnum):
    """Why a claim is risky.

    Drives both the default severity assigned by the auditor and the
    suggested mitigation surfaced to the reviewer.
    """

    GUARANTEED_OUTCOME = "guaranteed_outcome"
    FINANCIAL_PROMISE = "financial_promise"
    LEGAL_OR_TAX = "legal_or_tax"
    MEDICAL_OR_SENSITIVE = "medical_or_sensitive"
    COMPETITOR_COMPARISON = "competitor_comparison"
    SUPERLATIVE = "superlative"
    EXAGGERATED_BENEFIT = "exaggerated_benefit"
    ARTIFICIAL_URGENCY = "artificial_urgency"
    UNSOURCED_STATISTIC = "unsourced_statistic"
    ABSOLUTE_CLAIM = "absolute_claim"
    GENERIC_PROMISE = "generic_promise"
    RISK_FREE_CLAIM = "risk_free_claim"


# ============ Sub-models ============

class ClaimRule(DomainModel):
    """A single detection rule.

    A rule names a pattern, a default severity, a category, and an optional
    mitigation hint. Rules are data, not code — they can be extended without
    touching the scanner.

    ``pattern`` is a Python regex (case-insensitive matched). Use of
    backreferences and look-around is allowed but the auditor compiles
    patterns lazily; broken regexes surface at audit time.
    """

    rule_id: str = Field(min_length=1, max_length=200)
    category: ClaimCategory
    default_severity: ClaimSeverity
    description: str = Field(min_length=1, max_length=500)
    pattern: str = Field(min_length=1)
    suggested_mitigation: str | None = None
    requires_human_review: bool = True


class ClaimDetection(DomainModel):
    """A single match emitted by the auditor."""

    detection_id: str = Field(default_factory=new_id)
    rule_id: str
    rule_description: str
    category: ClaimCategory
    severity: ClaimSeverity
    text_span: str = Field(min_length=1, max_length=2000)
    located_in: str = Field(min_length=1, max_length=500)
    requires_human_review: bool = True
    suggested_mitigation: str | None = None
    evidence_refs: list[str] = Field(default_factory=list)
    verdict: ClaimVerdict = ClaimVerdict.UNVERIFIED


class ApprovalChecklistItem(DomainModel):
    """One line in the human-facing checklist of the pack."""

    item_id: str = Field(default_factory=new_id)
    title: str = Field(min_length=1, max_length=500)
    severity: Literal["blocker", "must", "should"] = "must"
    category: Literal[
        "strategy", "creative", "compliance", "operational", "claims"
    ]
    notes: str | None = None
    linked_detection_ids: list[str] = Field(default_factory=list)


class ApprovalDecision(DomainModel):
    """Recorded human decision when the pack moves to a terminal state."""

    reviewer: str = Field(min_length=1, max_length=200)
    decided_at: datetime
    notes: str | None = None

    @field_validator("decided_at")
    @classmethod
    def _tz(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("decided_at must be timezone-aware (UTC)")
        return v


# ============ Top-level ============

class ApprovalPack(DomainModel):
    """Bundle that a future Approval Center will consume.

    Lifecycle:
    - Constructed by :class:`ApprovalPackBuilder` from a
      :class:`CampaignStrategyReport` + the auditor's detections.
    - Persisted to memory under kind ``approval_pack`` with the singleton id
      ``"current"`` (matches MKT-3A's strategy report convention).
    - Transitions are explicit: ``submit_for_review`` / ``approve`` /
      ``reject`` on the builder; each transition emits an audit event.

    Fields:
        contract_version: pinned to ``approval-pack.v1``.
        state: lifecycle state.
        detections: every claim the auditor surfaced.
        overall_severity: at least as high as the max detection severity.
        blocks_publish: policy flag — when True, downstream publishers MUST
            refuse to act. Policy-only; no publisher exists in MKT-3B.
    """

    contract_version: Literal["approval-pack.v1"] = APPROVAL_PACK_VERSION
    pack_id: str = Field(default_factory=new_id)
    client_slug: Annotated[str, Field(min_length=2, max_length=64)]
    report_id: str = Field(min_length=1)
    report_contract_version: str = Field(min_length=1)
    state: ApprovalState = ApprovalState.DRAFT
    detections: list[ClaimDetection] = Field(default_factory=list)
    overall_severity: ClaimSeverity = ClaimSeverity.SAFE
    blocks_publish: bool = False
    checklist: list[ApprovalChecklistItem] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
    decision: ApprovalDecision | None = None
    rule_set_id: str | None = None  # which rule pack produced these detections

    @field_validator("client_slug")
    @classmethod
    def _slug(cls, v: str) -> str:
        return validate_slug(v)

    @field_validator("created_at", "updated_at")
    @classmethod
    def _tz(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("timestamps must be timezone-aware (UTC)")
        return v

    @property
    def is_terminal(self) -> bool:
        return self.state in _TERMINAL_STATES

    # -------- counters (informational, computed on demand) --------

    def count_by_severity(self) -> dict[str, int]:
        counts = {s.value: 0 for s in ClaimSeverity}
        for d in self.detections:
            counts[d.severity.value] += 1
        return counts

    def count_by_category(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for d in self.detections:
            counts[d.category.value] = counts.get(d.category.value, 0) + 1
        return counts

    @property
    def total_detections(self) -> int:
        return len(self.detections)

    @property
    def human_review_required_count(self) -> int:
        return sum(1 for d in self.detections if d.requires_human_review)
