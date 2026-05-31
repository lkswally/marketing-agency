"""Pydantic models for the Client Brief Intake Pack (MKT-3E).

Contract: ``client-intake.v1``.

The intake layer is the friendly entry point to the agency pipeline. It
accepts a permissive JSON shape from a human (or an upstream form), runs
deterministic validation and normalization, and produces:

- A persisted :class:`ClientIntake` (auditable, what the user actually sent).
- A persisted :class:`IntakeValidationResult` (what we noticed: warnings +
  missing-field flags by severity).
- A :class:`StrategyInputBrief` (MKT-1B / MKT-3A) ready to feed
  ``mkt run-strategy --brief``.

Cardinal rule: **the intake NEVER invents data**. The only defaults it
applies are three operational ones (``duration_weeks``, ``primary_kpi``,
``locale``), each declared in the warnings list at ``info`` severity so
the reviewer can see what was filled.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import Field, field_validator

from core.domain.base import DomainModel, new_id, validate_slug

CLIENT_INTAKE_VERSION = "client-intake.v1"
INTAKE_VALIDATION_VERSION = "intake-validation.v1"


# ============ Sub-models ============

class CompetitorIntake(DomainModel):
    """A competitor as supplied by the human in the intake JSON."""

    name: str = Field(min_length=1, max_length=200)
    url: str | None = None
    notes: str | None = Field(default=None, max_length=600)


# ============ ClientIntake ============

class ClientIntake(DomainModel):
    """The permissive intake shape — exactly what the human / form sends.

    Only ``client_name`` is hard-required at the model layer. Every other
    field is optional. The :class:`IntakeValidator` is what marks any
    missing-but-important field as ``critical`` / ``warning`` / ``info``.
    """

    schema_version: Literal["client-intake.v1"] = CLIENT_INTAKE_VERSION

    # ---- Identity ----
    client_name: str = Field(min_length=1, max_length=200)
    client_slug_override: str | None = None

    # ---- Business basics ----
    industry: str | None = Field(default=None, max_length=200)
    market: str | None = Field(default=None, max_length=200)
    product_or_service: str | None = Field(default=None, max_length=300)
    product_type: Literal[
        "product", "service", "subscription", "lead_magnet", "bundle", "other"
    ] | None = None

    # ---- Audience + objective ----
    audience_description: str | None = Field(default=None, max_length=1000)
    commercial_objective: str | None = Field(default=None, max_length=1000)

    # ---- Brand voice (preserved verbatim when supplied) ----
    brand_tone: list[str] = Field(default_factory=list)
    preferred_words: list[str] = Field(default_factory=list)
    forbidden_words: list[str] = Field(default_factory=list)
    claim_style: str | None = None

    # ---- Channels + competitors ----
    possible_channels: list[str] = Field(default_factory=list)
    known_competitors: list[CompetitorIntake] = Field(default_factory=list)

    # ---- Operational ----
    budget_estimate: float | None = Field(default=None, ge=0)
    budget_currency: str | None = Field(default=None, max_length=8)
    deadline: date | None = None
    duration_weeks: int | None = Field(default=None, ge=1, le=52)
    primary_kpi: str | None = Field(default=None, max_length=200)
    locale: str | None = Field(default=None, min_length=2, max_length=10)

    # ---- Constraints + claim policy ----
    constraints: list[str] = Field(default_factory=list)
    claims_to_avoid: list[str] = Field(default_factory=list)

    # ---- Reference content ----
    good_examples: list[str] = Field(default_factory=list)
    bad_examples: list[str] = Field(default_factory=list)
    additional_context: str | None = Field(default=None, max_length=4000)

    @field_validator("client_slug_override")
    @classmethod
    def _slug_override(cls, v: str | None) -> str | None:
        if v is None:
            return v
        return validate_slug(v)


# ============ Validation warnings ============

class IntakeWarning(DomainModel):
    """One issue surfaced by :class:`IntakeValidator`."""

    field_path: str = Field(min_length=1, max_length=200)
    severity: Literal["info", "warning", "critical"]
    message: str = Field(min_length=1, max_length=500)
    suggested_action: str | None = None


# ============ Validation result ============

class IntakeValidationResult(DomainModel):
    """The validator's deterministic report on an intake."""

    contract_version: Literal["intake-validation.v1"] = INTAKE_VALIDATION_VERSION
    intake_id: str = Field(default_factory=new_id)
    client_slug: Annotated[str, Field(min_length=2, max_length=64)]
    is_valid: bool
    can_normalize: bool
    warnings: list[IntakeWarning] = Field(default_factory=list)
    missing_critical_count: int = Field(default=0, ge=0)
    missing_warning_count: int = Field(default=0, ge=0)
    missing_info_count: int = Field(default=0, ge=0)
    operational_defaults_applied: dict[str, str] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime

    @field_validator("client_slug")
    @classmethod
    def _slug(cls, v: str) -> str:
        return validate_slug(v)

    @field_validator("created_at", "updated_at")
    @classmethod
    def _tz(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("timestamps must be timezone-aware (UTC)")
        return v

    # -------- helpers --------

    def count_by_severity(self) -> dict[str, int]:
        counts = {"info": 0, "warning": 0, "critical": 0}
        for w in self.warnings:
            counts[w.severity] += 1
        return counts
