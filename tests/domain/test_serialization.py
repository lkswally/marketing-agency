"""Round-trip serialization tests for every domain entity.

For each entity: model -> JSON -> model must yield an equivalent instance.
Also asserts that ``model_json_schema()`` is generable (i.e. the model is
JSON-schema-compatible without runtime introspection errors).
"""

from __future__ import annotations

import json

import pytest

from core.domain import (
    Asset,
    Audience,
    Brand,
    Campaign,
    Channel,
    Claim,
    Client,
    Competitor,
    DigitalFootprintSnapshot,
    DomainModel,
    Evidence,
    GrowthBacklogItem,
    MarketingBrief,
    Metric,
    Offer,
    Persona,
    Positioning,
    Report,
)


def _round_trip(instance: DomainModel) -> DomainModel:
    cls = type(instance)
    payload = instance.to_json()
    # Payload must be valid JSON text.
    json.loads(payload)
    return cls.from_json(payload)


@pytest.mark.parametrize(
    "fixture_name",
    [
        "demo_client",
        "demo_brand",
        "demo_audience",
        "demo_persona",
        "demo_brief",
        "demo_competitor",
        "demo_offer",
        "demo_positioning",
        "demo_channel",
        "demo_asset",
        "demo_evidence",
        "demo_claim",
        "demo_campaign",
        "demo_metric",
        "demo_footprint",
        "demo_backlog_item",
        "demo_report",
    ],
)
def test_round_trip_serialization(fixture_name: str, request: pytest.FixtureRequest) -> None:
    instance: DomainModel = request.getfixturevalue(fixture_name)
    reloaded = _round_trip(instance)
    assert reloaded.model_dump() == instance.model_dump()


@pytest.mark.parametrize(
    "model_cls",
    [
        Client,
        Brand,
        Audience,
        Persona,
        MarketingBrief,
        Competitor,
        Offer,
        Positioning,
        Channel,
        Asset,
        Evidence,
        Claim,
        Campaign,
        Metric,
        DigitalFootprintSnapshot,
        GrowthBacklogItem,
        Report,
    ],
)
def test_json_schema_is_generable(model_cls: type[DomainModel]) -> None:
    schema = model_cls.model_json_schema()
    assert isinstance(schema, dict)
    assert "properties" in schema
    assert "title" in schema


def test_enum_serializes_as_plain_string(demo_metric: Metric) -> None:
    payload = json.loads(demo_metric.to_json())
    assert payload["source"] == "ga4"
    assert payload["category"] == "acquisition"
    assert payload["unit"] == "count"
    assert payload["subject_type"] == "campaign"


def test_datetime_serializes_iso_utc(demo_metric: Metric) -> None:
    payload = json.loads(demo_metric.to_json())
    # ISO-8601 with explicit offset, in UTC.
    assert payload["measured_at"].endswith("+00:00") or payload["measured_at"].endswith("Z")


def test_backlog_ice_score_in_serialization(demo_backlog_item: GrowthBacklogItem) -> None:
    payload = json.loads(demo_backlog_item.to_json())
    # Computed field is included in JSON output by default.
    assert payload["ice_score"] == demo_backlog_item.impact * demo_backlog_item.confidence * demo_backlog_item.ease
