"""AdsFeedbackBridge — deterministic insight → feedback translator.

Reads a persisted :class:`GoogleAdsInsightPack` (MKT-6F) and turns
each insight into:

- one :class:`AdsRecommendation` mirroring the insight kind;
- one :class:`AdsCampaignAdjustment` when the kind implies a
  campaign-level direction (pause / scale / reallocate / optimize);
- one or more :class:`AdsSuggestedTask` entries mirroring the
  MKT-6B :class:`SuggestedTask` shape so a future opt-in
  promoter can lift them into the next feedback / execution
  pack;
- :class:`AdsKeywordProposal` entries when the source insight
  carries a search-term ``negative_keyword_candidate`` evidence
  key. (Search-term data lands with P-6E.1 / P-6F.2; the bridge
  ships the wiring today so promoting the rule later is a no-op
  for the bridge layer.)

Cross-references (best-effort, never required):

- :class:`CampaignFeedbackPack` → records ``feedback_pack_id``.
- :class:`CampaignExecutionTaskPack` → records
  ``execution_task_pack_id``.
- :class:`NextCampaignIterationPlan` → records
  ``iteration_plan_id``.

**Read-only over upstream packs.** The bridge never mutates the
insight pack, the feedback pack, the execution task pack, or the
iteration plan. It writes exactly one new artifact:
:class:`AdsFeedbackBridgePack`.

**No Google Ads SDK call.** No mutation of remote state. No
negative-keyword execution. The keyword proposals are persisted
text the operator reviews and applies manually.
"""

from __future__ import annotations

from core.ads_analysis.models import (
    GOOGLE_ADS_INSIGHT_PACK_KIND,
    AdsInsightAction,
    AdsInsightKind,
    AdsInsightSeverity,
    GoogleAdsInsight,
    GoogleAdsInsightPack,
)
from core.contracts import AuditEventType, AuditTrailEvent
from core.domain.base import utcnow
from core.memory import EntityNotFound, Memory

from .models import (
    ADS_FEEDBACK_BRIDGE_PACK_KIND,
    SINGLETON_ID,
    AdsAdjustmentKind,
    AdsBridgeStats,
    AdsCampaignAdjustment,
    AdsFeedbackBridgePack,
    AdsKeywordProposal,
    AdsRecommendation,
    AdsRecommendationKind,
    AdsRecommendationPriority,
    AdsSuggestedTask,
)

DEFAULT_ADS_BRIDGE_RULE_SET_ID = "ads-feedback-bridge.v1"


# ---------- mappings ----------


_INSIGHT_TO_REC_KIND: dict[AdsInsightKind, AdsRecommendationKind] = {
    AdsInsightKind.HIGH_SPEND_ZERO_CONV: AdsRecommendationKind.PAUSE_REVIEW,
    AdsInsightKind.HIGH_SPEND_LOW_CONV: AdsRecommendationKind.REVIEW_CAMPAIGN,
    AdsInsightKind.LOW_CTR_HIGH_IMPR: AdsRecommendationKind.IMPROVE_AD_COPY,
    AdsInsightKind.GOOD_CTR_LOW_CONV_RATE: AdsRecommendationKind.REVIEW_LANDING,
    AdsInsightKind.HIGH_CPA_OUTLIER: AdsRecommendationKind.REVIEW_AD_GROUP,
    AdsInsightKind.SCALE_CANDIDATE: AdsRecommendationKind.SCALE_OPPORTUNITY,
    AdsInsightKind.BUDGET_REVIEW: AdsRecommendationKind.BUDGET_REVIEW,
    AdsInsightKind.PAUSE_CANDIDATE: AdsRecommendationKind.PAUSE_REVIEW,
    AdsInsightKind.REVIEW_CAMPAIGN: AdsRecommendationKind.REVIEW_CAMPAIGN,
    AdsInsightKind.REVIEW_AD_GROUP: AdsRecommendationKind.REVIEW_AD_GROUP,
    AdsInsightKind.REVIEW_LANDING: AdsRecommendationKind.REVIEW_LANDING,
    AdsInsightKind.IMPROVE_AD_COPY: AdsRecommendationKind.IMPROVE_AD_COPY,
}

_SEVERITY_TO_PRIORITY: dict[AdsInsightSeverity, AdsRecommendationPriority] = {
    AdsInsightSeverity.HIGH: AdsRecommendationPriority.HIGH,
    AdsInsightSeverity.MEDIUM: AdsRecommendationPriority.MEDIUM,
    AdsInsightSeverity.LOW: AdsRecommendationPriority.LOW,
}

_ACTION_TO_ADJUSTMENT: dict[AdsInsightAction, AdsAdjustmentKind] = {
    AdsInsightAction.PAUSE_CANDIDATE: AdsAdjustmentKind.PAUSE_REVIEW,
    AdsInsightAction.SCALE_CANDIDATE: AdsAdjustmentKind.SCALE_REVIEW,
    AdsInsightAction.BUDGET_REVIEW: AdsAdjustmentKind.REALLOCATE_REVIEW,
    AdsInsightAction.REVIEW_CAMPAIGN: AdsAdjustmentKind.OPTIMIZE_REVIEW,
}

# Per-recommendation-kind suggested task category (MKT-6B compatible).
_KIND_TO_TASK_CATEGORY: dict[AdsRecommendationKind, str] = {
    AdsRecommendationKind.PAUSE_REVIEW: "optimization",
    AdsRecommendationKind.REVIEW_CAMPAIGN: "optimization",
    AdsRecommendationKind.REVIEW_AD_GROUP: "optimization",
    AdsRecommendationKind.REVIEW_LANDING: "optimization",
    AdsRecommendationKind.SCALE_OPPORTUNITY: "optimization",
    AdsRecommendationKind.IMPROVE_AD_COPY: "content",
    AdsRecommendationKind.BUDGET_REVIEW: "operational",
    AdsRecommendationKind.NEGATIVE_KEYWORD_PROPOSAL: "operational",
}


# ---------- bridge class ----------


class AdsFeedbackBridge:
    """Deterministic translator from insight pack to bridge pack."""

    def __init__(self, memory: Memory) -> None:
        self._memory = memory

    def build(
        self, client_slug: str, *, rule_set_id: str | None = None,
    ) -> AdsFeedbackBridgePack:
        insight_pack = self._load_insight_pack(client_slug)
        recommendations = [
            self._insight_to_recommendation(i) for i in insight_pack.insights
        ]
        adjustments = list(self._adjustments_from_insights(insight_pack.insights))
        keyword_proposals = list(
            self._keyword_proposals_from_insights(insight_pack.insights)
        )
        tasks = list(self._tasks_from_recommendations(recommendations))
        # Optional cross-refs.
        feedback_pack_id = self._optional_pack_id(
            client_slug, "campaign_feedback_pack", "pack_id",
        )
        execution_task_pack_id = self._optional_pack_id(
            client_slug, "campaign_execution_task_pack", "pack_id",
        )
        iteration_plan_id = self._optional_pack_id(
            client_slug, "next_campaign_iteration_plan", "plan_id",
        )

        summary = _build_summary(
            insight_pack=insight_pack,
            recommendations=recommendations,
            adjustments=adjustments,
            tasks=tasks,
        )

        stats = _build_stats(
            recommendations=recommendations,
            adjustments=adjustments,
            keyword_proposals=keyword_proposals,
            tasks=tasks,
            insights_consumed=len(insight_pack.insights),
        )
        return AdsFeedbackBridgePack(
            client_slug=client_slug,
            insight_pack_id=insight_pack.pack_id,
            insight_pack_contract_version=insight_pack.contract_version,
            snapshot_id=insight_pack.snapshot_id,
            feedback_pack_id=feedback_pack_id,
            execution_task_pack_id=execution_task_pack_id,
            iteration_plan_id=iteration_plan_id,
            recommendations=recommendations,
            campaign_adjustments=adjustments,
            keyword_proposals=keyword_proposals,
            suggested_tasks=tasks,
            executive_summary=summary,
            stats=stats,
            rule_set_id=rule_set_id or DEFAULT_ADS_BRIDGE_RULE_SET_ID,
            created_at=utcnow(),
        )

    def persist(self, pack: AdsFeedbackBridgePack) -> None:
        self._memory.put(
            pack.client_slug,
            ADS_FEEDBACK_BRIDGE_PACK_KIND,
            SINGLETON_ID,
            pack.model_dump(mode="json"),
        )
        prev = self._memory.last_audit_hash(pack.client_slug)
        event = AuditTrailEvent.build(
            event_type=AuditEventType.NOTE,
            actor="ads_feedback_bridge",
            occurred_at=utcnow(),
            client_slug=pack.client_slug,
            payload={
                "ads_feedback_bridge_pack": {
                    "action": "bridged",
                    "pack_id": pack.pack_id,
                    "insight_pack_id": pack.insight_pack_id,
                    "feedback_pack_id": pack.feedback_pack_id,
                    "execution_task_pack_id": pack.execution_task_pack_id,
                    "iteration_plan_id": pack.iteration_plan_id,
                    "total_recommendations": pack.stats.total_recommendations,
                    "total_campaign_adjustments": (
                        pack.stats.total_campaign_adjustments
                    ),
                    "total_suggested_tasks": pack.stats.total_suggested_tasks,
                    "rule_set_id": pack.rule_set_id,
                }
            },
            prev_hash=prev,
        )
        self._memory.append_audit_event(event)

    # ---------- internals ----------

    def _load_insight_pack(self, client_slug: str) -> GoogleAdsInsightPack:
        try:
            raw = self._memory.get(
                client_slug, GOOGLE_ADS_INSIGHT_PACK_KIND, SINGLETON_ID,
            )
        except EntityNotFound as e:
            raise ValueError(
                f"no GoogleAdsInsightPack for client {client_slug!r} — "
                "run `mkt ads-analyze` first"
            ) from e
        return GoogleAdsInsightPack.model_validate(raw)

    def _optional_pack_id(
        self,
        client_slug: str,
        kind: str,
        id_field: str,
    ) -> str | None:
        try:
            raw = self._memory.get(client_slug, kind, SINGLETON_ID)
        except EntityNotFound:
            return None
        value = raw.get(id_field)
        return value if isinstance(value, str) else None

    # ---------- transforms ----------

    def _insight_to_recommendation(
        self, insight: GoogleAdsInsight,
    ) -> AdsRecommendation:
        rec_kind = _INSIGHT_TO_REC_KIND.get(
            insight.kind, AdsRecommendationKind.REVIEW_CAMPAIGN,
        )
        action_text = _suggested_action_text(insight, rec_kind)
        return AdsRecommendation(
            kind=rec_kind,
            priority=_SEVERITY_TO_PRIORITY[insight.severity],
            title=insight.title,
            rationale=insight.rationale,
            suggested_action=action_text,
            campaign_id=insight.campaign_id,
            ad_group_id=insight.ad_group_id,
            content_ref=insight.content_ref,
            dimension=insight.dimension,
            evidence_refs=[f"insight:{insight.insight_id}"],
        )

    def _adjustments_from_insights(
        self, insights: list[GoogleAdsInsight],
    ):
        # One adjustment per (campaign_id, kind) combination — the
        # insight may fire multiple times per campaign (multiple ad
        # groups), but the campaign-level direction is the same.
        seen: set[tuple[str | None, AdsAdjustmentKind]] = set()
        for i in insights:
            adj_kind = _ACTION_TO_ADJUSTMENT.get(i.suggested_action)
            if adj_kind is None:
                continue
            key = (i.campaign_id, adj_kind)
            if key in seen:
                continue
            seen.add(key)
            dimension = _campaign_dimension(i.dimension)
            yield AdsCampaignAdjustment(
                campaign_id=i.campaign_id,
                dimension=dimension,
                kind=adj_kind,
                rationale=_adjustment_rationale(i, adj_kind),
                suggested_next_step=_adjustment_next_step(adj_kind),
                evidence_refs=[f"insight:{i.insight_id}"],
            )

    def _keyword_proposals_from_insights(
        self, insights: list[GoogleAdsInsight],
    ):
        # Search-term data is not yet in the snapshot (P-6E.1).
        # When it lands, the analyzer will populate
        # ``insight.evidence`` with ``negative_keyword_candidate``
        # entries; the bridge already knows how to surface them.
        for i in insights:
            term = _extract_negative_keyword_candidate(i)
            if not term:
                continue
            yield AdsKeywordProposal(
                keyword=term,
                rationale=(
                    f"Surfaced by insight `{i.kind.value}` on "
                    f"{i.dimension or i.content_ref or 'unknown'}."
                ),
                campaign_id=i.campaign_id,
                ad_group_id=i.ad_group_id,
                evidence_refs=[f"insight:{i.insight_id}"],
            )

    def _tasks_from_recommendations(
        self, recommendations: list[AdsRecommendation],
    ):
        # One task per recommendation. Plus one "review the
        # bridge pack itself" measurement task at the end so the
        # operator has a concrete next step.
        for r in recommendations:
            category = _KIND_TO_TASK_CATEGORY.get(r.kind, "optimization")
            yield AdsSuggestedTask(
                title=f"{r.title}",
                category=category,
                priority=r.priority,
                rationale=r.rationale,
                content_ref=r.content_ref,
                evidence_refs=[f"recommendation:{r.recommendation_id}"],
            )
        if recommendations:
            yield AdsSuggestedTask(
                title="Review Google Ads bridge pack with account lead",
                category="measurement",
                priority=AdsRecommendationPriority.MEDIUM,
                rationale=(
                    "Walk through the bridge pack's recommendations + "
                    "campaign adjustments with the account lead before "
                    "applying anything in the Ads UI."
                ),
                evidence_refs=[],
            )


def bridge_and_persist(
    memory: Memory, *, client_slug: str,
    rule_set_id: str | None = None,
) -> AdsFeedbackBridgePack:
    """Run the bridge + persist + audit in one call."""

    bridge = AdsFeedbackBridge(memory=memory)
    pack = bridge.build(client_slug, rule_set_id=rule_set_id)
    bridge.persist(pack)
    return pack


# ---------- helpers ----------


def _suggested_action_text(
    insight: GoogleAdsInsight, rec_kind: AdsRecommendationKind,
) -> str:
    label = insight.dimension or insight.content_ref or "this ad group"
    if rec_kind is AdsRecommendationKind.PAUSE_REVIEW:
        return (
            f"Review {label} for pause — confirm intent, landing fit and "
            "expected lift before deciding."
        )
    if rec_kind is AdsRecommendationKind.REVIEW_CAMPAIGN:
        return f"Review campaign for {label} — targeting + budget shape."
    if rec_kind is AdsRecommendationKind.REVIEW_AD_GROUP:
        return f"Review ad group {label} — CPA outlier vs snapshot median."
    if rec_kind is AdsRecommendationKind.REVIEW_LANDING:
        return f"Review the landing page behind {label}."
    if rec_kind is AdsRecommendationKind.SCALE_OPPORTUNITY:
        return f"Consider scaling budget on {label} after operator review."
    if rec_kind is AdsRecommendationKind.IMPROVE_AD_COPY:
        return f"Refresh headlines / descriptions on {label}."
    if rec_kind is AdsRecommendationKind.BUDGET_REVIEW:
        return f"Review budget allocation for {label}."
    return f"Review {label}."


def _campaign_dimension(dimension: str | None) -> str | None:
    if not dimension:
        return None
    head, _, _ = dimension.partition(" / ")
    return head or None


def _adjustment_rationale(
    insight: GoogleAdsInsight, kind: AdsAdjustmentKind,
) -> str:
    label = insight.dimension or insight.content_ref or "this campaign"
    if kind is AdsAdjustmentKind.PAUSE_REVIEW:
        return (
            f"Insight `{insight.kind.value}` flagged {label} as a pause "
            "candidate. Operator should review before pausing."
        )
    if kind is AdsAdjustmentKind.SCALE_REVIEW:
        return (
            f"Insight `{insight.kind.value}` flagged {label} as a scale "
            "candidate. Operator should review before scaling."
        )
    if kind is AdsAdjustmentKind.REALLOCATE_REVIEW:
        return (
            f"Insight `{insight.kind.value}` flagged {label} for budget "
            "review. Operator should review before reallocating."
        )
    return (
        f"Insight `{insight.kind.value}` suggests reviewing {label} for "
        "creative / targeting / landing optimisations."
    )


def _adjustment_next_step(kind: AdsAdjustmentKind) -> str:
    if kind is AdsAdjustmentKind.PAUSE_REVIEW:
        return "Manually pause in Ads UI if review confirms."
    if kind is AdsAdjustmentKind.SCALE_REVIEW:
        return "Manually raise daily budget in Ads UI if review confirms."
    if kind is AdsAdjustmentKind.REALLOCATE_REVIEW:
        return "Manually reallocate across campaigns in Ads UI."
    return "Apply the chosen optimisation manually in Ads UI."


def _extract_negative_keyword_candidate(
    insight: GoogleAdsInsight,
) -> str | None:
    """Search-term wiring (P-6E.1 / P-6F.2). When future analyzer
    rules populate ``insight.evidence`` with a textual
    ``negative_keyword_candidate`` value, surface it here. For the
    current rule set this always returns ``None``."""

    # The current ``evidence`` dict only holds floats. Future
    # search-term rules will add a parallel ``thresholds_used`` /
    # ``evidence`` field; until then, this is a no-op stub.
    return None


def _build_summary(
    *,
    insight_pack: GoogleAdsInsightPack,
    recommendations: list[AdsRecommendation],
    adjustments: list[AdsCampaignAdjustment],
    tasks: list[AdsSuggestedTask],
) -> str:
    if not insight_pack.insights:
        return (
            "No Google Ads insights to bridge — the analyzer returned an "
            "empty pack. Verify the snapshot has google_ads rows."
        )
    high = sum(
        1 for r in recommendations
        if r.priority is AdsRecommendationPriority.HIGH
    )
    parts: list[str] = []
    parts.append(
        f"Bridged {len(insight_pack.insights)} Google Ads insights into "
        f"{len(recommendations)} recommendations, {len(adjustments)} "
        f"campaign adjustments and {len(tasks)} suggested tasks."
    )
    if high:
        parts.append(f"{high} high-priority recommendation(s) require attention.")
    parts.append(
        "Nothing is applied automatically; review with the account lead "
        "before changing anything in the Ads UI."
    )
    return " ".join(parts)


def _build_stats(
    *,
    recommendations: list[AdsRecommendation],
    adjustments: list[AdsCampaignAdjustment],
    keyword_proposals: list[AdsKeywordProposal],
    tasks: list[AdsSuggestedTask],
    insights_consumed: int,
) -> AdsBridgeStats:
    by_kind: dict[str, int] = {}
    by_priority: dict[str, int] = {}
    for r in recommendations:
        by_kind[r.kind.value] = by_kind.get(r.kind.value, 0) + 1
        by_priority[r.priority.value] = by_priority.get(r.priority.value, 0) + 1
    by_adj: dict[str, int] = {}
    for a in adjustments:
        by_adj[a.kind.value] = by_adj.get(a.kind.value, 0) + 1
    return AdsBridgeStats(
        total_recommendations=len(recommendations),
        total_campaign_adjustments=len(adjustments),
        total_keyword_proposals=len(keyword_proposals),
        total_suggested_tasks=len(tasks),
        by_recommendation_kind=by_kind,
        by_recommendation_priority=by_priority,
        by_adjustment_kind=by_adj,
        insights_consumed=insights_consumed,
    )


__all__ = [
    "AdsFeedbackBridge",
    "DEFAULT_ADS_BRIDGE_RULE_SET_ID",
    "bridge_and_persist",
]
