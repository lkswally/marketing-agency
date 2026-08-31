"""Approval repository — versioned queries over ``approval_pack`` (MKT-11E).

Persistence is one file per approval: ``approval_pack/<pack_id>.json``
(written by :meth:`~core.approval.approval_pack.ApprovalPackBuilder.persist`).
This module adds the read-side that a single-record :meth:`load` can't:
list history for a client, find the latest, find the pending ones.

**No dual-write.** :func:`get_latest_for_client` is a dynamic query over
whatever is on disk right now — it never persists a second copy under any
other key (in particular, never under the legacy ``"current"`` id). See
``docs/MKT-11E-VERSIONED-APPROVAL-INVENTORY.md``.

A pre-existing ``approval_pack/current.json`` left over from before this
milestone (§7/§30 of the inventory: no real tracked data exists, but a
developer's local disk may still have one) is not special-cased or
migrated here — it is just one more file under the same kind directory,
picked up by :func:`list_for_client` like any other historical record.
Its own ``pack_id`` field (not the filename) is its real identity.
"""

from __future__ import annotations

from core.memory import Memory

from .approval_pack import APPROVAL_PACK_KIND
from .models import ApprovalPack, ApprovalState

_PENDING_STATES = frozenset({ApprovalState.DRAFT, ApprovalState.NEEDS_REVIEW})


def list_for_client(
    memory: Memory,
    client_slug: str,
    *,
    status: ApprovalState | None = None,
    job_id: str | None = None,
    limit: int | None = None,
) -> list[ApprovalPack]:
    """Every approval for one client, newest ``created_at`` first.

    ``status`` and ``job_id`` are the only supported filters (matching the
    fields the domain actually has) — nothing invented. A corrupted or
    schema-mismatched record raises (``json.JSONDecodeError`` /
    :class:`pydantic.ValidationError`), same as :meth:`ApprovalPackBuilder.load`
    — callers that want a best-effort, corruption-tolerant listing (e.g. the
    cross-tenant Approval Queue) catch and skip per-tenant; callers
    resolving a single client's history should let it surface as
    ``PERSISTENCE_ERROR``.
    """
    packs: list[ApprovalPack] = []
    for raw in memory.list(client_slug, APPROVAL_PACK_KIND):
        pack = ApprovalPack.model_validate(raw)
        if status is not None and pack.state is not status:
            continue
        if job_id is not None and pack.job_id != job_id:
            continue
        packs.append(pack)
    packs.sort(key=lambda p: p.created_at, reverse=True)
    if limit is not None:
        packs = packs[:limit]
    return packs


def list_pending_for_client(memory: Memory, client_slug: str) -> list[ApprovalPack]:
    """Approvals in a reviewable state, or terminal-but-blocking, for one
    client — the per-tenant building block behind a future Approval Queue.
    """
    return [
        p for p in list_for_client(memory, client_slug)
        if p.state in _PENDING_STATES or p.blocks_publish
    ]


def get_latest_for_client(memory: Memory, client_slug: str) -> ApprovalPack | None:
    """The most recently created approval for a client, or ``None``.

    This is the compatibility replacement for the old
    ``memory.get(client_slug, "approval_pack", "current")`` read pattern —
    a dynamic query, not a second persisted copy.
    """
    packs = list_for_client(memory, client_slug, limit=1)
    return packs[0] if packs else None


__all__ = [
    "get_latest_for_client",
    "list_for_client",
    "list_pending_for_client",
]
