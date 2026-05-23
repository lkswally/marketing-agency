"""Offer entity — a thing the client sells."""

from __future__ import annotations

from typing import Annotated

from pydantic import Field, field_validator

from .base import TimestampedModel, new_id, validate_slug
from .enums import OfferType


class Offer(TimestampedModel):
    """A product, service, subscription, lead-magnet or bundle the client sells."""

    id: str = Field(default_factory=new_id)
    client_slug: Annotated[str, Field(min_length=2, max_length=64)]
    name: Annotated[str, Field(min_length=1, max_length=200)]
    offer_type: OfferType = OfferType.PRODUCT
    description: str | None = None
    value_props: list[str] = Field(default_factory=list)
    price_model: str | None = None
    price_amount: float | None = Field(default=None, ge=0)
    price_currency: str | None = None
    target_audience_ids: list[str] = Field(default_factory=list)
    notes: str | None = None

    @field_validator("client_slug")
    @classmethod
    def _slug(cls, v: str) -> str:
        return validate_slug(v)
