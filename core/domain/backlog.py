"""GrowthBacklogItem entity — a prioritized hypothesis for growth work."""

from __future__ import annotations

from typing import Annotated

from pydantic import Field, computed_field, field_validator

from .base import TimestampedModel, new_id, validate_slug
from .enums import BacklogStatus


class GrowthBacklogItem(TimestampedModel):
    """A hypothesis to test, scored via ICE (Impact / Confidence / Ease).

    Each axis is 1..10. The ``ice_score`` computed property exposes a simple
    product for sorting; it is not stored and not authoritative.
    """

    id: str = Field(default_factory=new_id)
    client_slug: Annotated[str, Field(min_length=2, max_length=64)]
    hypothesis: Annotated[str, Field(min_length=1, max_length=1000)]
    impact: int = Field(ge=1, le=10)
    confidence: int = Field(ge=1, le=10)
    ease: int = Field(ge=1, le=10)
    status: BacklogStatus = BacklogStatus.PROPOSED
    owner: str | None = None
    related_campaign_id: str | None = None
    related_audience_ids: list[str] = Field(default_factory=list)
    notes: str | None = None

    @field_validator("client_slug")
    @classmethod
    def _slug(cls, v: str) -> str:
        return validate_slug(v)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def ice_score(self) -> int:
        return self.impact * self.confidence * self.ease
