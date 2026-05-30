"""Markdown renderer for :class:`ApprovalPack`.

Pure function: ``render_markdown_pack(pack) -> str``. No I/O.
"""

from __future__ import annotations

from .models import ApprovalPack, ApprovalState

_STATE_LABELS = {
    ApprovalState.DRAFT: "Draft",
    ApprovalState.NEEDS_REVIEW: "Needs review",
    ApprovalState.APPROVED: "Approved",
    ApprovalState.REJECTED: "Rejected",
}

_SEVERITY_EMOJI = {
    "safe": "🟢",
    "caveat": "🟡",
    "risky": "🟠",
    "unsafe": "🔴",
}


def render_markdown_pack(pack: ApprovalPack) -> str:
    """Render an :class:`ApprovalPack` to Markdown."""
    parts: list[str] = []
    parts.append(_render_header(pack))
    parts.append(_render_summary(pack))
    parts.append(_render_state(pack))
    parts.append(_render_detections(pack))
    parts.append(_render_checklist(pack))
    parts.append(_render_decision(pack))
    parts.append(_render_footer(pack))
    return "\n\n".join(parts) + "\n"


# ---------- helpers ----------

def _bullets(items: list[str]) -> str:
    if not items:
        return "_(vacío)_"
    return "\n".join(f"- {it}" for it in items)


def _section_h2(num: str, title: str) -> str:
    return f"## {num}. {title}"


def _short(s: str, limit: int) -> str:
    return s if len(s) <= limit else s[: limit - 1].rstrip() + "…"


# ---------- sections ----------

def _render_header(pack: ApprovalPack) -> str:
    return (
        f"# Approval Pack — {pack.client_slug}\n\n"
        f"- **Pack ID**: `{pack.pack_id}`\n"
        f"- **Report ID**: `{pack.report_id}`\n"
        f"- **Report contract**: `{pack.report_contract_version}`\n"
        f"- **Pack contract**: `{pack.contract_version}`\n"
        f"- **Rule set**: `{pack.rule_set_id or '—'}`\n"
        f"- **Generado**: `{pack.created_at.isoformat()}`\n"
        f"- **Última actualización**: `{pack.updated_at.isoformat()}`\n"
    )


def _render_summary(pack: ApprovalPack) -> str:
    severity_counts = pack.count_by_severity()
    category_counts = pack.count_by_category()
    blocks_emoji = "🛑" if pack.blocks_publish else "✅"
    lines = [_section_h2("01", "Resumen")]
    lines.append(
        f"- **Total detecciones**: {pack.total_detections}"
    )
    lines.append(
        f"- **Severidad agregada**: {_SEVERITY_EMOJI.get(pack.overall_severity.value, '·')} "
        f"`{pack.overall_severity.value}`"
    )
    lines.append(
        f"- **Bloquea publicación**: {blocks_emoji} `{pack.blocks_publish}`"
    )
    lines.append(
        f"- **Requieren revisión humana**: {pack.human_review_required_count}"
    )
    if any(v > 0 for v in severity_counts.values()):
        lines.append("\n**Conteo por severidad**:")
        for sev, count in severity_counts.items():
            if count:
                lines.append(f"- {_SEVERITY_EMOJI.get(sev, '·')} `{sev}`: {count}")
    if category_counts:
        lines.append("\n**Conteo por categoría**:")
        for cat, count in sorted(category_counts.items()):
            lines.append(f"- `{cat}`: {count}")
    return "\n".join(lines)


def _render_state(pack: ApprovalPack) -> str:
    lines = [_section_h2("02", "Estado del pack")]
    lines.append(
        f"**Estado actual**: `{pack.state.value}` ({_STATE_LABELS[pack.state]})"
    )
    if pack.is_terminal:
        lines.append("\n_El pack está en estado terminal._")
    else:
        lines.append("\n_El pack puede transicionar a NEEDS_REVIEW → APPROVED | REJECTED._")
    return "\n".join(lines)


def _render_detections(pack: ApprovalPack) -> str:
    lines = [_section_h2("03", "Claims detectados")]
    if not pack.detections:
        lines.append("_(no se detectaron claims sensibles)_")
        return "\n".join(lines)

    lines.append(
        "| Severidad | Categoría | Ubicación | Span | Mitigación |"
    )
    lines.append(
        "|-----------|-----------|-----------|------|------------|"
    )
    for d in pack.detections:
        emoji = _SEVERITY_EMOJI.get(d.severity.value, "·")
        mitig = _short(d.suggested_mitigation or "—", 90).replace("|", "\\|")
        span = _short(d.text_span, 60).replace("|", "\\|")
        location = d.located_in.replace("|", "\\|")
        lines.append(
            f"| {emoji} `{d.severity.value}` | `{d.category.value}` | "
            f"`{location}` | {span} | {mitig} |"
        )

    # Detail per detection for traceability.
    lines.append("\n### Detalle por detección")
    for d in pack.detections:
        lines.append(f"\n#### `{d.detection_id[:8]}…` — {d.rule_description}")
        lines.append(f"- **Regla**: `{d.rule_id}`")
        lines.append(f"- **Categoría**: `{d.category.value}`")
        lines.append(f"- **Severidad**: `{d.severity.value}`")
        lines.append(f"- **Ubicación**: `{d.located_in}`")
        lines.append(f"- **Texto detectado**: _{d.text_span}_")
        if d.suggested_mitigation:
            lines.append(f"- **Mitigación sugerida**: {d.suggested_mitigation}")
        lines.append(f"- **Requiere revisión humana**: `{d.requires_human_review}`")
        if d.evidence_refs:
            lines.append(
                "- **Evidencia asociada**: " + ", ".join(f"`{r}`" for r in d.evidence_refs)
            )
    return "\n".join(lines)


def _render_checklist(pack: ApprovalPack) -> str:
    lines = [_section_h2("04", "Checklist para el reviewer")]
    if not pack.checklist:
        lines.append("_(sin items)_")
        return "\n".join(lines)
    for item in pack.checklist:
        marker = {"blocker": "🛑", "must": "✅", "should": "🟡"}.get(item.severity, "•")
        lines.append(
            f"- [ ] {marker} **[{item.severity}]** _{item.category}_ — {item.title}"
        )
        if item.notes:
            lines.append(f"    - {item.notes}")
        if item.linked_detection_ids:
            ids = ", ".join(f"`{i[:8]}…`" for i in item.linked_detection_ids)
            lines.append(f"    - Linked: {ids}")
    return "\n".join(lines)


def _render_decision(pack: ApprovalPack) -> str:
    lines = [_section_h2("05", "Decisión humana")]
    if pack.decision is None:
        lines.append("_(sin decisión registrada todavía)_")
        return "\n".join(lines)
    d = pack.decision
    lines.append(f"- **Reviewer**: `{d.reviewer}`")
    lines.append(f"- **Decidido en**: `{d.decided_at.isoformat()}`")
    if d.notes:
        lines.append(f"\n**Notas**:\n\n> {d.notes}")
    return "\n".join(lines)


def _render_footer(pack: ApprovalPack) -> str:
    return (
        "---\n\n"
        f"_Generated by `core.approval` engine v1 (`{pack.contract_version}`). "
        "Rules-based, deterministic. Review before any external action._"
    )


__all__ = ["render_markdown_pack"]
