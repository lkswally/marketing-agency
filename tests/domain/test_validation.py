"""Validation tests — each model rejects malformed input."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from pydantic import ValidationError

from core.domain import (
    Audience,
    Brand,
    Campaign,
    Channel,
    ChannelType,
    Claim,
    ClaimSeverity,
    ClaimVerdict,
    Client,
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
    Report,
    ReportType,
    SubjectType,
    validate_slug,
)

# ---------- Slug validator ----------

@pytest.mark.parametrize(
    "bad_slug",
    ["", "Bad", "with space", "with_underscore", "trailing-", "-leading", "double--dash", "Caps"],
)
def test_validate_slug_rejects_bad_values(bad_slug: str) -> None:
    with pytest.raises(ValueError):
        validate_slug(bad_slug)


@pytest.mark.parametrize("good_slug", ["a", "demo", "demo-co", "acme-corp", "client-42"])
def test_validate_slug_accepts_good_values(good_slug: str) -> None:
    assert validate_slug(good_slug) == good_slug


def test_validate_slug_rejects_reserved() -> None:
    with pytest.raises(ValueError):
        validate_slug("_shared")


# ---------- Client ----------

def test_client_rejects_bad_slug() -> None:
    with pytest.raises(ValidationError):
        Client(slug="Bad Slug", name="X")


def test_client_rejects_extra_field() -> None:
    with pytest.raises(ValidationError):
        Client(slug="demo-co", name="X", unknown="oops")


def test_client_rejects_invalid_email() -> None:
    with pytest.raises(ValidationError):
        Client(slug="demo-co", name="X", primary_contact_email="not-an-email")


# ---------- Required fields ----------

def test_brand_requires_client_slug_and_name() -> None:
    with pytest.raises(ValidationError):
        Brand()  # type: ignore[call-arg]


def test_brief_requires_objective() -> None:
    with pytest.raises(ValidationError):
        MarketingBrief(client_slug="demo-co", title="X")  # type: ignore[call-arg]


def test_offer_rejects_negative_price() -> None:
    with pytest.raises(ValidationError):
        Offer(client_slug="demo-co", name="X", offer_type=OfferType.PRODUCT, price_amount=-1)


# ---------- Enums ----------

def test_channel_rejects_unknown_channel_type() -> None:
    with pytest.raises(ValidationError):
        Channel(client_slug="demo-co", channel_type="snail-mail", label="X")  # type: ignore[arg-type]


def test_metric_rejects_unknown_source() -> None:
    with pytest.raises(ValidationError):
        Metric(
            client_slug="demo-co",
            name="sessions",
            value=1.0,
            unit=MetricUnit.COUNT,
            source="ouija-board",  # type: ignore[arg-type]
            category=MetricCategory.ACQUISITION,
            measured_at=datetime(2026, 1, 1, tzinfo=UTC),
            subject_type=SubjectType.CAMPAIGN,
            subject_id="abc",
        )


def test_claim_rejects_unknown_severity() -> None:
    with pytest.raises(ValidationError):
        Claim(text="x", severity="nuclear", verdict=ClaimVerdict.UNVERIFIED)  # type: ignore[arg-type]


# ---------- Timezone awareness ----------

def test_brief_rejects_naive_deadline() -> None:
    with pytest.raises(ValidationError):
        MarketingBrief(
            client_slug="demo-co",
            title="X",
            objective="Y",
            deadline=datetime(2026, 1, 1),  # naive
        )


def test_metric_rejects_naive_measured_at() -> None:
    with pytest.raises(ValidationError):
        Metric(
            client_slug="demo-co",
            name="sessions",
            value=1.0,
            unit=MetricUnit.COUNT,
            source=MetricSource.GA4,
            category=MetricCategory.ACQUISITION,
            measured_at=datetime(2026, 1, 1),  # naive
            subject_type=SubjectType.CAMPAIGN,
            subject_id="abc",
        )


def test_evidence_rejects_naive_retrieved_at() -> None:
    with pytest.raises(ValidationError):
        Evidence(
            source_type=EvidenceSourceType.URL,
            location="https://x",
            retrieved_at=datetime(2026, 1, 1),  # naive
        )


# ---------- Numeric ranges ----------

def test_evidence_trust_level_bounds() -> None:
    with pytest.raises(ValidationError):
        Evidence(source_type=EvidenceSourceType.URL, location="https://x", trust_level=1.5)
    with pytest.raises(ValidationError):
        Evidence(source_type=EvidenceSourceType.URL, location="https://x", trust_level=-0.1)


def test_metric_confidence_bounds() -> None:
    base = dict(
        client_slug="demo-co",
        name="sessions",
        value=1.0,
        unit=MetricUnit.COUNT,
        source=MetricSource.GA4,
        category=MetricCategory.ACQUISITION,
        measured_at=datetime(2026, 1, 1, tzinfo=UTC),
        subject_type=SubjectType.CAMPAIGN,
        subject_id="abc",
    )
    with pytest.raises(ValidationError):
        Metric(**base, confidence=1.1)  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        Metric(**base, confidence=-0.1)  # type: ignore[arg-type]


def test_backlog_ice_axis_bounds() -> None:
    with pytest.raises(ValidationError):
        GrowthBacklogItem(client_slug="demo-co", hypothesis="x", impact=11, confidence=5, ease=5)
    with pytest.raises(ValidationError):
        GrowthBacklogItem(client_slug="demo-co", hypothesis="x", impact=0, confidence=5, ease=5)


def test_audience_size_non_negative() -> None:
    with pytest.raises(ValidationError):
        Audience(client_slug="demo-co", label="X", estimated_size=-1)


# ---------- Cross-field model validators ----------

def test_campaign_end_before_start_rejected() -> None:
    with pytest.raises(ValidationError):
        Campaign(
            client_slug="demo-co",
            name="X",
            goal="Y",
            start_at=datetime(2026, 9, 1, tzinfo=UTC),
            end_at=datetime(2026, 8, 1, tzinfo=UTC),
        )


def test_report_period_end_before_start_rejected() -> None:
    with pytest.raises(ValidationError):
        Report(
            client_slug="demo-co",
            report_type=ReportType.MONTHLY,
            title="X",
            period_start=date(2026, 7, 31),
            period_end=date(2026, 7, 1),
        )


# ---------- Persona ----------

def test_persona_requires_audience_id() -> None:
    with pytest.raises(ValidationError):
        Persona(audience_id="", archetype_name="X")


# ---------- DigitalFootprintSnapshot ----------

def test_footprint_rejects_bad_slug() -> None:
    with pytest.raises(ValidationError):
        DigitalFootprintSnapshot(
            client_slug="Bad",
            subject_type=SubjectType.COMPETITOR,
            subject_id="abc",
            snapshot_date=date(2026, 7, 1),
        )


# ---------- Channel options ----------

def test_channel_accepts_all_known_types() -> None:
    for ct in ChannelType:
        Channel(client_slug="demo-co", channel_type=ct, label=ct.value)


# ---------- Claim severity exhaustive ----------

def test_claim_severities_round_trip() -> None:
    for sev in ClaimSeverity:
        c = Claim(text="x", severity=sev, verdict=ClaimVerdict.UNVERIFIED)
        assert c.severity is sev
