"""Approval operations application service (MKT-11A, D-11.5).

Wraps — never duplicates — the existing :class:`~core.approval.ApprovalPackBuilder`
domain transitions (``approve`` / ``reject``). The policy gaps the domain
deliberately leaves open (idempotency, mandatory rejection reason) are
enforced here, at the application boundary, per
``docs/MKT-11A-Application-Services-Inventory.md`` §2 (F-4):

- **Idempotent success** when the pack is already in the requested target
  state — returns ``ok`` with a warning, no new audit event (the domain
  already recorded the original transition).
- **Structured error** for a genuinely invalid transition (e.g. reject an
  already-APPROVED pack) — the domain's :class:`ApprovalStateError` is
  caught and mapped to :data:`ErrorCode.INVALID_STATE_TRANSITION`.
- **Mandatory, non-empty reason** to reject — enforced before the domain
  is even called.

``list_pending`` is the one read that is inherently cross-tenant (an
Approval Queue has no meaning scoped to a single client), so it takes the
memory root directly rather than a client-scoped :class:`OperationContext`.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict

from core.approval import ApprovalPack, ApprovalPackBuilder, ApprovalState, ApprovalStateError
from core.memory import EntityNotFound, JsonFileMemory

from ..context import OperationContext
from ..result import ErrorCode, OperationResult, OperationWarning

_PENDING_STATES = frozenset({ApprovalState.NEEDS_REVIEW, ApprovalState.DRAFT})
_RESERVED_SLUGS = frozenset({"_shared"})


def _discover_client_slugs(root: Path) -> list[str]:
    """Minimal, memory-root-only client scan for the cross-tenant queue.

    Deliberately NOT a call into ``portal.client_discovery`` — the
    application layer must not depend on a presentation package (that
    dependency would point the wrong way). This mirrors only the piece
    of that helper's behaviour this service actually needs: direct
    subdirectories of the memory root, minus reserved slugs.
    """
    if not root.exists() or not root.is_dir():
        return []
    return sorted(
        entry.name for entry in root.iterdir()
        if entry.is_dir() and entry.name not in _RESERVED_SLUGS
    )


class PendingApprovalSummary(BaseModel):
    """One row in the cross-tenant Approval Queue listing."""

    model_config = ConfigDict(frozen=True)

    client_slug: str
    pack_id: str
    state: ApprovalState
    overall_severity: str
    blocks_publish: bool


def list_pending(*, root: Path) -> OperationResult:
    """List approval packs across every tenant that are NOT in a
    terminal state, or whose posture blocks publish even if reviewed.

    Cross-tenant by design — see module docstring.
    """
    memory = JsonFileMemory(root)
    rows: list[PendingApprovalSummary] = []
    for slug in _discover_client_slugs(root):
        try:
            raw = memory.get(slug, "approval_pack", "current")
        except EntityNotFound:
            continue
        pack = ApprovalPack.model_validate(raw)
        if pack.state in _PENDING_STATES or pack.blocks_publish:
            rows.append(PendingApprovalSummary(
                client_slug=slug,
                pack_id=pack.pack_id,
                state=pack.state,
                overall_severity=pack.overall_severity.value,
                blocks_publish=pack.blocks_publish,
            ))
    return OperationResult.ok_result(data=rows)


def show(ctx: OperationContext) -> OperationResult:
    """Load the current ApprovalPack for one tenant."""
    memory = JsonFileMemory(ctx.root)
    builder = ApprovalPackBuilder(memory=memory)
    try:
        pack = builder.load(ctx.client_slug)
    except EntityNotFound:
        return OperationResult.error_result(
            code=ErrorCode.NOT_FOUND,
            message=f"no ApprovalPack for client {ctx.client_slug!r}",
            remediation="run `mkt audit-strategy` first",
        )
    return OperationResult.ok_result(data=pack)


def approve(ctx: OperationContext, *, notes: str | None = None) -> OperationResult:
    """Approve the tenant's current pack. Idempotent: re-approving an
    already-APPROVED pack succeeds with a warning, no new audit event."""
    memory = JsonFileMemory(ctx.root)
    builder = ApprovalPackBuilder(memory=memory)
    try:
        pack = builder.load(ctx.client_slug)
    except EntityNotFound:
        return OperationResult.error_result(
            code=ErrorCode.NOT_FOUND,
            message=f"no ApprovalPack for client {ctx.client_slug!r}",
            remediation="run `mkt audit-strategy` first",
        )

    if pack.state is ApprovalState.APPROVED:
        return OperationResult.ok_result(
            data=pack,
            warnings=[OperationWarning(
                code="already_approved",
                message="pack is already APPROVED — no state change",
            )],
        )

    try:
        updated = builder.approve(ctx.client_slug, reviewer=ctx.actor_id, notes=notes)
    except ApprovalStateError as e:
        return OperationResult.error_result(
            code=ErrorCode.INVALID_STATE_TRANSITION,
            message=str(e),
        )
    audit_event_id = memory.last_audit_hash(ctx.client_slug)
    return OperationResult.ok_result(data=updated, audit_event_id=audit_event_id)


def reject(ctx: OperationContext, *, reason: str) -> OperationResult:
    """Reject the tenant's current pack. ``reason`` is mandatory (D-11.5)
    — enforced here, not in the domain, so other domain callers keep
    working with an optional ``notes``. Idempotent: re-rejecting an
    already-REJECTED pack succeeds with a warning, no new audit event."""
    if not reason or not reason.strip():
        return OperationResult.error_result(
            code=ErrorCode.INVALID_INPUT,
            message="a non-empty reason is required to reject an approval pack",
        )

    memory = JsonFileMemory(ctx.root)
    builder = ApprovalPackBuilder(memory=memory)
    try:
        pack = builder.load(ctx.client_slug)
    except EntityNotFound:
        return OperationResult.error_result(
            code=ErrorCode.NOT_FOUND,
            message=f"no ApprovalPack for client {ctx.client_slug!r}",
            remediation="run `mkt audit-strategy` first",
        )

    if pack.state is ApprovalState.REJECTED:
        return OperationResult.ok_result(
            data=pack,
            warnings=[OperationWarning(
                code="already_rejected",
                message="pack is already REJECTED — no state change",
            )],
        )

    try:
        updated = builder.reject(ctx.client_slug, reviewer=ctx.actor_id, notes=reason)
    except ApprovalStateError as e:
        return OperationResult.error_result(
            code=ErrorCode.INVALID_STATE_TRANSITION,
            message=str(e),
        )
    audit_event_id = memory.last_audit_hash(ctx.client_slug)
    return OperationResult.ok_result(data=updated, audit_event_id=audit_event_id)


__all__ = ["PendingApprovalSummary", "approve", "list_pending", "reject", "show"]
