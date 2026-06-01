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

import re
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

# ---------- Constants ----------

_GENERIC_NEGATIVES = ["free", "torrent", "jobs", "salary", "course", "tutorial gratis"]

_OWNED_DEFAULTS = [ChannelType.NEWSLETTER, ChannelType.BLOG]
_SOCIAL_DEFAULTS = [ChannelType.LINKEDIN, ChannelType.INSTAGRAM]
_OUT_OF_SCOPE_DEFAULTS = [ChannelType.OTHER]

_GENERIC_HASHTAGS = ["#marketing", "#growth", "#strategy"]


# ---------- Helpers ----------

def _slugify_keyword(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s-]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _hashtagify(text: str) -> str:
    text = re.sub(r"[^A-Za-z0-9]", "", text.title())
    return f"#{text}" if text else ""


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
    headline = (
        f"{brief.client.name}: campaña {brief.duration_weeks} semanas para "
        f"{primary_audience} con foco en {brief.primary_kpi}."
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
        strengths.append(f"{len(brief.competitors_known)} competidor(es) ya identificados.")
    else:
        challenges.append("Sin competidores listados — benchmark será de baja confianza.")
        opportunities.append("Investigar competidores antes de campaña en mercado denso.")

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
    differentiators = list(brief.product.value_props) or [
        f"Diseñado específicamente para {audience.label}",
        "Setup en menos de un día",
        "Sin contratos largos",
    ]
    proof_points = [
        f"Producto/servicio: {brief.product.name}",
        *(
            [f"Industria: {brief.client.industry}"]
            if brief.client.industry
            else []
        ),
    ]
    return ValueProposition(
        headline=_truncate(
            f"{brief.product.name}: {differentiators[0]}",
            280,
        ),
        category=brief.client.industry or "marketing tooling",
        target_audience_label=audience.label,
        differentiators=differentiators[:5],
        proof_points=proof_points,
        primary_benefit=differentiators[0] if differentiators else None,
        notes=brief.additional_context,
    )


def generate_competitor_benchmark(competitors: list[_InputCompetitor]) -> CompetitorBenchmark:
    entries = [
        CompetitorEntry(
            name=c.name,
            url=c.url,
            positioning_summary=c.positioning_summary,
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
    return CompetitorBenchmark(
        competitors=entries,
        overall_takeaway=(
            f"{len(entries)} competidor(es) identificados. Ver fortalezas y debilidades por "
            "competidor para encontrar ángulos diferenciales."
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

    entries: list[ChannelEntry] = []
    for i, ch in enumerate(ordered):
        role, cadence = role_map.get(ch, ("engagement", None))
        entries.append(
            ChannelEntry(
                channel_type=ch,
                label=f"{ch.value} (rol: {role})",
                priority=i + 1,
                rationale=(
                    f"Match con audiencia ({audience.label}); "
                    f"rol esperado: {role}."
                ),
                cadence_suggestion=cadence,
                expected_role=role,
            )
        )

    out_of_scope = [
        c
        for c in _OUT_OF_SCOPE_DEFAULTS
        if c not in seen
    ]

    return ChannelRecommendation(
        channels=entries,
        total_channels=len(entries),
        rationale_overall=(
            f"Mix de canales priorizado para {audience.label}, balanceando "
            "owned (newsletter, blog) y earned (social). Paid queda condicionado a presupuesto."
        ),
        out_of_scope_channels=out_of_scope,
    )


def generate_keyword_plan(
    brief: StrategyInputBrief,
    audience: TargetAudience,
    value_prop: ValueProposition,
) -> KeywordPlan:
    seeds: list[str] = []
    seeds.append(brief.product.name.lower())
    if brief.client.industry:
        seeds.append(brief.client.industry.lower())
    for d in value_prop.differentiators[:3]:
        seeds.append(_slugify_keyword(d).split(" ")[0])

    audience_token = _slugify_keyword(audience.label).split(" ")[0]

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

    if brief.product.name:
        clusters.append(
            KeywordCluster(
                label=f"{brief.product.name.lower()}_transactional",
                intent="transactional",
                keywords=[
                    f"comprar {brief.product.name.lower()}",
                    f"{brief.product.name.lower()} precio",
                    f"{brief.product.name.lower()} alternativa",
                    f"contratar {brief.product.name.lower()}",
                ],
                suggested_match="exact",
            )
        )

    competitor_negatives = [c.name.lower() for c in brief.competitors_known]
    negatives = sorted(set([*_GENERIC_NEGATIVES, *competitor_negatives]))

    hashtags_seed = []
    for s in seeds[:3]:
        h = _hashtagify(s)
        if h:
            hashtags_seed.append(h)
    if brief.client.industry:
        h = _hashtagify(brief.client.industry)
        if h:
            hashtags_seed.append(h)
    hashtags = sorted(set([*hashtags_seed, *_GENERIC_HASHTAGS]))[:10]

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
    hook_templates = [
        "Si {persona}, probablemente esto te suena: {pain}.",
        "La forma en la que la mayoría hace {topic} está rota. Acá hay otra.",
        "3 cosas que aprendimos construyendo {product}.",
        "{stat}% de {persona} pierde tiempo en {pain}. Acá una alternativa.",
    ]
    body_template = "{value} — y por eso {product} existe. {differentiator}."
    cta_template = "Conocé cómo →"
    persona_token = brief.audience_hints[0].label.lower()
    pain_token = "tareas repetitivas"
    product = brief.product.name
    topic = brief.client.industry or "esto"

    for i, ch in enumerate(channels.channels[:3]):
        hook = hook_templates[i % len(hook_templates)].format(
            persona=persona_token,
            pain=pain_token,
            topic=topic,
            product=product,
            stat="80",
        )
        body = body_template.format(
            value=value_prop.headline,
            product=product,
            differentiator=value_prop.differentiators[0] if value_prop.differentiators else "Te ahorra tiempo",
        )
        drafts.append(
            SocialPostDraft(
                post_id=new_id(),
                channel=ch.channel_type,
                hook=_truncate(hook, 300),
                body=body,
                cta=cta_template,
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

    emails: list[EmailDraft] = [
        EmailDraft(
            email_id=new_id(),
            step=1,
            subject=_truncate(f"Bienvenida a {product}", 80),
            preview_text=_truncate("Empezamos por lo más importante.", 140),
            body=(
                f"Hola,\n\nGracias por sumarte a {product}.\n\n"
                f"En este recorrido te vamos a mostrar cómo {value_prop.headline.lower()}.\n\n"
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
                f"Hola,\n\nAcá van 3 diferenciadores de {product}:\n\n"
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
                f"La mayoría de {audience.label.lower()} pierde tiempo en lo mismo.",
                f"{product} cambia eso porque {diffs[0]}.",
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
                "3-30s: error 1, error 2, error 3",
                "30-45s: solución (producto)",
                "45-50s: CTA",
            ],
            voiceover_lines=[
                "Estos 3 errores los vemos seguido.",
                "Error 1, error 2, error 3.",
                f"{product} los resuelve.",
                "Probalo.",
            ],
            on_screen_text=["Error 1", "Error 2", "Error 3", "Solución"],
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
