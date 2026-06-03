"""Markdown renderer for the NextCampaignIterationPlan."""

from __future__ import annotations

from .models import (
    NextCampaignIterationPlan,
)

_PRIORITY_EMOJI = {"high": "🔴", "medium": "🟠", "low": "⚪"}
_KIND_EMOJI = {
    "repeat_piece": "🔁",
    "improve_piece": "🛠️",
    "pause_piece": "⏸️",
    "create_new": "✨",
    "channel_promote": "📈",
    "channel_pause": "⏸️",
}
_CONTENT_KIND_EMOJI = {
    "seo_article": "🔎",
    "social_post": "📱",
    "email_draft": "📧",
    "landing_page": "🌐",
    "reels_script": "🎬",
}


def render_markdown_iteration_plan(plan: NextCampaignIterationPlan) -> str:
    parts: list[str] = []
    parts.append(_render_header(plan))
    if plan.executive_summary:
        parts.append(_render_summary(plan))
    parts.append(_render_stats(plan))
    parts.append(_render_actions(plan))
    parts.append(_render_new_content(plan))
    parts.append(_render_ab_tests(plan))
    parts.append(_render_calendar(plan))
    parts.append(_render_suggested_tasks(plan))
    if plan.executive_summary and plan.executive_summary.suggested_meeting_agenda:
        parts.append(_render_agenda(plan))
    parts.append(_render_footer(plan))
    return "\n\n".join(parts) + "\n"


def _render_header(plan: NextCampaignIterationPlan) -> str:
    return (
        f"# Next Campaign Iteration Plan — {plan.client_slug}\n\n"
        f"- **Plan ID**: `{plan.plan_id}`\n"
        f"- **Contract**: `{plan.contract_version}`\n"
        f"- **Rule set**: `{plan.rule_set_id or '—'}`\n"
        f"- **Feedback pack**: `{plan.feedback_pack_id}` "
        f"({plan.feedback_pack_contract_version})\n"
        f"- **Recommendation pack**: `{plan.recommendation_pack_id or '—'}`\n"
        f"- **Snapshot**: `{plan.snapshot_id or '—'}`\n"
        f"- **Run summary**: `{plan.run_summary_id or '—'}`\n"
        f"- **Strategy**: `{plan.strategy_report_id or '—'}`\n"
        f"- **Generado**: `{plan.created_at.isoformat()}`\n"
    )


def _render_summary(plan: NextCampaignIterationPlan) -> str:
    s = plan.executive_summary
    if s is None:
        return ""
    lines = ["## 01. Resumen ejecutivo"]
    lines.append(f"**{s.headline}**\n")
    for p in s.paragraphs:
        lines.append(f"> {p}")
    return "\n".join(lines)


def _render_stats(plan: NextCampaignIterationPlan) -> str:
    s = plan.stats
    lines = ["## 02. Estadísticas"]
    lines.append(f"- **Total items**: `{plan.total_items}`")
    lines.append(f"- 🎯 Acciones: {s.total_actions} (🔁 {s.repeats} · "
                 f"🛠️ {s.improves} · ⏸️ {s.pauses} · ✨ {s.creates})")
    lines.append(f"- 📈 Ajustes de canal: {s.channel_adjustments}")
    lines.append(f"- ✨ Ideas de contenido nuevas: {s.new_content_ideas}")
    lines.append(f"- 🧪 Tests A/B sugeridos: {s.ab_test_hypotheses}")
    lines.append(f"- 📅 Entradas de calendario: {s.calendar_entries}")
    lines.append(f"- 📋 Tareas sugeridas: {s.suggested_tasks}")
    return "\n".join(lines)


def _render_actions(plan: NextCampaignIterationPlan) -> str:
    if not plan.actions:
        return "## 03. Acciones\n_(sin acciones para el próximo ciclo)_"
    lines = ["## 03. Acciones para el próximo ciclo"]
    rank = {"high": 0, "medium": 1, "low": 2}
    actions = sorted(
        plan.actions,
        key=lambda a: (rank.get(a.priority.value, 9), a.kind.value, a.title),
    )
    for a in actions:
        kind_emoji = _KIND_EMOJI.get(a.kind.value, "·")
        prio_emoji = _PRIORITY_EMOJI.get(a.priority.value, "·")
        lines.append(
            f"\n### {kind_emoji} {a.title}  _({prio_emoji} `{a.priority.value}`, "
            f"`{a.kind.value}`)_"
        )
        if a.channel:
            lines.append(f"- **Canal**: `{a.channel}`")
        if a.target_ref:
            lines.append(f"- **Pieza**: `{a.target_ref}`")
        lines.append(f"- **Por qué**: {a.rationale}")
        lines.append(f"- **Próximo paso**: {a.suggested_next_step}")
    return "\n".join(lines)


def _render_new_content(plan: NextCampaignIterationPlan) -> str:
    if not plan.new_content_ideas:
        return "## 04. Ideas de contenido nuevas\n_(sin ideas)_"
    lines = ["## 04. Ideas de contenido nuevas"]
    lines.append("| # | Tipo | Idea | Canal | Prio |")
    lines.append("|---|------|------|-------|------|")
    for i, idea in enumerate(plan.new_content_ideas, start=1):
        emoji_k = _CONTENT_KIND_EMOJI.get(idea.kind.value, "·")
        emoji_p = _PRIORITY_EMOJI.get(idea.priority.value, "·")
        title = idea.title.replace("|", "\\|")[:80]
        lines.append(
            f"| {i} | {emoji_k} `{idea.kind.value}` | {title} | "
            f"`{idea.channel or '—'}` | {emoji_p} `{idea.priority.value}` |"
        )
    # Per-idea detail.
    lines.append("")
    for idea in plan.new_content_ideas:
        lines.append(f"\n### {idea.title}")
        if idea.angle:
            lines.append(f"- **Ángulo**: {idea.angle}")
        lines.append(f"- **Por qué**: {idea.rationale}")
    return "\n".join(lines)


def _render_ab_tests(plan: NextCampaignIterationPlan) -> str:
    if not plan.ab_test_hypotheses:
        return "## 05. Hipótesis A/B\n_(sin tests propuestos)_"
    lines = ["## 05. Hipótesis A/B"]
    for h in plan.ab_test_hypotheses:
        lines.append(f"\n### 🧪 Test en `{h.surface}`")
        lines.append(f"- **A (control)**: {h.variant_a}")
        lines.append(f"- **B (variante)**: {h.variant_b}")
        lines.append(
            f"- **Métrica de éxito**: `{h.success_metric}` ({h.success_threshold})"
        )
        lines.append(f"- **Por qué**: {h.rationale}")
    return "\n".join(lines)


def _render_calendar(plan: NextCampaignIterationPlan) -> str:
    if not plan.calendar:
        return "## 06. Calendario sugerido\n_(sin calendario)_"
    lines = ["## 06. Calendario sugerido"]
    lines.append("| Semana | Fecha | Canal | Pieza | Nota |")
    lines.append("|--------|-------|-------|-------|------|")
    for e in plan.calendar:
        date_str = e.suggested_date.isoformat() if e.suggested_date else "—"
        note = (e.note or "—").replace("|", "\\|")[:60]
        lines.append(
            f"| {e.week} | {date_str} | `{e.channel}` | "
            f"`{e.piece_type}` | {note} |"
        )
    return "\n".join(lines)


def _render_suggested_tasks(plan: NextCampaignIterationPlan) -> str:
    if not plan.suggested_tasks:
        return "## 07. Tareas sugeridas\n_(sin tareas)_"
    rank = {"high": 0, "medium": 1, "low": 2}
    tasks = sorted(
        plan.suggested_tasks,
        key=lambda t: (rank.get(t.priority.value, 9), t.category, t.title),
    )
    lines = ["## 07. Tareas sugeridas para el próximo ciclo"]
    lines.append("| # | Tarea | Categoría | Prio | Owner |")
    lines.append("|---|-------|-----------|------|-------|")
    for i, t in enumerate(tasks, start=1):
        emoji = _PRIORITY_EMOJI.get(t.priority.value, "·")
        title = t.title.replace("|", "\\|")[:80]
        lines.append(
            f"| {i} | {title} | `{t.category}` | "
            f"{emoji} `{t.priority.value}` | `{t.suggested_owner or '—'}` |"
        )
    return "\n".join(lines)


def _render_agenda(plan: NextCampaignIterationPlan) -> str:
    s = plan.executive_summary
    if s is None or not s.suggested_meeting_agenda:
        return ""
    lines = ["## 08. Agenda sugerida para la review"]
    for item in s.suggested_meeting_agenda:
        lines.append(f"- {item}")
    return "\n".join(lines)


def _render_footer(plan: NextCampaignIterationPlan) -> str:
    return (
        "---\n\n"
        f"_Generated by `core.iteration.planner` v1 "
        f"(`{plan.contract_version}`). Heurísticas deterministas; sin LLM, "
        "sin API externa. **El plan no aplica cambios — una persona "
        "revisa y decide qué promover al próximo brief.**_"
    )


__all__ = ["render_markdown_iteration_plan"]
