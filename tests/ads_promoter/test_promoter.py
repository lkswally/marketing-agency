"""Tests for the MKT-6H ads bridge promoter."""

from __future__ import annotations

from datetime import UTC, datetime

from core.ads_feedback.models import (
    AdsAdjustmentKind,
    AdsBridgeStats,
    AdsCampaignAdjustment,
    AdsFeedbackBridgePack,
    AdsRecommendation,
    AdsRecommendationKind,
    AdsRecommendationPriority,
    AdsSuggestedTask,
)
from core.ads_promoter import (
    ADS_BRIDGE_ORIGIN_MARKER,
    AdsPromoter,
    promote_into_execution_tasks,
    promote_into_feedback_pack,
    promote_into_iteration_plan,
)
from core.execution.models import (
    CampaignExecutionTaskPack,
    TaskCategory,
    TaskPriority,
    TaskState,
)
from core.feedback.models import (
    CampaignFeedbackPack,
    ChannelPriority,
    ContentSuggestionKind,
    ExecutiveSummary,
    FeedbackStats,
)
from core.iteration.models import (
    IterationActionKind,
    IterationExecutiveSummary,
    IterationStats,
    NextCampaignIterationPlan,
)


def _now() -> datetime:
    return datetime(2026, 6, 4, tzinfo=UTC)


# ---------- fixtures ----------


def _bridge_pack(
    *,
    recs: list[AdsRecommendation] | None = None,
    adjustments: list[AdsCampaignAdjustment] | None = None,
    tasks: list[AdsSuggestedTask] | None = None,
) -> AdsFeedbackBridgePack:
    recs = recs or []
    adjustments = adjustments or []
    tasks = tasks or []
    stats = AdsBridgeStats(
        total_recommendations=len(recs),
        total_campaign_adjustments=len(adjustments),
        total_keyword_proposals=0,
        total_suggested_tasks=len(tasks),
        insights_consumed=len(recs),
    )
    return AdsFeedbackBridgePack(
        client_slug="acme",
        insight_pack_id="insight-1",
        insight_pack_contract_version="google-ads-insight-pack.v1",
        recommendations=recs,
        campaign_adjustments=adjustments,
        keyword_proposals=[],
        suggested_tasks=tasks,
        executive_summary="t",
        stats=stats,
        created_at=_now(),
        rule_set_id="ads-feedback-bridge.v1",
    )


def _empty_feedback_pack() -> CampaignFeedbackPack:
    return CampaignFeedbackPack(
        client_slug="acme",
        recommendation_pack_id="rec-1",
        recommendation_pack_contract_version="optimization-recommendation-pack.v1",
        executive_summary=ExecutiveSummary(
            headline="t", paragraphs=["p"], suggested_meeting_agenda=["a"],
        ),
        suggested_tasks=[],
        channel_adjustments=[],
        content_suggestions=[],
        seo_recommendations=[],
        email_recommendations=[],
        social_recommendations=[],
        stats=FeedbackStats(
            total_suggested_tasks=0, high_priority_tasks=0,
            channel_adjustments=0, content_suggestions=0,
            seo_recommendations=0, email_recommendations=0,
            social_recommendations=0,
        ),
        created_at=_now(),
        rule_set_id="feedback-planner.v1",
    )


def _empty_task_pack() -> CampaignExecutionTaskPack:
    return CampaignExecutionTaskPack(
        client_slug="acme",
        report_id="report-1",
        report_contract_version="campaign-strategy-report.v1",
        tasks=[],
        created_at=_now(),
        updated_at=_now(),
        rule_set_id="task-factory.v1",
    )


def _empty_iteration_plan() -> NextCampaignIterationPlan:
    return NextCampaignIterationPlan(
        client_slug="acme",
        feedback_pack_id="feedback-1",
        feedback_pack_contract_version="campaign-feedback-pack.v1",
        actions=[],
        new_content_ideas=[],
        ab_test_hypotheses=[],
        calendar=[],
        suggested_tasks=[],
        executive_summary=IterationExecutiveSummary(
            headline="t", paragraphs=["p"], suggested_meeting_agenda=["a"],
        ),
        stats=IterationStats(
            total_actions=0, repeats=0, pauses=0, improves=0, creates=0,
            channel_adjustments=0, new_content_ideas=0,
            ab_test_hypotheses=0, calendar_entries=0, suggested_tasks=0,
        ),
        created_at=_now(),
        rule_set_id="iteration-planner.v1",
    )


def _recommendation(
    *,
    kind: AdsRecommendationKind = AdsRecommendationKind.PAUSE_REVIEW,
    priority: AdsRecommendationPriority = AdsRecommendationPriority.HIGH,
    content_ref: str | None = "campaign:42::ad_group:100",
    title: str = "Pause Brand Wasteful",
) -> AdsRecommendation:
    return AdsRecommendation(
        kind=kind, priority=priority, title=title,
        rationale="High spend zero conv.",
        suggested_action="Review for pause.",
        campaign_id="42", ad_group_id="100",
        content_ref=content_ref,
        dimension="Brand / Wasteful",
    )


def _adjustment(
    *,
    kind: AdsAdjustmentKind = AdsAdjustmentKind.PAUSE_REVIEW,
    campaign_id: str | None = "42",
) -> AdsCampaignAdjustment:
    return AdsCampaignAdjustment(
        campaign_id=campaign_id,
        dimension="Brand",
        kind=kind,
        rationale="Reason.",
        suggested_next_step="Manually pause.",
    )


def _bridge_task() -> AdsSuggestedTask:
    return AdsSuggestedTask(
        title="Review",
        category="optimization",
        priority=AdsRecommendationPriority.HIGH,
        rationale="r",
    )


# ---------- feedback pack promotion ----------


def test_promote_into_feedback_pack_basic() -> None:
    pack = _empty_feedback_pack()
    bridge = _bridge_pack(
        recs=[_recommendation()],
        adjustments=[_adjustment()],
    )
    result = promote_into_feedback_pack(bridge, pack)
    assert result.recommendations_promoted == 1
    assert result.tasks_promoted == 1
    assert result.channel_adjustments_promoted == 1
    # ContentSuggestion fires because PAUSE_REVIEW maps to PAUSE
    # and we set a content_ref on the recommendation.
    assert result.content_suggestions_promoted == 1
    # Stats reflect promotion.
    assert pack.stats.total_suggested_tasks == 1
    assert pack.stats.channel_adjustments == 1
    assert pack.stats.content_suggestions == 1
    assert pack.stats.high_priority_tasks == 1


def test_promote_into_feedback_pack_no_content_ref_skips_content() -> None:
    """IMPROVE_AD_COPY without content_ref does not produce a
    ContentSuggestion (the suggestion needs a piece reference)."""
    pack = _empty_feedback_pack()
    bridge = _bridge_pack(recs=[_recommendation(
        kind=AdsRecommendationKind.IMPROVE_AD_COPY,
        content_ref=None,
        title="Improve copy",
    )])
    result = promote_into_feedback_pack(bridge, pack)
    assert result.recommendations_promoted == 1
    assert result.tasks_promoted == 1
    assert result.content_suggestions_promoted == 0


def test_promote_into_feedback_pack_marks_origin() -> None:
    pack = _empty_feedback_pack()
    bridge = _bridge_pack(recs=[_recommendation()])
    promote_into_feedback_pack(bridge, pack)
    task = pack.suggested_tasks[0]
    assert ADS_BRIDGE_ORIGIN_MARKER in task.evidence_refs
    assert any(
        e.startswith("ads_bridge:") for e in task.evidence_refs
    )
    assert any(
        e.startswith("ads_bridge_source:") for e in task.evidence_refs
    )
    assert task.channel == "google_ads"


def test_promote_into_feedback_pack_is_idempotent() -> None:
    pack = _empty_feedback_pack()
    bridge = _bridge_pack(
        recs=[_recommendation()],
        adjustments=[_adjustment()],
    )
    first = promote_into_feedback_pack(bridge, pack)
    second = promote_into_feedback_pack(bridge, pack)
    # First adds: 1 task + 1 content + 1 adjustment.
    assert first.tasks_promoted == 1
    assert first.duplicates_skipped == 0
    # Second adds: 0; everything is a duplicate.
    assert second.tasks_promoted == 0
    assert second.channel_adjustments_promoted == 0
    assert second.content_suggestions_promoted == 0
    # 1 task + 1 content + 1 adjustment = 3 duplicates skipped.
    assert second.duplicates_skipped == 3
    # Lists were not appended-to a second time.
    assert len(pack.suggested_tasks) == 1
    assert len(pack.channel_adjustments) == 1
    assert len(pack.content_suggestions) == 1


def test_promote_into_feedback_pack_pause_review_emits_pause_channel() -> None:
    pack = _empty_feedback_pack()
    bridge = _bridge_pack(adjustments=[_adjustment(
        kind=AdsAdjustmentKind.PAUSE_REVIEW,
    )])
    promote_into_feedback_pack(bridge, pack)
    assert pack.channel_adjustments[0].channel == "google_ads"
    assert pack.channel_adjustments[0].new_priority is ChannelPriority.PAUSE


def test_promote_into_feedback_pack_scale_emits_high() -> None:
    pack = _empty_feedback_pack()
    bridge = _bridge_pack(adjustments=[_adjustment(
        kind=AdsAdjustmentKind.SCALE_REVIEW,
    )])
    promote_into_feedback_pack(bridge, pack)
    assert pack.channel_adjustments[0].new_priority is ChannelPriority.HIGH


def test_promote_content_suggestion_kind_mapping() -> None:
    pack = _empty_feedback_pack()
    bridge = _bridge_pack(recs=[
        _recommendation(
            kind=AdsRecommendationKind.SCALE_OPPORTUNITY,
        ),
    ])
    promote_into_feedback_pack(bridge, pack)
    assert pack.content_suggestions[0].kind is ContentSuggestionKind.REPEAT


# ---------- execution task pack promotion ----------


def test_promote_into_execution_tasks_basic() -> None:
    pack = _empty_task_pack()
    bridge = _bridge_pack(recs=[_recommendation()])
    result = promote_into_execution_tasks(bridge, pack)
    assert result.tasks_promoted == 1
    assert len(pack.tasks) == 1
    task = pack.tasks[0]
    assert task.state is TaskState.TODO
    assert task.priority is TaskPriority.HIGH
    assert task.channel == "google_ads"
    assert ADS_BRIDGE_ORIGIN_MARKER in (task.notes or "")
    assert "ads_bridge_source:" in (task.notes or "")


def test_promote_into_execution_tasks_is_idempotent() -> None:
    pack = _empty_task_pack()
    bridge = _bridge_pack(recs=[_recommendation()])
    first = promote_into_execution_tasks(bridge, pack)
    second = promote_into_execution_tasks(bridge, pack)
    assert first.tasks_promoted == 1
    assert second.tasks_promoted == 0
    assert second.duplicates_skipped == 1
    assert len(pack.tasks) == 1


def test_promote_into_execution_tasks_category_mapping() -> None:
    pack = _empty_task_pack()
    bridge = _bridge_pack(recs=[
        _recommendation(kind=AdsRecommendationKind.IMPROVE_AD_COPY),
    ])
    promote_into_execution_tasks(bridge, pack)
    assert pack.tasks[0].category is TaskCategory.SOCIAL


# ---------- iteration plan promotion ----------


def test_promote_into_iteration_plan_basic() -> None:
    plan = _empty_iteration_plan()
    bridge = _bridge_pack(
        adjustments=[_adjustment()],
        tasks=[_bridge_task()],
    )
    result = promote_into_iteration_plan(bridge, plan)
    assert result.iteration_actions_promoted == 1
    assert result.tasks_promoted == 1
    assert len(plan.actions) == 1
    assert plan.actions[0].kind is IterationActionKind.PAUSE_PIECE
    assert plan.actions[0].channel == "google_ads"
    assert plan.suggested_tasks[0].channel == "google_ads"
    # Stats reflect promotion.
    assert plan.stats.total_actions == 1
    assert plan.stats.pauses == 1
    assert plan.stats.suggested_tasks == 1


def test_promote_into_iteration_plan_scale_becomes_channel_promote() -> None:
    plan = _empty_iteration_plan()
    bridge = _bridge_pack(adjustments=[_adjustment(
        kind=AdsAdjustmentKind.SCALE_REVIEW,
    )])
    promote_into_iteration_plan(bridge, plan)
    assert plan.actions[0].kind is IterationActionKind.CHANNEL_PROMOTE
    assert plan.stats.channel_adjustments == 1


def test_promote_into_iteration_plan_is_idempotent() -> None:
    plan = _empty_iteration_plan()
    bridge = _bridge_pack(
        adjustments=[_adjustment()],
        tasks=[_bridge_task()],
    )
    promote_into_iteration_plan(bridge, plan)
    second = promote_into_iteration_plan(bridge, plan)
    assert second.iteration_actions_promoted == 0
    assert second.tasks_promoted == 0
    assert second.duplicates_skipped == 2
    assert len(plan.actions) == 1
    assert len(plan.suggested_tasks) == 1


def test_promote_into_iteration_plan_marks_origin() -> None:
    plan = _empty_iteration_plan()
    bridge = _bridge_pack(adjustments=[_adjustment()])
    promote_into_iteration_plan(bridge, plan)
    refs = plan.actions[0].evidence_refs
    assert ADS_BRIDGE_ORIGIN_MARKER in refs
    assert any(r.startswith("ads_bridge:") for r in refs)


# ---------- AdsPromoter class ----------


def test_ads_promoter_aggregates_calls() -> None:
    bridge = _bridge_pack(
        recs=[_recommendation()],
        adjustments=[_adjustment()],
        tasks=[_bridge_task()],
    )
    promoter = AdsPromoter(bridge)
    assert promoter.bridge_pack_id == bridge.pack_id

    fb = _empty_feedback_pack()
    et = _empty_task_pack()
    it = _empty_iteration_plan()
    promoter.into_feedback_pack(fb)
    promoter.into_execution_tasks(et)
    promoter.into_iteration_plan(it)
    assert len(fb.suggested_tasks) == 1
    assert len(et.tasks) == 1
    assert len(it.actions) == 1
    assert len(it.suggested_tasks) == 1


# ---------- byte-compat / no-op when not invoked ----------


def test_promoter_does_not_mutate_bridge_pack() -> None:
    bridge = _bridge_pack(
        recs=[_recommendation()],
        adjustments=[_adjustment()],
        tasks=[_bridge_task()],
    )
    bridge_before = bridge.model_dump(mode="json")
    pack = _empty_feedback_pack()
    promote_into_feedback_pack(bridge, pack)
    bridge_after = bridge.model_dump(mode="json")
    assert bridge_before == bridge_after


def test_no_google_ads_sdk_reference_in_promoter_source() -> None:
    """Pin: the promoter module must not reference the Google Ads SDK
    or any mutation method."""
    import pathlib

    root = (
        pathlib.Path(__file__).resolve().parents[2]
        / "core" / "ads_promoter"
    )
    forbidden = (
        "google.ads", "googleads", "GoogleAdsClient",
        "mutate_campaigns", "mutate_ad_groups", "mutate_ads",
        "CampaignOperation", "AdGroupOperation",
    )
    for py in root.glob("*.py"):
        text = py.read_text(encoding="utf-8")
        for needle in forbidden:
            assert needle not in text, f"{py.name} references {needle!r}"
