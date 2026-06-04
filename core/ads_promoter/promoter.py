"""AdsPromoter — opt-in fold of an `AdsFeedbackBridgePack` into the
three canonical operational packs.

Each ``promote_into_*`` function takes the freshly-built target
pack from its planner and a previously-persisted bridge pack, and
returns the same pack with promoted entries appended.

**Idempotent.** Re-running with the same bridge pack does not
duplicate entries — the dedup walks `evidence_refs` (or `notes`
for `ExecutionTask`) for the per-source marker
``ads_bridge_source:<id>``.

**Read-only over the bridge pack** — the promoter only reads the
bridge pack; it never modifies it.

The CLI handlers call the promoter only when the operator passes
``--include-ads-bridge``. Without the flag, this module is not
invoked and pack outputs are byte-compatible with the
pre-MKT-6H baseline.
"""

from __future__ import annotations

from dataclasses import dataclass

from core.ads_feedback.models import (
    AdsAdjustmentKind,
    AdsCampaignAdjustment,
    AdsFeedbackBridgePack,
    AdsRecommendation,
    AdsRecommendationKind,
    AdsRecommendationPriority,
    AdsSuggestedTask,
)
from core.execution.models import (
    CampaignExecutionTaskPack,
    ExecutionTask,
    TaskCategory,
    TaskPriority,
    TaskState,
)
from core.feedback.models import (
    CampaignFeedbackPack,
    ChannelAdjustment,
    ChannelPriority,
    ContentSuggestion,
    ContentSuggestionKind,
    SuggestedTask,
    SuggestedTaskCategory,
    SuggestedTaskPriority,
)
from core.iteration.models import (
    IterationAction,
    IterationActionKind,
    IterationActionPriority,
    NextCampaignIterationPlan,
    SuggestedIterationTask,
)

ADS_BRIDGE_ORIGIN_MARKER = "origin:ads_bridge"
"""Sentinel string emitted on every promoted entry so re-runs can
detect duplicates without ambiguity."""


# ---------- mappings (extracted as module constants for testability) ----------


_REC_TO_FEEDBACK_TASK_CATEGORY: dict[AdsRecommendationKind, SuggestedTaskCategory] = {
    AdsRecommendationKind.PAUSE_REVIEW: SuggestedTaskCategory.OPTIMIZATION,
    AdsRecommendationKind.REVIEW_CAMPAIGN: SuggestedTaskCategory.OPTIMIZATION,
    AdsRecommendationKind.REVIEW_AD_GROUP: SuggestedTaskCategory.OPTIMIZATION,
    AdsRecommendationKind.REVIEW_LANDING: SuggestedTaskCategory.OPTIMIZATION,
    AdsRecommendationKind.SCALE_OPPORTUNITY: SuggestedTaskCategory.OPTIMIZATION,
    AdsRecommendationKind.IMPROVE_AD_COPY: SuggestedTaskCategory.CONTENT,
    AdsRecommendationKind.BUDGET_REVIEW: SuggestedTaskCategory.OPERATIONAL,
    AdsRecommendationKind.NEGATIVE_KEYWORD_PROPOSAL: SuggestedTaskCategory.OPERATIONAL,
}

_REC_TO_EXECUTION_CATEGORY: dict[AdsRecommendationKind, TaskCategory] = {
    AdsRecommendationKind.PAUSE_REVIEW: TaskCategory.OPERATIONAL,
    AdsRecommendationKind.REVIEW_CAMPAIGN: TaskCategory.OPERATIONAL,
    AdsRecommendationKind.REVIEW_AD_GROUP: TaskCategory.OPERATIONAL,
    AdsRecommendationKind.REVIEW_LANDING: TaskCategory.OPERATIONAL,
    AdsRecommendationKind.SCALE_OPPORTUNITY: TaskCategory.OPERATIONAL,
    AdsRecommendationKind.IMPROVE_AD_COPY: TaskCategory.SOCIAL,
    AdsRecommendationKind.BUDGET_REVIEW: TaskCategory.OPERATIONAL,
    AdsRecommendationKind.NEGATIVE_KEYWORD_PROPOSAL: TaskCategory.OPERATIONAL,
}

_REC_PRIORITY_TO_TASK_PRIORITY_FEEDBACK: dict[
    AdsRecommendationPriority, SuggestedTaskPriority,
] = {
    AdsRecommendationPriority.HIGH: SuggestedTaskPriority.HIGH,
    AdsRecommendationPriority.MEDIUM: SuggestedTaskPriority.MEDIUM,
    AdsRecommendationPriority.LOW: SuggestedTaskPriority.LOW,
}

_REC_PRIORITY_TO_EXECUTION_PRIORITY: dict[
    AdsRecommendationPriority, TaskPriority,
] = {
    AdsRecommendationPriority.HIGH: TaskPriority.HIGH,
    AdsRecommendationPriority.MEDIUM: TaskPriority.MEDIUM,
    AdsRecommendationPriority.LOW: TaskPriority.LOW,
}

_REC_PRIORITY_TO_ITERATION_PRIORITY: dict[
    AdsRecommendationPriority, IterationActionPriority,
] = {
    AdsRecommendationPriority.HIGH: IterationActionPriority.HIGH,
    AdsRecommendationPriority.MEDIUM: IterationActionPriority.MEDIUM,
    AdsRecommendationPriority.LOW: IterationActionPriority.LOW,
}

_ADJ_TO_ITERATION_KIND: dict[AdsAdjustmentKind, IterationActionKind] = {
    AdsAdjustmentKind.PAUSE_REVIEW: IterationActionKind.PAUSE_PIECE,
    AdsAdjustmentKind.SCALE_REVIEW: IterationActionKind.CHANNEL_PROMOTE,
    AdsAdjustmentKind.REALLOCATE_REVIEW: IterationActionKind.CHANNEL_PROMOTE,
    AdsAdjustmentKind.OPTIMIZE_REVIEW: IterationActionKind.IMPROVE_PIECE,
}

# Map ads recommendation kind → ContentSuggestion kind when the
# recommendation targets an ad-group piece (not a campaign-level
# direction).
_REC_TO_CONTENT_SUGGESTION_KIND: dict[
    AdsRecommendationKind, ContentSuggestionKind,
] = {
    AdsRecommendationKind.PAUSE_REVIEW: ContentSuggestionKind.PAUSE,
    AdsRecommendationKind.IMPROVE_AD_COPY: ContentSuggestionKind.IMPROVE,
    AdsRecommendationKind.SCALE_OPPORTUNITY: ContentSuggestionKind.REPEAT,
    AdsRecommendationKind.REVIEW_LANDING: ContentSuggestionKind.IMPROVE,
}


# ---------- result object ----------


@dataclass(frozen=True)
class PromotionResult:
    """How much was promoted in this run.

    The CLI handlers surface these counts in the JSON summary so
    the operator sees at a glance what the flag did.
    """

    recommendations_promoted: int = 0
    tasks_promoted: int = 0
    channel_adjustments_promoted: int = 0
    content_suggestions_promoted: int = 0
    iteration_actions_promoted: int = 0
    duplicates_skipped: int = 0


# ---------- public API ----------


class AdsPromoter:
    """Stateful aggregator that exposes a fluent ``into_*`` API.

    The CLI handlers instantiate one promoter per run and call the
    matching ``into_*`` method; standalone tests use the module-
    level wrappers ``promote_into_*``.
    """

    def __init__(self, bridge_pack: AdsFeedbackBridgePack) -> None:
        self._bridge = bridge_pack

    @property
    def bridge_pack_id(self) -> str:
        return self._bridge.pack_id

    def into_feedback_pack(
        self, pack: CampaignFeedbackPack,
    ) -> PromotionResult:
        return _promote_feedback(self._bridge, pack)

    def into_execution_tasks(
        self, pack: CampaignExecutionTaskPack,
    ) -> PromotionResult:
        return _promote_execution_tasks(self._bridge, pack)

    def into_iteration_plan(
        self, plan: NextCampaignIterationPlan,
    ) -> PromotionResult:
        return _promote_iteration(self._bridge, plan)


def promote_into_feedback_pack(
    bridge: AdsFeedbackBridgePack, pack: CampaignFeedbackPack,
) -> PromotionResult:
    return _promote_feedback(bridge, pack)


def promote_into_execution_tasks(
    bridge: AdsFeedbackBridgePack, pack: CampaignExecutionTaskPack,
) -> PromotionResult:
    return _promote_execution_tasks(bridge, pack)


def promote_into_iteration_plan(
    bridge: AdsFeedbackBridgePack, plan: NextCampaignIterationPlan,
) -> PromotionResult:
    return _promote_iteration(bridge, plan)


# ---------- feedback pack ----------


def _promote_feedback(
    bridge: AdsFeedbackBridgePack, pack: CampaignFeedbackPack,
) -> PromotionResult:
    rec_promoted = 0
    tasks_promoted = 0
    adj_promoted = 0
    content_promoted = 0
    duplicates = 0

    bridge_marker = _bridge_marker(bridge)

    # --- recommendations → SuggestedTask + optional ContentSuggestion ---
    existing_task_markers = _collect_evidence_markers(
        e for t in pack.suggested_tasks for e in t.evidence_refs
    )
    existing_content_markers = _collect_evidence_markers(
        e for c in pack.content_suggestions for e in c.evidence_refs
    )
    existing_adj_markers = _collect_evidence_markers(
        e for a in pack.channel_adjustments for e in a.evidence_refs
    )

    for rec in bridge.recommendations:
        rec_marker = _source_marker(rec.recommendation_id)
        # SuggestedTask
        if rec_marker in existing_task_markers:
            duplicates += 1
        else:
            pack.suggested_tasks.append(
                _rec_to_feedback_task(rec, bridge_marker, rec_marker),
            )
            tasks_promoted += 1
            rec_promoted += 1

        # ContentSuggestion (only for the kinds that target a piece)
        suggestion_kind = _REC_TO_CONTENT_SUGGESTION_KIND.get(rec.kind)
        if suggestion_kind is not None and rec.content_ref:
            if rec_marker in existing_content_markers:
                duplicates += 1
            else:
                pack.content_suggestions.append(
                    _rec_to_content_suggestion(
                        rec, suggestion_kind, bridge_marker, rec_marker,
                    ),
                )
                content_promoted += 1

    # --- campaign adjustments → ChannelAdjustment("google_ads") ---
    for adj in bridge.campaign_adjustments:
        adj_marker = _source_marker(
            adj.campaign_id or f"campaign:{adj.kind.value}",
        )
        if adj_marker in existing_adj_markers:
            duplicates += 1
            continue
        new_priority = _adjustment_to_channel_priority(adj.kind)
        pack.channel_adjustments.append(
            ChannelAdjustment(
                channel="google_ads",
                current_priority=None,
                new_priority=new_priority,
                rationale=(
                    f"Promoted from ads bridge — {adj.rationale}"
                ),
                evidence_refs=[
                    bridge_marker, adj_marker, ADS_BRIDGE_ORIGIN_MARKER,
                ],
            ),
        )
        adj_promoted += 1
        existing_adj_markers.add(adj_marker)

    # Recompute pack stats so the persisted JSON reflects the
    # added entries.
    from core.feedback.models import FeedbackStats

    pack.stats = FeedbackStats(
        total_suggested_tasks=len(pack.suggested_tasks),
        high_priority_tasks=sum(
            1 for t in pack.suggested_tasks
            if t.priority is SuggestedTaskPriority.HIGH
        ),
        channel_adjustments=len(pack.channel_adjustments),
        content_suggestions=len(pack.content_suggestions),
        seo_recommendations=len(pack.seo_recommendations),
        email_recommendations=len(pack.email_recommendations),
        social_recommendations=len(pack.social_recommendations),
    )

    return PromotionResult(
        recommendations_promoted=rec_promoted,
        tasks_promoted=tasks_promoted,
        channel_adjustments_promoted=adj_promoted,
        content_suggestions_promoted=content_promoted,
        duplicates_skipped=duplicates,
    )


# ---------- execution tasks ----------


def _promote_execution_tasks(
    bridge: AdsFeedbackBridgePack, pack: CampaignExecutionTaskPack,
) -> PromotionResult:
    promoted = 0
    duplicates = 0
    bridge_marker = _bridge_marker(bridge)

    existing_markers = _collect_note_markers(
        t.notes for t in pack.tasks if t.notes
    )

    for rec in bridge.recommendations:
        rec_marker = _source_marker(rec.recommendation_id)
        if rec_marker in existing_markers:
            duplicates += 1
            continue
        pack.tasks.append(_rec_to_execution_task(
            rec, bridge_marker, rec_marker,
        ))
        promoted += 1
        existing_markers.add(rec_marker)

    return PromotionResult(
        tasks_promoted=promoted,
        duplicates_skipped=duplicates,
    )


# ---------- iteration plan ----------


def _promote_iteration(
    bridge: AdsFeedbackBridgePack, plan: NextCampaignIterationPlan,
) -> PromotionResult:
    actions_promoted = 0
    tasks_promoted = 0
    duplicates = 0
    bridge_marker = _bridge_marker(bridge)

    existing_action_markers = _collect_evidence_markers(
        e for a in plan.actions for e in a.evidence_refs
    )
    existing_task_markers = _collect_evidence_markers(
        e for t in plan.suggested_tasks for e in t.evidence_refs
    )

    # Campaign adjustments → IterationAction
    for adj in bridge.campaign_adjustments:
        adj_marker = _source_marker(
            adj.campaign_id or f"campaign:{adj.kind.value}",
        )
        if adj_marker in existing_action_markers:
            duplicates += 1
            continue
        kind = _ADJ_TO_ITERATION_KIND.get(adj.kind, IterationActionKind.IMPROVE_PIECE)
        plan.actions.append(IterationAction(
            kind=kind,
            priority=IterationActionPriority.MEDIUM,
            title=(
                f"[ads bridge] {adj.kind.value} — "
                f"{adj.dimension or f'campaign:{adj.campaign_id}'}"
            ),
            target_ref=(
                f"campaign:{adj.campaign_id}" if adj.campaign_id else None
            ),
            channel="google_ads",
            rationale=adj.rationale,
            suggested_next_step=adj.suggested_next_step,
            evidence_refs=[
                bridge_marker, adj_marker, ADS_BRIDGE_ORIGIN_MARKER,
            ],
        ))
        actions_promoted += 1
        existing_action_markers.add(adj_marker)

    # Bridge tasks → SuggestedIterationTask
    for bt in bridge.suggested_tasks:
        # Use the task_id from the bridge as the source marker.
        task_marker = _source_marker(bt.task_id)
        if task_marker in existing_task_markers:
            duplicates += 1
            continue
        plan.suggested_tasks.append(SuggestedIterationTask(
            title=bt.title,
            category=bt.category,
            priority=_REC_PRIORITY_TO_ITERATION_PRIORITY[bt.priority],
            rationale=bt.rationale,
            channel="google_ads",
            evidence_refs=[
                bridge_marker, task_marker, ADS_BRIDGE_ORIGIN_MARKER,
            ],
        ))
        tasks_promoted += 1
        existing_task_markers.add(task_marker)

    # Recompute pack stats so the persisted JSON reflects the
    # added entries.
    from core.iteration.models import IterationStats

    actions = plan.actions
    plan.stats = IterationStats(
        total_actions=len(actions),
        repeats=sum(1 for a in actions if a.kind is IterationActionKind.REPEAT_PIECE),
        pauses=sum(1 for a in actions if a.kind is IterationActionKind.PAUSE_PIECE),
        improves=sum(1 for a in actions if a.kind is IterationActionKind.IMPROVE_PIECE),
        creates=sum(1 for a in actions if a.kind is IterationActionKind.CREATE_NEW),
        channel_adjustments=sum(
            1 for a in actions
            if a.kind in (
                IterationActionKind.CHANNEL_PROMOTE,
                IterationActionKind.CHANNEL_PAUSE,
            )
        ),
        new_content_ideas=len(plan.new_content_ideas),
        ab_test_hypotheses=len(plan.ab_test_hypotheses),
        calendar_entries=len(plan.calendar),
        suggested_tasks=len(plan.suggested_tasks),
    )

    return PromotionResult(
        iteration_actions_promoted=actions_promoted,
        tasks_promoted=tasks_promoted,
        duplicates_skipped=duplicates,
    )


# ---------- factories ----------


def _rec_to_feedback_task(
    rec: AdsRecommendation, bridge_marker: str, rec_marker: str,
) -> SuggestedTask:
    return SuggestedTask(
        title=f"[ads bridge] {rec.title}",
        category=_REC_TO_FEEDBACK_TASK_CATEGORY.get(
            rec.kind, SuggestedTaskCategory.OPTIMIZATION,
        ),
        priority=_REC_PRIORITY_TO_TASK_PRIORITY_FEEDBACK[rec.priority],
        rationale=rec.rationale,
        channel="google_ads",
        content_ref=rec.content_ref,
        evidence_refs=[bridge_marker, rec_marker, ADS_BRIDGE_ORIGIN_MARKER],
    )


def _rec_to_content_suggestion(
    rec: AdsRecommendation,
    kind: ContentSuggestionKind,
    bridge_marker: str,
    rec_marker: str,
) -> ContentSuggestion:
    return ContentSuggestion(
        kind=kind,
        content_ref=rec.content_ref,
        channel="google_ads",
        title=f"[ads bridge] {rec.title}",
        rationale=rec.rationale,
        suggested_next_step=rec.suggested_action,
        evidence_refs=[bridge_marker, rec_marker, ADS_BRIDGE_ORIGIN_MARKER],
    )


def _rec_to_execution_task(
    rec: AdsRecommendation, bridge_marker: str, rec_marker: str,
) -> ExecutionTask:
    note_parts = [
        f"[{ADS_BRIDGE_ORIGIN_MARKER}]",
        bridge_marker,
        rec_marker,
        rec.suggested_action,
    ]
    return ExecutionTask(
        title=f"[ads bridge] {rec.title}",
        description=rec.rationale,
        category=_REC_TO_EXECUTION_CATEGORY.get(
            rec.kind, TaskCategory.OPERATIONAL,
        ),
        priority=_REC_PRIORITY_TO_EXECUTION_PRIORITY[rec.priority],
        state=TaskState.TODO,
        channel="google_ads",
        asset_ref=rec.content_ref,
        owner_hint="account_lead",
        notes=" | ".join(note_parts),
    )


def _adjustment_to_channel_priority(
    kind: AdsAdjustmentKind,
) -> ChannelPriority:
    if kind is AdsAdjustmentKind.PAUSE_REVIEW:
        return ChannelPriority.PAUSE
    if kind is AdsAdjustmentKind.SCALE_REVIEW:
        return ChannelPriority.HIGH
    if kind is AdsAdjustmentKind.REALLOCATE_REVIEW:
        return ChannelPriority.MEDIUM
    return ChannelPriority.MEDIUM


# ---------- markers + dedup ----------


def _bridge_marker(bridge: AdsFeedbackBridgePack) -> str:
    return f"ads_bridge:{bridge.pack_id}"


def _source_marker(source_id: str) -> str:
    return f"ads_bridge_source:{source_id}"


def _collect_evidence_markers(refs) -> set[str]:
    """Walk an iterable of evidence-ref strings and return the set
    of ``ads_bridge_source:...`` markers found."""

    out: set[str] = set()
    for ref in refs:
        if isinstance(ref, str) and ref.startswith("ads_bridge_source:"):
            out.add(ref)
    return out


def _collect_note_markers(notes_iter) -> set[str]:
    """Walk an iterable of ``ExecutionTask.notes`` strings and pull
    the ``ads_bridge_source:...`` markers out."""

    out: set[str] = set()
    for n in notes_iter:
        for part in (n or "").split("|"):
            part = part.strip()
            if part.startswith("ads_bridge_source:"):
                out.add(part)
    return out


# Suppress unused warnings for symbols re-exported for tests.
_ = AdsCampaignAdjustment  # noqa: F841
_ = AdsSuggestedTask  # noqa: F841


__all__ = [
    "ADS_BRIDGE_ORIGIN_MARKER",
    "AdsPromoter",
    "PromotionResult",
    "promote_into_execution_tasks",
    "promote_into_feedback_pack",
    "promote_into_iteration_plan",
]
