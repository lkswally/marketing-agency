"""Tests for core.intelligence.models (MKT-10X Pydantic contracts)."""

import pytest
from pydantic import ValidationError

from core.intelligence.models import (
    INTELLIGENCE_CONTRACT_VERSION,
    UTM_CONTRACT_VERSION,
    CompetitorSignal,
    ContentGap,
    MarketIntelligencePack,
    TrackingRecommendation,
    TrendSignal,
    UTMPlan,
    UTMTaggedLink,
)

# ---------------------------------------------------------------------------
# TrendSignal
# ---------------------------------------------------------------------------


class TestTrendSignal:
    def test_valid_rising(self):
        s = TrendSignal(keyword="AI marketing", relative_interest=80.0, direction="rising")
        assert s.direction == "rising"
        assert s.source == "dry-run"
        assert s.signal_id  # auto-generated

    def test_direction_validation(self):
        with pytest.raises(ValidationError):
            TrendSignal(keyword="x", relative_interest=50.0, direction="unknown")

    def test_interest_bounds(self):
        with pytest.raises(ValidationError):
            TrendSignal(keyword="x", relative_interest=101.0, direction="stable")
        with pytest.raises(ValidationError):
            TrendSignal(keyword="x", relative_interest=-1.0, direction="stable")

    def test_immutable(self):
        s = TrendSignal(keyword="x", relative_interest=50.0, direction="stable")
        with pytest.raises((TypeError, ValidationError)):
            s.keyword = "y"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# CompetitorSignal
# ---------------------------------------------------------------------------


class TestCompetitorSignal:
    def test_valid(self):
        cs = CompetitorSignal(
            competitor_name="Acme",
            observation_type="new_content",
            summary="Published 5 blog posts.",
        )
        assert cs.confidence == "low"
        assert cs.source == "dry-run"

    def test_invalid_observation_type(self):
        with pytest.raises(ValidationError):
            CompetitorSignal(
                competitor_name="X",
                observation_type="hacked",
                summary="test",
            )

    def test_confidence_values(self):
        for v in ("high", "medium", "low"):
            cs = CompetitorSignal(
                competitor_name="X",
                observation_type="other",
                summary="test",
                confidence=v,
            )
            assert cs.confidence == v

        with pytest.raises(ValidationError):
            CompetitorSignal(
                competitor_name="X",
                observation_type="other",
                summary="test",
                confidence="extreme",
            )


# ---------------------------------------------------------------------------
# ContentGap
# ---------------------------------------------------------------------------


class TestContentGap:
    def test_valid(self):
        g = ContentGap(topic="AI content strategy", gap_score=55.0)
        assert g.gap_id
        assert g.gap_score == 55.0

    def test_gap_score_bounds(self):
        with pytest.raises(ValidationError):
            ContentGap(topic="x", gap_score=101.0)
        with pytest.raises(ValidationError):
            ContentGap(topic="x", gap_score=-0.1)

    def test_defaults(self):
        g = ContentGap(topic="x")
        assert g.gap_score == 0.0
        assert g.keywords == []
        assert g.competitor_coverage == []


# ---------------------------------------------------------------------------
# MarketIntelligencePack
# ---------------------------------------------------------------------------


class TestMarketIntelligencePack:
    def test_empty_pack(self):
        pack = MarketIntelligencePack(client_slug="test-client")
        assert pack.contract_version == INTELLIGENCE_CONTRACT_VERSION
        assert pack.trend_signals == []
        assert pack.competitor_signals == []
        assert pack.content_gaps == []
        assert pack.pack_id

    def test_pack_with_signals(self):
        ts = TrendSignal(keyword="seo", relative_interest=60.0, direction="rising")
        cs = CompetitorSignal(
            competitor_name="Rival", observation_type="new_content", summary="New posts"
        )
        cg = ContentGap(topic="video marketing", gap_score=40.0)
        pack = MarketIntelligencePack(
            client_slug="acme-corp",
            trend_signals=[ts],
            competitor_signals=[cs],
            content_gaps=[cg],
        )
        assert len(pack.trend_signals) == 1
        assert len(pack.competitor_signals) == 1
        assert len(pack.content_gaps) == 1

    def test_immutable(self):
        pack = MarketIntelligencePack(client_slug="acme-corp")
        with pytest.raises((TypeError, ValidationError)):
            pack.client_slug = "other"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# UTMTaggedLink
# ---------------------------------------------------------------------------


class TestUTMTaggedLink:
    def test_valid(self):
        link = UTMTaggedLink(
            piece_title="Instagram Carousel",
            channel="instagram",
            base_url="https://acme.com",
            utm_source="instagram",
            utm_medium="social",
            utm_campaign="acme-2024-06",
            utm_content="instagram-carousel",
            final_url="https://acme.com?utm_source=instagram&utm_medium=social",
        )
        assert link.link_id
        assert link.utm_term is None

    def test_with_term(self):
        link = UTMTaggedLink(
            piece_title="Google Ad",
            channel="google_ads",
            base_url="https://acme.com",
            utm_source="google",
            utm_medium="cpc",
            utm_campaign="acme-2024-06",
            utm_content="search-ad",
            utm_term="marketing-software",
            final_url="https://acme.com?utm_source=google&utm_medium=cpc&utm_term=marketing-software",
        )
        assert link.utm_term == "marketing-software"


# ---------------------------------------------------------------------------
# TrackingRecommendation
# ---------------------------------------------------------------------------


class TestTrackingRecommendation:
    def test_valid(self):
        rec = TrackingRecommendation(
            priority="high",
            description="Configure GA4 UTM dimensions.",
            affected_channels=["instagram", "linkedin"],
            action="configure_ga4",
        )
        assert rec.recommendation_id

    def test_invalid_priority(self):
        with pytest.raises(ValidationError):
            TrackingRecommendation(
                priority="critical",
                description="x",
                action="x",
            )


# ---------------------------------------------------------------------------
# UTMPlan
# ---------------------------------------------------------------------------


class TestUTMPlan:
    def test_empty_plan(self):
        plan = UTMPlan(
            client_slug="acme-corp",
            campaign_name="Acme Summer 2024",
            period="2024-06",
        )
        assert plan.contract_version == UTM_CONTRACT_VERSION
        assert plan.total_links == 0
        assert plan.tagged_links == []
        assert plan.plan_id

    def test_plan_with_links(self):
        link = UTMTaggedLink(
            piece_title="Email Welcome",
            channel="email",
            base_url="https://acme.com",
            utm_source="email",
            utm_medium="email",
            utm_campaign="acme-2024-06",
            utm_content="email-welcome",
            final_url="https://acme.com?utm_source=email&utm_medium=email",
        )
        plan = UTMPlan(
            client_slug="acme-corp",
            campaign_name="Acme Summer",
            period="2024-06",
            tagged_links=[link],
            total_links=1,
            channels_covered=["email"],
        )
        assert len(plan.tagged_links) == 1
        assert "email" in plan.channels_covered
