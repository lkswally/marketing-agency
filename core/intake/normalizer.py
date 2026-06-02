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

_SHORT_NAME_MAX = 80
_SHORT_NAME_SPLITTERS = (" — ", " - ", " – ", ":", "(", "|")


def _short_product_name(prose: str) -> str:
    """Derive a short product name from a longer ``product_or_service`` string.

    Picks the prefix before the first separator (em-dash, colon, paren,
    pipe), strips it, and caps at ``_SHORT_NAME_MAX`` chars. If the
    result is empty or unhelpful, falls back to the full string capped.
    Pure function. Never raises.

    Examples
    --------
    >>> _short_product_name("Acme Pro — suite de automatización")
    'Acme Pro'
    >>> _short_product_name("Pipeline determinístico, auditable y multi-tenant que genera estrategia, copies, emails ...")
    'Pipeline determinístico, auditable y multi-tenant que genera estrategia, copies, ...'  # truncated to 80
    """
    text = (prose or "").strip()
    if not text:
        return text
    for sep in _SHORT_NAME_SPLITTERS:
        idx = text.find(sep)
        if 0 < idx <= _SHORT_NAME_MAX:
            return text[:idx].strip()
    if len(text) <= _SHORT_NAME_MAX:
        return text
    # Hard truncate at word boundary if possible.
    cut = text[:_SHORT_NAME_MAX].rsplit(" ", 1)[0]
    return (cut or text[:_SHORT_NAME_MAX]).rstrip(",;:.") + "..."


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
        good_examples=list(intake.good_examples),
        bad_examples=list(intake.bad_examples),
    )

    # ---- Product ----
    # ``product_or_service`` is required for normalization (validator pinned it).
    assert intake.product_or_service is not None  # pinned by validator
    # MKT-4C: derive a SHORT product name (cap 80 chars, first phrase before
    # an em-dash, colon or opening paren) so downstream titles like
    # ``f"Hero campaña — {product.name}"`` stay within the asset title caps
    # (200 chars on ReelsAsset / ImagePromptAsset). The full prose stays in
    # ``description`` so prompts and visual concepts can still use it.
    short_name = _short_product_name(intake.product_or_service)
    # If the product_or_service had no natural separator (we ended up with
    # a hard truncation ending in "..."), prefer the client_name as the
    # human-facing label. Real-data observation from MKT-4C: long product
    # descriptions without an em-dash produce garbage names like
    # "Pipeline determinístico, auditable y multi-tenant que genera
    # estrategia...". The client_name is invariably cleaner.
    if short_name.endswith("...") and intake.client_name:
        short_name = intake.client_name[:_SHORT_NAME_MAX]
    # When we shortened the name BY SPLITTING (short_name is a real
    # prefix of the prose), the suffix after the separator is an
    # elevator-pitch / value-prop fragment. Surface it as an explicit
    # value prop so the strategy templates AND the claim audit see it.
    # If short_name came from the client_name fallback (NOT a prefix
    # of the prose), DO NOT slice the prose — that produces meaningless
    # mid-word cuts. Fixed in MKT-4D after first-pass quality review.
    extracted_value_props: list[str] = []
    if (
        short_name != intake.product_or_service
        and intake.product_or_service.startswith(short_name)
    ):
        tail = intake.product_or_service[len(short_name):].lstrip(" —-–:|(")
        if tail and tail not in short_name:
            extracted_value_props.append(tail.strip())
    long_description = (
        intake.additional_context
        if short_name == intake.product_or_service
        else f"{intake.product_or_service}\n\n{intake.additional_context or ''}".strip()
    )
    product = _InputProduct(
        name=short_name,
        offer_type=intake.product_type or "product",
        description=long_description or None,
        value_props=extracted_value_props,
        price_amount=None,
        price_currency=None,
    )

    # ---- Audience hint ----
    assert intake.audience_description is not None  # pinned by validator
    # MKT-4C: derive a SHORT audience label (same heuristic as the product
    # name) so downstream titles + Visual.target_audience (cap 300) stay
    # within bounds. Full prose stays in description. If truncation kicks
    # in we still keep the ugly "..." string because there's no client_name
    # equivalent for audience — but at least the cap is respected.
    audience_label = _short_product_name(intake.audience_description or "") or (
        intake.audience_description or ""
    )
    audience_hint = _InputAudienceHint(
        label=audience_label,
        description=intake.audience_description,
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
