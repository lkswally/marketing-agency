"""Tests for the ads feedback bridge models."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from core.ads_feedback.models import (
    ADS_FEEDBACK_BRIDGE_PACK_KIND,
    ADS_FEEDBACK_BRIDGE_PACK_VERSION,
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


def _now() -> datetime:
    return datetime(2026, 6, 4, tzinfo=UTC)


def _base_pack(**overrides) -> dict:
    base = dict(
        client_slug="acme",
        insight_pack_id="insight-1",
        insight_pack_contract_version="google-ads-insight-pack.v1",
        stats=AdsBridgeStats(
            total_recommendations=0,
            total_campaign_adjustments=0,
            total_keyword_proposals=0,
            total_suggested_tasks=0,
            insights_consumed=0,
        ),
        created_at=_now(),
    )
    base.update(overrides)
    return base


def test_kind_constants() -> None:
    assert ADS_FEEDBACK_BRIDGE_PACK_KIND == "ads_feedback_bridge_pack"
    assert ADS_FEEDBACK_BRIDGE_PACK_VERSION == "ads-feedback-bridge-pack.v1"


def test_pack_round_trip() -> None:
    pack = AdsFeedbackBridgePack(**_base_pack())
    raw = pack.model_dump(mode="json")
    again = AdsFeedbackBridgePack.model_validate(raw)
    assert again.pack_id == pack.pack_id
    assert again.contract_version == ADS_FEEDBACK_BRIDGE_PACK_VERSION


def test_pack_rejects_naive_datetime() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        AdsFeedbackBridgePack(**_base_pack(created_at=datetime(2026, 6, 4)))


def test_pack_rejects_invalid_slug() -> None:
    with pytest.raises(ValueError):
        AdsFeedbackBridgePack(**_base_pack(client_slug="UPPER"))


def test_recommendation_kind_enum_complete() -> None:
    expected = {
        "pause_review", "review_campaign", "review_ad_group",
        "review_landing", "scale_opportunity", "improve_ad_copy",
        "budget_review", "negative_keyword_proposal",
    }
    assert {k.value for k in AdsRecommendationKind} == expected


def test_adjustment_kind_enum_complete() -> None:
    expected = {
        "pause_review", "scale_review", "reallocate_review",
        "optimize_review",
    }
    assert {k.value for k in AdsAdjustmentKind} == expected


def test_keyword_proposal_proposed_as_locked_to_negative() -> None:
    kp = AdsKeywordProposal(keyword="cheap", rationale="example")
    assert kp.proposed_as == "negative_keyword"
    # ``Literal["negative_keyword"]`` should reject anything else.
    with pytest.raises(ValueError):
        AdsKeywordProposal(
            keyword="cheap", proposed_as="positive_keyword",  # type: ignore[arg-type]
            rationale="x",
        )


def test_suggested_task_default_channel_is_google_ads() -> None:
    t = AdsSuggestedTask(
        title="Review",
        category="optimization",
        priority=AdsRecommendationPriority.HIGH,
        rationale="r",
    )
    assert t.channel == "google_ads"


def test_recommendation_round_trip() -> None:
    r = AdsRecommendation(
        kind=AdsRecommendationKind.PAUSE_REVIEW,
        priority=AdsRecommendationPriority.HIGH,
        title="t",
        rationale="r",
        suggested_action="review pause",
        campaign_id="42",
        ad_group_id="100",
    )
    raw = r.model_dump(mode="json")
    again = AdsRecommendation.model_validate(raw)
    assert again.kind is AdsRecommendationKind.PAUSE_REVIEW
    assert again.campaign_id == "42"


def test_adjustment_round_trip() -> None:
    a = AdsCampaignAdjustment(
        campaign_id="42",
        kind=AdsAdjustmentKind.PAUSE_REVIEW,
        rationale="r",
        suggested_next_step="review",
    )
    raw = a.model_dump(mode="json")
    AdsCampaignAdjustment.model_validate(raw)


def test_no_credential_fields_on_pack() -> None:
    forbidden = {
        "token", "api_key", "secret", "credential", "credentials",
        "customer_id", "url", "webhook_url",
    }
    declared = set(AdsFeedbackBridgePack.model_fields.keys())
    assert declared.isdisjoint(forbidden), declared & forbidden


def test_no_credential_fields_on_recommendation() -> None:
    forbidden = {
        "token", "api_key", "secret", "credential", "customer_id",
    }
    declared = set(AdsRecommendation.model_fields.keys())
    assert declared.isdisjoint(forbidden), declared & forbidden


def test_extra_fields_forbidden_on_pack() -> None:
    with pytest.raises(ValueError):
        AdsFeedbackBridgePack(**_base_pack(secret_token="nope"))
