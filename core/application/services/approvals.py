"""Approval operations application service (MKT-11A/11B/11E).

Wraps — never duplicates — the existing :class:`~core.approval.ApprovalPackBuilder`
domain transitions (``approve`` / ``reject``) and the
:mod:`core.approval.repository` versioned queries. The policy gaps the
domain deliberately leaves open are enforced here, at the application
boundary, per ``docs/MKT-11A-Application-Services-Inventory.md`` §2 (F-4),
``docs/MKT-11B-Approval-Operations-Inventory.md`` and
``docs/MKT-11E-VERSIONED-APPROVAL-INVENTORY.md``:

- **Idempotent success** (D-11B.1, confirmed) when the pack is already in
  the requested target state — returns ``ok`` with a warning, no new
  audit event. A genuinely invalid cross-transition (e.g. reject an
  already-APPROVED pack) maps the domain's :class:`ApprovalStateError` to
  :data:`ErrorCode.INVALID_STATE_TRANSITION`.
- **Mandatory, non-empty reason** to reject — enforced before the domain
  is even called.
- **``approval_id`` real identity (MKT-11E)** — every client can have
  multiple approvals now (one per pipeline/job run). Mutations resolve a
  *specific* record:
    - ``approval_id`` given → resolve exactly that record (``NOT_FOUND``
      if it doesn't exist for this client — tenant-isolated).
    - ``approval_id`` omitted → resolve via
      :func:`core.approval.repository.list_pending_for_client`: exactly
      one pending approval → use it (this is the common single-approval
      case, kept ergonomic for the CLI); zero → ``NOT_FOUND``; more than
      one → ``ErrorCode.INVALID_INPUT`` ("ambiguous"), never guessed.
  No implicit "the current one" — the old singleton read is gone.
- **Role authorization** (D-11.6) via :func:`core.application.policies.check_can_decide_approval`
  — checked before memory is touched.
- **``audit_event_id`` is the real ``AuditTrailEvent.event_id``** (MKT-11B
  fix) — read back via ``read_audit_events`` after the domain transition,
  since :meth:`ApprovalPackBuilder._transition` does not return the event
  it builds.
- **Corrupted / schema-mismatched persistence** maps to
  :data:`ErrorCode.PERSISTENCE_ERROR`, distinct from
  :data:`ErrorCode.NOT_FOUND` — the record exists on disk but cannot be
  read back.

``list_pending`` is the one read that is inherently cross-tenant (an
Approval Queue has no meaning scoped to a single client), so it takes the
memory root directly rather than a client-scoped :class:`OperationContext`.
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, ValidationError

from core.approval import ApprovalPack, ApprovalPackBuilder, ApprovalState, ApprovalStateError
from core.approval import repository as approval_repository
from core.memory import EntityNotFound, JsonFileMemory

from ..context import OperationContext
from ..policies import check_can_decide_approval
from ..result import ErrorCode, OperationResult, OperationWarning

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
    approval_id: str
    pack_id: str  # == approval_id, kept for pre-11E field-name compatibility
    state: ApprovalState
    overall_severity: str
    blocks_publish: bool
    job_id: str | None = None


def _resolve_pack_or_error(
    memory: JsonFileMemory, client_slug: str, approval_id: str | None,
) -> tuple[ApprovalPack | None, OperationResult | None]:
    """Resolve exactly one approval for a mutation/show call (MKT-11E).

    ``approval_id`` given → load that exact record (``NOT_FOUND`` if it
    doesn't exist for this client — tenant-isolated by construction, since
    the lookup itself is scoped to ``client_slug``).

    ``approval_id`` omitted → resolve via *every* approval the client has
    (not just the pending ones — an idempotent re-approve/re-reject on an
    already-terminal sole approval must still resolve it, matching the
    pre-11E single-pack-per-client ergonomics): exactly one → use it;
    zero → ``NOT_FOUND``; more than one → ``INVALID_INPUT`` ("ambiguous"),
    never guessed.
    """
    if approval_id is not None:
        builder = ApprovalPackBuilder(memory=memory)
        try:
            pack = builder.load(client_slug, approval_id)
        except EntityNotFound:
            return None, OperationResult.error_result(
                code=ErrorCode.NOT_FOUND,
                message=(
                    f"no ApprovalPack with id {approval_id!r} for client "
                    f"{client_slug!r}"
                ),
            )
        except (json.JSONDecodeError, ValidationError) as e:
            return None, OperationResult.error_result(
                code=ErrorCode.PERSISTENCE_ERROR,
                message=(
                    f"ApprovalPack {approval_id!r} for client "
                    f"{client_slug!r} could not be read: {e}"
                ),
            )
        return pack, None

    try:
        candidates = approval_repository.list_for_client(memory, client_slug)
    except (json.JSONDecodeError, ValidationError) as e:
        return None, OperationResult.error_result(
            code=ErrorCode.PERSISTENCE_ERROR,
            message=f"approval history for client {client_slug!r} could not be read: {e}",
        )
    if not candidates:
        return None, OperationResult.error_result(
            code=ErrorCode.NOT_FOUND,
            message=f"no ApprovalPack for client {client_slug!r}",
            remediation="run `mkt audit-strategy` or `mkt run-campaign` first",
        )
    if len(candidates) > 1:
        return None, OperationResult.error_result(
            code=ErrorCode.INVALID_INPUT,
            message=(
                f"{len(candidates)} approvals exist for client {client_slug!r} — "
                "ambiguous without --approval-id"
            ),
            remediation="pass --approval-id (see `mkt approvals list --client " + client_slug + "`)",
        )
    return candidates[0], None


def _latest_audit_event_id(memory: JsonFileMemory, client_slug: str) -> str | None:
    """Real ``AuditTrailEvent.event_id`` of the most recent event — the
    fix for MKT-11A's hash-mislabelled ``audit_event_id`` (see module
    docstring). Single-writer assumption, same as the rest of the
    project (P-1D.3)."""
    events = memory.read_audit_events(client_slug)
    if not events:
        return None
    return events[-1].event_id


def list_pending(
    *,
    root: Path,
    client_slug: str | None = None,
    status: ApprovalState | None = None,
    job_id: str | None = None,
    limit: int | None = None,
) -> OperationResult:
    """List approvals across every tenant that are NOT in a terminal
    state, or whose posture blocks publish even if reviewed (MKT-11E:
    multiple approvals per client are now possible, so this can return
    more than one row per tenant).

    Cross-tenant by design — see module docstring. ``client_slug``
    narrows to one tenant; ``status`` narrows to one :class:`ApprovalState`
    (bypassing the default pending/blocked filter — an explicit status
    filter means the caller wants exactly that state, terminal or not);
    ``job_id`` narrows to the approval associated with one job;
    ``limit`` caps the number of rows returned. Deterministic order:
    tenants in ``client_slug`` ascending order, each tenant's own
    approvals newest-``created_at``-first.
    """
    memory = JsonFileMemory(root)
    slugs = [client_slug] if client_slug else _discover_client_slugs(root)
    rows: list[PendingApprovalSummary] = []
    for slug in slugs:
        try:
            if status is not None:
                packs = approval_repository.list_for_client(
                    memory, slug, status=status, job_id=job_id,
                )
            else:
                packs = approval_repository.list_pending_for_client(memory, slug)
                if job_id is not None:
                    packs = [p for p in packs if p.job_id == job_id]
        except (json.JSONDecodeError, ValidationError):
            continue  # corrupted entries are skipped in a queue listing,
            # not surfaced as a hard failure — `show`/`approve`/`reject`
            # against a specific approval_id still reports PERSISTENCE_ERROR.
        for pack in packs:
            rows.append(PendingApprovalSummary(
                client_slug=slug,
                approval_id=pack.pack_id,
                pack_id=pack.pack_id,
                state=pack.state,
                overall_severity=pack.overall_severity.value,
                blocks_publish=pack.blocks_publish,
                job_id=pack.job_id,
            ))
            if limit is not None and len(rows) >= limit:
                return OperationResult.ok_result(data=rows)
    return OperationResult.ok_result(data=rows)


def show(ctx: OperationContext, *, approval_id: str | None = None) -> OperationResult:
    """Load one approval for a tenant — a specific one, or (if omitted)
    the tenant's sole pending approval when unambiguous (MKT-11E)."""
    memory = JsonFileMemory(ctx.root)
    pack, error = _resolve_pack_or_error(memory, ctx.client_slug, approval_id)
    if error is not None:
        return error
    assert pack is not None
    return OperationResult.ok_result(data=pack)


def approve(
    ctx: OperationContext,
    *,
    notes: str | None = None,
    approval_id: str | None = None,
) -> OperationResult:
    """Approve one specific approval. Idempotent: re-approving an
    already-APPROVED pack succeeds with a warning, no new audit event."""
    perm_error = check_can_decide_approval(ctx)
    if perm_error is not None:
        return perm_error

    memory = JsonFileMemory(ctx.root)
    pack, error = _resolve_pack_or_error(memory, ctx.client_slug, approval_id)
    if error is not None:
        return error
    assert pack is not None

    if pack.state is ApprovalState.APPROVED:
        return OperationResult.ok_result(
            data=pack,
            warnings=[OperationWarning(
                code="already_approved",
                message="pack is already APPROVED — no state change",
            )],
        )

    builder = ApprovalPackBuilder(memory=memory)
    try:
        updated = builder.approve(
            ctx.client_slug, pack.pack_id, reviewer=ctx.actor_id, notes=notes,
        )
    except ApprovalStateError as e:
        return OperationResult.error_result(
            code=ErrorCode.INVALID_STATE_TRANSITION,
            message=str(e),
        )
    audit_event_id = _latest_audit_event_id(memory, ctx.client_slug)
    return OperationResult.ok_result(data=updated, audit_event_id=audit_event_id)


def reject(
    ctx: OperationContext,
    *,
    reason: str,
    approval_id: str | None = None,
) -> OperationResult:
    """Reject one specific approval. ``reason`` is mandatory (D-11.5) —
    enforced here, not in the domain, so other domain callers keep
    working with an optional ``notes``. Idempotent: re-rejecting an
    already-REJECTED pack succeeds with a warning, no new audit event."""
    if not reason or not reason.strip():
        return OperationResult.error_result(
            code=ErrorCode.INVALID_INPUT,
            message="a non-empty reason is required to reject an approval pack",
        )

    perm_error = check_can_decide_approval(ctx)
    if perm_error is not None:
        return perm_error

    memory = JsonFileMemory(ctx.root)
    pack, error = _resolve_pack_or_error(memory, ctx.client_slug, approval_id)
    if error is not None:
        return error
    assert pack is not None

    if pack.state is ApprovalState.REJECTED:
        return OperationResult.ok_result(
            data=pack,
            warnings=[OperationWarning(
                code="already_rejected",
                message="pack is already REJECTED — no state change",
            )],
        )

    builder = ApprovalPackBuilder(memory=memory)
    try:
        updated = builder.reject(
            ctx.client_slug, pack.pack_id, reviewer=ctx.actor_id, notes=reason,
        )
    except ApprovalStateError as e:
        return OperationResult.error_result(
            code=ErrorCode.INVALID_STATE_TRANSITION,
            message=str(e),
        )
    audit_event_id = _latest_audit_event_id(memory, ctx.client_slug)
    return OperationResult.ok_result(data=updated, audit_event_id=audit_event_id)


# Re-exported for tests that want to construct a summary row directly.
__all__ = [
    "PendingApprovalSummary",
    "approve",
    "list_pending",
    "reject",
    "show",
]
