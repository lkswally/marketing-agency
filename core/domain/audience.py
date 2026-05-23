"""Audience entity — a defined segment targeted by campaigns."""

from __future__ import annotations

from typing import Annotated

from pydantic import Field, field_validator

from .base import TimestampedModel, new_id, validate_slug
from .enums import ChannelType


class Audience(TimestampedModel):
    """A segment of people defined by demographic and psychographic attributes.

    Channels list which channels are believed to reach this audience.
    Persona references are held in ``persona_ids``.
    """

    id: str = Field(default_factory=new_id)
    client_slug: Annotated[str, Field(min_length=2, max_length=64)]
    label: Annotated[str, Field(min_length=1, max_length=200)]
    description: str | None = None
    estimated_size: int | None = Field(default=None, ge=0)
    demographics: dict[str, str] = Field(default_factory=dict)
    psychographics: dict[str, str] = Field(default_factory=dict)
    preferred_channels: list[ChannelType] = Field(default_factory=list)
    persona_ids: list[str] = Field(default_factory=list)

    @field_validator("client_slug")
    @classmethod
    def _slug(cls, v: str) -> str:
        return validate_slug(v)
