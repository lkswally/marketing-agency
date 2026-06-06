"""Deterministic template generators for the campaign strategy engine.

Every function in this module is pure, deterministic, and LLM-free. Given
the same inputs, they produce the same outputs (modulo explicit timestamps
or ids which the caller injects).

The intentional trade: outputs are reviewable and complete, but they are
template-driven and not creative. Promotion to LLM-backed generators is a
future block that requires the safety boundaries from
``docs/runtime/agent-backend-safety.md`` to be in place.
"""

from __future__ import annotations

from datetime import date, timedelta

from core.domain.base import new_id
from core.domain.enums import ChannelType

from .models import (
    ApprovalChecklist,
    BusinessDiagnosis,
    BuyerPersona,
    CampaignSchedule,
    CampaignStrategy,
    ChannelEntry,
    ChannelRecommendation,
    ChecklistItem,
    CompetitorBenchmark,
    CompetitorEntry,
    CreativeBriefEntry,
    CreativeBriefPack,
    EmailDraft,
    EmailSequenceDraft,
    ExecutiveSummary,
    KeywordCluster,
    KeywordPlan,
    ReelsScriptEntry,
    ReelsScriptPack,
    RiskAssessment,
    RiskItem,
    ScheduleEntry,
    SocialPostDraft,
    StrategyInputBrief,
    SuggestedPiece,
    TargetAudience,
    ValueProposition,
    _InputCompetitor,
)
from .style import (
    first_meaningful_token,
    is_meaningful_keyword,
    make_hashtag,
    pick_preferred_word,
    tone_adjective,
    tone_connector,
    tone_opener,
)

# ---------- Constants ----------

_GENERIC_NEGATIVES = ["free", "torrent", "jobs", "salary", "course", "tutorial gratis"]

_OWNED_DEFAULTS = [ChannelType.NEWSLETTER, ChannelType.BLOG]
_SOCIAL_DEFAULTS = [ChannelType.LINKEDIN, ChannelType.INSTAGRAM]
_OUT_OF_SCOPE_DEFAULTS = [ChannelType.OTHER]

_GENERIC_HASHTAGS = ["#marketing", "#growth", "#strategy"]


# ---------- Helpers ----------

def _slugify_keyword(text: str) -> str:
    """Backward-compatible facade over :func:`style.normalize_for_slug`.

    Kept so callers outside this file continue to work; new code in this
    module uses ``normalize_for_slug`` directly.
    """
    from .style import normalize_for_slug

    return normalize_for_slug(text)


def _hashtagify(text: str) -> str:
    """Backward-compatible facade over :func:`style.make_hashtag`.

    Returns ``""`` instead of ``None`` for compatibility with callers
    that check truthiness.
    """
    return make_hashtag(text) or ""


def _estimated_size_band(size: int | None) -> str:
    if size is None:
        return "medium"
    if size < 5_000:
        return "niche"
    if size < 50_000:
        return "small"
    if size < 500_000:
        return "medium"
    return "large"


def _truncate(text: str, max_len: int) -> str:
    return text if len(text) <= max_len else text[: max_len - 1].rstrip() + "…"


# ---------- Section generators ----------

def generate_executive_summary(brief: StrategyInputBrief) -> ExecutiveSummary:
    primary_audience = brief.audience_hints[0].label
    # MKT-9B: weave one preferred word (lexicon_do) into the headline
    # so the tone of the campaign is set from the first read. Falls
    # back to a neutral phrase when no preferred word is declared.
    pref_word = pick_preferred_word(brief.brand.lexicon_do)
    foco = (
        f"{pref_word} para {brief.primary_kpi.replace('_', ' ')}"
        if pref_word
        else f"foco en {brief.primary_kpi}"
    )
    headline = (
        f"{brief.client.name}: campaña {brief.duration_weeks} semanas para "
        f"{primary_audience} con {foco}."
    )
    one_liner = _truncate(
        f"{brief.product.name} para {primary_audience}: {brief.objective}", 280
    )
    return ExecutiveSummary(
        headline=_truncate(headline, 400),
        one_liner=one_liner,
        primary_objective=brief.objective,
        key_metrics=[
            f"KPI primario: {brief.primary_kpi}",
            f"Duración: {brief.duration_weeks} semanas",
            *(
                [f"Deadline: {brief.deadline.isoformat()}"]
                if brief.deadline
                else []
            ),
        ],
    )


def generate_diagnosis(brief: StrategyInputBrief) -> BusinessDiagnosis:
    has_competitors = bool(brief.competitors_known)
    has_budget = brief.budget_amount is not None
    has_brand_voice = bool(brief.brand.tone_words)

    strengths: list[str] = []
    challenges: list[str] = []
    opportunities: list[str] = []
    assumptions: list[str] = []

    if has_brand_voice:
        strengths.append("Tono de marca articulado por el cliente.")
    else:
        challenges.append("Tono de marca no provisto — se asumirá tono profesional neutro.")
        assumptions.append("Tono neutro y claro; revisar con el cliente.")

    if brief.product.value_props:
        strengths.append(
            f"Propuestas de valor declaradas ({len(brief.product.value_props)}): "
            + ", ".join(brief.product.value_props[:3])
        )
    else:
        challenges.append("Sin propuestas de valor declaradas — se inferirán del objetivo.")

    if has_competitors:
        # MKT-9B: name the competitors explicitly so downstream
        # documents (and the operator) see them at a glance.
        names = ", ".join(c.name for c in brief.competitors_known[:5])
        strengths.append(
            f"{len(brief.competitors_known)} competidor(es) ya identificados: "
            f"{names}."
        )
    else:
        challenges.append("Sin competidores listados — benchmark será de baja confianza.")
        opportunities.append("Investigar competidores antes de campaña en mercado denso.")

    # MKT-9B: surface the forbidden-words guard so the approval
    # reviewer can spot violations early. Listed in challenges
    # because they constrain the copy across every piece.
    if brief.brand.banned_words:
        avoid_preview = ", ".join(
            repr(w) for w in brief.brand.banned_words[:5]
        )
        challenges.append(
            f"Claims/palabras prohibidas declaradas: {avoid_preview}. "
            "Revisar cada pieza antes de aprobar."
        )

    if has_budget:
        strengths.append(
            f"Budget declarado: {brief.budget_amount:.0f} {brief.budget_currency or ''}."
        )
    else:
        assumptions.append("Budget no provisto — recomendaciones priorizan canales orgánicos.")

    if brief.preferred_channels:
        strengths.append(
            "Canales preferidos definidos: " + ", ".join(c.value for c in brief.preferred_channels)
        )

    if not opportunities:
        opportunities.append(
            f"Diferenciación en {brief.client.industry or 'el rubro'} via "
            f"propuesta enfocada en {brief.audience_hints[0].label}."
        )

    stage = "early traction" if brief.budget_amount is None or (brief.budget_amount < 10_000) else "scale-up"

    return BusinessDiagnosis(
        industry=brief.client.industry,
        stage_observed=stage,
        strengths=strengths,
        challenges=challenges,
        opportunities=opportunities,
        assumptions_made=assumptions,
    )


def generate_target_audience(brief: StrategyInputBrief) -> TargetAudience:
    hint = brief.audience_hints[0]
    pains = list(hint.psychographics.get("pains", "").split("|")) if hint.psychographics.get("pains") else []
    outcomes = list(hint.psychographics.get("desired", "").split("|")) if hint.psychographics.get("desired") else []
    return TargetAudience(
        audience_id=new_id(),
        label=hint.label,
        estimated_size_band=_estimated_size_band(hint.estimated_size),  # type: ignore[arg-type]
        demographics=dict(hint.demographics),
        psychographics={
            k: v for k, v in hint.psychographics.items() if k not in ("pains", "desired")
        },
        preferred_channels=list(hint.preferred_channels) or list(brief.preferred_channels),
        pain_points=[p for p in pains if p] or ["Falta de tiempo", "Sobrecarga informativa"],
        desired_outcomes=[o for o in outcomes if o]
        or [f"Lograr {brief.primary_kpi.replace('_', ' ')}"],
    )


def generate_buyer_persona(audience: TargetAudience, brief: StrategyInputBrief) -> BuyerPersona:
    archetype_name = audience.label.split()[0].title() + " típico/a"
    occupation = audience.demographics.get("occupation")
    age_range = audience.demographics.get("age_range") or "28–45"
    return BuyerPersona(
        persona_id=new_id(),
        archetype_name=archetype_name,
        age_range=age_range,
        occupation=occupation,
        a_day_in_life=(
            f"Trabaja desde {audience.demographics.get('geo', 'remoto')}, "
            "balancea múltiples responsabilidades y prioriza herramientas que ahorran tiempo."
        ),
        motivations=audience.desired_outcomes
        or [f"Mejorar {brief.primary_kpi.replace('_', ' ')}"],
        objections=[
            "Ya probé herramientas similares y no funcionaron",
            "No tengo presupuesto para esto ahora",
            "No quiero un proceso de onboarding largo",
        ],
        quotes=[
            f"Necesito {brief.product.name.lower()} sin tener que pensarlo demasiado.",
        ],
    )


def generate_value_proposition(
    brief: StrategyInputBrief, audience: TargetAudience
) -> ValueProposition:
    """Compose a value proposition from real intake content.

    Replaces the MKT-3A placeholder ``"X: Diseñado específicamente para Y"``
    (documented in MKT-4C P-4C.3) with a headline derived from concrete
    intake fields, in priority order:

    1. The first declared ``product.value_props`` entry (when the
       normalizer extracted one from ``product_or_service``).
    2. An intake-specific phrase using ``audience pains`` + a preferred
       word from the brand lexicon when available.
    3. A last-resort headline that still avoids the placeholder.

    The placeholder ``"Diseñado específicamente"`` is NEVER emitted.
    """
    # ---- Differentiators ----
    declared = list(brief.product.value_props)
    fallback_diffs = _fallback_differentiators(brief, audience)
    differentiators = (declared + fallback_diffs)[:5] or fallback_diffs

    # ---- Headline (no placeholder allowed) ----
    pref_word = pick_preferred_word(brief.brand.lexicon_do)
    headline = _compose_value_headline(
        brief=brief,
        audience=audience,
        differentiator=differentiators[0] if differentiators else None,
        preferred=pref_word,
    )

    proof_points = [
        f"Producto/servicio: {brief.product.name}",
        *(
            [f"Industria: {brief.client.industry}"]
            if brief.client.industry
            else []
        ),
    ]

    return ValueProposition(
        headline=_truncate(headline, 280),
        category=brief.client.industry or "marketing tooling",
        target_audience_label=audience.label,
        differentiators=differentiators[:5],
        proof_points=proof_points,
        primary_benefit=differentiators[0] if differentiators else None,
        notes=brief.additional_context,
    )


def _fallback_differentiators(
    brief: StrategyInputBrief, audience: TargetAudience
) -> list[str]:
    """Build differentiators from concrete intake data when
    ``product.value_props`` is empty. Never returns the legacy
    placeholder."""
    out: list[str] = []
    pains = audience.pain_points or []
    if pains:
        out.append(f"Resuelve un dolor concreto: {pains[0]}")
    if brief.product.description:
        # First sentence of the description; capped.
        first_sentence = brief.product.description.split(".")[0].strip()
        if first_sentence and len(first_sentence) > 12:
            out.append(_truncate(first_sentence, 160))
    if brief.objective:
        out.append(_truncate(f"Mide impacto contra: {brief.objective}", 160))
    # Generic backstops that don't echo audience/product names.
    out.extend([
        "Setup en menos de un día",
        "Sin contratos largos",
    ])
    return out


def _compose_value_headline(
    *,
    brief: StrategyInputBrief,
    audience: TargetAudience,
    differentiator: str | None,
    preferred: str | None,
) -> str:
    """Compose a non-placeholder headline. Tries three forms in order
    of specificity and returns the first one that actually contains
    intake-derived content."""
    product = brief.product.name
    pain = (audience.pain_points or [None])[0]

    # Form 1: pain-led, with preferred word if available.
    if pain:
        if preferred:
            return f"{product}: {preferred} para resolver {pain.lower()}."
        return f"{product}: enfocado en resolver {pain.lower()}."

    # Form 2: differentiator-led (avoids the placeholder by virtue of
    # _fallback_differentiators never returning it).
    if differentiator:
        return f"{product}: {differentiator}."

    # Form 3: objective-led last resort.
    if brief.objective:
        return f"{product} — diseñado alrededor de: {brief.objective}."

    return f"{product}: la propuesta concreta para {audience.label}."


def generate_competitor_benchmark(competitors: list[_InputCompetitor]) -> CompetitorBenchmark:
    entries = [
        CompetitorEntry(
            name=c.name,
            url=c.url,
            positioning_summary=c.positioning_summary or (
                # MKT-9B: fall back to notes when the normalizer did not
                # extract an explicit positioning summary, so each
                # competitor entry shows SOMETHING the operator can act on.
                (c.notes or "")[:280] if c.notes else None
            ),
            observed_strengths=c.strengths,
            observed_weaknesses=c.weaknesses,
            differentiating_angle_for_us=(
                "Posicionarse en oposición a " + ", ".join(c.weaknesses[:2])
                if c.weaknesses
                else None
            ),
        )
        for c in competitors
    ]
    if not entries:
        return CompetitorBenchmark(
            competitors=[],
            overall_takeaway="Sin competidores provistos — recomendado relevar antes de Fase 4.",
            market_gaps_identified=[],
            confidence="low",
        )
    # MKT-9B: include competitor names in the takeaway so the read
    # of the strategy report mentions them at least once.
    names_preview = ", ".join(e.name for e in entries[:3])
    return CompetitorBenchmark(
        competitors=entries,
        overall_takeaway=(
            f"{len(entries)} competidor(es) identificados ({names_preview}). "
            "Ver fortalezas y debilidades por competidor para encontrar "
            "ángulos diferenciales."
        ),
        market_gaps_identified=[
            f"Debilidad común: {w}"
            for c in entries
            for w in c.observed_weaknesses[:1]
        ][:3],
        confidence="medium" if len(entries) >= 2 else "low",
    )


def generate_channel_recommendation(
    brief: StrategyInputBrief, audience: TargetAudience
) -> ChannelRecommendation:
    seed: list[ChannelType] = []
    seed.extend(audience.preferred_channels)
    seed.extend(brief.preferred_channels)

    # Deduplicate while preserving order.
    seen: set[ChannelType] = set()
    ordered: list[ChannelType] = []
    for c in seed:
        if c not in seen:
            ordered.append(c)
            seen.add(c)

    # Backfill defaults if too few.
    for default in [*_OWNED_DEFAULTS, *_SOCIAL_DEFAULTS]:
        if len(ordered) >= 5:
            break
        if default not in seen:
            ordered.append(default)
            seen.add(default)

    ordered = ordered[:5]

    role_map = {
        ChannelType.NEWSLETTER: ("nurture", "Semanal o quincenal."),
        ChannelType.BLOG: ("acquisition", "1–2 por semana."),
        ChannelType.LINKEDIN: ("engagement", "3 posts/semana + 1 carrusel."),
        ChannelType.INSTAGRAM: ("engagement", "4 posts/semana + 2 reels."),
        ChannelType.X: ("engagement", "Hilo + 4 posts cortos/semana."),
        ChannelType.PODCAST: ("acquisition", "Episodio mensual o invitaciones."),
        ChannelType.YOUTUBE: ("acquisition", "1 video/semana."),
        ChannelType.TIKTOK: ("engagement", "3 videos/semana."),
        ChannelType.SEO: ("acquisition", "Continuo."),
        ChannelType.PAID_SEARCH: ("conversion", "Always-on, presupuesto controlado."),
        ChannelType.PAID_SOCIAL: ("conversion", "Always-on, retargeting prioritario."),
        ChannelType.EMAIL: ("conversion", "Secuencia + broadcasts."),
        ChannelType.FACEBOOK: ("engagement", "2 posts/semana."),
        ChannelType.DISPLAY: ("awareness", "Retargeting acotado."),
        ChannelType.PR: ("awareness", "Esporádico."),
        ChannelType.OTHER: ("engagement", "Revisar caso a caso."),
    }

    # MKT-9B: enriched rationale that grounds each channel in the
    # actual intake — uses the commercial objective, the product
    # one-liner and a short reason tied to the channel's role,
    # instead of the previous boilerplate "Match con audiencia (X);
    # rol esperado: Y." that read identically for every channel.
    objective_hint = (brief.objective or "").strip()
    product_hint = (
        getattr(brief.product, "description", None) or brief.product.name or ""
    ).strip()
    per_channel_reason: dict[ChannelType, str] = {
        ChannelType.LINKEDIN: (
            "Audiencia profesional B2B donde se construye autoridad y "
            "se generan demos cualificadas."
        ),
        ChannelType.EMAIL: (
            "Canal directo de conversión y nurture — secuencias 1:1 "
            "para mover lead a demo."
        ),
        ChannelType.NEWSLETTER: (
            "Owned media de bajo costo para mantener atención entre "
            "ciclos de compra."
        ),
        ChannelType.BLOG: (
            "SEO de fondo + activos reutilizables para el resto de "
            "los canales."
        ),
        ChannelType.SEO: (
            "Adquisición orgánica sostenida; complementa los "
            "esfuerzos owned con descubrimiento de marca."
        ),
        ChannelType.INSTAGRAM: (
            "Soporte para humanizar la marca y mostrar producto "
            "en contexto; secundario al canal principal."
        ),
        ChannelType.X: (
            "Conversación rápida con la audiencia técnica del nicho; "
            "amplifica contenido de blog/LinkedIn."
        ),
        ChannelType.YOUTUBE: (
            "Tutoriales y demos extendidas que reducen fricción "
            "para la conversión."
        ),
        ChannelType.PODCAST: (
            "Tiempo largo con prospectos de alto valor; complementa "
            "el canal principal."
        ),
        ChannelType.TIKTOK: (
            "Alcance amplio; testear si la audiencia objetivo está "
            "presente antes de invertir."
        ),
        ChannelType.PAID_SEARCH: (
            "Capturar intent de búsqueda específico, condicionado al "
            "presupuesto disponible."
        ),
        ChannelType.PAID_SOCIAL: (
            "Retargeting y amplificación del contenido orgánico; "
            "asignar presupuesto controlado."
        ),
        ChannelType.FACEBOOK: (
            "Audiencia generalista; útil para retargeting pero no "
            "primario."
        ),
        ChannelType.DISPLAY: "Retargeting acotado, no adquisición principal.",
        ChannelType.PR: "Relaciones públicas esporádicas, no programáticas.",
        ChannelType.OTHER: "Revisar caso a caso con el equipo de cuenta.",
    }

    entries: list[ChannelEntry] = []
    for i, ch in enumerate(ordered):
        role, cadence = role_map.get(ch, ("engagement", None))
        reason = per_channel_reason.get(
            ch,
            f"Match con audiencia ({audience.label}); rol esperado: {role}.",
        )
        # Compose: audience fit + role + reason + objective tie-in.
        rationale_parts = [
            f"Audiencia: {audience.label}.",
            f"Rol: {role}.",
            reason,
        ]
        if objective_hint:
            rationale_parts.append(f"Conecta con: {objective_hint}.")
        elif product_hint:
            rationale_parts.append(f"Apoya a: {product_hint}.")
        rationale = " ".join(rationale_parts)
        entries.append(
            ChannelEntry(
                channel_type=ch,
                label=f"{ch.value} (rol: {role})",
                priority=i + 1,
                rationale=rationale[:600],
                cadence_suggestion=cadence,
                expected_role=role,
            )
        )

    out_of_scope = [
        c
        for c in _OUT_OF_SCOPE_DEFAULTS
        if c not in seen
    ]

    # Rationale overall now mentions the top-2 channels by name so
    # the read is not just "Mix de canales priorizado".
    top2 = [e.channel_type.value for e in entries[:2]]
    top2_text = ", ".join(top2) if top2 else "canales seleccionados"
    overall = (
        f"Mix priorizado para {audience.label}. "
        f"Foco inicial en {top2_text}: combinan adquisición y "
        "conversión con costo controlado. "
        "Owned (newsletter/blog) sostiene el ciclo; "
        "paid queda condicionado al presupuesto disponible."
    )

    return ChannelRecommendation(
        channels=entries,
        total_channels=len(entries),
        rationale_overall=overall[:600],
        out_of_scope_channels=out_of_scope,
    )


def generate_keyword_plan(
    brief: StrategyInputBrief,
    audience: TargetAudience,
    value_prop: ValueProposition,
) -> KeywordPlan:
    """Build keyword + hashtag plan from real intake content.

    Replaces MKT-3A's naive ASCII slug + token split (P-4C.4, P-4C.5)
    with Unicode-aware normalization (NFD) + Spanish stopword filter
    + minimum-length / generic-token rejection. Junk seeds like
    ``sin``, ``diseado``, ``setup`` are dropped.
    """
    # ---- Seeds (curated for meaningfulness) ----
    from .style import normalize_for_slug

    seeds: list[str] = []

    # Product name slug — always kept if meaningful.
    product_slug = normalize_for_slug(brief.product.name)
    if product_slug and is_meaningful_keyword(product_slug.split(" ")[0]):
        seeds.append(product_slug)

    # Industry slug — kept as a multi-word phrase.
    if brief.client.industry:
        industry_slug = normalize_for_slug(brief.client.industry)
        if industry_slug:
            seeds.append(industry_slug)

    # First meaningful token from each top differentiator — filters out
    # stopwords (``sin``), generic tokens (``setup``), short verbs
    # (``diseado``).
    for d in value_prop.differentiators[:3]:
        tok = first_meaningful_token(d)
        if tok and tok not in seeds:
            seeds.append(tok)

    # Audience first meaningful token, or product slug as fallback.
    audience_token = (
        first_meaningful_token(audience.label)
        or product_slug.split(" ")[0]
        or "equipos"
    )

    # ---- Clusters ----
    clusters: list[KeywordCluster] = []
    for seed in seeds[:5]:
        clusters.append(
            KeywordCluster(
                label=f"{seed}_informational",
                intent="informational",
                keywords=[
                    f"qué es {seed}",
                    f"{seed} para {audience_token}",
                    f"cómo usar {seed}",
                    f"guía {seed}",
                ],
                suggested_match="phrase",
            )
        )

    if product_slug:
        clusters.append(
            KeywordCluster(
                label=f"{product_slug}_transactional",
                intent="transactional",
                keywords=[
                    f"comprar {product_slug}",
                    f"{product_slug} precio",
                    f"{product_slug} alternativa",
                    f"contratar {product_slug}",
                ],
                suggested_match="exact",
            )
        )

    # ---- Negatives ----
    competitor_negatives = [c.name.lower() for c in brief.competitors_known]
    negatives = sorted(set([*_GENERIC_NEGATIVES, *competitor_negatives]))

    # ---- Hashtags (Unicode-aware) ----
    hashtags_set: set[str] = set(_GENERIC_HASHTAGS)
    candidates = [brief.product.name]
    if brief.client.industry:
        candidates.append(brief.client.industry)
    # Up to 2 preferred words as hashtags — the client picked them.
    candidates.extend(brief.brand.lexicon_do[:2])
    for c in candidates:
        h = make_hashtag(c)
        if h:
            hashtags_set.add(h)
    hashtags = sorted(hashtags_set)[:10]

    return KeywordPlan(
        clusters=clusters[:6],
        negative_keywords=negatives,
        hashtags=hashtags,
        source="reasoning_only",
        notes=(
            "v1: keywords derivadas del brief sin volumen. Validar con GA4 / GSC cuando "
            "los adapters R3 estén disponibles."
        ),
    )


def generate_campaign_strategy(
    brief: StrategyInputBrief, value_prop: ValueProposition
) -> CampaignStrategy:
    return CampaignStrategy(
        objective=brief.objective,
        duration_weeks=brief.duration_weeks,
        primary_kpi=brief.primary_kpi,
        secondary_kpis=[
            "cost_per_acquisition",
            "engagement_rate",
            "newsletter_growth",
        ],
        funnel_focus="full_funnel",
        budget_estimate=brief.budget_amount,
        budget_currency=brief.budget_currency,
        big_idea=value_prop.headline,
        narrative_arc=[
            "Semana 1–2: awareness — presentamos la categoría y el problema.",
            "Semana 3–4: consideration — diferenciadores y proof points.",
            "Semana 5–6: conversion — oferta y CTA claros.",
            "Semana 7–8: retention — onboarding y casos.",
        ][: max(1, brief.duration_weeks // 2)],
    )


def generate_suggested_pieces(
    brief: StrategyInputBrief, channels: ChannelRecommendation
) -> list[SuggestedPiece]:
    pieces: list[SuggestedPiece] = []
    for ch in channels.channels[:4]:
        if ch.channel_type is ChannelType.NEWSLETTER:
            pieces.append(SuggestedPiece(
                piece_type="email_campaign",
                channel=ch.channel_type,
                purpose="Lanzamiento + secuencia nurture",
                quantity=4,
            ))
        elif ch.channel_type is ChannelType.BLOG:
            pieces.append(SuggestedPiece(
                piece_type="seo_article",
                channel=ch.channel_type,
                purpose="Capturar tráfico de búsqueda informacional",
                quantity=6,
            ))
        elif ch.channel_type in (ChannelType.LINKEDIN, ChannelType.X, ChannelType.FACEBOOK):
            pieces.append(SuggestedPiece(
                piece_type="social_post_thread",
                channel=ch.channel_type,
                purpose="Distribuir insights y hooks",
                quantity=8,
            ))
        elif ch.channel_type in (ChannelType.INSTAGRAM, ChannelType.TIKTOK):
            pieces.append(SuggestedPiece(
                piece_type="reels_short_form",
                channel=ch.channel_type,
                purpose="Hooks visuales + storytelling",
                quantity=6,
            ))
        else:
            pieces.append(SuggestedPiece(
                piece_type="copy_pack",
                channel=ch.channel_type,
                purpose="Mensajería de soporte para el canal",
                quantity=3,
            ))
    return pieces


def generate_creative_brief_pack(
    brief: StrategyInputBrief,
    value_prop: ValueProposition,
    audience: TargetAudience,
) -> CreativeBriefPack:
    palette_hint = ["#0F172A", "#22D3EE", "#F8FAFC"]  # default neutral + accent
    typography_hint = "Sans-serif moderno; jerarquía clara; nada decorativo."
    diffs = value_prop.differentiators or [value_prop.headline]

    briefs = [
        CreativeBriefEntry(
            brief_id=new_id(),
            title=f"Hero campaña — {brief.product.name}",
            piece_type="hero_image",
            aspect_ratio="16:9",
            visual_concept=(
                f"Composición editorial mostrando a {audience.label} usando {brief.product.name}. "
                "Espacio negativo para overlay de copy."
            ),
            palette_hint=palette_hint,
            typography_hint=typography_hint,
            copy_overlay=[value_prop.headline, "Empezá hoy"],
            cta="Empezá hoy",
            accessibility_notes=["Contraste AA mínimo", "Texto legible a 320px"],
            prompt_for_image_model=(
                f"Editorial hero image, professional, modern, target audience: {audience.label}. "
                f"Product context: {brief.product.name}. Mood: confident, calm. "
                "Negative space top-right for headline overlay. No stock-cliché handshakes. "
                "16:9 aspect ratio."
            ),
        ),
        CreativeBriefEntry(
            brief_id=new_id(),
            title=f"Carrusel diferenciadores — {brief.product.name}",
            piece_type="instagram_carousel",
            aspect_ratio="1:1",
            visual_concept=(
                f"Un slide por diferenciador ({len(diffs)}). Tipografía dominante, ilustraciones simples."
            ),
            palette_hint=palette_hint,
            typography_hint=typography_hint,
            copy_overlay=diffs[:4],
            cta="Probalo gratis",
            accessibility_notes=["Texto >= 24px", "Sin animaciones"],
            prompt_for_image_model=(
                "Instagram carousel template, 1:1, minimal, typography-led. "
                f"Topic: {value_prop.category}. One key message per slide. "
                "Generic friendly illustrations, no people stock photos."
            ),
        ),
        CreativeBriefEntry(
            brief_id=new_id(),
            title="Reels cover frame",
            piece_type="reels_thumbnail",
            aspect_ratio="9:16",
            visual_concept=(
                f"Close-up con hook visual de {value_prop.differentiators[0] if value_prop.differentiators else 'la propuesta'}."
            ),
            palette_hint=palette_hint,
            typography_hint=typography_hint,
            copy_overlay=["3 segundos para enganchar"],
            cta="Mirá el reel",
            accessibility_notes=["Texto centrado evitando zonas de UI"],
            prompt_for_image_model=(
                "Vertical 9:16 thumbnail for a Reel. Strong visual hook, single human face "
                "or product detail, bold title text top-third. No watermarks."
            ),
        ),
    ]

    return CreativeBriefPack(
        briefs=briefs,
        overall_visual_direction=(
            "Editorial moderna, tipografía dominante, paleta neutra con un acento. "
            "Evitar cliché de stock corporativo."
        ),
        do_not_use=[
            "Stock photos de handshakes",
            "Gradientes púrpura genéricos",
            "Iconografía clip-art",
            *brief.brand.banned_words,
        ],
    )


def generate_social_post_drafts(
    brief: StrategyInputBrief,
    value_prop: ValueProposition,
    channels: ChannelRecommendation,
    keyword_plan: KeywordPlan,
) -> list[SocialPostDraft]:
    drafts: list[SocialPostDraft] = []
    product = brief.product.name
    persona_token = brief.audience_hints[0].label.lower()
    topic = brief.client.industry or "esto"
    pain_token = (
        brief.audience_hints[0].psychographics.get("pains", "tareas repetitivas").split("|")[0]
        if brief.audience_hints[0].psychographics.get("pains")
        else "tareas repetitivas"
    )
    diff = value_prop.differentiators[0] if value_prop.differentiators else "Te ahorra tiempo"

    # Tone-aware connector + adjective, picked once per run.
    adjective = tone_adjective(brief.brand.tone_words)
    connector = tone_connector(brief.brand.tone_words)

    # Channel-specific copy. Each channel gets its OWN hook + body so
    # the output stops being a template echo across 3+ surfaces.
    channel_voices: dict[str, tuple[str, str, str]] = {
        # channel_value: (hook_template, body_template, cta)
        "newsletter": (
            "Esta semana, un experimento {adjective}: {pain} sin la opción de siempre.",
            "Lo que probamos: usar {product} para algo {adjective} que veníamos posponiendo. "
            "{connector}, {diff}. Te dejamos el detalle abajo — un caso, dos números, una decisión.",
            "Leer el caso →",
        ),
        "blog": (
            "Cómo hicimos {topic} sin {pain}: un walkthrough.",
            "Documentamos paso por paso. Stack, decisiones, los puntos donde nos equivocamos. "
            "{connector}, {diff}.",
            "Leer el post →",
        ),
        "linkedin": (
            "3 decisiones {adjective}s que tomamos esta semana en {product}.",
            "{connector}, las comparto sin filtro: qué probamos, qué descartamos, "
            "qué dejamos andando. {diff}.",
            "Ver el detalle →",
        ),
        "x": (
            "{product}, en {short_diff}.",
            "Para {persona} que se cansaron de {pain}. {connector}, así lo armamos.",
            "Mirá →",
        ),
        "instagram": (
            "El problema no era la herramienta. Era cómo la usábamos.",
            "Carrusel con la decisión, el cambio y el resultado. {connector}, {diff}.",
            "Ver carrusel →",
        ),
    }
    default_voice = (
        "{product}: lo que probamos esta semana.",
        "{connector}, {diff}.",
        "Conocé cómo →",
    )

    short_diff = _truncate(diff, 60)

    # Pull a preferred word per channel so the lexicon shows up but
    # not always the same word in every post.
    pref_iter = iter(brief.brand.lexicon_do)

    for i, ch in enumerate(channels.channels[:5]):
        hook_t, body_t, cta_t = channel_voices.get(ch.channel_type.value, default_voice)
        pref = next(pref_iter, None)
        format_kwargs = dict(
            persona=persona_token, pain=pain_token, topic=topic, product=product,
            adjective=adjective, connector=connector, diff=diff,
            short_diff=short_diff,
        )
        hook = hook_t.format(**format_kwargs)
        body = body_t.format(**format_kwargs)
        # Weave one preferred word in if it's not already in the body.
        if pref and pref.lower() not in body.lower():
            body = f"{body} ({pref})"
        drafts.append(
            SocialPostDraft(
                post_id=new_id(),
                channel=ch.channel_type,
                hook=_truncate(hook, 300),
                body=body,
                cta=cta_t,
                hashtags=keyword_plan.hashtags[:4],
                suggested_send_at=f"Semana {i + 1} · mar 10:00",
            )
        )
    return drafts


def generate_email_sequence(
    brief: StrategyInputBrief,
    value_prop: ValueProposition,
    audience: TargetAudience,
) -> EmailSequenceDraft:
    product = brief.product.name
    diffs = value_prop.differentiators or [value_prop.headline]
    opener = tone_opener(brief.brand.tone_words)
    pref1 = pick_preferred_word(brief.brand.lexicon_do)
    pref2 = pick_preferred_word(brief.brand.lexicon_do, already_used=[pref1] if pref1 else [])
    objective = brief.objective

    pref1_phrase = f" ({pref1})" if pref1 else ""

    emails: list[EmailDraft] = [
        EmailDraft(
            email_id=new_id(),
            step=1,
            subject=_truncate(f"Bienvenida a {product}", 80),
            preview_text=_truncate("Empezamos por lo más importante.", 140),
            body=(
                f"Hola,\n\nGracias por sumarte a {product}.\n\n"
                f"{opener} este recorrido apunta a un objetivo concreto: {objective}{pref1_phrase}.\n\n"
                "Empezá por acá: revisá la guía de setup (5 min).\n\nAbrazo,\nEl equipo"
            ),
            cta="Ver guía de setup",
            send_after_days=0,
        ),
        EmailDraft(
            email_id=new_id(),
            step=2,
            subject=_truncate(f"3 cosas que {product} hace distinto", 80),
            preview_text=_truncate("Lo que cambia respecto al status quo.", 140),
            body=(
                "Hola,\n\n"
                + (f"{opener} " if opener else "")
                + (f"resumido en una palabra: {pref2}.\n\n" if pref2 else "")
                + f"Tres puntos donde {product} cambia el statu quo:\n\n"
                + "\n".join(f"• {d}" for d in diffs[:3])
                + "\n\nSi querés, lo charlamos en 15 minutos.\n\nAbrazo"
            ),
            cta="Agendar 15 min",
            send_after_days=2,
        ),
        EmailDraft(
            email_id=new_id(),
            step=3,
            subject=_truncate("Cómo lo usaron otros equipos", 80),
            preview_text=_truncate("Casos reales — sin maquillaje.", 140),
            body=(
                "Hola,\n\nUn par de casos rápidos de cómo otros equipos usan "
                f"{product}.\n\n[Insertar 2 casos cortos — pending para revisión humana.]\n\n"
                "Si querés ver más casos, escribime a este email.\n\nAbrazo"
            ),
            cta="Ver más casos",
            send_after_days=5,
        ),
        EmailDraft(
            email_id=new_id(),
            step=4,
            subject=_truncate("Tu próximo paso con " + product, 80),
            preview_text=_truncate("Sin presión — y un descuento si te suma.", 140),
            body=(
                f"Hola,\n\nDespués de esta semana con {product} probablemente ya tengas "
                "una idea clara de si te suma o no.\n\n"
                "Si querés avanzar, te dejamos un descuento por activación esta semana.\n\n"
                "Si no, no pasa nada — quedamos a la mano cuando lo necesites.\n\n"
                "Gracias por haber leído hasta acá.\n\nAbrazo"
            ),
            cta="Activar con descuento",
            send_after_days=10,
        ),
    ]

    return EmailSequenceDraft(
        sequence_name=f"{brief.client.name} — nurture {brief.duration_weeks}w",
        goal=brief.objective,
        audience_label=audience.label,
        emails=emails,
    )


def generate_reels_script_pack(
    brief: StrategyInputBrief,
    value_prop: ValueProposition,
    audience: TargetAudience,
) -> ReelsScriptPack:
    product = brief.product.name
    diffs = value_prop.differentiators or [value_prop.headline]
    # MKT-4D: tone-aware reels voiceover. The legacy line
    # ``f"{product} cambia eso porque {diffs[0]}."`` produced
    # ungrammatical voiceover when diffs[0] was a noun phrase
    # ("Diseñado específicamente para X"). The new line is a
    # complete sentence regardless of differentiator shape.
    pain_token = (
        brief.audience_hints[0].psychographics.get("pains", "").split("|")[0]
        if brief.audience_hints and brief.audience_hints[0].psychographics.get("pains")
        else "lo mismo de siempre"
    )
    pref_word = pick_preferred_word(brief.brand.lexicon_do)
    pref_suffix = f" — {pref_word}." if pref_word else "."

    scripts = [
        ReelsScriptEntry(
            script_id=new_id(),
            title=_truncate(f"Hook #1 — el problema de {audience.label}", 200),
            hook=_truncate(
                f"Si sos {audience.label.lower()}, esto te va a sonar.", 200
            ),
            beats=[
                "0-3s: hook con problema concreto",
                "3-12s: muestra el dolor en pantalla",
                "12-25s: contraste — cómo cambia con la solución",
                "25-30s: CTA",
            ],
            voiceover_lines=[
                f"La mayoría de {audience.label.lower()} pierde tiempo en {pain_token}.",
                f"Con {product} eso cambia{pref_suffix}",
                "Probalo hoy.",
            ],
            on_screen_text=[
                "¿Te suena?",
                diffs[0],
                "Empezá hoy",
            ],
            cta="Empezá hoy",
            target_duration_s=30,
        ),
        ReelsScriptEntry(
            script_id=new_id(),
            title="Hook #2 — los 3 errores comunes",
            hook=_truncate(
                f"3 errores comunes en {brief.client.industry or 'marketing'} (y cómo evitarlos).",
                200,
            ),
            beats=[
                "0-3s: anuncio del tema",
                "3-30s: tres errores concretos",
                "30-45s: solución (producto)",
                "45-50s: CTA",
            ],
            voiceover_lines=[
                "Estos 3 errores los vemos seguido.",
                # MKT-4D: derived from real diffs when available — used
                # to literally read "Error 1, error 2, error 3."
                ". ".join(diffs[:3]) + ".",
                f"{product} los resuelve.",
                "Probalo.",
            ],
            on_screen_text=[
                _truncate(d, 40) for d in diffs[:3]
            ] + ["Solución"],
            cta="Ver más",
            target_duration_s=50,
        ),
        ReelsScriptEntry(
            script_id=new_id(),
            title="Hook #3 — testimonio rápido",
            hook="Esto fue lo que nos dijeron en la primera semana.",
            beats=[
                "0-3s: hook con cita",
                "3-20s: caso concreto",
                "20-30s: CTA",
            ],
            voiceover_lines=[
                "Esto fue lo que nos dijeron.",
                "[Insertar cita de cliente real — pending revisión humana.]",
                "Si te suena, probalo.",
            ],
            on_screen_text=[
                "Caso real",
                "Resultado en 1 semana",
                "Probalo",
            ],
            cta="Probalo gratis",
            target_duration_s=30,
        ),
    ]

    return ReelsScriptPack(
        scripts=scripts,
        overall_tone=(
            "Directo, sin floritura, ritmo rápido. Sin música épica, sin clichés de stock."
        ),
    )


def generate_schedule(
    brief: StrategyInputBrief, channels: ChannelRecommendation
) -> CampaignSchedule:
    weeks = brief.duration_weeks
    start = date.today() if brief.deadline is None else (
        brief.deadline - timedelta(weeks=weeks)
    )
    end = start + timedelta(weeks=weeks)

    entries: list[ScheduleEntry] = []
    for week in range(1, weeks + 1):
        for ch in channels.channels[:3]:
            entries.append(
                ScheduleEntry(
                    week=week,
                    channel=ch.channel_type,
                    piece_type=(
                        "email" if ch.channel_type is ChannelType.NEWSLETTER else
                        "article" if ch.channel_type is ChannelType.BLOG else
                        "post"
                    ),
                    cadence_note=ch.cadence_suggestion,
                )
            )

    return CampaignSchedule(
        weeks_total=weeks,
        start_date=start,
        end_date=end,
        entries=entries,
        notes=(
            "Calendario semanal. Ajustar según disponibilidad real del equipo del cliente."
        ),
    )


def generate_approval_checklist() -> ApprovalChecklist:
    items = [
        ChecklistItem(
            item_id=new_id(),
            title="Validar tono y voz de marca contra muestras existentes",
            severity="must",
            category="strategy",
        ),
        ChecklistItem(
            item_id=new_id(),
            title="Confirmar audiencia primaria con cliente",
            severity="blocker",
            category="strategy",
        ),
        ChecklistItem(
            item_id=new_id(),
            title="Validar claims marketinis pendientes (ver Sección 19)",
            severity="blocker",
            category="compliance",
        ),
        ChecklistItem(
            item_id=new_id(),
            title="Revisar briefs de creativos antes de pasar a producción",
            severity="must",
            category="creative",
        ),
        ChecklistItem(
            item_id=new_id(),
            title="Validar copies de email con cliente",
            severity="must",
            category="creative",
        ),
        ChecklistItem(
            item_id=new_id(),
            title="Revisar scripts de reels — incluir solo si están aprobados",
            severity="must",
            category="creative",
        ),
        ChecklistItem(
            item_id=new_id(),
            title="Confirmar canales activos y handles",
            severity="must",
            category="operational",
        ),
        ChecklistItem(
            item_id=new_id(),
            title="Programar setup de tracking (UTMs, eventos) antes de lanzar",
            severity="must",
            category="operational",
        ),
        ChecklistItem(
            item_id=new_id(),
            title="Definir responsable de aprobación por área",
            severity="must",
            category="operational",
        ),
        ChecklistItem(
            item_id=new_id(),
            title="Revisión legal de claims y referencias a terceros",
            severity="should",
            category="compliance",
        ),
    ]
    return ApprovalChecklist(
        items=items,
        approvers_required=["account_lead", "client_marketing_lead"],
    )


def generate_risk_assessment(
    value_prop: ValueProposition,
    competitor_benchmark: CompetitorBenchmark,
    brief: StrategyInputBrief | None = None,
    generated_corpus: str | None = None,
) -> RiskAssessment:
    risks: list[RiskItem] = []

    for d in value_prop.differentiators[:3]:
        risks.append(
            RiskItem(
                risk_id=new_id(),
                description=f"Diferenciador sin fuente verificada: '{d}'",
                severity="medium",
                mitigation="Pedir al cliente una fuente / caso / dato que respalde antes de publicar.",
                claim_text=d,
            )
        )

    if competitor_benchmark.confidence == "low":
        risks.append(
            RiskItem(
                risk_id=new_id(),
                description="Benchmark de competidores de baja confianza.",
                severity="medium",
                mitigation="Investigar 3–5 competidores reales antes de lanzar.",
            )
        )

    # MKT-4D: forbidden words from brand.banned_words scanned against
    # generated text. Each hit becomes a high-severity risk so the
    # human reviewer sees it before approving.
    if brief and generated_corpus and brief.brand.banned_words:
        from .style import contains_forbidden, matches_bad_example_pattern

        found = contains_forbidden(generated_corpus, brief.brand.banned_words)
        for word in found:
            risks.append(
                RiskItem(
                    risk_id=new_id(),
                    description=f"Palabra prohibida detectada en outputs: '{word}'",
                    severity="high",
                    mitigation=(
                        "Reescribir la pieza que contiene la palabra. El intake "
                        "del cliente declaró esta palabra como prohibida."
                    ),
                    claim_text=word,
                )
            )

        # bad_examples — flag pieces that fit a known anti-pattern.
        bad_hits = matches_bad_example_pattern(
            generated_corpus, brief.brand.bad_examples
        )
        for example in bad_hits:
            risks.append(
                RiskItem(
                    risk_id=new_id(),
                    description=(
                        "Output coincide con un patrón marcado como bad_example: "
                        f"'{_truncate(example, 80)}'"
                    ),
                    severity="medium",
                    mitigation=(
                        "Revisar la pieza coincidente y reescribir alineada a "
                        "los good_examples del intake."
                    ),
                )
            )

    risks.append(
        RiskItem(
            risk_id=new_id(),
            description="Outputs generados deterministicamente — no LLM ni datos en vivo.",
            severity="low",
            mitigation=(
                "Revisión humana antes de aprobar; refinar con datos reales cuando "
                "los MCPs estén disponibles (post MKT-2C)."
            ),
        )
    )

    return RiskAssessment(
        risks=risks,
        unverified_claims_count=sum(1 for r in risks if r.claim_text),
        requires_compliance_audit=any(r.claim_text for r in risks),
    )


def generate_next_steps() -> list[str]:
    return [
        "Revisar el reporte con account lead y cliente.",
        "Validar audiencia primaria, propuesta de valor y claims pendientes.",
        "Pasar creatives aprobados a producción.",
        "Configurar tracking (UTMs, eventos GA4).",
        "Cargar copies de email a la ESP elegida.",
        "Definir fecha de lanzamiento concreta.",
        "Programar review semanal de métricas.",
    ]
