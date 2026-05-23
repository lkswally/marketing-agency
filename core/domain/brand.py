"""Brand entity — the identity attached to a client."""

from __future__ import annotations

from typing import Annotated

from pydantic import Field, field_validator

from .base import TimestampedModel, new_id, validate_slug


class BrandVoice(TimestampedModel):
    """Verbal expression of a brand.

    Embedded inside Brand. Not a top-level entity because it has no independent
    lifecycle from its Brand.
    """

    tone_words: list[str] = Field(default_factory=list)
    lexicon_do: list[str] = Field(default_factory=list)
    lexicon_dont: list[str] = Field(default_factory=list)
    banned_words: list[str] = Field(default_factory=list)
    sample_phrases: list[str] = Field(default_factory=list)


class Brand(TimestampedModel):
    """A client's brand identity: voice, vocabulary, visual rules."""

    id: str = Field(default_factory=new_id)
    client_slug: Annotated[str, Field(min_length=2, max_length=64)]
    name: Annotated[str, Field(min_length=1, max_length=200)]
    mission: str | None = None
    voice: BrandVoice = Field(default_factory=BrandVoice)
    visual_rules: dict[str, str] = Field(default_factory=dict)
    claim_style: str | None = None
    logo_asset_ids: list[str] = Field(default_factory=list)

    @field_validator("client_slug")
    @classmethod
    def _slug(cls, v: str) -> str:
        return validate_slug(v)
