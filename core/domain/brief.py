"""MarketingBrief entity — the input that kicks off a workflow."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from pydantic import Field, field_validator

from .base import TimestampedModel, new_id, validate_slug
from .enums import BriefStatus


class MarketingBrief(TimestampedModel):
    """An incoming request for marketing work.

    Briefs are the canonical entry point for workflows. They reference
    Audience(s) by id and may carry a free-text raw_input alongside structured
    fields.
    """

    id: str = Field(default_factory=new_id)
    client_slug: Annotated[str, Field(min_length=2, max_length=64)]
    title: Annotated[str, Field(min_length=1, max_length=300)]
    objective: Annotated[str, Field(min_length=1)]
    audience_ids: list[str] = Field(default_factory=list)
    deliverables: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    deadline: datetime | None = None
    budget_currency: str | None = None
    budget_amount: float | None = Field(default=None, ge=0)
    status: BriefStatus = BriefStatus.DRAFT
    raw_input: str | None = None

    @field_validator("client_slug")
    @classmethod
    def _slug(cls, v: str) -> str:
        return validate_slug(v)

    @field_validator("deadline")
    @classmethod
    def _deadline_tz(cls, v: datetime | None) -> datetime | None:
        if v is not None and v.tzinfo is None:
            raise ValueError("deadline must be timezone-aware")
        return v
