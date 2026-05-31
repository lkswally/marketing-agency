"""IntakeValidator — deterministic warning surfacing on a ClientIntake.

The validator looks at every field that matters, decides whether anything
missing is ``critical`` / ``warning`` / ``info``, and produces an
:class:`IntakeValidationResult`. It does NOT mutate the intake; it does
NOT invent any values.

The three operational defaults that the normalizer applies
(``duration_weeks``, ``primary_kpi``, ``locale``) are surfaced here as
``info`` entries so the reviewer can see what was filled.
"""

from __future__ import annotations

import re
from typing import Final

from core.domain.base import utcnow
from core.domain.enums import ChannelType

from .models import (
    ClientIntake,
    IntakeValidationResult,
    IntakeWarning,
)

# Operational defaults the normalizer is allowed to apply. These are NOT
# inventions — they are documented system defaults the pipeline already
# uses today (see ``core/strategy/models.py::StrategyInputBrief``).
DEFAULT_DURATION_WEEKS: Final[int] = 8
DEFAULT_PRIMARY_KPI: Final[str] = "qualified_leads"
DEFAULT_LOCALE: Final[str] = "es-AR"

# Reserved slugs from MKT-1A. Cannot be used as a client slug.
RESERVED_SLUGS = frozenset({"_shared"})

# Slug derivation regex: lowercase, dashes between alnum runs.
_SLUG_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def derive_slug(client_name: str) -> str:
    """Derive a URL-safe slug from a client name.

    - lowercase
    - non-alphanumeric runs → single dash
    - leading / trailing dashes stripped
    - clamped to 64 chars (slug field max)
    """
    if not isinstance(client_name, str):
        raise TypeError(f"client_name must be str, got {type(client_name).__name__}")
    lowered = client_name.lower()
    dashed = _SLUG_NON_ALNUM.sub("-", lowered).strip("-")
    if not dashed:
        raise ValueError(
            f"could not derive slug from client_name {client_name!r}"
        )
    return dashed[:64].strip("-") or dashed[:64]


class IntakeValidator:
    """Stateless validator. Same intake → same result."""

    def validate(self, intake: ClientIntake) -> IntakeValidationResult:
        warnings: list[IntakeWarning] = []
        slug = self._resolve_slug(intake, warnings)

        # ----- critical fields -----
        self._collect_critical(intake, warnings)

        # ----- warning-level missing fields -----
        self._collect_warnings(intake, warnings)

        # ----- info-level missing fields -----
        defaults_applied = self._collect_info_and_defaults(intake, warnings)

        # ----- channel sanity -----
        self._check_channels(intake, warnings)

        # ----- counts -----
        counts = {"info": 0, "warning": 0, "critical": 0}
        for w in warnings:
            counts[w.severity] += 1

        is_valid = counts["critical"] == 0
        can_normalize = is_valid  # critical means we can't produce a brief

        now = utcnow()
        return IntakeValidationResult(
            client_slug=slug,
            is_valid=is_valid,
            can_normalize=can_normalize,
            warnings=warnings,
            missing_critical_count=counts["critical"],
            missing_warning_count=counts["warning"],
            missing_info_count=counts["info"],
            operational_defaults_applied=defaults_applied,
            created_at=now,
            updated_at=now,
        )

    # ---------- internal checks ----------

    def _resolve_slug(
        self, intake: ClientIntake, warnings: list[IntakeWarning]
    ) -> str:
        """Compute the resolved slug. The slug is the only field the
        validator MAY synthesize from inputs — but it never invents a
        default; it always derives from ``client_name`` (or honors the
        explicit override)."""
        if intake.client_slug_override:
            slug = intake.client_slug_override
        else:
            try:
                slug = derive_slug(intake.client_name)
            except (ValueError, TypeError) as e:
                # Surface as critical and use a placeholder slug so the
                # IntakeValidationResult can still be built.
                warnings.append(
                    IntakeWarning(
                        field_path="client_name",
                        severity="critical",
                        message=f"cannot derive slug: {e}",
                        suggested_action=(
                            "Proveer un client_name con caracteres alfanuméricos "
                            "o usar client_slug_override."
                        ),
                    )
                )
                return "invalid-name"

        if slug in RESERVED_SLUGS:
            warnings.append(
                IntakeWarning(
                    field_path="client_slug_override",
                    severity="critical",
                    message=f"slug {slug!r} is reserved",
                    suggested_action="Elegir un slug distinto.",
                )
            )
            return "invalid-name"
        return slug

    def _collect_critical(
        self, intake: ClientIntake, warnings: list[IntakeWarning]
    ) -> int:
        n = 0
        if not intake.product_or_service or not intake.product_or_service.strip():
            warnings.append(
                IntakeWarning(
                    field_path="product_or_service",
                    severity="critical",
                    message="No se puede generar un brief sin producto o servicio.",
                    suggested_action="Describir qué vende el cliente en una frase.",
                )
            )
            n += 1
        if not intake.commercial_objective or not intake.commercial_objective.strip():
            warnings.append(
                IntakeWarning(
                    field_path="commercial_objective",
                    severity="critical",
                    message="No se puede generar un brief sin objetivo comercial.",
                    suggested_action="Definir un objetivo accionable (ej: 200 leads/mes).",
                )
            )
            n += 1
        if (
            not intake.audience_description
            or not intake.audience_description.strip()
        ):
            warnings.append(
                IntakeWarning(
                    field_path="audience_description",
                    severity="critical",
                    message="No se puede generar un brief sin público objetivo.",
                    suggested_action="Describir la audiencia primaria en una frase.",
                )
            )
            n += 1
        return n

    def _collect_warnings(
        self, intake: ClientIntake, warnings: list[IntakeWarning]
    ) -> None:
        if not intake.industry or not intake.industry.strip():
            warnings.append(
                IntakeWarning(
                    field_path="industry",
                    severity="warning",
                    message="No se especificó industria — diagnosis perderá precisión.",
                    suggested_action="Indicar industria (ej: SaaS B2B, retail, salud).",
                )
            )
        if not intake.market or not intake.market.strip():
            warnings.append(
                IntakeWarning(
                    field_path="market",
                    severity="warning",
                    message="No se especificó país / mercado.",
                    suggested_action="Indicar mercado primario (ej: LATAM, AR, US).",
                )
            )
        if not intake.brand_tone:
            warnings.append(
                IntakeWarning(
                    field_path="brand_tone",
                    severity="warning",
                    message="Sin tono de marca declarado — copy quedará neutro.",
                    suggested_action="Proveer 3-5 adjetivos de tono (ej: claro, directo, irreverente).",
                )
            )
        if not intake.known_competitors:
            warnings.append(
                IntakeWarning(
                    field_path="known_competitors",
                    severity="warning",
                    message="Sin competidores listados — benchmark queda con confianza baja.",
                    suggested_action="Investigar competidores antes de fase 4.",
                )
            )
        if intake.budget_estimate is None:
            warnings.append(
                IntakeWarning(
                    field_path="budget_estimate",
                    severity="warning",
                    message="Sin budget declarado — estrategia priorizará canales orgánicos.",
                    suggested_action="Confirmar si hay budget aunque sea estimado.",
                )
            )
        if not intake.constraints:
            warnings.append(
                IntakeWarning(
                    field_path="constraints",
                    severity="warning",
                    message="Sin restricciones declaradas — útil saber qué NO hacer.",
                    suggested_action="Listar canales/temas/claims fuera de scope.",
                )
            )

    def _collect_info_and_defaults(
        self, intake: ClientIntake, warnings: list[IntakeWarning]
    ) -> dict[str, str]:
        defaults: dict[str, str] = {}
        if intake.duration_weeks is None:
            warnings.append(
                IntakeWarning(
                    field_path="duration_weeks",
                    severity="info",
                    message=f"No provista — se aplicará default operacional {DEFAULT_DURATION_WEEKS} semanas.",
                    suggested_action="Confirmar duración real con el cliente.",
                )
            )
            defaults["duration_weeks"] = str(DEFAULT_DURATION_WEEKS)
        if not intake.primary_kpi:
            warnings.append(
                IntakeWarning(
                    field_path="primary_kpi",
                    severity="info",
                    message=f"No provisto — se aplicará default operacional {DEFAULT_PRIMARY_KPI!r}.",
                    suggested_action="Definir KPI primario explícito.",
                )
            )
            defaults["primary_kpi"] = DEFAULT_PRIMARY_KPI
        if not intake.locale:
            warnings.append(
                IntakeWarning(
                    field_path="locale",
                    severity="info",
                    message=f"No provisto — se aplicará default operacional {DEFAULT_LOCALE!r}.",
                    suggested_action="Confirmar locale del cliente (ej: en-US, es-MX).",
                )
            )
            defaults["locale"] = DEFAULT_LOCALE
        if not intake.deadline:
            warnings.append(
                IntakeWarning(
                    field_path="deadline",
                    severity="info",
                    message="Sin deadline — el calendar partirá desde la fecha del run.",
                    suggested_action="Confirmar fecha de lanzamiento si la hay.",
                )
            )
        if not intake.claim_style:
            warnings.append(
                IntakeWarning(
                    field_path="claim_style",
                    severity="info",
                    message="Sin claim style declarado — usar default conservador.",
                )
            )
        if not intake.forbidden_words:
            warnings.append(
                IntakeWarning(
                    field_path="forbidden_words",
                    severity="info",
                    message="Sin lista de palabras prohibidas.",
                    suggested_action="Pedirlas al cliente si tiene una lista oficial.",
                )
            )
        if not intake.good_examples and not intake.bad_examples:
            warnings.append(
                IntakeWarning(
                    field_path="good_examples",
                    severity="info",
                    message="Sin ejemplos de contenido bueno/malo — útil para calibrar tono.",
                    suggested_action="Pedir 2-3 ejemplos de cada lado al cliente.",
                )
            )
        return defaults

    def _check_channels(
        self, intake: ClientIntake, warnings: list[IntakeWarning]
    ) -> None:
        valid_values = {c.value for c in ChannelType}
        for i, raw in enumerate(intake.possible_channels):
            if raw not in valid_values:
                warnings.append(
                    IntakeWarning(
                        field_path=f"possible_channels[{i}]",
                        severity="warning",
                        message=(
                            f"Canal {raw!r} no es un ChannelType conocido — será "
                            "descartado del brief."
                        ),
                        suggested_action=(
                            "Usar un valor del enum ChannelType: "
                            + ", ".join(sorted(valid_values))
                        ),
                    )
                )


__all__ = [
    "IntakeValidator",
    "derive_slug",
    "DEFAULT_DURATION_WEEKS",
    "DEFAULT_PRIMARY_KPI",
    "DEFAULT_LOCALE",
    "RESERVED_SLUGS",
]
