"""Claim entity — a factual assertion in a marketing output."""

from __future__ import annotations

from typing import Annotated

from pydantic import Field

from .base import TimestampedModel, new_id
from .enums import ClaimSeverity, ClaimVerdict


class Claim(TimestampedModel):
    """A factual assertion that must be backed by Evidence.

    Compliance is a first-class subsystem (ARCHITECTURE.md D4). Severity and
    Verdict together determine whether an output containing the claim may ship.
    """

    id: str = Field(default_factory=new_id)
    text: Annotated[str, Field(min_length=1, max_length=2000)]
    severity: ClaimSeverity = ClaimSeverity.SAFE
    verdict: ClaimVerdict = ClaimVerdict.UNVERIFIED
    evidence_ids: list[str] = Field(default_factory=list)
    raised_in_asset_id: str | None = None
    rationale: str | None = None
    reviewer: str | None = None
