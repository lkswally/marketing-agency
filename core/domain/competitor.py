"""Competitor entity — an observed rival of the client."""

from __future__ import annotations

from typing import Annotated

from pydantic import Field, field_validator

from .base import TimestampedModel, new_id, validate_slug


class Competitor(TimestampedModel):
    """A rival the client competes with.

    ``observed_claims`` and ``sources`` are unstructured here; structured
    Claim/Evidence linkage is done separately via Claim entities that may
    reference this competitor by id.
    """

    id: str = Field(default_factory=new_id)
    client_slug: Annotated[str, Field(min_length=2, max_length=64)]
    name: Annotated[str, Field(min_length=1, max_length=200)]
    url: str | None = None
    positioning_summary: str | None = None
    observed_claims: list[str] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    notes: str | None = None

    @field_validator("client_slug")
    @classmethod
    def _slug(cls, v: str) -> str:
        return validate_slug(v)
