"""DigitalFootprintSnapshot entity — a grouped reading of public presence.

Aggregates N Metrics taken at (roughly) the same time about the same subject
(a client, competitor, channel, etc.). Useful for reconstructing "what the
public surface looked like on date X" without ad-hoc filtering.

No connector code lives here. Snapshots are populated by future agents that
collect data from public sources (research agents, manual entry, etc.).
"""

from __future__ import annotations

from datetime import date as date_type
from typing import Annotated

from pydantic import Field, field_validator

from .base import TimestampedModel, new_id, validate_slug
from .enums import SubjectType


class DigitalFootprintSnapshot(TimestampedModel):
    """A point-in-time bundle of metrics describing a subject's public surface.

    A snapshot does not embed metric values — it references them by
    ``metric_ids`` so individual measurements stay sovereign and can be reused
    across snapshots, reports, and dashboards (future).
    """

    id: str = Field(default_factory=new_id)
    client_slug: Annotated[str, Field(min_length=2, max_length=64)]
    subject_type: SubjectType
    subject_id: Annotated[str, Field(min_length=1)]
    snapshot_date: date_type
    label: str | None = None
    metric_ids: list[str] = Field(default_factory=list)
    coverage: dict[str, str] = Field(default_factory=dict)
    notes: str | None = None

    @field_validator("client_slug")
    @classmethod
    def _slug(cls, v: str) -> str:
        return validate_slug(v)
