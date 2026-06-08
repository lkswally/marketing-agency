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
    tone_adjective_for_brief,
    tone_connector_for_brief,
    tone_family_for_brief,
    tone_opener_for_brief,
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


# ---------- MKT-9C: domain-aware extraction helpers ----------
#
# These helpers stay pure / LLM-free. They look for high-signal
# substrings in the intake text and turn them into concrete pain
# phrases. The goal is to stop emitting the legacy "Falta de
# tiempo" / "Sobrecarga informativa" fallback when the intake
# carries enough material to do better.


# Lower-case anti-pattern tokens we recognise in audience
# descriptions. When present, they suggest the audience lives in
# a disjointed manual workflow — a pain we can name explicitly.
_ANTIPATTERN_TOKENS: tuple[str, ...] = (
    "excel", "planilla", "planillas",
    "whatsapp", "wsp",
    "carpeta", "carpetas",
    "recordatorio manual", "recordatorios manuales",
    "manual", "manuales", "manualmente",
    "papel", "papeles",
    "mail suelto", "mails sueltos",
    "post-it", "post it",
)

# Stop-words inside product feature lists. After splitting the
# product description at colons / em-dashes, we drop these.
_FEATURE_STOPWORDS: frozenset[str] = frozenset({
    "y", "o", "u", "para", "de", "del", "la", "el", "los", "las",
    "con", "en", "a", "al", "que", "como",
})

# A small set of "inverse modifiers" used to turn a product feature
# noun into a pain phrase. The modifier rotates per feature so the
# final list does not repeat "desordenados" five times.
_PAIN_INVERSES: tuple[str, ...] = (
    "desordenados",
    "sin trazabilidad",
    "dispersas",
    "que se pierden",
    "sin seguimiento",
    "manuales",
)


def _extract_product_features(brief: StrategyInputBrief) -> list[str]:
    """Pull a list of concrete features from the product description.

    The intake's ``product_or_service`` is typically a string with a
    feature list after a colon or em-dash::

        "LEXIA — software de gestión legal para abogados y estudios
         jurídicos: expedientes, vencimientos, tareas, honorarios,
         seguimiento judicial, informes a clientes y antecedentes."

    Returns the post-colon feature tokens (``["expedientes",
    "vencimientos", "tareas", "honorarios", "seguimiento judicial",
    "informes a clientes", "antecedentes"]``).
    """

    description = (brief.product.description or "").strip()
    if not description:
        return []
    # The feature list lives after the first ``:`` in real intakes.
    # If there is no colon, look at the value props list — those
    # are extracted by the normalizer in the same shape.
    after_colon = description.split(":", 1)[1] if ":" in description else ""
    if not after_colon and brief.product.value_props:
        # The first value_prop usually carries the same feature list.
        first = brief.product.value_props[0]
        after_colon = first.split(":", 1)[1] if ":" in first else first
    if not after_colon:
        return []
    # Take the first sentence (period or newline ends the list).
    chunk = after_colon.split(".", 1)[0].split("\n", 1)[0]
    raw_features = [f.strip() for f in chunk.replace(" y ", ",").split(",")]
    features: list[str] = []
    for f in raw_features:
        f_clean = f.strip(" .;–—-:")
        if not f_clean:
            continue
        tokens = f_clean.lower().split()
        # Drop pure-stopword fragments ("y antecedentes" → already
        # split, but be defensive against odd punctuation).
        if all(t in _FEATURE_STOPWORDS for t in tokens):
            continue
        features.append(f_clean)
    # Cap so we never blow up the pain list later.
    return features[:8]


def _detect_anti_pattern_tools(brief: StrategyInputBrief) -> list[str]:
    """Detect manual-workflow tool mentions in the audience
    description. Returns the unique list of tokens we recognised."""

    descs: list[str] = []
    for hint in brief.audience_hints:
        if hint.description:
            descs.append(hint.description.lower())
    blob = " ".join(descs)
    found: list[str] = []
    for token in _ANTIPATTERN_TOKENS:
        if token in blob and token not in found:
            found.append(token)
    return found


def _extract_pains_from_intake(brief: StrategyInputBrief) -> list[str]:
    """Compose realistic pain phrases for the target audience.

    Priority order:

    1. Explicit ``psychographics["pains"]`` carried through by the
       normalizer (split on ``|``). When present, those win — the
       client described them directly.
    2. Product features turned into "feature + inverse modifier"
       phrases (``"expedientes desordenados"``).
    3. Anti-pattern tool mentions in the audience description
       (``"Gestión dispersa en Excel, WhatsApp y carpetas"``).
    4. Last-resort generic fallback.
    """

    hint = brief.audience_hints[0]
    explicit = [
        p.strip() for p in
        hint.psychographics.get("pains", "").split("|")
        if p.strip()
    ]
    if explicit:
        return explicit[:5]

    pains: list[str] = []
    # MKT-9C: anti-pattern detection goes first so an LEXIA-shaped
    # intake (with Excel / WhatsApp / carpetas in the audience
    # description) ALWAYS gets the synthetic "Procesos dispersos
    # en ..." pain — that's the most operationally meaningful one
    # for the operator and ATLAS handoff brief.
    anti_tools = _detect_anti_pattern_tools(brief)
    if anti_tools:
        labelled: list[str] = []
        if any(t.startswith("excel") or t.startswith("planilla") for t in anti_tools):
            labelled.append("Excel")
        if any(t.startswith("whats") or t.startswith("wsp") for t in anti_tools):
            labelled.append("WhatsApp")
        if any(t.startswith("carpeta") for t in anti_tools):
            labelled.append("carpetas")
        if any("manual" in t for t in anti_tools):
            labelled.append("recordatorios manuales")
        if labelled:
            pains.append("Procesos dispersos en " + ", ".join(labelled[:4]))

    features = _extract_product_features(brief)
    for i, feature in enumerate(features):
        if len(pains) >= 5:
            break
        # Pick an inverse that does NOT echo a word already in the
        # feature — avoids "seguimiento judicial sin seguimiento".
        feature_words = set(feature.lower().split())
        inverse_candidates = [
            inv for inv in _PAIN_INVERSES
            if not any(word in inv.lower() for word in feature_words)
        ]
        if not inverse_candidates:
            inverse_candidates = list(_PAIN_INVERSES)
        inverse = inverse_candidates[i % len(inverse_candidates)]
        # Concordancia simple: feminize "desordenados" / "dispersos"
        # if the feature looks feminine plural (".as"). Cheap and
        # readable in Spanish.
        if inverse in ("desordenados", "dispersas", "manuales") and (
            feature.endswith("as") or feature.endswith("nes")
        ):
            inverse = {
                "desordenados": "desordenadas",
                "dispersas": "dispersas",
                "manuales": "manuales",
            }[inverse]
        pains.append(f"{feature.capitalize()} {inverse}")

    if pains:
        return pains[:5]
    return ["Falta de tiempo", "Sobrecarga informativa"]


def _sanitize_forbidden(text: str, banned_words: list[str]) -> str:
    """Scrub a generated string of phrases the client banned.

    The templated backend has been audited and does NOT currently
    emit any of LEXIA's forbidden phrases — this helper exists as
    a safety net for future template changes and downstream LLM
    backends. It performs a case-insensitive substring replacement
    leaving ``[REDACTED]`` in place so the operator notices.
    """

    if not banned_words or not text:
        return text
    out = text
    lower = out.lower()
    for raw in banned_words:
        phrase = (raw or "").strip()
        if not phrase or len(phrase) < 3:
            continue
        # find every case-insensitive occurrence
        idx = 0
        phrase_l = phrase.lower()
        while True:
            pos = lower.find(phrase_l, idx)
            if pos == -1:
                break
            out = out[:pos] + "[REDACTED]" + out[pos + len(phrase):]
            lower = out.lower()
            idx = pos + len("[REDACTED]")
    return out


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
    outcomes = list(hint.psychographics.get("desired", "").split("|")) if hint.psychographics.get("desired") else []
    # MKT-9C: derive realistic pains from the intake. Falls back to
    # the legacy generic pair only when there is literally nothing
    # to extract.
    pains = _extract_pains_from_intake(brief)
    # MKT-9C: derive desired outcomes from the preferred_words
    # vocabulary when the intake didn't supply explicit ones —
    # e.g. for LEXIA the lexicon is ``["claridad","orden",...]``,
    # which makes a more meaningful outcome list than the legacy
    # ``"Lograr qualified demo requests"`` echo.
    if not [o for o in outcomes if o]:
        if brief.brand.lexicon_do:
            lexicon_outcomes = [
                w for w in brief.brand.lexicon_do[:5]
                if w and len(w) > 2
            ]
            outcomes = [
                w.capitalize() + " operativa"
                if w in {"orden", "claridad", "trazabilidad", "eficiencia"}
                else w.capitalize()
                for w in lexicon_outcomes
            ] or [f"Lograr {brief.primary_kpi.replace('_', ' ')}"]
        else:
            outcomes = [f"Lograr {brief.primary_kpi.replace('_', ' ')}"]
    return TargetAudience(
        audience_id=new_id(),
        label=hint.label,
        estimated_size_band=_estimated_size_band(hint.estimated_size),  # type: ignore[arg-type]
        demographics=dict(hint.demographics),
        psychographics={
            k: v for k, v in hint.psychographics.items() if k not in ("pains", "desired")
        },
        preferred_channels=list(hint.preferred_channels) or list(brief.preferred_channels),
        pain_points=pains,
        desired_outcomes=[o for o in outcomes if o],
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
    # MKT-9C: pick the FIRST extracted pain that is not the legacy
    # generic fallback. If the audience only carries the fallback
    # pair (``"Falta de tiempo"`` / ``"Sobrecarga informativa"``),
    # we still use the first one but the extractor will normally
    # have produced something better for any real-business intake.
    pains = list(audience.pain_points or [])
    legacy_fallback = {"falta de tiempo", "sobrecarga informativa"}
    non_legacy = [
        p for p in pains
        if p and p.strip().lower() not in legacy_fallback
    ]
    pain = (non_legacy or pains or [None])[0]

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

    # MKT-9C: seed concrete domain features extracted from the
    # intake's product description BEFORE differentiator tokens.
    # For LEXIA these surface as ``expedientes``, ``vencimientos``,
    # ``honorarios`` etc. — the vocabulary actual prospects search
    # for, far more valuable than the generic differentiator
    # tokens.
    for feature in _extract_product_features(brief)[:5]:
        slug = normalize_for_slug(feature)
        if slug and is_meaningful_keyword(slug.split(" ")[0]) and slug not in seeds:
            seeds.append(slug)

    # First meaningful token from each top differentiator — filters out
    # stopwords (``sin``), generic tokens (``setup``), short verbs
    # (``diseado``).
    for d in value_prop.differentiators[:3]:
        tok = first_meaningful_token(d)
        if tok and tok not in seeds:
            seeds.append(tok)

    # MKT-9C: seed every preferred_word that survives the
    # meaningfulness filter — these are the words the client
    # explicitly asked the campaign to use.
    for pref in brief.brand.lexicon_do[:6]:
        slug = normalize_for_slug(pref)
        if slug and is_meaningful_keyword(slug.split(" ")[0]) and slug not in seeds:
            seeds.append(slug)

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
    # MKT-9C: use the same intake-aware pain extractor as
    # ``generate_target_audience`` so social posts and the
    # ``pain_points`` field in the audience speak about the same
    # concrete problem (no more boilerplate "tareas repetitivas").
    extracted_pains = _extract_pains_from_intake(brief)
    pain_token = extracted_pains[0].lower() if extracted_pains else "tareas repetitivas"
    diff = value_prop.differentiators[0] if value_prop.differentiators else "Te ahorra tiempo"

    # MKT-9D: pick tone family from the BRIEF (industry +
    # audience), not just brand.tone_words. For legal /
    # legaltech intakes the system now switches to the
    # ``legal-pro`` family which carries sober adjectives,
    # connectors and openers — no more "decisiones claros que
    # tomamos esta semana" startup-genérica.
    family = tone_family_for_brief(brief)
    adjective = tone_adjective_for_brief(brief)
    connector = tone_connector_for_brief(brief)

    # Channel-specific copy. Each channel gets its OWN hook + body so
    # the output stops being a template echo across 3+ surfaces.
    # MKT-9D: when the family is ``legal-pro`` we substitute the
    # SaaS-flavoured templates with sober versions per channel.
    if family == "legal-pro":
        channel_voices: dict[str, tuple[str, str, str]] = {
            # channel_value: (hook_template, body_template, cta)
            "newsletter": (
                "Cómo evitar {pain} en el estudio.",
                "Resumen breve para el estudio: usar {product} para "
                "ordenar lo que hoy vive en {pain}. {connector}, {diff}.",
                "Leer el caso",
            ),
            "blog": (
                "Cómo ordenar {topic} en el estudio sin {pain}.",
                "Documentamos paso por paso lo que cambia en la "
                "operación del estudio. {connector}, {diff}.",
                "Leer el informe",
            ),
            "linkedin": (
                "3 cambios concretos en la operación de un estudio "
                "jurídico con {product}.",
                "{connector}, lo comparto con detalle: qué ordenamos, "
                "qué dejó de perderse, qué quedó trazable. {diff}.",
                "Ver el detalle",
            ),
            "x": (
                "{product}: {short_diff}.",
                "Para {persona} que necesitan {pain} bajo control. "
                "{connector}, así lo planteamos.",
                "Ver más",
            ),
            "instagram": (
                "Un estudio jurídico puede dejar de operar a oscuras.",
                "Carrusel con un caso concreto: qué cambió en la "
                "operación. {connector}, {diff}.",
                "Ver carrusel",
            ),
            "email": (
                "Cómo evitar {pain} sin sumar carga al estudio.",
                "Caso breve: el estudio que ordenó {pain} en una "
                "semana. {connector}, {diff}.",
                "Pedir demo",
            ),
        }
        default_voice = (
            "{product} para el estudio jurídico: lo que cambia en la "
            "práctica.",
            "{connector}, {diff}.",
            "Pedir demo",
        )
    else:
        channel_voices = {
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
    # MKT-9D: pick the opener from the FAMILY-aware helper so legal
    # / legaltech intakes get "En la práctica del estudio:" instead
    # of "Concretamente:".
    family = tone_family_for_brief(brief)
    opener = tone_opener_for_brief(brief)
    pref1 = pick_preferred_word(brief.brand.lexicon_do)
    pref2 = pick_preferred_word(brief.brand.lexicon_do, already_used=[pref1] if pref1 else [])
    objective = brief.objective

    pref1_phrase = f" ({pref1})" if pref1 else ""

    if family == "legal-pro":
        emails: list[EmailDraft] = [
            EmailDraft(
                email_id=new_id(),
                step=1,
                subject=_truncate(f"Bienvenida a {product}", 80),
                preview_text=_truncate(
                    "Para que el estudio empiece con orden.", 140,
                ),
                body=(
                    f"Estimado/a,\n\nGracias por sumarte a {product}.\n\n"
                    f"{opener} esta secuencia te orienta hacia un objetivo "
                    f"concreto: {objective}{pref1_phrase}.\n\n"
                    "Primer paso recomendado: revisar la guía de setup "
                    "(5 minutos).\n\nUn saludo,\nEl equipo de "
                    f"{product}"
                ),
                cta="Ver guía de setup",
                send_after_days=0,
            ),
            EmailDraft(
                email_id=new_id(),
                step=2,
                subject=_truncate(
                    f"3 puntos donde {product} ordena la operación", 80,
                ),
                preview_text=_truncate(
                    "Qué cambia para el estudio en la práctica.", 140,
                ),
                body=(
                    "Estimado/a,\n\n"
                    + (f"{opener} " if opener else "")
                    + (
                        f"resumido en una palabra: {pref2}.\n\n"
                        if pref2 else ""
                    )
                    + f"Tres puntos donde {product} ordena la operación "
                    "del estudio:\n\n"
                    + "\n".join(f"• {d}" for d in diffs[:3])
                    + "\n\nSi te interesa verlo aplicado a tu estudio, "
                    "coordinemos una demo de 20 minutos.\n\nUn saludo"
                ),
                cta="Reservar demo",
                send_after_days=2,
            ),
            EmailDraft(
                email_id=new_id(),
                step=3,
                subject=_truncate(
                    "Cómo lo usan otros estudios jurídicos", 80,
                ),
                preview_text=_truncate(
                    "Casos breves — para que veas el impacto en la práctica.",
                    140,
                ),
                body=(
                    "Estimado/a,\n\nDos casos breves de estudios que ya "
                    f"usan {product}.\n\n"
                    "[Insertar 2 casos reales — pendiente de revisión "
                    "humana antes de enviar.]\n\n"
                    "Si querés ver más casos del estudio que te "
                    "interesa, respondeme a este correo.\n\nUn saludo"
                ),
                cta="Ver casos",
                send_after_days=5,
            ),
            EmailDraft(
                email_id=new_id(),
                step=4,
                subject=_truncate(
                    f"Próximo paso con {product}", 80,
                ),
                preview_text=_truncate(
                    "Sin presión — un acuerdo de activación si te suma.",
                    140,
                ),
                body=(
                    f"Estimado/a,\n\nTras esta semana con {product} "
                    "probablemente ya tengas claridad sobre si te suma "
                    "para la operación del estudio.\n\n"
                    "Si querés avanzar, podemos coordinar un acuerdo "
                    "de activación para esta semana.\n\n"
                    "Si todavía no es el momento, sin problema — "
                    "quedamos a disposición.\n\n"
                    "Gracias por leer hasta acá.\n\nUn saludo"
                ),
                cta="Coordinar activación",
                send_after_days=10,
            ),
        ]
    else:
        emails = [
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
    # MKT-9C: prefer the audience-derived pain (which now uses
    # the intake-aware extractor) over the legacy stub.
    pain_token = (
        audience.pain_points[0].lower()
        if audience.pain_points
        else "lo mismo de siempre"
    )
    pref_word = pick_preferred_word(brief.brand.lexicon_do)
    pref_suffix = f" — {pref_word}." if pref_word else "."
    # MKT-9D: industry-aware closers and openers per family. For
    # legal-pro we drop "Probalo hoy" / "Probalo gratis" — too
    # SaaS-flavoured for a legaltech audience — and use "Pedir
    # demo" / "Reservar 15 minutos" instead.
    family = tone_family_for_brief(brief)
    if family == "legal-pro":
        closer = "Pedí una demo."
        cta_default = "Pedir demo"
        cta_short = "Pedir demo"
        contrast_phrase = f"Con {product} eso queda ordenado{pref_suffix}"
        errors_intro = (
            "Tres problemas que se ven seguido en estudios jurídicos."
        )
        errors_outro = f"{product} los ordena."
        testimony_hook = (
            "Esto fue lo que nos dijeron tras la primera semana en un "
            "estudio jurídico."
        )
        testimony_closer = "Si suena familiar, coordinemos una demo."
        on_screen_problem = "¿Te suena?"
        on_screen_outro = "Pedir demo"
    else:
        closer = "Probalo hoy."
        cta_default = "Empezá hoy"
        cta_short = "Probalo gratis"
        contrast_phrase = f"Con {product} eso cambia{pref_suffix}"
        errors_intro = "Estos 3 errores los vemos seguido."
        errors_outro = f"{product} los resuelve."
        testimony_hook = "Esto fue lo que nos dijeron en la primera semana."
        testimony_closer = "Si te suena, probalo."
        on_screen_problem = "¿Te suena?"
        on_screen_outro = "Empezá hoy"

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
                contrast_phrase,
                closer,
            ],
            on_screen_text=[
                on_screen_problem,
                diffs[0],
                on_screen_outro,
            ],
            cta=cta_default,
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
                errors_intro,
                # MKT-4D: derived from real diffs when available — used
                # to literally read "Error 1, error 2, error 3."
                ". ".join(diffs[:3]) + ".",
                errors_outro,
                closer,
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
            hook=testimony_hook,
            beats=[
                "0-3s: hook con cita",
                "3-20s: caso concreto",
                "20-30s: CTA",
            ],
            voiceover_lines=[
                "Esto fue lo que nos dijeron.",
                "[Insertar cita de cliente real — pending revisión humana.]",
                testimony_closer,
            ],
            on_screen_text=[
                "Caso real",
                "Resultado en 1 semana",
                on_screen_outro,
            ],
            cta=cta_short,
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
