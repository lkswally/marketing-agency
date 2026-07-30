"""Approval operations application service (MKT-11A + MKT-11B, D-11.5).

Wraps — never duplicates — the existing :class:`~core.approval.ApprovalPackBuilder`
domain transitions (``approve`` / ``reject``). The policy gaps the domain
deliberately leaves open are enforced here, at the application boundary,
per ``docs/MKT-11A-Application-Services-Inventory.md`` §2 (F-4) and
``docs/MKT-11B-Approval-Operations-Inventory.md``:

- **Idempotent success** (D-11B.1, confirmed) when the pack is already in
  the requested target state — returns ``ok`` with a warning, no new
  audit event. A genuinely invalid cross-transition (e.g. reject an
  already-APPROVED pack) maps the domain's :class:`ApprovalStateError` to
  :data:`ErrorCode.INVALID_STATE_TRANSITION`.
- **Mandatory, non-empty reason** to reject — enforced before the domain
  is even called.
- **``--approval-id`` as optional verification only** (D-11B.2, confirmed)
  — there is no per-approval index in the domain (one pack per client,
  entity id always ``"current"``). When supplied, it is compared against
  the loaded pack's ``pack_id``; a mismatch is ``NOT_FOUND``, exactly as
  if the approval did not exist. No new index, no history, no new
  persistence.
- **Role authorization** (D-11.6) via :func:`core.application.policies.check_can_decide_approval`
  — checked before memory is touched.
- **``audit_event_id`` is the real ``AuditTrailEvent.event_id``** (MKT-11B
  fix) — read back via ``read_audit_events`` after the domain transition,
  since :meth:`ApprovalPackBuilder._transition` does not return the event
  it builds. Previously (MKT-11A) this field held the hash-chain tail,
  which is a different value with a different meaning; no code outside
  this module ever consumed that value contractually, so nothing else
  changes.
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
from core.memory import EntityNotFound, JsonFileMemory

from ..context import OperationContext
from ..policies import check_can_decide_approval
from ..result import ErrorCode, OperationResult, OperationWarning

_PENDING_STATES = frozenset({ApprovalState.NEEDS_REVIEW, ApprovalState.DRAFT})
_RESERVED_SLUGS = frozenset({"_shared"})
_APPROVAL_PACK_KIND = "approval_pack"
_APPROVAL_PACK_SINGLETON = "current"


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


def _load_pack_or_error(
    memory: JsonFileMemory, client_slug: str,
) -> tuple[ApprovalPack | None, OperationResult | None]:
    """Shared load path: NOT_FOUND vs PERSISTENCE_ERROR vs success."""
    builder = ApprovalPackBuilder(memory=memory)
    try:
        pack = builder.load(client_slug)
    except EntityNotFound:
        return None, OperationResult.error_result(
            code=ErrorCode.NOT_FOUND,
            message=f"no ApprovalPack for client {client_slug!r}",
            remediation="run `mkt audit-strategy` first",
        )
    except (json.JSONDecodeError, ValidationError) as e:
        return None, OperationResult.error_result(
            code=ErrorCode.PERSISTENCE_ERROR,
            message=f"ApprovalPack for client {client_slug!r} could not be read: {e}",
        )
    return pack, None


def _verify_approval_id(
    pack: ApprovalPack, approval_id: str | None, client_slug: str,
) -> OperationResult | None:
    """D-11B.2: optional verification only — no index, no history."""
    if approval_id is not None and approval_id != pack.pack_id:
        return OperationResult.error_result(
            code=ErrorCode.NOT_FOUND,
            message=(
                f"no ApprovalPack with id {approval_id!r} for client "
                f"{client_slug!r} (current pack id is {pack.pack_id!r})"
            ),
        )
    return None


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
    limit: int | None = None,
) -> OperationResult:
    """List approval packs across every tenant that are NOT in a
    terminal state, or whose posture blocks publish even if reviewed.

    Cross-tenant by design — see module docstring. ``client_slug``
    narrows to one tenant; ``status`` narrows to one :class:`ApprovalState`
    (bypassing the default pending/blocked filter — an explicit status
    filter means the caller wants exactly that state, terminal or not);
    ``limit`` caps the number of rows returned (deterministic order:
    sorted by ``client_slug``, ascending, same as the tenant scan).
    """
    memory = JsonFileMemory(root)
    slugs = [client_slug] if client_slug else _discover_client_slugs(root)
    rows: list[PendingApprovalSummary] = []
    for slug in slugs:
        try:
            raw = memory.get(slug, _APPROVAL_PACK_KIND, _APPROVAL_PACK_SINGLETON)
        except EntityNotFound:
            continue
        except (json.JSONDecodeError, ValidationError):
            continue  # corrupted entries are skipped in a queue listing,
            # not surfaced as a hard failure — `show`/`approve`/`reject`
            # against that specific client will report PERSISTENCE_ERROR.
        pack = ApprovalPack.model_validate(raw)
        if status is not None:
            if pack.state is not status:
                continue
        elif not (pack.state in _PENDING_STATES or pack.blocks_publish):
            continue
        rows.append(PendingApprovalSummary(
            client_slug=slug,
            pack_id=pack.pack_id,
            state=pack.state,
            overall_severity=pack.overall_severity.value,
            blocks_publish=pack.blocks_publish,
        ))
        if limit is not None and len(rows) >= limit:
            break
    return OperationResult.ok_result(data=rows)


def show(ctx: OperationContext, *, approval_id: str | None = None) -> OperationResult:
    """Load the current ApprovalPack for one tenant."""
    memory = JsonFileMemory(ctx.root)
    pack, error = _load_pack_or_error(memory, ctx.client_slug)
    if error is not None:
        return error
    assert pack is not None
    id_error = _verify_approval_id(pack, approval_id, ctx.client_slug)
    if id_error is not None:
        return id_error
    return OperationResult.ok_result(data=pack)


def approve(
    ctx: OperationContext,
    *,
    notes: str | None = None,
    approval_id: str | None = None,
) -> OperationResult:
    """Approve the tenant's current pack. Idempotent: re-approving an
    already-APPROVED pack succeeds with a warning, no new audit event."""
    perm_error = check_can_decide_approval(ctx)
    if perm_error is not None:
        return perm_error

    memory = JsonFileMemory(ctx.root)
    pack, error = _load_pack_or_error(memory, ctx.client_slug)
    if error is not None:
        return error
    assert pack is not None
    id_error = _verify_approval_id(pack, approval_id, ctx.client_slug)
    if id_error is not None:
        return id_error

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
        updated = builder.approve(ctx.client_slug, reviewer=ctx.actor_id, notes=notes)
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
    """Reject the tenant's current pack. ``reason`` is mandatory (D-11.5)
    — enforced here, not in the domain, so other domain callers keep
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
    pack, error = _load_pack_or_error(memory, ctx.client_slug)
    if error is not None:
        return error
    assert pack is not None
    id_error = _verify_approval_id(pack, approval_id, ctx.client_slug)
    if id_error is not None:
        return id_error

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
        updated = builder.reject(ctx.client_slug, reviewer=ctx.actor_id, notes=reason)
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
