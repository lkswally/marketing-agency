"""Base classes and shared utilities for MKT domain models.

Contract: domain-model.v1
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

# A slug is lowercase ASCII with single-dash separators. Used for client_slug,
# campaign slugs, and other human-readable IDs.
SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

# Slugs reserved for system use; not assignable to clients.
RESERVED_SLUGS = frozenset({"_shared"})


def utcnow() -> datetime:
    """Timezone-aware UTC 'now'."""
    return datetime.now(UTC)


def new_id() -> str:
    """Generate a new opaque entity id (UUID4 hex, 32 chars)."""
    return uuid4().hex


def validate_slug(value: str) -> str:
    """Validate a slug per the project's slug rules.

    Raises:
        ValueError: if the value is not a valid slug or is reserved.
    """
    if not isinstance(value, str) or not SLUG_RE.match(value):
        raise ValueError(
            f"invalid slug {value!r}: must be lowercase alphanumeric with single-dash separators"
        )
    if value in RESERVED_SLUGS:
        raise ValueError(f"slug {value!r} is reserved")
    return value


class DomainModel(BaseModel):
    """Base for every MKT domain entity.

    - Forbids extra fields (catches typos and rogue keys).
    - Strips whitespace from strings.
    - Validates on assignment (mutations re-validate).
    """

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        validate_assignment=True,
    )

    def to_json(self, **kwargs: Any) -> str:
        """Serialize to a JSON string."""
        return self.model_dump_json(**kwargs)

    @classmethod
    def from_json(cls, data: str | bytes):
        """Deserialize from a JSON string.

        Strips computed-field keys before validation so that round-trips work
        even when the model declares computed fields (e.g. ``ice_score``).
        """
        import json as _json

        payload = _json.loads(data)
        if isinstance(payload, dict):
            for key in cls.model_computed_fields:
                payload.pop(key, None)
        return cls.model_validate(payload)


class TimestampedModel(DomainModel):
    """Domain model with UTC creation and update timestamps."""

    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)

    @field_validator("created_at", "updated_at")
    @classmethod
    def _require_tz(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("timestamps must be timezone-aware (UTC)")
        return v
