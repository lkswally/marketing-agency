"""Tests for the Google Ads insight pack models."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from core.ads_analysis.models import (
    GOOGLE_ADS_INSIGHT_PACK_KIND,
    GOOGLE_ADS_INSIGHT_PACK_VERSION,
    AdGroupProfile,
    AdsInsightAction,
    AdsInsightKind,
    AdsInsightSeverity,
    AdsInsightStats,
    GoogleAdsInsight,
    GoogleAdsInsightPack,
)


def _now() -> datetime:
    return datetime(2026, 6, 4, tzinfo=UTC)


def _base_pack(**overrides) -> dict:
    base = dict(
        client_slug="acme",
        snapshot_id="snap-1",
        snapshot_contract_version="metrics-snapshot.v1",
        profiles=[],
        insights=[],
        stats=AdsInsightStats(
            total_insights=0, by_severity={}, by_kind={}, by_action={},
            ad_groups_profiled=0, rows_analyzed=0,
        ),
        created_at=_now(),
    )
    base.update(overrides)
    return base


def test_kind_constants() -> None:
    assert GOOGLE_ADS_INSIGHT_PACK_KIND == "google_ads_insight_pack"
    assert GOOGLE_ADS_INSIGHT_PACK_VERSION == "google-ads-insight-pack.v1"


def test_pack_round_trip() -> None:
    pack = GoogleAdsInsightPack(**_base_pack())
    raw = pack.model_dump(mode="json")
    again = GoogleAdsInsightPack.model_validate(raw)
    assert again.pack_id == pack.pack_id
    assert again.contract_version == GOOGLE_ADS_INSIGHT_PACK_VERSION


def test_pack_rejects_naive_datetime() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        GoogleAdsInsightPack(**_base_pack(created_at=datetime(2026, 6, 4)))


def test_pack_rejects_invalid_slug() -> None:
    with pytest.raises(ValueError):
        GoogleAdsInsightPack(**_base_pack(client_slug="UPPER"))


def test_insight_kind_enum_values_complete() -> None:
    expected = {
        "high_spend_zero_conv", "high_spend_low_conv", "low_ctr_high_impr",
        "good_ctr_low_conv_rate", "high_cpa_outlier", "scale_candidate",
        "review_campaign", "review_ad_group", "review_landing",
        "pause_candidate", "improve_ad_copy", "budget_review",
    }
    assert {k.value for k in AdsInsightKind} == expected


def test_action_enum_values_complete() -> None:
    expected = {
        "review_campaign", "review_ad_group", "review_landing",
        "pause_candidate", "scale_candidate", "improve_ad_copy",
        "budget_review",
    }
    assert {a.value for a in AdsInsightAction} == expected


def test_profile_recomputed_rates_within_bounds() -> None:
    p = AdGroupProfile(
        content_ref="campaign:1::ad_group:100",
        sample_rows=4,
        impressions=1000, clicks=50, cost=25.0,
        conversions=3, conversions_value=150.0,
        ctr=0.05, cpc=0.5, cpa=8.33, conversion_rate=0.06,
    )
    raw = p.model_dump(mode="json")
    again = AdGroupProfile.model_validate(raw)
    assert again.cpa == 8.33


def test_insight_no_credential_fields() -> None:
    forbidden = {"token", "api_key", "secret", "credential", "url",
                 "customer_id"}
    fields = set(GoogleAdsInsight.model_fields.keys())
    assert fields.isdisjoint(forbidden), fields & forbidden


def test_pack_no_credential_fields() -> None:
    forbidden = {"token", "api_key", "secret", "credential", "url",
                 "customer_id"}
    fields = set(GoogleAdsInsightPack.model_fields.keys())
    assert fields.isdisjoint(forbidden), fields & forbidden


def test_insight_round_trip() -> None:
    i = GoogleAdsInsight(
        kind=AdsInsightKind.HIGH_SPEND_ZERO_CONV,
        severity=AdsInsightSeverity.HIGH,
        suggested_action=AdsInsightAction.PAUSE_CANDIDATE,
        title="Test",
        rationale="Reason",
        evidence={"cost": 100.0, "conversions": 0.0},
        thresholds_used={"min_cost": 50.0},
    )
    raw = i.model_dump(mode="json")
    again = GoogleAdsInsight.model_validate(raw)
    assert again.kind is AdsInsightKind.HIGH_SPEND_ZERO_CONV
    assert again.evidence["cost"] == 100.0
