"""Minimal, explicit authorization policies (MKT-11B, D-11.6).

No decorators, no framework magic, no UI-side check. A policy is a plain
function: it inspects an :class:`OperationContext` and returns an
:class:`OperationResult` error when the actor's role does not authorize
the operation, or ``None`` when it does. Services call the relevant
policy function *before* touching memory — never after.

**Scope of MKT-11B's policy:** approve/reject only. Read operations
(``list_pending``, ``show``) are unrestricted — nothing in the role
matrix asked for read-side gating, and gating reads would be new,
un-asked-for scope.

**Why ``OPERATOR`` is allowed to approve/reject** (not just ``APPROVER``
/ ``ADMIN``): the MKT-11B brief's own role matrix carves out an explicit
exception — *"operator: no puede aprobar salvo que el contrato actual lo
permita"*. Before this policy existed, nothing gated approval at all —
every existing caller (all 32 pre-11B tests, every CLI invocation) acted
as an unrestricted actor and succeeded. That IS today's actual contract.
Per the matrix's own carve-out clause, ``OPERATOR`` therefore remains
authorized — this is what keeps the pre-existing test suite green without
touching a single existing assertion, while ``VIEWER`` and ``ANALYST``
(unambiguously read-only roles in the matrix) are newly, really blocked.
"""

from __future__ import annotations

from .context import OperationContext, OperationRole
from .result import ErrorCode, OperationResult

_ALLOWED_TO_DECIDE = frozenset({
    OperationRole.OPERATOR,
    OperationRole.APPROVER,
    OperationRole.ADMIN,
})


def check_can_decide_approval(ctx: OperationContext) -> OperationResult | None:
    """Return a ``PERMISSION_DENIED`` error result when ``ctx.role`` may
    not approve or reject an approval pack; ``None`` when it may."""
    if ctx.role in _ALLOWED_TO_DECIDE:
        return None
    return OperationResult.error_result(
        code=ErrorCode.PERMISSION_DENIED,
        message=(
            f"role {ctx.role.value!r} is not authorized to approve or "
            "reject approval packs"
        ),
        remediation="use an actor with role 'operator', 'approver', or 'admin'",
    )


__all__ = ["check_can_decide_approval"]
