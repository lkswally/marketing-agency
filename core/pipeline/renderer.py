"""Markdown renderer for :class:`CampaignRunSummary`.

Pure function: same summary → same Markdown. No I/O.
"""

from __future__ import annotations

from .models import CampaignRunSummary

_OUTCOME_EMOJI = {
    "succeeded": "✅",
    "skipped": "⏭️",
    "blocked": "🛑",
    "failed": "❌",
}

_STATE_EMOJI = {
    "draft": "🟢",
    "needs_review": "🟡",
    "ready_for_publish": "✅",
    "blocked": "🛑",
}


def render_markdown_summary(summary: CampaignRunSummary) -> str:
    parts: list[str] = []
    parts.append(_render_header(summary))
    parts.append(_render_summary(summary))
    parts.append(_render_backend(summary))
    parts.append(_render_stages(summary))
    parts.append(_render_artifacts(summary))
    parts.append(_render_next_steps(summary))
    parts.append(_render_footer(summary))
    return "\n\n".join(parts) + "\n"


def _render_backend(summary: CampaignRunSummary) -> str:
    """Backend bookkeeping section. Always present; surfaces fallbacks loudly."""
    lines = [_section_h2("01b", "Strategy backend")]
    requested = summary.backend_requested
    effective = summary.backend_effective
    fb_count = summary.backend_fallback_count

    requested_emoji = "📋" if requested == "templated" else "🤖"
    if requested == "templated":
        lines.append(f"- **Backend solicitado**: {requested_emoji} `templated` (default).")
    else:
        lines.append(f"- **Backend solicitado**: {requested_emoji} `claude`.")

    if requested == "claude":
        if effective == "claude":
            lines.append("- **Backend efectivo**: 🤖 `claude` (sin fallback).")
        elif effective == "mixed":
            lines.append(
                f"- ⚠️ **Backend efectivo**: `mixed` — {fb_count} de 6 llamadas "
                "creativas cayeron al backend `templated`."
            )
        else:  # templated
            lines.append(
                "- 🛑 **Backend efectivo**: `templated` — **NINGUNA** llamada "
                "creativa fue resuelta por Claude real. "
                "Toda la salida vino del backend determinístico (fallback)."
            )
    else:
        lines.append("- **Backend efectivo**: 📋 `templated`.")

    if fb_count > 0:
        lines.append(f"\n**Fallbacks registrados ({fb_count})**:")
        for note in summary.backend_fallback_notes:
            lines.append(f"- ⚠️ {note}")
        lines.append(
            "\n> Este pipeline NO usó Claude real para los métodos listados. "
            "El backend Claude no está cableado a ningún invoker real todavía "
            "(scope MKT-4B). Los outputs vinieron del backend `templated`."
        )

    return "\n".join(lines)


# ---------- helpers ----------

def _section_h2(num: str, title: str) -> str:
    return f"## {num}. {title}"


# ---------- sections ----------

def _render_header(summary: CampaignRunSummary) -> str:
    return (
        f"# Campaign Pipeline Run — {summary.client_slug}\n\n"
        f"- **Run ID**: `{summary.run_id}`\n"
        f"- **Pipeline contract**: `{summary.contract_version}`\n"
        f"- **Rule set**: `{summary.rule_set_id or '—'}`\n"
        f"- **Iniciado**: `{summary.started_at.isoformat()}`\n"
        f"- **Finalizado**: `{summary.finished_at.isoformat()}`\n"
        f"- **Duración**: `{summary.duration_seconds:.2f}s`\n"
    )


def _render_summary(summary: CampaignRunSummary) -> str:
    blocks_emoji = "🛑" if summary.blocks_publish else "✅"
    lines = [_section_h2("01", "Resumen")]
    lines.append(
        f"- **Estado general**: {_STATE_EMOJI.get(summary.overall_state.value, '·')} "
        f"`{summary.overall_state.value}`"
    )
    lines.append(
        f"- **Bloquea publicación**: {blocks_emoji} `{summary.blocks_publish}`"
    )
    lines.append(f"- **Pipeline completo**: `{summary.is_complete}`")

    counts = summary.count_by_outcome()
    lines.append("\n**Conteo por outcome**:")
    for o in ("succeeded", "blocked", "skipped", "failed"):
        c = counts.get(o, 0)
        if c:
            lines.append(f"- {_OUTCOME_EMOJI[o]} `{o}`: {c}")

    lines.append("\n**Intake warnings**:")
    lines.append(f"- 🛑 critical: {summary.intake_critical_count}")
    lines.append(f"- 🟡 warning: {summary.intake_warning_count}")
    lines.append(f"- 🔵 info: {summary.intake_info_count}")
    return "\n".join(lines)


def _render_stages(summary: CampaignRunSummary) -> str:
    lines = [_section_h2("02", "Stages")]
    if not summary.stages:
        lines.append("_(sin stages ejecutadas)_")
        return "\n".join(lines)
    lines.append("| Stage | Outcome | Duración (s) | Notas |")
    lines.append("|-------|---------|--------------|-------|")
    for s in summary.stages:
        duration = (s.finished_at - s.started_at).total_seconds()
        emoji = _OUTCOME_EMOJI.get(s.outcome.value, "·")
        notes = (s.notes or "—").replace("|", "\\|")
        lines.append(
            f"| `{s.stage_id.value}` | {emoji} `{s.outcome.value}` | "
            f"{duration:.2f} | {notes} |"
        )
    return "\n".join(lines)


def _render_artifacts(summary: CampaignRunSummary) -> str:
    lines = [_section_h2("03", "Artefactos producidos")]
    if not summary.stages:
        lines.append("_(sin artefactos)_")
        return "\n".join(lines)

    # Persisted-pack references
    persisted: list[tuple[str, str | None]] = [
        ("intake_id", summary.intake_id),
        ("validation_id", summary.validation_id),
        ("report_id", summary.report_id),
        ("approval_pack_id", summary.approval_pack_id),
        ("creative_pack_id", summary.creative_pack_id),
        ("visual_pack_id", summary.visual_pack_id),
    ]
    lines.append("\n**Pack IDs**:")
    for k, v in persisted:
        lines.append(f"- `{k}`: `{v or '—'}`")

    # File artifacts (markdown + JSON)
    lines.append("\n**Archivos en disco**:")
    any_file = False
    for s in summary.stages:
        for ref in s.artifact_refs:
            any_file = True
            lines.append(f"- `{s.stage_id.value}` → `{ref}`")
    if not any_file:
        lines.append("- _(sin archivos)_")
    return "\n".join(lines)


def _render_next_steps(summary: CampaignRunSummary) -> str:
    lines = [_section_h2("04", "Próximos pasos")]
    state = summary.overall_state.value

    if state == "blocked" or summary.blocks_publish:
        lines.append(
            "- 🛑 Resolver los claims que generan bloqueo en el Approval Pack."
        )
        lines.append("- Volver a correr `mkt run-campaign` con el intake corregido.")
    elif state == "ready_for_publish":
        lines.append("- ✅ Pack aprobado — listo para producción / publicación manual.")
        lines.append("- Confirmar handle/canal por pieza antes de enviar.")
    elif state == "needs_review":
        lines.append(
            "- 🟡 Hay claims pendientes de revisión humana — revisar Approval Pack."
        )
        lines.append("- Cuando esté ok, ejecutar `ApprovalPackBuilder.approve(...)`.")
    else:
        lines.append("- 🟢 Pack en draft — revisar con account lead y cliente.")

    intake_has_critical = summary.intake_critical_count > 0
    if intake_has_critical:
        lines.append("- 🛑 Resolver issues críticos del intake antes de seguir.")
    return "\n".join(lines)


def _render_footer(summary: CampaignRunSummary) -> str:
    return (
        "---\n\n"
        f"_Generated by `core.pipeline` orchestrator v1 (`{summary.contract_version}`). "
        "Deterministic. No external API was called. No image was generated. "
        "No piece was published._"
    )


__all__ = ["render_markdown_summary"]
