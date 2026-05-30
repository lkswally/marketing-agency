"""Markdown renderer for :class:`CampaignStrategyReport`.

Produces a 20-section document. Pure: the output is fully determined by the
report instance. No I/O.
"""

from __future__ import annotations

from .models import CampaignStrategyReport

_SECTION_HEADERS = [
    ("01", "Resumen ejecutivo"),
    ("02", "Diagnóstico del negocio"),
    ("03", "Público objetivo"),
    ("04", "Buyer persona"),
    ("05", "Propuesta de valor"),
    ("06", "Benchmark de competidores"),
    ("07", "Canales recomendados"),
    ("08", "Keywords principales"),
    ("09", "Keywords negativas"),
    ("10", "Hashtags sugeridos"),
    ("11", "Estrategia de campaña"),
    ("12", "Piezas sugeridas"),
    ("13", "Briefs para flyers / imágenes"),
    ("14", "Copies para redes"),
    ("15", "Secuencia de emails"),
    ("16", "Guiones de reels"),
    ("17", "Calendario sugerido"),
    ("18", "Checklist de aprobación"),
    ("19", "Riesgos / claims a validar"),
    ("20", "Próximos pasos"),
]


def render_markdown_report(report: CampaignStrategyReport) -> str:
    parts: list[str] = []
    parts.append(_render_header(report))
    parts.append(_render_toc())
    parts.append(_render_executive_summary(report))
    parts.append(_render_diagnosis(report))
    parts.append(_render_target_audience(report))
    parts.append(_render_buyer_persona(report))
    parts.append(_render_value_proposition(report))
    parts.append(_render_competitor_benchmark(report))
    parts.append(_render_channel_recommendation(report))
    parts.append(_render_keywords_main(report))
    parts.append(_render_keywords_negatives(report))
    parts.append(_render_hashtags(report))
    parts.append(_render_campaign_strategy(report))
    parts.append(_render_suggested_pieces(report))
    parts.append(_render_creative_brief_pack(report))
    parts.append(_render_social_drafts(report))
    parts.append(_render_email_sequence(report))
    parts.append(_render_reels_pack(report))
    parts.append(_render_schedule(report))
    parts.append(_render_approval_checklist(report))
    parts.append(_render_risk_assessment(report))
    parts.append(_render_next_steps(report))
    parts.append(_render_footer(report))
    return "\n\n".join(parts) + "\n"


# ---------- helpers ----------

def _bullet_list(items: list[str]) -> str:
    if not items:
        return "_(vacío)_"
    return "\n".join(f"- {item}" for item in items)


def _kv_list(d: dict[str, str]) -> str:
    if not d:
        return "_(vacío)_"
    return "\n".join(f"- **{k}**: {v}" for k, v in d.items())


def _section_h2(num: str, title: str) -> str:
    return f"## {num}. {title}"


# ---------- sections ----------

def _render_header(r: CampaignStrategyReport) -> str:
    return (
        f"# Campaign Strategy Report — {r.client_slug}\n\n"
        f"- **Report ID**: `{r.report_id}`\n"
        f"- **Brief ref**: `{r.brief_id}`\n"
        f"- **Contract**: `{r.contract_version}`\n"
        f"- **Generado**: `{r.generated_at.isoformat()}`\n"
    )


def _render_toc() -> str:
    lines = ["## Índice"]
    for num, title in _SECTION_HEADERS:
        lines.append(f"- {num}. {title}")
    return "\n".join(lines)


def _render_executive_summary(r: CampaignStrategyReport) -> str:
    s = r.executive_summary
    lines = [_section_h2("01", "Resumen ejecutivo"), f"**{s.headline}**", "", s.one_liner, ""]
    lines.append(f"**Objetivo primario**: {s.primary_objective}")
    lines.append("**Métricas clave**:")
    lines.append(_bullet_list(s.key_metrics))
    return "\n".join(lines)


def _render_diagnosis(r: CampaignStrategyReport) -> str:
    d = r.diagnosis
    lines = [_section_h2("02", "Diagnóstico del negocio")]
    if d.industry:
        lines.append(f"**Industria**: {d.industry}")
    lines.append(f"**Etapa observada**: {d.stage_observed}")
    lines.append("\n**Fortalezas**:")
    lines.append(_bullet_list(d.strengths))
    lines.append("\n**Desafíos**:")
    lines.append(_bullet_list(d.challenges))
    lines.append("\n**Oportunidades**:")
    lines.append(_bullet_list(d.opportunities))
    if d.assumptions_made:
        lines.append("\n**Supuestos asumidos**:")
        lines.append(_bullet_list(d.assumptions_made))
    return "\n".join(lines)


def _render_target_audience(r: CampaignStrategyReport) -> str:
    a = r.target_audience
    lines = [_section_h2("03", "Público objetivo")]
    lines.append(f"**Etiqueta**: {a.label}")
    lines.append(f"**Tamaño estimado (banda)**: {a.estimated_size_band}")
    lines.append("\n**Demografía**:")
    lines.append(_kv_list(a.demographics))
    lines.append("\n**Psicografía**:")
    lines.append(_kv_list(a.psychographics))
    lines.append("\n**Canales preferidos**:")
    lines.append(_bullet_list([c.value for c in a.preferred_channels]))
    lines.append("\n**Pain points**:")
    lines.append(_bullet_list(a.pain_points))
    lines.append("\n**Outcomes deseados**:")
    lines.append(_bullet_list(a.desired_outcomes))
    return "\n".join(lines)


def _render_buyer_persona(r: CampaignStrategyReport) -> str:
    lines = [_section_h2("04", "Buyer persona")]
    if r.buyer_persona is None:
        lines.append("_(no se generó persona para este reporte)_")
        return "\n".join(lines)
    p = r.buyer_persona
    lines.append(f"**Arquetipo**: {p.archetype_name}")
    if p.age_range:
        lines.append(f"**Rango de edad**: {p.age_range}")
    if p.occupation:
        lines.append(f"**Ocupación**: {p.occupation}")
    if p.a_day_in_life:
        lines.append(f"\n**Un día en su vida**:\n\n{p.a_day_in_life}")
    lines.append("\n**Motivaciones**:")
    lines.append(_bullet_list(p.motivations))
    lines.append("\n**Objeciones**:")
    lines.append(_bullet_list(p.objections))
    if p.quotes:
        lines.append("\n**Citas**:")
        lines.append(_bullet_list([f'"{q}"' for q in p.quotes]))
    return "\n".join(lines)


def _render_value_proposition(r: CampaignStrategyReport) -> str:
    v = r.value_proposition
    lines = [_section_h2("05", "Propuesta de valor")]
    lines.append(f"**Headline**: {v.headline}")
    lines.append(f"**Categoría**: {v.category}")
    lines.append(f"**Para**: {v.target_audience_label}")
    lines.append("\n**Diferenciadores**:")
    lines.append(_bullet_list(v.differentiators))
    lines.append("\n**Proof points**:")
    lines.append(_bullet_list(v.proof_points))
    if v.primary_benefit:
        lines.append(f"\n**Beneficio primario**: {v.primary_benefit}")
    if v.notes:
        lines.append(f"\n**Notas**: {v.notes}")
    return "\n".join(lines)


def _render_competitor_benchmark(r: CampaignStrategyReport) -> str:
    b = r.competitor_benchmark
    lines = [_section_h2("06", "Benchmark de competidores")]
    lines.append(f"**Confianza del benchmark**: {b.confidence}")
    if b.competitors:
        for c in b.competitors:
            lines.append(f"\n### {c.name}")
            if c.url:
                lines.append(f"- URL: {c.url}")
            if c.positioning_summary:
                lines.append(f"- Posicionamiento: {c.positioning_summary}")
            if c.observed_strengths:
                lines.append("- Fortalezas observadas:")
                lines.append(_bullet_list(c.observed_strengths))
            if c.observed_weaknesses:
                lines.append("- Debilidades observadas:")
                lines.append(_bullet_list(c.observed_weaknesses))
            if c.differentiating_angle_for_us:
                lines.append(f"- Ángulo diferencial para nosotros: {c.differentiating_angle_for_us}")
    else:
        lines.append("\n_(sin competidores listados)_")
    if b.overall_takeaway:
        lines.append(f"\n**Takeaway**: {b.overall_takeaway}")
    if b.market_gaps_identified:
        lines.append("\n**Gaps de mercado**:")
        lines.append(_bullet_list(b.market_gaps_identified))
    return "\n".join(lines)


def _render_channel_recommendation(r: CampaignStrategyReport) -> str:
    rec = r.channel_recommendation
    lines = [_section_h2("07", "Canales recomendados")]
    lines.append(f"**Total canales**: {rec.total_channels}")
    if rec.rationale_overall:
        lines.append(f"\n**Rationale general**: {rec.rationale_overall}\n")
    lines.append("| # | Canal | Rol | Cadencia | Rationale |")
    lines.append("|---|-------|-----|----------|-----------|")
    for ch in rec.channels:
        lines.append(
            f"| {ch.priority} | {ch.channel_type.value} | "
            f"{ch.expected_role or '—'} | {ch.cadence_suggestion or '—'} | {ch.rationale} |"
        )
    if rec.out_of_scope_channels:
        lines.append("\n**Fuera de scope**:")
        lines.append(_bullet_list([c.value for c in rec.out_of_scope_channels]))
    return "\n".join(lines)


def _render_keywords_main(r: CampaignStrategyReport) -> str:
    kp = r.keyword_plan
    lines = [_section_h2("08", "Keywords principales")]
    lines.append(f"**Fuente**: {kp.source}")
    if not kp.clusters:
        lines.append("_(sin clusters)_")
    for c in kp.clusters:
        lines.append(f"\n### Cluster: {c.label}  _(intent: {c.intent}, match: {c.suggested_match})_")
        lines.append(_bullet_list(c.keywords))
    if kp.notes:
        lines.append(f"\n**Notas**: {kp.notes}")
    return "\n".join(lines)


def _render_keywords_negatives(r: CampaignStrategyReport) -> str:
    lines = [_section_h2("09", "Keywords negativas")]
    lines.append(_bullet_list(r.keyword_plan.negative_keywords))
    return "\n".join(lines)


def _render_hashtags(r: CampaignStrategyReport) -> str:
    lines = [_section_h2("10", "Hashtags sugeridos")]
    lines.append(_bullet_list(r.keyword_plan.hashtags))
    return "\n".join(lines)


def _render_campaign_strategy(r: CampaignStrategyReport) -> str:
    s = r.campaign_strategy
    lines = [_section_h2("11", "Estrategia de campaña")]
    lines.append(f"**Objetivo**: {s.objective}")
    lines.append(f"**Duración**: {s.duration_weeks} semanas")
    lines.append(f"**KPI primario**: {s.primary_kpi}")
    if s.secondary_kpis:
        lines.append("\n**KPIs secundarios**:")
        lines.append(_bullet_list(s.secondary_kpis))
    lines.append(f"\n**Foco de funnel**: {s.funnel_focus}")
    if s.budget_estimate:
        lines.append(f"**Budget estimado**: {s.budget_estimate} {s.budget_currency or ''}")
    if s.big_idea:
        lines.append(f"\n**Big idea**: {s.big_idea}")
    if s.narrative_arc:
        lines.append("\n**Arco narrativo**:")
        lines.append(_bullet_list(s.narrative_arc))
    return "\n".join(lines)


def _render_suggested_pieces(r: CampaignStrategyReport) -> str:
    lines = [_section_h2("12", "Piezas sugeridas")]
    if not r.suggested_pieces:
        lines.append("_(vacío)_")
        return "\n".join(lines)
    lines.append("| Tipo | Canal | Propósito | Cantidad |")
    lines.append("|------|-------|-----------|----------|")
    for p in r.suggested_pieces:
        lines.append(
            f"| {p.piece_type} | {p.channel.value} | {p.purpose} | {p.quantity} |"
        )
    return "\n".join(lines)


def _render_creative_brief_pack(r: CampaignStrategyReport) -> str:
    pack = r.creative_brief_pack
    lines = [_section_h2("13", "Briefs para flyers / imágenes")]
    if pack.overall_visual_direction:
        lines.append(f"**Dirección visual general**: {pack.overall_visual_direction}\n")
    if pack.do_not_use:
        lines.append("**No usar**:")
        lines.append(_bullet_list(pack.do_not_use))
    for b in pack.briefs:
        lines.append(f"\n### {b.title}  _(tipo: {b.piece_type}, aspect: {b.aspect_ratio})_")
        lines.append(f"- Concepto: {b.visual_concept}")
        if b.palette_hint:
            lines.append("- Paleta: " + ", ".join(f"`{c}`" for c in b.palette_hint))
        if b.typography_hint:
            lines.append(f"- Tipografía: {b.typography_hint}")
        if b.copy_overlay:
            lines.append("- Copy overlay:")
            lines.append(_bullet_list(b.copy_overlay))
        if b.cta:
            lines.append(f"- CTA: {b.cta}")
        if b.accessibility_notes:
            lines.append("- Accesibilidad:")
            lines.append(_bullet_list(b.accessibility_notes))
        lines.append(f"\n**Prompt para image model**:\n\n> {b.prompt_for_image_model}")
    return "\n".join(lines)


def _render_social_drafts(r: CampaignStrategyReport) -> str:
    lines = [_section_h2("14", "Copies para redes")]
    if not r.social_post_drafts:
        lines.append("_(vacío)_")
        return "\n".join(lines)
    for p in r.social_post_drafts:
        lines.append(f"\n### {p.channel.value}  _(send: {p.suggested_send_at or '—'})_")
        lines.append(f"**Hook**: {p.hook}")
        lines.append(f"\n{p.body}")
        lines.append(f"\n**CTA**: {p.cta}")
        if p.hashtags:
            lines.append("**Hashtags**: " + " ".join(p.hashtags))
    return "\n".join(lines)


def _render_email_sequence(r: CampaignStrategyReport) -> str:
    seq = r.email_sequence
    lines = [_section_h2("15", "Secuencia de emails")]
    lines.append(f"**Nombre**: {seq.sequence_name}")
    lines.append(f"**Objetivo**: {seq.goal}")
    lines.append(f"**Audiencia**: {seq.audience_label}")
    for e in seq.emails:
        lines.append(
            f"\n### Email {e.step} — `{e.subject}` _(send +{e.send_after_days}d)_"
        )
        lines.append(f"**Preview text**: {e.preview_text}\n")
        lines.append(e.body)
        lines.append(f"\n**CTA**: {e.cta}")
    return "\n".join(lines)


def _render_reels_pack(r: CampaignStrategyReport) -> str:
    pack = r.reels_script_pack
    lines = [_section_h2("16", "Guiones de reels")]
    if pack.overall_tone:
        lines.append(f"**Tono general**: {pack.overall_tone}\n")
    for s in pack.scripts:
        lines.append(f"\n### {s.title}  _(duración objetivo: {s.target_duration_s}s)_")
        lines.append(f"**Hook**: {s.hook}")
        lines.append("\n**Beats**:")
        lines.append(_bullet_list(s.beats))
        lines.append("\n**Voiceover**:")
        lines.append(_bullet_list(s.voiceover_lines))
        lines.append("\n**Texto en pantalla**:")
        lines.append(_bullet_list(s.on_screen_text))
        lines.append(f"\n**CTA**: {s.cta}")
    return "\n".join(lines)


def _render_schedule(r: CampaignStrategyReport) -> str:
    sched = r.schedule
    lines = [_section_h2("17", "Calendario sugerido")]
    lines.append(f"**Total semanas**: {sched.weeks_total}")
    if sched.start_date:
        lines.append(f"**Inicio**: {sched.start_date.isoformat()}")
    if sched.end_date:
        lines.append(f"**Fin**: {sched.end_date.isoformat()}")
    if sched.notes:
        lines.append(f"\n**Notas**: {sched.notes}\n")
    lines.append("| Semana | Canal | Pieza | Cadencia |")
    lines.append("|--------|-------|-------|----------|")
    for e in sched.entries:
        lines.append(
            f"| {e.week} | {e.channel.value} | {e.piece_type} | {e.cadence_note or '—'} |"
        )
    return "\n".join(lines)


def _render_approval_checklist(r: CampaignStrategyReport) -> str:
    ck = r.approval_checklist
    lines = [_section_h2("18", "Checklist de aprobación")]
    if ck.approvers_required:
        lines.append("**Aprobadores requeridos**:")
        lines.append(_bullet_list(ck.approvers_required))
    lines.append("")
    if not ck.items:
        lines.append("_(checklist vacío)_")
    for it in ck.items:
        marker = {"blocker": "🛑", "must": "✅", "should": "🟡"}.get(it.severity, "•")
        lines.append(f"- [ ] {marker} **[{it.severity}]** _{it.category}_ — {it.title}")
        if it.notes:
            lines.append(f"    - {it.notes}")
    return "\n".join(lines)


def _render_risk_assessment(r: CampaignStrategyReport) -> str:
    ra = r.risk_assessment
    lines = [_section_h2("19", "Riesgos / claims a validar")]
    lines.append(f"**Claims no verificados**: {ra.unverified_claims_count}")
    lines.append(f"**Requiere auditoría de compliance**: {ra.requires_compliance_audit}")
    if not ra.risks:
        lines.append("_(sin riesgos registrados)_")
    for risk in ra.risks:
        lines.append(f"\n### [{risk.severity}] {risk.description}")
        if risk.claim_text:
            lines.append(f"- Claim asociado: _{risk.claim_text}_")
        if risk.mitigation:
            lines.append(f"- Mitigación: {risk.mitigation}")
    return "\n".join(lines)


def _render_next_steps(r: CampaignStrategyReport) -> str:
    lines = [_section_h2("20", "Próximos pasos")]
    lines.append(_bullet_list(r.next_steps))
    return "\n".join(lines)


def _render_footer(r: CampaignStrategyReport) -> str:
    return (
        "---\n\n"
        f"_Generated by `core.strategy` engine v1 (`{r.contract_version}`). "
        "Deterministic, LLM-free output. Review before any external action._"
    )


__all__ = ["render_markdown_report"]
