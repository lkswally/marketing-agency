"""ApprovalPackBuilder — build, persist, transition.

The builder:
1. Audits a :class:`CampaignStrategyReport` against the auditor's rules.
2. Builds a checklist that surfaces the detections to a human reviewer.
3. Persists the resulting :class:`ApprovalPack` to memory.
4. Emits audit events on every state transition.

All operations are pure with respect to inputs; only the explicit
``persist`` and transition methods touch memory.
"""

from __future__ import annotations

from typing import Any

from core.contracts import AuditEventType, AuditTrailEvent
from core.domain.base import utcnow
from core.domain.enums import ClaimSeverity
from core.memory import Memory
from core.strategy.models import CampaignStrategyReport

from .claim_auditor import ClaimAuditor
from .models import (
    APPROVAL_PACK_VERSION,
    ApprovalChecklistItem,
    ApprovalDecision,
    ApprovalPack,
    ApprovalState,
    ClaimDetection,
)

# Memory kind for the persisted pack.
APPROVAL_PACK_KIND = "approval_pack"
SINGLETON_ID = "current"
"""Legacy entity id (pre-MKT-11E). No longer written by
:meth:`ApprovalPackBuilder.persist` — packs are now persisted at
``<pack_id>.json`` (versioned history, one file per approval). Kept as a
constant only because a pre-existing ``current.json`` may still be present
on a developer's disk (never migrated or deleted automatically — see
``docs/MKT-11E-VERSIONED-APPROVAL-INVENTORY.md`` §7/§30) and because a few
call sites still reference the name in comments/tests."""


# Severity ranking used to compute ``overall_severity`` and ``blocks_publish``.
_SEVERITY_RANK = {
    ClaimSeverity.SAFE: 0,
    ClaimSeverity.CAVEAT: 1,
    ClaimSeverity.RISKY: 2,
    ClaimSeverity.UNSAFE: 3,
}


def _max_severity(detections: list[ClaimDetection]) -> ClaimSeverity:
    if not detections:
        return ClaimSeverity.SAFE
    return max(detections, key=lambda d: _SEVERITY_RANK[d.severity]).severity


def _build_checklist(detections: list[ClaimDetection]) -> list[ApprovalChecklistItem]:
    """Build a per-detection checklist plus a couple of structural items."""
    items: list[ApprovalChecklistItem] = []

    # Always-present structural items.
    items.append(
        ApprovalChecklistItem(
            title="Revisar el reporte completo antes de aprobar.",
            severity="must",
            category="operational",
        )
    )
    items.append(
        ApprovalChecklistItem(
            title="Confirmar que las claims sensibles cuentan con evidencia o se reformulan.",
            severity="must",
            category="claims",
        )
    )

    # Per-detection item — the most severe ones become blockers.
    for d in detections:
        if d.severity is ClaimSeverity.UNSAFE:
            severity: str = "blocker"
        elif d.severity is ClaimSeverity.RISKY:
            severity = "must"
        else:
            severity = "should"

        title = (
            f"[{d.category.value}] '{_short(d.text_span, 80)}' en `{d.located_in}` — {d.rule_description}"
        )
        items.append(
            ApprovalChecklistItem(
                title=title,
                severity=severity,  # type: ignore[arg-type]
                category="claims",
                notes=d.suggested_mitigation,
                linked_detection_ids=[d.detection_id],
            )
        )

    return items


def _short(s: str, limit: int) -> str:
    return s if len(s) <= limit else s[: limit - 1].rstrip() + "…"


def _blocks_publish(state: ApprovalState, overall_severity: ClaimSeverity) -> bool:
    """Policy: an unapproved pack with risky or unsafe overall severity blocks publish.

    Approved packs never block. Rejected packs always block (publishing a
    rejected pack is itself a policy violation).
    """
    if state is ApprovalState.APPROVED:
        return False
    if state is ApprovalState.REJECTED:
        return True
    return overall_severity in (ClaimSeverity.RISKY, ClaimSeverity.UNSAFE)


class ApprovalPackBuilder:
    """Build, persist and transition an :class:`ApprovalPack`."""

    def __init__(
        self,
        memory: Memory,
        *,
        auditor: ClaimAuditor | None = None,
    ) -> None:
        self._memory = memory
        self._auditor = auditor or ClaimAuditor()

    # ---------- build ----------

    def build_from_report(
        self,
        report: CampaignStrategyReport,
        *,
        job_id: str | None = None,
        correlation_id: str | None = None,
        campaign_run_id: str | None = None,
        requested_by: str | None = None,
    ) -> ApprovalPack:
        """Audit the report and assemble a new :class:`ApprovalPack` (state=DRAFT).

        Every call builds a **new** pack with a fresh ``pack_id`` (MKT-11E)
        — this never mutates or overwrites a prior pack for the same
        client. ``job_id``/``correlation_id``/``campaign_run_id`` are
        optional association metadata, threaded through only when the
        caller (the job system / pipeline) actually has them.
        """
        detections = self._auditor.audit(report)
        overall = _max_severity(detections)
        now = utcnow()
        pack = ApprovalPack(
            contract_version=APPROVAL_PACK_VERSION,
            client_slug=report.client_slug,
            report_id=report.report_id,
            report_contract_version=report.contract_version,
            state=ApprovalState.DRAFT,
            detections=detections,
            overall_severity=overall,
            blocks_publish=_blocks_publish(ApprovalState.DRAFT, overall),
            checklist=_build_checklist(detections),
            created_at=now,
            updated_at=now,
            rule_set_id=self._auditor.rule_set_id,
            job_id=job_id,
            correlation_id=correlation_id,
            campaign_run_id=campaign_run_id,
            requested_by=requested_by,
        )
        return pack

    # ---------- persistence ----------

    def persist(self, pack: ApprovalPack) -> None:
        """Persist the pack to ``approval_pack/<pack_id>.json`` and emit the
        ``created``/``updated`` audit event (MKT-11E: versioned, never the
        ``"current"`` singleton — see :data:`SINGLETON_ID`'s docstring).

        Idempotent re-persisting (same ``pack_id``) overwrites that one
        record and emits an ``updated`` note; it never touches any other
        client's or any other approval's record — no dual-write, no
        cross-approval overwrite.
        """
        existed = self._memory.exists(
            pack.client_slug, APPROVAL_PACK_KIND, pack.pack_id
        )
        self._memory.put(
            pack.client_slug,
            APPROVAL_PACK_KIND,
            pack.pack_id,
            pack.model_dump(mode="json"),
        )
        payload: dict[str, Any] = {
            "approval_id": pack.pack_id,
            "pack_id": pack.pack_id,
            "report_id": pack.report_id,
            "state": pack.state.value,
            "overall_severity": pack.overall_severity.value,
            "blocks_publish": pack.blocks_publish,
            "total_detections": pack.total_detections,
            "action": "updated" if existed else "created",
        }
        if pack.job_id is not None:
            payload["job_id"] = pack.job_id
        if pack.correlation_id is not None:
            payload["correlation_id"] = pack.correlation_id
        self._emit_event(
            client_slug=pack.client_slug,
            payload=payload,
        )

    def load(self, client_slug: str, approval_id: str) -> ApprovalPack:
        """Load one specific approval by its real identity.

        Raises ``EntityNotFound`` if no record with that ``pack_id`` exists
        for this client. There is no implicit "current" fallback here —
        callers that want "the latest approval" must say so explicitly via
        :func:`core.approval.repository.get_latest_for_client`.
        """
        raw = self._memory.get(client_slug, APPROVAL_PACK_KIND, approval_id)
        return ApprovalPack.model_validate(raw)

    # ---------- transitions ----------

    def submit_for_review(self, client_slug: str, approval_id: str) -> ApprovalPack:
        """Move the pack from ``DRAFT`` to ``NEEDS_REVIEW``."""
        pack = self.load(client_slug, approval_id)
        if pack.state is not ApprovalState.DRAFT:
            raise ApprovalStateError(
                f"can only submit a DRAFT pack (current state: {pack.state.value})"
            )
        return self._transition(
            pack,
            new_state=ApprovalState.NEEDS_REVIEW,
            decision=None,
            action="submitted",
        )

    def approve(
        self,
        client_slug: str,
        approval_id: str,
        *,
        reviewer: str,
        notes: str | None = None,
    ) -> ApprovalPack:
        """Move the pack to ``APPROVED``."""
        pack = self.load(client_slug, approval_id)
        if pack.state is ApprovalState.APPROVED:
            raise ApprovalStateError("pack is already APPROVED")
        if pack.state is ApprovalState.REJECTED:
            raise ApprovalStateError("cannot approve a REJECTED pack")
        decision = ApprovalDecision(
            reviewer=reviewer, decided_at=utcnow(), notes=notes
        )
        return self._transition(
            pack,
            new_state=ApprovalState.APPROVED,
            decision=decision,
            action="approved",
        )

    def reject(
        self,
        client_slug: str,
        approval_id: str,
        *,
        reviewer: str,
        notes: str | None = None,
    ) -> ApprovalPack:
        """Move the pack to ``REJECTED``."""
        pack = self.load(client_slug, approval_id)
        if pack.state is ApprovalState.REJECTED:
            raise ApprovalStateError("pack is already REJECTED")
        if pack.state is ApprovalState.APPROVED:
            raise ApprovalStateError("cannot reject an APPROVED pack")
        decision = ApprovalDecision(
            reviewer=reviewer, decided_at=utcnow(), notes=notes
        )
        return self._transition(
            pack,
            new_state=ApprovalState.REJECTED,
            decision=decision,
            action="rejected",
        )

    # ---------- internals ----------

    def _transition(
        self,
        pack: ApprovalPack,
        *,
        new_state: ApprovalState,
        decision: ApprovalDecision | None,
        action: str,
    ) -> ApprovalPack:
        updated = pack.model_copy(
            update={
                "state": new_state,
                "blocks_publish": _blocks_publish(new_state, pack.overall_severity),
                "decision": decision,
                "updated_at": utcnow(),
            }
        )
        self._memory.put(
            updated.client_slug,
            APPROVAL_PACK_KIND,
            updated.pack_id,
            updated.model_dump(mode="json"),
        )
        payload: dict[str, Any] = {
            "approval_id": updated.pack_id,
            "pack_id": updated.pack_id,
            "report_id": updated.report_id,
            "state": updated.state.value,
            "overall_severity": updated.overall_severity.value,
            "blocks_publish": updated.blocks_publish,
            "action": action,
            "reviewer": decision.reviewer if decision else None,
        }
        if updated.job_id is not None:
            payload["job_id"] = updated.job_id
        if updated.correlation_id is not None:
            payload["correlation_id"] = updated.correlation_id
        self._emit_event(
            client_slug=updated.client_slug,
            payload=payload,
        )
        return updated

    def _emit_event(
        self, *, client_slug: str, payload: dict[str, Any]
    ) -> None:
        prev = self._memory.last_audit_hash(client_slug)
        event = AuditTrailEvent.build(
            event_type=AuditEventType.NOTE,
            actor="approval_pack_builder",
            occurred_at=utcnow(),
            client_slug=client_slug,
            payload={"approval_pack": payload},
            prev_hash=prev,
        )
        self._memory.append_audit_event(event)


class ApprovalStateError(RuntimeError):
    """Raised when a transition is attempted from an incompatible state."""


# ---------- High-level pipeline ----------

def audit_and_persist(
    memory: Memory,
    report: CampaignStrategyReport,
    *,
    auditor: ClaimAuditor | None = None,
) -> ApprovalPack:
    """Convenience: audit a report, build the pack, persist it.

    Returns the persisted pack (state ``DRAFT``).
    """
    builder = ApprovalPackBuilder(memory, auditor=auditor)
    pack = builder.build_from_report(report)
    builder.persist(pack)
    return pack


__all__ = [
    "APPROVAL_PACK_KIND",
    "SINGLETON_ID",
    "ApprovalPackBuilder",
    "ApprovalStateError",
    "audit_and_persist",
]
