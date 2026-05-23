"""Evidence entity — a source backing a Claim."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from pydantic import Field, field_validator

from .base import TimestampedModel, new_id
from .enums import EvidenceSourceType


class Evidence(TimestampedModel):
    """A pointer to a source supporting (or contradicting) a claim.

    ``trust_level`` is a 0..1 score reflecting how much weight to place on the
    source. Connector implementations to verify retrievability are deferred.
    """

    id: str = Field(default_factory=new_id)
    source_type: EvidenceSourceType
    location: Annotated[str, Field(min_length=1, max_length=2048)]
    excerpt: str | None = Field(default=None, max_length=4000)
    retrieved_at: datetime | None = None
    trust_level: float = Field(default=0.5, ge=0.0, le=1.0)
    author: str | None = None
    notes: str | None = None

    @field_validator("retrieved_at")
    @classmethod
    def _tz(cls, v: datetime | None) -> datetime | None:
        if v is not None and v.tzinfo is None:
            raise ValueError("retrieved_at must be timezone-aware")
        return v
