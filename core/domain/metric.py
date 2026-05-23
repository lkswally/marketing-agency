"""Metric entity — a single measurement.

Designed to absorb data from multiple future sources (GA4, social, email,
search/SEO, public footprint, manual entry, internal reports). No connector
code is implemented in MKT-1B; the model is the integration contract.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from pydantic import Field, field_validator

from .base import TimestampedModel, new_id, validate_slug
from .enums import MetricCategory, MetricSource, MetricUnit, SubjectType


class Metric(TimestampedModel):
    """A single measurement at a point in time.

    Fields:
        client_slug: tenant scope.
        name: human-readable metric name ("sessions", "open_rate", "followers").
        value: the numeric measurement.
        unit: how to interpret ``value`` (count, percent, currency, etc.).
        source: where the measurement came from.
        category: what the metric measures, regardless of source.
        measured_at: when the measurement was taken (UTC).
        subject_type / subject_id: the entity the metric is about.
        dimensions: free-form cuts (device, country, utm_source, etc.).
        provider_ref: external id for future reconciliation (GA4 propertyId,
            post id, etc.). No format is enforced.
        confidence: 0..1 score; useful for estimates from public footprint.
        is_estimate: True if the value is an approximation rather than direct.
    """

    id: str = Field(default_factory=new_id)
    client_slug: Annotated[str, Field(min_length=2, max_length=64)]
    name: Annotated[str, Field(min_length=1, max_length=200)]
    value: float
    unit: MetricUnit = MetricUnit.COUNT
    source: MetricSource
    category: MetricCategory
    measured_at: datetime
    subject_type: SubjectType
    subject_id: Annotated[str, Field(min_length=1)]
    dimensions: dict[str, str] = Field(default_factory=dict)
    provider_ref: str | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    is_estimate: bool = False
    notes: str | None = None

    @field_validator("client_slug")
    @classmethod
    def _slug(cls, v: str) -> str:
        return validate_slug(v)

    @field_validator("measured_at")
    @classmethod
    def _measured_tz(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("measured_at must be timezone-aware (UTC)")
        return v
