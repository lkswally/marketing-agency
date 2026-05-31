"""IntakeNormalizer — converts a validated ClientIntake into a StrategyInputBrief.

Pure function. No I/O. Same intake + same validation result → same brief.

Cardinal rule: **the normalizer NEVER invents data**. The three operational
defaults (``duration_weeks``, ``primary_kpi``, ``locale``) are applied
explicitly and are recorded by the validator in
``IntakeValidationResult.operational_defaults_applied``.
"""

from __future__ import annotations

from core.domain.enums import ChannelType
from core.strategy.models import (
    StrategyInputBrief,
    _InputAudienceHint,
    _InputBrand,
    _InputClient,
    _InputCompetitor,
    _InputProduct,
)

from .models import ClientIntake, IntakeValidationResult
from .validator import DEFAULT_DURATION_WEEKS, DEFAULT_LOCALE, DEFAULT_PRIMARY_KPI


class IntakeNormalizationError(RuntimeError):
    """Raised when a normalization is attempted on an intake that cannot be normalized."""


def normalize_intake(
    intake: ClientIntake, validation: IntakeValidationResult
) -> StrategyInputBrief:
    """Convert a validated :class:`ClientIntake` into a :class:`StrategyInputBrief`.

    Raises:
        IntakeNormalizationError: when ``validation.can_normalize`` is False
            (i.e. the intake has critical missing fields).
    """
    if not validation.can_normalize:
        raise IntakeNormalizationError(
            "intake cannot be normalized: "
            f"{validation.missing_critical_count} critical issue(s) present"
        )

    # ---- Client ----
    client = _InputClient(
        slug=validation.client_slug,
        name=intake.client_name,
        industry=intake.industry,
        locale=intake.locale or DEFAULT_LOCALE,
    )

    # ---- Brand (verbatim) ----
    brand = _InputBrand(
        name=None,
        mission=None,
        tone_words=list(intake.brand_tone),
        lexicon_do=list(intake.preferred_words),
        lexicon_dont=[],
        banned_words=list(intake.forbidden_words),
        claim_style=intake.claim_style,
    )

    # ---- Product ----
    # ``product_or_service`` is required for normalization (validator pinned it).
    assert intake.product_or_service is not None  # pinned by validator
    product = _InputProduct(
        name=intake.product_or_service,
        offer_type=intake.product_type or "product",
        description=intake.additional_context,
        value_props=[],
        price_amount=None,
        price_currency=None,
    )

    # ---- Audience hint ----
    assert intake.audience_description is not None  # pinned by validator
    audience_hint = _InputAudienceHint(
        label=intake.audience_description,
        description=intake.additional_context,
        demographics={"geo": intake.market} if intake.market else {},
        psychographics={},
        preferred_channels=_normalize_channels(intake.possible_channels),
        estimated_size=None,
    )

    # ---- Competitors ----
    competitors_known = [
        _InputCompetitor(
            name=c.name,
            url=c.url,
            positioning_summary=c.notes,
            strengths=[],
            weaknesses=[],
        )
        for c in intake.known_competitors
    ]

    # ---- Constraints + claims_to_avoid ----
    constraints = list(intake.constraints)
    for claim in intake.claims_to_avoid:
        constraints.append(f"Claim to avoid: {claim}")

    # ---- Compose ----
    assert intake.commercial_objective is not None  # pinned by validator
    brief = StrategyInputBrief(
        client=client,
        brand=brand,
        product=product,
        objective=intake.commercial_objective,
        audience_hints=[audience_hint],
        constraints=constraints,
        preferred_channels=_normalize_channels(intake.possible_channels),
        competitors_known=competitors_known,
        budget_amount=intake.budget_estimate,
        budget_currency=intake.budget_currency,
        deadline=intake.deadline,
        duration_weeks=intake.duration_weeks or DEFAULT_DURATION_WEEKS,
        primary_kpi=intake.primary_kpi or DEFAULT_PRIMARY_KPI,
        additional_context=intake.additional_context,
    )
    return brief


def _normalize_channels(raw: list[str]) -> list[ChannelType]:
    """Convert string channel names to :class:`ChannelType`, dropping unknowns.

    Unknown channels surface as ``warning`` in the validator; here they are
    silently dropped so the brief stays Pydantic-valid.
    """
    out: list[ChannelType] = []
    valid_values = {c.value for c in ChannelType}
    for r in raw:
        if r in valid_values:
            out.append(ChannelType(r))
    return out


__all__ = [
    "IntakeNormalizationError",
    "normalize_intake",
]
