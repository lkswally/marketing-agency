"""Markdown renderer for :class:`SEOIntelligenceReportPack` (MKT-10C).

Professional, executive, actionable — deliberately NOT a reproduction of
any client's visual report design. Plain Markdown sections only.
"""

from __future__ import annotations

from .models import (
    FindingNature,
    SEOFinding,
    SEOIntelligenceReportPack,
)

_NATURE_LABEL = {
    FindingNature.FACT: "FACT",
    FindingNature.HYPOTHESIS: "HYPOTHESIS",
    FindingNature.RECOMMENDATION: "RECOMMENDATION",
}


def render_markdown_seo_report(pack: SEOIntelligenceReportPack) -> str:
    lines: list[str] = []
    lines.append(f"# SEO Intelligence Report — `{pack.client_slug}`")
    lines.append("")
    lines.append(f"- **Report id:** `{pack.report_id}`")
    lines.append(f"- **Created:** `{pack.created_at.isoformat()}`")
    if pack.period_label or pack.period_start:
        period = pack.period_label or f"{pack.period_start} → {pack.period_end}"
        lines.append(f"- **Period:** {period}")
    lines.append(f"- **Evidence input supplied:** {pack.evidence_input_provided}")
    if pack.snapshot_id:
        lines.append(f"- **Snapshot id:** `{pack.snapshot_id}`")
    lines.append("")

    # 1. Executive summary
    lines.append("## 1. Resumen ejecutivo")
    lines.append("")
    s = pack.executive_summary
    lines.append(s.headline)
    lines.append("")
    lines.append(
        f"- Facts: **{s.facts_count}** · Hypotheses: **{s.hypotheses_count}** · "
        f"Recommendations: **{s.recommendations_count}** · "
        f"High-severity risks: **{s.high_severity_risk_count}**"
    )
    if s.top_opportunities:
        lines.append(f"- Top opportunities: {', '.join(s.top_opportunities)}")
    lines.append(f"- {s.evidence_coverage_note}")
    lines.append("")

    # 2 / 19. Evidence status / missing data
    lines.append("## 2. Estado de la evidencia")
    lines.append("")
    if pack.missing_evidence:
        for m in pack.missing_evidence:
            lines.append(f"- ⚪ `{m.category.value}` — {m.description}")
    else:
        lines.append("_All expected evidence categories had coverage this run._")
    lines.append("")

    # 3-4. Keyword research + intent
    lines.append("## 3-4. Keyword research e intenciones de búsqueda")
    lines.append("")
    if pack.keyword_clusters:
        lines.append("| Cluster | Intent | Keywords | Total volume | Avg position |")
        lines.append("|---|---|---:|---:|---:|")
        for c in pack.keyword_clusters:
            vol = f"{c.total_search_volume:.0f}" if c.total_search_volume is not None else "—"
            pos = f"{c.avg_position:.1f}" if c.avg_position is not None else "—"
            lines.append(
                f"| {c.label} | {c.dominant_intent.value} | {len(c.keywords)} | {vol} | {pos} |"
            )
    else:
        lines.append("_NOT_AVAILABLE — see Estado de la evidencia._")
    lines.append("")

    # 5. Organic performance
    lines.append("## 5. Rendimiento orgánico")
    lines.append("")
    _render_findings(lines, pack.organic_performance_findings)

    # 6. Page architecture
    lines.append("## 6. Arquitectura de páginas")
    lines.append("")
    _render_findings(lines, pack.page_architecture_findings)

    # 7. Canonicalization
    lines.append("## 7. Canonicalización")
    lines.append("")
    if pack.canonical_risks:
        for r in pack.canonical_risks:
            lines.append(
                f"- [{r.severity.value.upper()}] ({r.nature.value}) "
                f"{r.description}" + (f" — `{r.affected_url}`" if r.affected_url else "")
            )
    else:
        lines.append("_NOT_AVAILABLE — see Estado de la evidencia._")
    lines.append("")

    # 8. Indexation
    lines.append("## 8. Indexación")
    lines.append("")
    if pack.indexation_risks:
        for r in pack.indexation_risks:
            lines.append(
                f"- [{r.severity.value.upper()}] ({r.nature.value}) "
                f"{r.description}" + (f" — `{r.affected_url}`" if r.affected_url else "")
            )
    else:
        lines.append("_NOT_AVAILABLE — see Estado de la evidencia._")
    lines.append("")

    # 9-10-11. Thin content, internal linking, content clusters
    lines.append("## 9. Thin content")
    lines.append("")
    thin = [g for g in pack.content_gaps if g.kind == "thin_content"]
    if thin:
        for g in thin:
            lines.append(f"- {g.rationale}" + (f" — `{g.affected_url}`" if g.affected_url else ""))
    else:
        lines.append("_NOT_AVAILABLE — see Estado de la evidencia._")
    lines.append("")

    lines.append("## 10. Enlazado interno")
    lines.append("")
    if pack.internal_link_opportunities:
        for o in pack.internal_link_opportunities:
            lines.append(f"- `{o.source_url}` → `{o.target_url}` — {o.rationale}")
    else:
        lines.append("_No opportunities surfaced this run._")
    lines.append("")

    lines.append("## 11. Contenido y clusters")
    lines.append("")
    missing_topics = [g for g in pack.content_gaps if g.kind == "missing_topic"]
    if missing_topics:
        for g in missing_topics:
            lines.append(f"- **{g.topic}** — {g.rationale}")
    else:
        lines.append("_No content-cluster gaps surfaced this run._")
    lines.append("")

    # 12. Locales
    lines.append("## 12. Países, idiomas y locales")
    lines.append("")
    if pack.locale_opportunities:
        for o in pack.locale_opportunities:
            status = "active" if o.is_active_today else "target"
            lines.append(f"- `{o.locale}` ({status}) — {o.description}")
    else:
        lines.append("_NOT_AVAILABLE — see Estado de la evidencia._")
    lines.append("")

    # 13. Competitors
    lines.append("## 13. Competidores")
    lines.append("")
    _render_findings(lines, pack.competitor_findings)

    # 14. Risks (rollup)
    lines.append("## 14. Riesgos")
    lines.append("")
    risk_count = len(pack.canonical_risks) + len(pack.indexation_risks)
    if risk_count:
        lines.append(
            f"{risk_count} risk(s) identified: "
            f"{len(pack.canonical_risks)} canonicalization, "
            f"{len(pack.indexation_risks)} indexation. All HYPOTHESIS-nature "
            "unless the source note explicitly confirms the behaviour."
        )
    else:
        lines.append("_No risks surfaced this run._")
    lines.append("")

    # 15. Opportunities (rollup)
    lines.append("## 15. Oportunidades")
    lines.append("")
    opp_count = len(pack.internal_link_opportunities) + len(pack.content_gaps) + len(
        [o for o in pack.locale_opportunities if not o.is_active_today]
    )
    if opp_count:
        lines.append(f"{opp_count} opportunity(ies) across linking, content and locale expansion.")
    else:
        lines.append("_No opportunities surfaced this run._")
    lines.append("")

    # 16. Roadmap
    lines.append("## 16. Roadmap por fases")
    lines.append("")
    if pack.roadmap:
        for phase in pack.roadmap:
            lines.append(f"### Phase {phase.phase_number} — {phase.title}")
            lines.append("")
            lines.append(f"- **Objective:** {phase.objective}")
            lines.append(f"- **Effort:** {phase.effort.value}")
            lines.append(f"- **Can become task:** {phase.can_become_task}")
            if phase.acceptance_criteria:
                lines.append("- **Acceptance criteria:**")
                for ac in phase.acceptance_criteria:
                    lines.append(f"  - {ac.description}")
            lines.append("")
    else:
        lines.append("_No roadmap phases proposed this run._")
        lines.append("")

    # 17-18. Dev gaps + acceptance criteria
    lines.append("## 17-18. Gaps para desarrollo y criterios de aceptación")
    lines.append("")
    if pack.development_gaps:
        for g in pack.development_gaps:
            lines.append(f"### {g.title}")
            lines.append("")
            lines.append(g.description)
            if g.acceptance_criteria:
                lines.append("")
                lines.append("Acceptance criteria:")
                for ac in g.acceptance_criteria:
                    lines.append(f"- {ac.description}")
            lines.append("")
    else:
        lines.append("_No development gaps identified this run._")
        lines.append("")

    # 19. Missing data (explicit callback)
    lines.append("## 19. Datos faltantes")
    lines.append("")
    if pack.missing_evidence:
        for m in pack.missing_evidence:
            lines.append(f"- `{m.category.value}`: {m.description}")
    else:
        lines.append("_No missing evidence this run._")
    lines.append("")

    # 20. Next decisions
    lines.append("## 20. Próximas decisiones requeridas")
    lines.append("")
    for d in pack.next_decisions_required:
        lines.append(f"- {d}")
    lines.append("")

    lines.append("---")
    lines.append("")
    lines.append(
        "_Deterministic consolidation. No scraping, no external API, no "
        "LLM. Every finding traces to a declared evidence source; "
        "hypotheses and recommendations are explicitly labelled and never "
        "asserted as fact._"
    )
    lines.append("")
    return "\n".join(lines)


def _render_findings(lines: list[str], findings: list[SEOFinding]) -> None:
    if not findings:
        lines.append("_NOT_AVAILABLE — see Estado de la evidencia._")
        lines.append("")
        return
    for f in findings:
        nature = _NATURE_LABEL[f.nature]
        sev = f" [{f.severity.value.upper()}]" if f.severity else ""
        lines.append(f"- **[{nature}]{sev}** ({f.confidence.value}) {f.statement}")
        if f.metrics_cited:
            metrics = ", ".join(f"{k}={v}" for k, v in sorted(f.metrics_cited.items()))
            lines.append(f"  - Metrics: {metrics}")
    lines.append("")


__all__ = ["render_markdown_seo_report"]
