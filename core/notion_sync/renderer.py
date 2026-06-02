"""Markdown renderer for the Notion sync dry-run plan (MKT-5A)."""

from __future__ import annotations

from .models import (
    NotionPlanIssueSeverity,
    NotionSyncPlan,
    PlannedAction,
)

_ACTION_EMOJI: dict[str, str] = {
    "create": "🟢",
    "skip_blocked": "🛑",
    "skip_invalid": "❌",
}

_SEVERITY_EMOJI: dict[str, str] = {
    "info": "ℹ️",
    "warning": "⚠️",
    "error": "🛑",
}


def render_markdown_plan(plan: NotionSyncPlan) -> str:
    parts: list[str] = []
    parts.append(_render_header(plan))
    parts.append(_render_summary(plan))
    parts.append(_render_database(plan))
    parts.append(_render_mappings(plan))
    parts.append(_render_records(plan))
    parts.append(_render_issues(plan))
    parts.append(_render_footer(plan))
    return "\n\n".join(parts) + "\n"


def _render_header(plan: NotionSyncPlan) -> str:
    return (
        f"# Notion Sync Plan — {plan.client_slug} _(DRY RUN)_\n\n"
        f"- **Plan ID**: `{plan.plan_id}`\n"
        f"- **Contract**: `{plan.contract_version}`\n"
        f"- **Rule set**: `{plan.rule_set_id or '—'}`\n"
        f"- **Task pack**: `{plan.task_pack_id}` "
        f"({plan.task_pack_contract_version})\n"
        f"- **Notion payload schema**: `{plan.notion_payload_schema_version}`\n"
        f"- **Generado**: `{plan.created_at.isoformat()}`\n\n"
        "> ⚠️ Esto es un dry-run. No se conectó a Notion, no se creó "
        "ninguna página, no se usaron credenciales."
    )


def _render_summary(plan: NotionSyncPlan) -> str:
    stats = plan.stats
    blocks_emoji = "🛑" if plan.blocks_publish else "✅"
    lines = ["## 01. Resumen"]
    lines.append(f"- **Total de tareas**: `{stats.total_tasks}`")
    lines.append(
        f"- **Bloquea publicación**: {blocks_emoji} `{plan.blocks_publish}`"
    )
    if plan.upstream_overall_state:
        lines.append(f"- **Estado upstream**: `{plan.upstream_overall_state}`")
    lines.append("\n**Acciones planeadas**:")
    lines.append(f"- 🟢 `create`: {stats.would_create}")
    lines.append(f"- 🛑 `skip_blocked`: {stats.skip_blocked}")
    lines.append(f"- ❌ `skip_invalid`: {stats.skip_invalid}")
    lines.append("\n**Issues detectados**:")
    lines.append(f"- 🛑 error: {stats.issues_error}")
    lines.append(f"- ⚠️ warning: {stats.issues_warning}")
    lines.append(f"- ℹ️ info: {stats.issues_info}")
    return "\n".join(lines)


def _render_database(plan: NotionSyncPlan) -> str:
    db = plan.recommended_database
    lines = ["## 02. Base Notion recomendada"]
    lines.append(f"- **Título sugerido**: `{db.title}`")
    if db.icon:
        lines.append(f"- **Icono sugerido**: {db.icon}")
    if db.description:
        lines.append(f"- **Descripción**: {db.description}")
    if db.notes:
        lines.append("\n**Notas para el operador**:")
        for n in db.notes:
            lines.append(f"- {n}")
    return "\n".join(lines)


def _render_mappings(plan: NotionSyncPlan) -> str:
    lines = ["## 03. Mapping de propiedades"]
    lines.append(
        "| Propiedad Notion | Tipo | Campo fuente | Requerido | Opciones |"
    )
    lines.append("|------------------|------|--------------|-----------|----------|")
    for m in plan.recommended_database.property_mappings:
        opts = ", ".join(f"`{o}`" for o in m.select_options) if m.select_options else "—"
        req = "✅" if m.required else "—"
        lines.append(
            f"| `{m.notion_name}` | `{m.notion_type.value}` | "
            f"`{m.source_field}` | {req} | {opts} |"
        )
    notes = [
        m for m in plan.recommended_database.property_mappings
        if m.notes
    ]
    if notes:
        lines.append("\n**Notas por propiedad**:")
        for m in notes:
            lines.append(f"- **{m.notion_name}** — {m.notes}")
    return "\n".join(lines)


def _render_records(plan: NotionSyncPlan) -> str:
    lines = ["## 04. Registros planeados"]
    if not plan.planned_records:
        lines.append("_(no hay tareas que sincronizar)_")
        return "\n".join(lines)
    lines.append(
        "| # | Acción | Tarea | Estado | Prio | Categoría | Campos | Razón |"
    )
    lines.append("|---|--------|-------|--------|------|-----------|--------|-------|")
    # Sort: SKIP first (loud), then by category, then by title.
    action_rank = {
        PlannedAction.SKIP_INVALID.value: 0,
        PlannedAction.SKIP_BLOCKED.value: 1,
        PlannedAction.CREATE.value: 2,
    }
    records = sorted(
        plan.planned_records,
        key=lambda r: (
            action_rank.get(r.action.value, 9),
            r.proposed_category,
            r.title,
        ),
    )
    for i, r in enumerate(records, start=1):
        action = f"{_ACTION_EMOJI.get(r.action.value, '·')} `{r.action.value}`"
        title = r.title.replace("|", "\\|")[:80]
        reason = (r.reason or "—").replace("|", "\\|")[:80]
        lines.append(
            f"| {i} | {action} | {title} | `{r.proposed_status}` | "
            f"`{r.proposed_priority}` | `{r.proposed_category}` | "
            f"{r.field_count} | {reason} |"
        )
    return "\n".join(lines)


def _render_issues(plan: NotionSyncPlan) -> str:
    lines = ["## 05. Issues de validación"]
    if not plan.issues:
        lines.append("_(sin issues)_")
        return "\n".join(lines)
    # Group by severity in fixed order.
    for sev in (
        NotionPlanIssueSeverity.ERROR,
        NotionPlanIssueSeverity.WARNING,
        NotionPlanIssueSeverity.INFO,
    ):
        bucket = plan.issues_for(sev)
        if not bucket:
            continue
        lines.append(
            f"\n### {_SEVERITY_EMOJI[sev.value]} {sev.value.upper()} "
            f"({len(bucket)})"
        )
        for issue in bucket:
            target = (
                f" — task `{issue.task_id[:8]}`" if issue.task_id else " — global"
            )
            field = f" / field `{issue.field}`" if issue.field else ""
            lines.append(
                f"- **[{issue.code}]**{target}{field}: {issue.message}"
            )
            if issue.mitigation:
                lines.append(f"  - _Mitigación_: {issue.mitigation}")
    return "\n".join(lines)


def _render_footer(plan: NotionSyncPlan) -> str:
    return (
        "---\n\n"
        f"_Generated by `core.notion_sync` v1 (`{plan.contract_version}`). "
        "Deterministic dry-run. **No Notion API was called. No credential "
        "was read. No page was created.** El sync real (con auth + write) "
        "es scope de un bloque futuro._"
    )


__all__ = ["render_markdown_plan"]
