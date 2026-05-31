"""Client Brief Intake Pack (MKT-3E).

Contracts: ``client-intake.v1`` + ``intake-validation.v1``.

Entry point of the agency pipeline. Given a permissive JSON intake from a
human (or an upstream form), this layer:

1. Validates the intake (severity-tagged warnings, no fabrication).
2. Normalizes it to a :class:`StrategyInputBrief` (MKT-3A) ready for
   ``mkt run-strategy --brief``.
3. Persists the intake + validation result to memory.
4. Writes a Markdown summary plus a JSON brief.
"""

from __future__ import annotations

from .models import (
    CLIENT_INTAKE_VERSION,
    INTAKE_VALIDATION_VERSION,
    ClientIntake,
    CompetitorIntake,
    IntakeValidationResult,
    IntakeWarning,
)
from .normalizer import IntakeNormalizationError, normalize_intake
from .renderer import render_intake_summary
from .validator import (
    DEFAULT_DURATION_WEEKS,
    DEFAULT_LOCALE,
    DEFAULT_PRIMARY_KPI,
    RESERVED_SLUGS,
    IntakeValidator,
    derive_slug,
)

# Memory kinds used by the intake layer.
INTAKE_KIND = "client_intake"
VALIDATION_KIND = "intake_validation"
SINGLETON_ID = "current"


__all__ = [
    "CLIENT_INTAKE_VERSION",
    "INTAKE_VALIDATION_VERSION",
    "INTAKE_KIND",
    "VALIDATION_KIND",
    "SINGLETON_ID",
    # Models
    "ClientIntake",
    "CompetitorIntake",
    "IntakeWarning",
    "IntakeValidationResult",
    # Components
    "IntakeValidator",
    "derive_slug",
    "normalize_intake",
    "IntakeNormalizationError",
    "render_intake_summary",
    # Defaults
    "DEFAULT_DURATION_WEEKS",
    "DEFAULT_PRIMARY_KPI",
    "DEFAULT_LOCALE",
    "RESERVED_SLUGS",
]
