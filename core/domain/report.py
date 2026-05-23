"""Report entity — a narrative artifact summarizing metrics over a period."""

from __future__ import annotations

from datetime import date as date_type
from typing import Annotated

from pydantic import Field, field_validator, model_validator

from .base import TimestampedModel, new_id, validate_slug
from .enums import ReportType


class Report(TimestampedModel):
    """A narrative deliverable summarizing metrics for a period.

    The report does not embed metric values; it references ``metric_ids`` and
    leaves rendering to a future presentation layer.
    """

    id: str = Field(default_factory=new_id)
    client_slug: Annotated[str, Field(min_length=2, max_length=64)]
    report_type: ReportType
    title: Annotated[str, Field(min_length=1, max_length=300)]
    period_start: date_type
    period_end: date_type
    metric_ids: list[str] = Field(default_factory=list)
    campaign_ids: list[str] = Field(default_factory=list)
    narrative: str | None = None
    highlights: list[str] = Field(default_factory=list)
    next_steps: list[str] = Field(default_factory=list)

    @field_validator("client_slug")
    @classmethod
    def _slug(cls, v: str) -> str:
        return validate_slug(v)

    @model_validator(mode="after")
    def _period_order(self) -> Report:
        if self.period_end < self.period_start:
            raise ValueError("period_end must be >= period_start")
        return self
