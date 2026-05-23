"""Client entity — a customer of the agency."""

from __future__ import annotations

from typing import Annotated

from pydantic import Field, field_validator

from .base import TimestampedModel, validate_slug


class Client(TimestampedModel):
    """A real-world customer of the agency.

    The ``slug`` is the multi-tenant scoping key used everywhere in the system
    (filesystem paths, Engram topic keys, memory partitions).
    """

    slug: Annotated[str, Field(min_length=2, max_length=64)]
    name: Annotated[str, Field(min_length=1, max_length=200)]
    industry: str | None = None
    locale: Annotated[str, Field(min_length=2, max_length=10)] = "en-US"
    primary_contact_email: str | None = None
    brand_id: str | None = None
    notes: str | None = None

    @field_validator("slug")
    @classmethod
    def _slug(cls, v: str) -> str:
        return validate_slug(v)

    @field_validator("primary_contact_email")
    @classmethod
    def _email(cls, v: str | None) -> str | None:
        if v is None:
            return v
        # Lightweight check — full RFC 5322 not required here.
        if "@" not in v or "." not in v.split("@")[-1]:
            raise ValueError(f"invalid email: {v!r}")
        return v
