"""Fixtures for a deterministic demo client used across domain tests."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from core.domain import (
    Asset,
    AssetType,
    Audience,
    Brand,
    BrandVoice,
    Campaign,
    CampaignStatus,
    Channel,
    ChannelType,
    Claim,
    ClaimSeverity,
    ClaimVerdict,
    Client,
    Competitor,
    DigitalFootprintSnapshot,
    Evidence,
    EvidenceSourceType,
    GrowthBacklogItem,
    MarketingBrief,
    Metric,
    MetricCategory,
    MetricSource,
    MetricUnit,
    Offer,
    OfferType,
    Persona,
    Positioning,
    Report,
    ReportType,
    SubjectType,
)

DEMO_SLUG = "demo-co"


@pytest.fixture
def demo_client() -> Client:
    return Client(
        slug=DEMO_SLUG,
        name="Demo Co.",
        industry="SaaS",
        locale="en-US",
        primary_contact_email="ops@demo.co",
    )


@pytest.fixture
def demo_brand() -> Brand:
    return Brand(
        client_slug=DEMO_SLUG,
        name="Demo",
        mission="Help small teams ship marketing faster.",
        voice=BrandVoice(
            tone_words=["clear", "warm", "irreverent"],
            lexicon_do=["we", "teams", "ship"],
            lexicon_dont=["leverage", "synergy"],
            banned_words=["disruptive"],
        ),
        claim_style="Specific, sourced, never superlative without proof.",
    )


@pytest.fixture
def demo_audience() -> Audience:
    return Audience(
        client_slug=DEMO_SLUG,
        label="Founders of bootstrapped SaaS",
        description="Solo founders or small teams running B2B SaaS without VC funding.",
        estimated_size=120_000,
        demographics={"age_range": "28-45", "geo": "global"},
        psychographics={"motivation": "independence", "fear": "burnout"},
        preferred_channels=[ChannelType.NEWSLETTER, ChannelType.X, ChannelType.PODCAST],
    )


@pytest.fixture
def demo_persona(demo_audience: Audience) -> Persona:
    return Persona(
        audience_id=demo_audience.id,
        archetype_name="Solo Founder Sam",
        age_range="32-38",
        occupation="Bootstrapped SaaS founder",
        motivations=["control over roadmap", "sustainable income"],
        pains=["wears every hat", "no time for marketing"],
        jobs_to_be_done=["acquire customers without VC budget"],
    )


@pytest.fixture
def demo_brief() -> MarketingBrief:
    return MarketingBrief(
        client_slug=DEMO_SLUG,
        title="Q3 evergreen lead gen",
        objective="Generate 200 qualified trials/month via SEO + newsletter cross-promo.",
        deliverables=["10 SEO articles", "4 newsletter swaps", "1 lead magnet"],
        constraints=["No paid ads", "Founder voice"],
    )


@pytest.fixture
def demo_competitor() -> Competitor:
    return Competitor(
        client_slug=DEMO_SLUG,
        name="Acme Marketing Suite",
        url="https://acme.example",
        positioning_summary="All-in-one marketing suite for enterprise.",
        strengths=["brand recognition", "deep integrations"],
        weaknesses=["expensive", "slow to ship"],
    )


@pytest.fixture
def demo_offer() -> Offer:
    return Offer(
        client_slug=DEMO_SLUG,
        name="Demo Pro (monthly)",
        offer_type=OfferType.SUBSCRIPTION,
        description="Full access to Demo for one team.",
        value_props=["one-day setup", "no contracts"],
        price_model="monthly_recurring",
        price_amount=49.0,
        price_currency="USD",
    )


@pytest.fixture
def demo_positioning() -> Positioning:
    return Positioning(
        client_slug=DEMO_SLUG,
        category="marketing automation",
        alt_to=["Acme Marketing Suite", "Big SaaS"],
        differentiators=["built for solo founders", "no setup engineer needed"],
        proof_points=["1-day onboarding", "Used by 300+ bootstrapped teams"],
        one_liner="Marketing automation for solo founders who refuse to hire an ops team.",
    )


@pytest.fixture
def demo_channel() -> Channel:
    return Channel(
        client_slug=DEMO_SLUG,
        channel_type=ChannelType.NEWSLETTER,
        handle="demo-weekly",
        url="https://demo.co/newsletter",
        label="Demo Weekly Newsletter",
        config={"esp": "resend", "list_id": "placeholder"},
    )


@pytest.fixture
def demo_asset() -> Asset:
    return Asset(
        client_slug=DEMO_SLUG,
        asset_type=AssetType.COPY,
        label="Hero headline v1",
        body_text="Marketing automation that respects your time.",
        tags=["hero", "homepage"],
    )


@pytest.fixture
def demo_evidence() -> Evidence:
    return Evidence(
        source_type=EvidenceSourceType.URL,
        location="https://demo.co/case-studies/founder-x",
        excerpt="Founder X shipped 4 campaigns in their first week.",
        retrieved_at=datetime(2026, 5, 1, 12, 0, tzinfo=UTC),
        trust_level=0.9,
        author="internal case study",
    )


@pytest.fixture
def demo_claim(demo_evidence: Evidence) -> Claim:
    return Claim(
        text="Customers ship marketing 3x faster after switching.",
        severity=ClaimSeverity.RISKY,
        verdict=ClaimVerdict.PARTIAL,
        evidence_ids=[demo_evidence.id],
        rationale="Supported by one internal case study; needs broader sample.",
    )


@pytest.fixture
def demo_campaign(demo_brief: MarketingBrief, demo_audience: Audience, demo_channel: Channel) -> Campaign:
    return Campaign(
        client_slug=DEMO_SLUG,
        name="Q3 evergreen launch",
        goal="200 qualified trials/month",
        status=CampaignStatus.PLANNED,
        brief_id=demo_brief.id,
        audience_ids=[demo_audience.id],
        channel_ids=[demo_channel.id],
        start_at=datetime(2026, 7, 1, tzinfo=UTC),
        end_at=datetime(2026, 9, 30, tzinfo=UTC),
        budget_amount=5000.0,
        budget_currency="USD",
        kpis=["trials", "trial_to_paid_rate"],
    )


@pytest.fixture
def demo_metric(demo_campaign: Campaign) -> Metric:
    return Metric(
        client_slug=DEMO_SLUG,
        name="sessions",
        value=12_345.0,
        unit=MetricUnit.COUNT,
        source=MetricSource.GA4,
        category=MetricCategory.ACQUISITION,
        measured_at=datetime(2026, 7, 15, 0, 0, tzinfo=UTC),
        subject_type=SubjectType.CAMPAIGN,
        subject_id=demo_campaign.id,
        dimensions={"device": "desktop", "country": "AR"},
        provider_ref="ga4:property/123456",
        confidence=0.95,
    )


@pytest.fixture
def demo_footprint(demo_competitor: Competitor, demo_metric: Metric) -> DigitalFootprintSnapshot:
    return DigitalFootprintSnapshot(
        client_slug=DEMO_SLUG,
        subject_type=SubjectType.COMPETITOR,
        subject_id=demo_competitor.id,
        snapshot_date=date(2026, 7, 1),
        label="Acme competitor public surface — Jul 2026",
        metric_ids=[demo_metric.id],
        coverage={"social": "partial", "seo": "estimate"},
    )


@pytest.fixture
def demo_backlog_item() -> GrowthBacklogItem:
    return GrowthBacklogItem(
        client_slug=DEMO_SLUG,
        hypothesis="Adding a free template gallery will lift signups 20%.",
        impact=8,
        confidence=6,
        ease=7,
    )


@pytest.fixture
def demo_report(demo_metric: Metric) -> Report:
    return Report(
        client_slug=DEMO_SLUG,
        report_type=ReportType.MONTHLY,
        title="July 2026 — Acquisition recap",
        period_start=date(2026, 7, 1),
        period_end=date(2026, 7, 31),
        metric_ids=[demo_metric.id],
        narrative="Acquisition grew driven by newsletter swaps.",
        highlights=["Sessions +20% MoM"],
        next_steps=["Double down on swap partners with >5k subs"],
    )
