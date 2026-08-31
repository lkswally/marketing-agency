"""Claim audit + approval pack layer (MKT-3B).

Contract: ``approval-pack.v1``.
"""

from __future__ import annotations

from .approval_pack import (
    APPROVAL_PACK_KIND,
    SINGLETON_ID,
    ApprovalPackBuilder,
    ApprovalStateError,
    audit_and_persist,
)
from .claim_auditor import DEFAULT_RULE_SET_ID, DEFAULT_RULES, ClaimAuditor
from .models import (
    APPROVAL_PACK_VERSION,
    ApprovalChecklistItem,
    ApprovalDecision,
    ApprovalPack,
    ApprovalState,
    ClaimCategory,
    ClaimDetection,
    ClaimRule,
)
from .renderer import render_markdown_pack
from .repository import (
    get_latest_for_client,
    list_for_client,
    list_pending_for_client,
)

__all__ = [
    "APPROVAL_PACK_VERSION",
    "APPROVAL_PACK_KIND",
    "SINGLETON_ID",
    "DEFAULT_RULE_SET_ID",
    "DEFAULT_RULES",
    # Auditor
    "ClaimAuditor",
    # Builder + helpers
    "ApprovalPackBuilder",
    "ApprovalStateError",
    "audit_and_persist",
    # Models
    "ApprovalPack",
    "ApprovalState",
    "ApprovalChecklistItem",
    "ApprovalDecision",
    "ClaimDetection",
    "ClaimRule",
    "ClaimCategory",
    # Renderer
    "render_markdown_pack",
    # Repository (MKT-11E)
    "get_latest_for_client",
    "list_for_client",
    "list_pending_for_client",
]
