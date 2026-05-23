"""Persona entity — a representative archetype within an Audience."""

from __future__ import annotations

from typing import Annotated

from pydantic import Field

from .base import TimestampedModel, new_id


class Persona(TimestampedModel):
    """A named archetype representing a slice of an Audience.

    A Persona belongs to exactly one Audience (``audience_id``). Demographics
    and psychographics here describe the archetype, not the population.
    """

    id: str = Field(default_factory=new_id)
    audience_id: Annotated[str, Field(min_length=1)]
    archetype_name: Annotated[str, Field(min_length=1, max_length=200)]
    age_range: str | None = None
    occupation: str | None = None
    demographics: dict[str, str] = Field(default_factory=dict)
    motivations: list[str] = Field(default_factory=list)
    pains: list[str] = Field(default_factory=list)
    jobs_to_be_done: list[str] = Field(default_factory=list)
    objections: list[str] = Field(default_factory=list)
    quotes: list[str] = Field(default_factory=list)
