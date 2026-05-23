"""Campaign entity — a bounded marketing effort."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from pydantic import Field, field_validator, model_validator

from .base import TimestampedModel, new_id, validate_slug
from .enums import CampaignStatus


class Campaign(TimestampedModel):
    """A bounded marketing effort tied to one or more audiences and channels.

    References to other entities (audience_ids, channel_ids, asset_ids) are
    held as ids — referential integrity is enforced at the repository layer,
    not by the model.
    """

    id: str = Field(default_factory=new_id)
    client_slug: Annotated[str, Field(min_length=2, max_length=64)]
    name: Annotated[str, Field(min_length=1, max_length=200)]
    goal: Annotated[str, Field(min_length=1)]
    status: CampaignStatus = CampaignStatus.PLANNED
    brief_id: str | None = None
    audience_ids: list[str] = Field(default_factory=list)
    channel_ids: list[str] = Field(default_factory=list)
    asset_ids: list[str] = Field(default_factory=list)
    offer_ids: list[str] = Field(default_factory=list)
    start_at: datetime | None = None
    end_at: datetime | None = None
    budget_amount: float | None = Field(default=None, ge=0)
    budget_currency: str | None = None
    kpis: list[str] = Field(default_factory=list)

    @field_validator("client_slug")
    @classmethod
    def _slug(cls, v: str) -> str:
        return validate_slug(v)

    @field_validator("start_at", "end_at")
    @classmethod
    def _tz(cls, v: datetime | None) -> datetime | None:
        if v is not None and v.tzinfo is None:
            raise ValueError("timestamps must be timezone-aware")
        return v

    @model_validator(mode="after")
    def _date_order(self) -> Campaign:
        if self.start_at and self.end_at and self.end_at < self.start_at:
            raise ValueError("end_at must be >= start_at")
        return self
