"""Channel entity — a distribution surface owned or used by the client."""

from __future__ import annotations

from typing import Annotated

from pydantic import Field, field_validator

from .base import TimestampedModel, new_id, validate_slug
from .enums import ChannelType


class Channel(TimestampedModel):
    """A distribution surface (email list, social handle, paid platform account)."""

    id: str = Field(default_factory=new_id)
    client_slug: Annotated[str, Field(min_length=2, max_length=64)]
    channel_type: ChannelType
    handle: str | None = None
    url: str | None = None
    label: Annotated[str, Field(min_length=1, max_length=200)]
    config: dict[str, str] = Field(default_factory=dict)
    is_owned: bool = True
    notes: str | None = None

    @field_validator("client_slug")
    @classmethod
    def _slug(cls, v: str) -> str:
        return validate_slug(v)
