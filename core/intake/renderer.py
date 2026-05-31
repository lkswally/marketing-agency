"""Markdown renderer for the intake summary.

Pure function. Same (intake, validation) → same Markdown.
"""

from __future__ import annotations

from .models import ClientIntake, IntakeValidationResult

_SEVERITY_EMOJI = {
    "info": "🔵",
    "warning": "🟡",
    "critical": "🛑",
}


def render_intake_summary(
    intake: ClientIntake, validation: IntakeValidationResult
) -> str:
    parts: list[str] = []
    parts.append(_render_header(intake, validation))
    parts.append(_render_status(validation))
    parts.append(_render_warnings(validation))
    parts.append(_render_intake_recap(intake))
    parts.append(_render_defaults(validation))
    parts.append(_render_footer(validation))
    return "\n\n".join(parts) + "\n"


# ---------- helpers ----------

def _section_h2(num: str, title: str) -> str:
    return f"## {num}. {title}"


def _bullets(items: list[str]) -> str:
    if not items:
        return "_(vacío)_"
    return "\n".join(f"- {it}" for it in items)


# ---------- sections ----------

def _render_header(intake: ClientIntake, validation: IntakeValidationResult) -> str:
    return (
        f"# Client Brief Intake — {intake.client_name}\n\n"
        f"- **Client slug**: `{validation.client_slug}`\n"
        f"- **Intake ID**: `{validation.intake_id}`\n"
        f"- **Intake contract**: `{intake.schema_version}`\n"
        f"- **Validation contract**: `{validation.contract_version}`\n"
        f"- **Generado**: `{validation.created_at.isoformat()}`\n"
    )


def _render_status(validation: IntakeValidationResult) -> str:
    badge = "✅" if validation.is_valid else "🛑"
    normalize_badge = "✅" if validation.can_normalize else "🛑"
    counts = validation.count_by_severity()
    lines = [_section_h2("01", "Estado del intake")]
    lines.append(f"- **Valid**: {badge} `{validation.is_valid}`")
    lines.append(f"- **Can normalize → brief**: {normalize_badge} `{validation.can_normalize}`")
    lines.append("\n**Conteo por severidad**:")
    for sev in ("critical", "warning", "info"):
        c = counts.get(sev, 0)
        lines.append(f"- {_SEVERITY_EMOJI[sev]} `{sev}`: {c}")
    return "\n".join(lines)


def _render_warnings(validation: IntakeValidationResult) -> str:
    lines = [_section_h2("02", "Warnings / datos faltantes")]
    if not validation.warnings:
        lines.append("_(sin warnings)_")
        return "\n".join(lines)
    lines.append("| Severidad | Campo | Mensaje | Acción sugerida |")
    lines.append("|-----------|-------|---------|------------------|")
    for w in validation.warnings:
        action = (w.suggested_action or "—").replace("|", "\\|")
        msg = w.message.replace("|", "\\|")
        lines.append(
            f"| {_SEVERITY_EMOJI[w.severity]} `{w.severity}` | `{w.field_path}` | "
            f"{msg} | {action} |"
        )
    return "\n".join(lines)


def _render_intake_recap(intake: ClientIntake) -> str:
    lines = [_section_h2("03", "Resumen del intake recibido")]
    lines.append(f"- **Nombre**: {intake.client_name}")
    if intake.industry:
        lines.append(f"- **Industria**: {intake.industry}")
    if intake.market:
        lines.append(f"- **Mercado**: {intake.market}")
    if intake.product_or_service:
        lines.append(f"- **Producto/Servicio**: {intake.product_or_service}")
    if intake.product_type:
        lines.append(f"- **Tipo de oferta**: `{intake.product_type}`")
    if intake.commercial_objective:
        lines.append(f"- **Objetivo comercial**: {intake.commercial_objective}")
    if intake.audience_description:
        lines.append(f"- **Audiencia**: {intake.audience_description}")
    if intake.budget_estimate is not None:
        lines.append(
            f"- **Budget estimado**: {intake.budget_estimate} {intake.budget_currency or ''}"
        )
    if intake.deadline:
        lines.append(f"- **Deadline**: `{intake.deadline.isoformat()}`")

    lines.append("\n**Tono de marca**:")
    lines.append(_bullets(intake.brand_tone))
    lines.append("\n**Palabras preferidas**:")
    lines.append(_bullets(intake.preferred_words))
    lines.append("\n**Palabras prohibidas**:")
    lines.append(_bullets(intake.forbidden_words))

    lines.append("\n**Canales posibles**:")
    lines.append(_bullets(intake.possible_channels))

    lines.append("\n**Competidores conocidos**:")
    if not intake.known_competitors:
        lines.append("_(ninguno listado)_")
    else:
        for c in intake.known_competitors:
            line = f"- **{c.name}**"
            if c.url:
                line += f" — {c.url}"
            if c.notes:
                line += f" — {c.notes}"
            lines.append(line)

    if intake.constraints:
        lines.append("\n**Restricciones declaradas**:")
        lines.append(_bullets(intake.constraints))
    if intake.claims_to_avoid:
        lines.append("\n**Claims a evitar**:")
        lines.append(_bullets(intake.claims_to_avoid))
    if intake.good_examples:
        lines.append("\n**Ejemplos buenos**:")
        lines.append(_bullets(intake.good_examples))
    if intake.bad_examples:
        lines.append("\n**Ejemplos malos**:")
        lines.append(_bullets(intake.bad_examples))
    if intake.additional_context:
        lines.append(f"\n**Contexto adicional**:\n\n> {intake.additional_context}")
    return "\n".join(lines)


def _render_defaults(validation: IntakeValidationResult) -> str:
    lines = [_section_h2("04", "Defaults operacionales aplicados")]
    if not validation.operational_defaults_applied:
        lines.append("_(ninguno — el intake provee todos los campos operacionales)_")
        return "\n".join(lines)
    lines.append(
        "Los siguientes defaults se aplican porque el intake no los provee. "
        "Están declarados en el código como operacionales — no son inventados."
    )
    lines.append("\n| Campo | Default aplicado |")
    lines.append("|-------|------------------|")
    for k, v in validation.operational_defaults_applied.items():
        lines.append(f"| `{k}` | `{v}` |")
    return "\n".join(lines)


def _render_footer(validation: IntakeValidationResult) -> str:
    return (
        "---\n\n"
        f"_Generated by `core.intake` engine v1 (`{validation.contract_version}`). "
        "Deterministic, no data fabrication. Missing values are reported as warnings."
        + (
            "\n\n_Brief listo para ejecutar:_ `mkt run-strategy --brief outputs/<slug>/brief.json --audit`"
            if validation.can_normalize
            else "\n\n_Brief NO se puede generar todavía — resolver issues críticos primero._"
        )
    )


__all__ = ["render_intake_summary"]
