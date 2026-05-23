"""Positioning entity — how the brand stakes its claim in the market."""

from __future__ import annotations

from typing import Annotated

from pydantic import Field, field_validator

from .base import TimestampedModel, new_id, validate_slug


class Positioning(TimestampedModel):
    """Articulates category, alternatives, differentiator and proof.

    Follows the "April Dunford" positioning pattern: a brand is positioned
    *as* a category alternative *for* an audience *because of* a differentiator
    *backed by* proof points.
    """

    id: str = Field(default_factory=new_id)
    client_slug: Annotated[str, Field(min_length=2, max_length=64)]
    category: Annotated[str, Field(min_length=1, max_length=200)]
    alt_to: list[str] = Field(default_factory=list)
    differentiators: list[str] = Field(default_factory=list)
    proof_points: list[str] = Field(default_factory=list)
    target_audience_ids: list[str] = Field(default_factory=list)
    one_liner: str | None = Field(default=None, max_length=280)

    @field_validator("client_slug")
    @classmethod
    def _slug(cls, v: str) -> str:
        return validate_slug(v)
