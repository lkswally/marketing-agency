"""Markdown renderer for :class:`VisualDirectionPack`.

Pure function. Same pack → same Markdown.
"""

from __future__ import annotations

from .models import VisualDirectionPack

_STATE_EMOJI = {
    "draft": "🟢",
    "needs_review": "🟡",
    "ready_for_publish": "✅",
    "blocked": "🛑",
}


def render_markdown_pack(pack: VisualDirectionPack) -> str:
    parts: list[str] = []
    parts.append(_render_header(pack))
    parts.append(_render_summary(pack))
    parts.append(_render_style_guide(pack))
    parts.append(_render_directions(pack))
    parts.append(_render_risks(pack))
    parts.append(_render_checklist(pack))
    parts.append(_render_footer(pack))
    return "\n\n".join(parts) + "\n"


# ---------- helpers ----------

def _section_h2(num: str, title: str) -> str:
    return f"## {num}. {title}"


def _bullets(items: list[str]) -> str:
    if not items:
        return "_(vacío)_"
    return "\n".join(f"- {i}" for i in items)


def _state_badge(state) -> str:
    v = state.value
    return f"{_STATE_EMOJI.get(v, '·')} `{v}`"


def _render_header(pack: VisualDirectionPack) -> str:
    return (
        f"# Visual Direction Pack — {pack.client_slug}\n\n"
        f"- **Pack ID**: `{pack.pack_id}`\n"
        f"- **Contract**: `{pack.contract_version}`\n"
        f"- **Strategy report**: `{pack.report_id}` (`{pack.report_contract_version}`)\n"
        f"- **Approval pack**: "
        + (f"`{pack.approval_pack_id}` (`{pack.approval_pack_contract_version}`)" if pack.approval_pack_id else "_(ninguno)_")
        + "\n"
        "- **Creative pack**: "
        + (f"`{pack.creative_pack_id}` (`{pack.creative_pack_contract_version}`)" if pack.creative_pack_id else "_(ninguno)_")
        + "\n"
        f"- **Rule set**: `{pack.rule_set_id or '—'}`\n"
        f"- **Generado**: `{pack.created_at.isoformat()}`\n"
    )


def _render_summary(pack: VisualDirectionPack) -> str:
    lines = [_section_h2("01", "Resumen")]
    block_emoji = "🛑" if pack.blocks_publish else "✅"
    lines.append(
        f"- **Estado derivado**: {_state_badge(pack.derived_overall_state)}"
    )
    lines.append(
        f"- **Bloquea publicación**: {block_emoji} `{pack.blocks_publish}`"
    )
    lines.append(f"- **Direcciones por piece type**: {pack.total_directions}")
    lines.append(f"- **Total prompt variants**: {pack.total_prompt_variants}")

    state_counts = pack.count_by_state()
    if any(v for v in state_counts.values()):
        lines.append("\n**Conteo por estado**:")
        for state, count in state_counts.items():
            if count:
                lines.append(f"- {_STATE_EMOJI.get(state, '·')} `{state}`: {count}")

    risk_counts = pack.count_risks_by_severity()
    if any(v for v in risk_counts.values()):
        lines.append("\n**Riesgos visuales globales por severidad**:")
        for sev, count in risk_counts.items():
            if count:
                lines.append(f"- `{sev}`: {count}")
    return "\n".join(lines)


def _render_style_guide(pack: VisualDirectionPack) -> str:
    g = pack.style_guide
    lines = [_section_h2("02", "Style Guide de campaña")]
    lines.append(f"**Mood general**: {g.overall_mood}")
    lines.append("\n**Paleta primaria**: " + ", ".join(f"`{c}`" for c in g.palette_primary))
    if g.palette_accent:
        lines.append("**Paleta de acento**: " + ", ".join(f"`{c}`" for c in g.palette_accent))
    lines.append(f"\n**Tipografía headline**: {g.typography_headline}")
    lines.append(f"**Tipografía body**: {g.typography_body}")
    if g.typography_principles:
        lines.append("\n**Principios tipográficos**:")
        lines.append(_bullets(g.typography_principles))
    if g.visual_motifs:
        lines.append("\n**Motivos visuales**:")
        lines.append(_bullets(g.visual_motifs))
    if g.composition_principles:
        lines.append("\n**Principios de composición**:")
        lines.append(_bullets(g.composition_principles))
    if g.do_use:
        lines.append("\n**Usar**:")
        lines.append(_bullets(g.do_use))
    if g.do_not_use:
        lines.append("\n**No usar**:")
        lines.append(_bullets(g.do_not_use))
    return "\n".join(lines)


def _render_directions(pack: VisualDirectionPack) -> str:
    lines = [_section_h2("03", "Direcciones por pieza")]
    if not pack.directions:
        lines.append("_(sin direcciones)_")
        return "\n".join(lines)
    for d in pack.directions:
        spec = d.spec
        channel_label = d.channel.value if d.channel else "—"
        lines.append(
            f"\n### {d.piece_type.value} — {_state_badge(d.state)} "
            f"_(canal: {channel_label}, ratio: `{spec.aspect_ratio}`, {spec.dimensions_px})_"
        )
        if d.scheduled_for:
            lines.append(f"- **Programado**: `{d.scheduled_for.isoformat()}`")
        if d.source_creative_asset_id:
            lines.append(f"- **Source asset**: `{d.source_creative_asset_id}`")
        if d.source_creative_image_prompt_id:
            lines.append(
                f"- **Source image prompt (MKT-3C)**: `{d.source_creative_image_prompt_id}`"
            )

        # Spec block.
        lines.append("\n**Spec del piece type**:")
        if spec.safe_zones:
            lines.append("- Safe zones:")
            for k, v in spec.safe_zones.items():
                lines.append(f"    - {k}: {v}")
        if spec.text_guidelines:
            lines.append("- Text guidelines:")
            for k, v in spec.text_guidelines.items():
                lines.append(f"    - {k}: {v}")
        if spec.file_format_hints:
            lines.append("- File formats: " + ", ".join(f"`{x}`" for x in spec.file_format_hints))
        if spec.delivery_notes:
            lines.append("- Delivery notes:")
            lines.append(_bullets(spec.delivery_notes))
        lines.append(f"- **Negative prompt típico**: _{spec.typical_negative_prompt}_")

        # Variants.
        for v in d.prompt_variants:
            lines.append(
                f"\n#### Variant {v.variant_id} _(intended use: `{v.intended_use}`)_"
            )
            lines.append(f"- **Objective**: {v.objective}")
            lines.append(f"- **Audience**: {v.target_audience}")
            lines.append(f"- **Visual style**: {v.visual_style}")
            lines.append(f"- **Emotional tone**: {v.emotional_tone}")
            lines.append(f"- **Composition**: {v.composition}")
            if v.in_image_text:
                lines.append("- **Texto en imagen**:")
                lines.append(_bullets(v.in_image_text))
            if v.visual_elements:
                lines.append("- **Elementos visuales**:")
                lines.append(_bullets(v.visual_elements))
            if v.suggested_colors:
                lines.append("- **Colores sugeridos**: " + ", ".join(f"`{c}`" for c in v.suggested_colors))
            lines.append(f"- **Aspect ratio**: `{v.aspect_ratio}`")
            if v.restrictions:
                lines.append("- **Restricciones**:")
                lines.append(_bullets(v.restrictions))
            lines.append(f"\n**Prompt completo**:\n\n> {v.full_prompt_text}")
            lines.append(f"\n**Negative prompt**:\n\n> {v.negative_prompt}")

        # Per-direction checklist.
        lines.append("\n**Checklist del piece type**:")
        lines.append(_render_checklist_items(d.checklist))
    return "\n".join(lines)


def _render_risks(pack: VisualDirectionPack) -> str:
    lines = [_section_h2("04", "Riesgos visuales globales")]
    if not pack.global_visual_risks:
        lines.append("_(sin riesgos registrados)_")
        return "\n".join(lines)
    lines.append("| Severidad | Categoría | Descripción | Mitigación |")
    lines.append("|-----------|-----------|-------------|------------|")
    for r in pack.global_visual_risks:
        desc = r.description.replace("|", "\\|")
        mit = (r.mitigation or "—").replace("|", "\\|")
        lines.append(
            f"| `{r.severity}` | `{r.category}` | {desc} | {mit} |"
        )
    return "\n".join(lines)


def _render_checklist(pack: VisualDirectionPack) -> str:
    lines = [_section_h2("05", "Checklist global")]
    if not pack.global_checklist:
        lines.append("_(sin items)_")
        return "\n".join(lines)
    lines.append(_render_checklist_items(pack.global_checklist))
    return "\n".join(lines)


def _render_checklist_items(items) -> str:
    if not items:
        return "_(sin items)_"
    out: list[str] = []
    for it in items:
        marker = {"blocker": "🛑", "must": "✅", "should": "🟡"}.get(it.severity, "•")
        out.append(
            f"- [ ] {marker} **[{it.severity}]** _{it.category}_ — {it.title}"
        )
        if it.notes:
            out.append(f"    - {it.notes}")
    return "\n".join(out)


def _render_footer(pack: VisualDirectionPack) -> str:
    return (
        "---\n\n"
        f"_Generated by `core.visual` engine v1 (`{pack.contract_version}`). "
        "Deterministic, LLM-free, image-API-free. Prompts are text — "
        "no PNG/JPG is produced. Terminal positive state is `ready_for_publish`._"
    )


__all__ = ["render_markdown_pack"]
