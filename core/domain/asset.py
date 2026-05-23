"""Asset entity — a binary or text artifact tied to a client."""

from __future__ import annotations

from typing import Annotated

from pydantic import Field, field_validator

from .base import TimestampedModel, new_id, validate_slug
from .enums import AssetType


class Asset(TimestampedModel):
    """A file or piece of content (logo, image, copy, email template, etc.).

    Paths point to ``assets/clients/<client_slug>/`` per the multi-tenant
    folder taxonomy (ARCHITECTURE.md D7).
    """

    id: str = Field(default_factory=new_id)
    client_slug: Annotated[str, Field(min_length=2, max_length=64)]
    asset_type: AssetType
    label: Annotated[str, Field(min_length=1, max_length=200)]
    path: str | None = None
    mime: str | None = None
    body_text: str | None = None
    campaign_id: str | None = None
    claim_ids: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)

    @field_validator("client_slug")
    @classmethod
    def _slug(cls, v: str) -> str:
        return validate_slug(v)
