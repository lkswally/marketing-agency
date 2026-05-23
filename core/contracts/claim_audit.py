"""ClaimAudit — embedded block of ReturnEnvelope for outputs that carry claims.

Contract: ``claim-audit.v1``

Mirrors 1-to-1 with :class:`core.domain.Claim` + :class:`core.domain.Evidence`
but in a denormalized, transport-friendly shape that can live inside an
envelope without joining storage.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from core.domain.base import DomainModel
from core.domain.enums import ClaimSeverity, ClaimVerdict

CLAIM_AUDIT_VERSION = "claim-audit.v1"


# Severity ordering used by the coherence validator. SAFE < CAVEAT < RISKY < UNSAFE.
_SEVERITY_ORDER: tuple[ClaimSeverity, ...] = (
    ClaimSeverity.SAFE,
    ClaimSeverity.CAVEAT,
    ClaimSeverity.RISKY,
    ClaimSeverity.UNSAFE,
)


def severity_rank(s: ClaimSeverity) -> int:
    """Return the ordinal rank of a severity. Higher is worse."""
    return _SEVERITY_ORDER.index(s)


class EvidenceRef(DomainModel):
    """Lightweight reference to a piece of Evidence stored elsewhere."""

    evidence_id: str = Field(min_length=1)
    location: str | None = None
    trust_level: float | None = Field(default=None, ge=0.0, le=1.0)


class ClaimAuditItem(DomainModel):
    """A single audited claim."""

    claim_id: str = Field(min_length=1)
    text: str = Field(min_length=1, max_length=2000)
    severity: ClaimSeverity
    verdict: ClaimVerdict
    evidence_refs: list[EvidenceRef] = Field(default_factory=list)
    rationale: str | None = None


class ClaimAudit(DomainModel):
    """Audit block returned alongside a ReturnEnvelope when its output carries claims.

    Fields:
        contract_version: pinned to ``claim-audit.v1``.
        claims: per-claim verdicts (may be empty if explicitly audited as "no claims present").
        overall_severity: at least as high as the max item severity.
        overall_verdict: aggregate verdict across items.
        notes: optional human-readable summary.
    """

    contract_version: Literal["claim-audit.v1"] = CLAIM_AUDIT_VERSION
    claims: list[ClaimAuditItem] = Field(default_factory=list)
    overall_severity: ClaimSeverity = ClaimSeverity.SAFE
    overall_verdict: ClaimVerdict = ClaimVerdict.UNVERIFIED
    notes: str | None = None

    @model_validator(mode="after")
    def _overall_severity_coherent(self) -> ClaimAudit:
        if not self.claims:
            return self
        max_item = max(self.claims, key=lambda c: severity_rank(c.severity)).severity
        if severity_rank(self.overall_severity) < severity_rank(max_item):
            raise ValueError(
                f"overall_severity={self.overall_severity.value} is below the maximum "
                f"item severity={max_item.value}"
            )
        return self

    @property
    def blocks_emission(self) -> bool:
        """True if the audit should prevent the carrying envelope from shipping.

        Default policy (see docs/contracts/claim-audit.md):
        - UNSAFE severity always blocks.
        - RISKY + (UNVERIFIED | CONTRADICTED) blocks.
        - Otherwise ship.
        """
        if self.overall_severity is ClaimSeverity.UNSAFE:
            return True
        return (
            self.overall_severity is ClaimSeverity.RISKY
            and self.overall_verdict in (ClaimVerdict.UNVERIFIED, ClaimVerdict.CONTRADICTED)
        )
