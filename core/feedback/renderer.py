"""Markdown renderer for the CampaignFeedbackPack."""

from __future__ import annotations

from .models import (
    CampaignFeedbackPack,
)

_PRIORITY_EMOJI = {"high": "🔴", "medium": "🟠", "low": "⚪"}
_CHANNEL_PRIO_EMOJI = {
    "high": "🔴",
    "medium": "🟠",
    "low": "⚪",
    "pause": "⏸️",
}
_KIND_EMOJI = {"repeat": "🔁", "improve": "🛠️", "pause": "⏸️"}


def render_markdown_feedback(pack: CampaignFeedbackPack) -> str:
    parts: list[str] = []
    parts.append(_render_header(pack))
    if pack.executive_summary:
        parts.append(_render_summary(pack))
    parts.append(_render_stats(pack))
    parts.append(_render_channel_adjustments(pack))
    parts.append(_render_content_suggestions(pack))
    parts.append(_render_seo(pack))
    parts.append(_render_email(pack))
    parts.append(_render_social(pack))
    parts.append(_render_suggested_tasks(pack))
    if pack.executive_summary and pack.executive_summary.suggested_meeting_agenda:
        parts.append(_render_meeting_agenda(pack))
    parts.append(_render_footer(pack))
    return "\n\n".join(parts) + "\n"


def _render_header(pack: CampaignFeedbackPack) -> str:
    return (
        f"# Campaign Feedback Pack — {pack.client_slug}\n\n"
        f"- **Pack ID**: `{pack.pack_id}`\n"
        f"- **Contract**: `{pack.contract_version}`\n"
        f"- **Rule set**: `{pack.rule_set_id or '—'}`\n"
        f"- **Recommendation pack**: `{pack.recommendation_pack_id or '—'}`\n"
        f"- **Snapshot**: `{pack.snapshot_id or '—'}`\n"
        f"- **Run summary**: `{pack.run_summary_id or '—'}`\n"
        f"- **Strategy**: `{pack.strategy_report_id or '—'}`\n"
        f"- **Task pack**: `{pack.task_pack_id or '—'}`\n"
        f"- **Generado**: `{pack.created_at.isoformat()}`\n"
    )


def _render_summary(pack: CampaignFeedbackPack) -> str:
    s = pack.executive_summary
    if s is None:
        return ""
    lines = ["## 01. Resumen ejecutivo"]
    lines.append(f"**{s.headline}**\n")
    for p in s.paragraphs:
        lines.append(f"> {p}")
    return "\n".join(lines)


def _render_stats(pack: CampaignFeedbackPack) -> str:
    s = pack.stats
    lines = ["## 02. Estadísticas"]
    lines.append(f"- **Total items**: `{pack.total_items}`")
    lines.append(f"- 🔴 **High-priority tasks**: {s.high_priority_tasks}")
    lines.append(f"- 📋 Tareas sugeridas: {s.total_suggested_tasks}")
    lines.append(f"- 🎯 Ajustes de canal: {s.channel_adjustments}")
    lines.append(f"- 📝 Sugerencias de contenido: {s.content_suggestions}")
    lines.append(f"- 🔎 Recomendaciones SEO: {s.seo_recommendations}")
    lines.append(f"- 📧 Recomendaciones de email: {s.email_recommendations}")
    lines.append(f"- 📱 Recomendaciones sociales: {s.social_recommendations}")
    return "\n".join(lines)


def _render_channel_adjustments(pack: CampaignFeedbackPack) -> str:
    if not pack.channel_adjustments:
        return "## 03. Ajustes de canal\n_(sin ajustes)_"
    lines = ["## 03. Ajustes de canal"]
    lines.append("| Canal | Actual | Nueva | Rationale |")
    lines.append("|-------|--------|-------|-----------|")
    for a in pack.channel_adjustments:
        cur = (
            f"{_CHANNEL_PRIO_EMOJI.get(a.current_priority.value, '·')} "
            f"`{a.current_priority.value}`"
            if a.current_priority is not None else "—"
        )
        new = (
            f"{_CHANNEL_PRIO_EMOJI.get(a.new_priority.value, '·')} "
            f"`{a.new_priority.value}`"
        )
        reason = a.rationale.replace("|", "\\|")[:100]
        lines.append(f"| `{a.channel}` | {cur} | {new} | {reason} |")
    return "\n".join(lines)


def _render_content_suggestions(pack: CampaignFeedbackPack) -> str:
    if not pack.content_suggestions:
        return "## 04. Sugerencias de contenido\n_(sin sugerencias)_"
    lines = ["## 04. Sugerencias de contenido"]
    # Sort: repeat first, then improve, then pause.
    rank = {"repeat": 0, "improve": 1, "pause": 2}
    sorted_items = sorted(
        pack.content_suggestions,
        key=lambda c: (rank.get(c.kind.value, 9), c.title),
    )
    for c in sorted_items:
        emoji = _KIND_EMOJI.get(c.kind.value, "·")
        lines.append(f"\n### {emoji} `{c.kind.value}` — {c.title}")
        if c.channel:
            lines.append(f"- **Canal**: `{c.channel}`")
        if c.content_ref:
            lines.append(f"- **Pieza**: `{c.content_ref}`")
        lines.append(f"- **Por qué**: {c.rationale}")
        lines.append(f"- **Próximo paso**: {c.suggested_next_step}")
    return "\n".join(lines)


def _render_seo(pack: CampaignFeedbackPack) -> str:
    if not pack.seo_recommendations:
        return "## 05. SEO\n_(sin oportunidades detectadas)_"
    lines = ["## 05. SEO"]
    lines.append("| # | Query / Page | Score | Prio | Acción |")
    lines.append("|---|--------------|-------|------|--------|")
    for i, r in enumerate(pack.seo_recommendations, start=1):
        label = (r.query or r.page or "—").replace("|", "\\|")[:60]
        emoji = _PRIORITY_EMOJI.get(r.priority.value, "·")
        action = r.suggested_action.replace("|", "\\|")[:80]
        lines.append(
            f"| {i} | `{label}` | {r.opportunity_score:.1f} | "
            f"{emoji} `{r.priority.value}` | {action} |"
        )
    return "\n".join(lines)


def _render_email(pack: CampaignFeedbackPack) -> str:
    if not pack.email_recommendations:
        return "## 06. Email\n_(sin recomendaciones)_"
    lines = ["## 06. Email"]
    lines.append("| Campaign | Open | Click | Prio | Acción |")
    lines.append("|----------|------|-------|------|--------|")
    for r in pack.email_recommendations:
        emoji = _PRIORITY_EMOJI.get(r.priority.value, "·")
        open_rate = f"{r.open_rate:.1%}" if r.open_rate is not None else "—"
        click_rate = f"{r.click_rate:.1%}" if r.click_rate is not None else "—"
        action = r.suggested_action.replace("|", "\\|")[:80]
        lines.append(
            f"| `{r.campaign_ref or '—'}` | {open_rate} | {click_rate} | "
            f"{emoji} `{r.priority.value}` | {action} |"
        )
    return "\n".join(lines)


def _render_social(pack: CampaignFeedbackPack) -> str:
    if not pack.social_recommendations:
        return "## 07. Social\n_(sin recomendaciones)_"
    lines = ["## 07. Social"]
    lines.append("| Canal | Pieza | Prio | Acción |")
    lines.append("|-------|-------|------|--------|")
    for r in pack.social_recommendations:
        emoji = _PRIORITY_EMOJI.get(r.priority.value, "·")
        ref = (r.content_ref or "—").replace("|", "\\|")[:30]
        action = r.suggested_action.replace("|", "\\|")[:80]
        lines.append(
            f"| `{r.channel}` | `{ref}` | {emoji} `{r.priority.value}` | {action} |"
        )
    return "\n".join(lines)


def _render_suggested_tasks(pack: CampaignFeedbackPack) -> str:
    if not pack.suggested_tasks:
        return "## 08. Tareas sugeridas\n_(sin tareas)_"
    rank = {"high": 0, "medium": 1, "low": 2}
    tasks = sorted(
        pack.suggested_tasks,
        key=lambda t: (rank.get(t.priority.value, 9), t.category.value, t.title),
    )
    lines = ["## 08. Tareas sugeridas"]
    lines.append("| # | Tarea | Categoría | Prio | Owner |")
    lines.append("|---|-------|-----------|------|-------|")
    for i, t in enumerate(tasks, start=1):
        emoji = _PRIORITY_EMOJI.get(t.priority.value, "·")
        title = t.title.replace("|", "\\|")[:80]
        lines.append(
            f"| {i} | {title} | `{t.category.value}` | "
            f"{emoji} `{t.priority.value}` | `{t.suggested_owner or '—'}` |"
        )
    return "\n".join(lines)


def _render_meeting_agenda(pack: CampaignFeedbackPack) -> str:
    s = pack.executive_summary
    if s is None or not s.suggested_meeting_agenda:
        return ""
    lines = ["## 09. Agenda sugerida para la review con cliente"]
    for item in s.suggested_meeting_agenda:
        lines.append(f"- {item}")
    return "\n".join(lines)


def _render_footer(pack: CampaignFeedbackPack) -> str:
    return (
        "---\n\n"
        f"_Generated by `core.feedback.planner` v1 "
        f"(`{pack.contract_version}`). Heurísticas deterministas; sin LLM, "
        "sin API externa, sin GA4 / Ads / Search Console real. **Las "
        "sugerencias no aplican cambios automáticamente — una persona "
        "revisa y decide.**_"
    )


__all__ = ["render_markdown_feedback"]
