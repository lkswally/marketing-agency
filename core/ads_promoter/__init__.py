"""Ads Bridge Promoter (MKT-6H) — opt-in fold of `AdsFeedbackBridgePack`
content into the canonical operational packs.

The promoter is invoked **only** when the operator passes the
`--include-ads-bridge` flag on:

- ``mkt feedback-plan``
- ``mkt build-tasks``
- ``mkt apply-feedback``

Without the flag, the CLI handlers never call the promoter. Pack
outputs are byte-compatible with the pre-MKT-6H baseline.

The promoter never mutates the bridge pack or any other upstream
artifact. It receives a freshly-built target pack from the
corresponding planner and returns the same pack with extra
entries appended.

Provenance — every promoted entry carries
``evidence_refs`` containing:

- ``ads_bridge:<pack_id>`` — back-reference to the bridge pack.
- ``ads_bridge_source:<recommendation_id | adjustment ix>`` — the
  source item inside the bridge pack.
- ``origin:ads_bridge`` — sentinel string used by ``--include-ads-bridge``
  re-runs to detect duplicates.

For :class:`ExecutionTask` (which has no ``evidence_refs`` field)
the provenance is encoded in the ``notes`` field with the same
markers so dedup works there too.
"""

from __future__ import annotations

from .promoter import (
    ADS_BRIDGE_ORIGIN_MARKER,
    AdsPromoter,
    PromotionResult,
    promote_into_execution_tasks,
    promote_into_feedback_pack,
    promote_into_iteration_plan,
)

__all__ = [
    "ADS_BRIDGE_ORIGIN_MARKER",
    "AdsPromoter",
    "PromotionResult",
    "promote_into_execution_tasks",
    "promote_into_feedback_pack",
    "promote_into_iteration_plan",
]
