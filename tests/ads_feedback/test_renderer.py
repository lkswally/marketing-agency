"""Tests for the ads feedback bridge Markdown renderer."""

from __future__ import annotations

from datetime import UTC, datetime

from core.ads_feedback import (
    AdsAdjustmentKind,
    AdsBridgeStats,
    AdsCampaignAdjustment,
    AdsFeedbackBridgePack,
    AdsKeywordProposal,
    AdsRecommendation,
    AdsRecommendationKind,
    AdsRecommendationPriority,
    AdsSuggestedTask,
    render_markdown_ads_bridge,
)


def _make_pack(**overrides) -> AdsFeedbackBridgePack:
    recs = overrides.pop("recommendations", [])
    adjs = overrides.pop("campaign_adjustments", [])
    kps = overrides.pop("keyword_proposals", [])
    tasks = overrides.pop("suggested_tasks", [])
    stats = AdsBridgeStats(
        total_recommendations=len(recs),
        total_campaign_adjustments=len(adjs),
        total_keyword_proposals=len(kps),
        total_suggested_tasks=len(tasks),
        insights_consumed=overrides.pop("insights_consumed", 0),
    )
    return AdsFeedbackBridgePack(
        client_slug="acme",
        insight_pack_id="insight-1",
        insight_pack_contract_version="google-ads-insight-pack.v1",
        recommendations=recs,
        campaign_adjustments=adjs,
        keyword_proposals=kps,
        suggested_tasks=tasks,
        executive_summary=overrides.pop("executive_summary", "Test summary."),
        stats=stats,
        created_at=datetime(2026, 6, 4, tzinfo=UTC),
        rule_set_id="ads-feedback-bridge.v1",
    )


def test_render_empty_pack() -> None:
    md = render_markdown_ads_bridge(_make_pack(executive_summary="Empty."))
    assert "Ads Insights → Feedback Bridge" in md
    assert "no recommendations" in md
    assert "no campaign-level adjustments" in md
    assert "Read-only" in md


def test_render_includes_recommendation() -> None:
    rec = AdsRecommendation(
        kind=AdsRecommendationKind.PAUSE_REVIEW,
        priority=AdsRecommendationPriority.HIGH,
        title="Pause review on Brand / Wasteful",
        rationale="Spent $120 with 0 conversions.",
        suggested_action="Review for pause.",
        campaign_id="42", ad_group_id="100",
        content_ref="campaign:42::ad_group:100",
        dimension="Brand / Wasteful",
    )
    md = render_markdown_ads_bridge(_make_pack(recommendations=[rec]))
    assert "[HIGH] Pause review on Brand / Wasteful" in md
    assert "pause_review" in md
    assert "campaign:42::ad_group:100" in md


def test_render_keyword_proposals() -> None:
    kp = AdsKeywordProposal(
        keyword="free trial",
        rationale="Wasted spend, no conversions.",
    )
    md = render_markdown_ads_bridge(_make_pack(keyword_proposals=[kp]))
    assert "free trial" in md
    assert "operator applies manually" in md


def test_render_campaign_adjustments() -> None:
    adj = AdsCampaignAdjustment(
        campaign_id="42",
        dimension="Brand",
        kind=AdsAdjustmentKind.PAUSE_REVIEW,
        rationale="Insight flagged pause.",
        suggested_next_step="Manually pause if review confirms.",
    )
    md = render_markdown_ads_bridge(_make_pack(campaign_adjustments=[adj]))
    assert "[pause_review]" in md
    assert "Brand" in md


def test_render_tasks() -> None:
    t = AdsSuggestedTask(
        title="Review pause candidate",
        category="optimization",
        priority=AdsRecommendationPriority.HIGH,
        rationale="r",
    )
    md = render_markdown_ads_bridge(_make_pack(suggested_tasks=[t]))
    assert "[HIGH]" in md
    assert "(optimization)" in md


def test_renderer_is_pure() -> None:
    pack = _make_pack()
    assert render_markdown_ads_bridge(pack) == render_markdown_ads_bridge(pack)
