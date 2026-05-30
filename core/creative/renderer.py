"""Markdown renderer for :class:`CreativeAssetPack`.

Pure function. Same pack → same markdown.
"""

from __future__ import annotations

from .models import CreativeAssetPack, CreativeAssetState

_STATE_EMOJI = {
    "draft": "🟢",
    "needs_review": "🟡",
    "ready_for_publish": "✅",
    "blocked": "🛑",
}

_STATE_LABEL = {
    "draft": "Draft",
    "needs_review": "Needs review",
    "ready_for_publish": "Ready for publish",
    "blocked": "Blocked",
}


def render_markdown_pack(pack: CreativeAssetPack) -> str:
    parts: list[str] = []
    parts.append(_render_header(pack))
    parts.append(_render_summary(pack))
    parts.append(_render_calendar(pack))
    parts.append(_render_social_posts(pack))
    parts.append(_render_emails(pack))
    parts.append(_render_reels(pack))
    parts.append(_render_flyers(pack))
    parts.append(_render_image_prompts(pack))
    parts.append(_render_footer(pack))
    return "\n\n".join(parts) + "\n"


# ---------- helpers ----------

def _section_h2(num: str, title: str) -> str:
    return f"## {num}. {title}"


def _bullets(items: list[str]) -> str:
    if not items:
        return "_(vacío)_"
    return "\n".join(f"- {i}" for i in items)


def _state_badge(state: CreativeAssetState) -> str:
    v = state.value
    return f"{_STATE_EMOJI.get(v, '·')} `{v}`"


# ---------- sections ----------

def _render_header(pack: CreativeAssetPack) -> str:
    return (
        f"# Creative Asset Pack — {pack.client_slug}\n\n"
        f"- **Pack ID**: `{pack.pack_id}`\n"
        f"- **Pack contract**: `{pack.contract_version}`\n"
        f"- **Strategy report**: `{pack.report_id}` (`{pack.report_contract_version}`)\n"
        f"- **Approval pack**: "
        + (f"`{pack.approval_pack_id}` (`{pack.approval_pack_contract_version}`)" if pack.approval_pack_id else "_(ninguno)_")
        + "\n"
        f"- **Template set**: `{pack.rule_set_id or '—'}`\n"
        f"- **Generado**: `{pack.created_at.isoformat()}`\n"
    )


def _render_summary(pack: CreativeAssetPack) -> str:
    lines = [_section_h2("01", "Resumen")]
    block_emoji = "🛑" if pack.blocks_publish else "✅"
    lines.append(
        f"- **Estado derivado**: {_state_badge(pack.derived_overall_state)}"
    )
    lines.append(
        f"- **Bloquea publicación**: {block_emoji} `{pack.blocks_publish}`"
    )
    lines.append(f"- **Total assets**: {pack.total_assets}")

    state_counts = pack.count_by_state()
    if any(v for v in state_counts.values()):
        lines.append("\n**Conteo por estado**:")
        for state, count in state_counts.items():
            if count:
                lines.append(f"- {_STATE_EMOJI.get(state, '·')} `{state}`: {count}")

    kind_counts = pack.count_by_kind()
    lines.append("\n**Conteo por tipo**:")
    for kind, count in kind_counts.items():
        if count:
            lines.append(f"- `{kind}`: {count}")
    return "\n".join(lines)


def _render_calendar(pack: CreativeAssetPack) -> str:
    lines = [_section_h2("02", "Calendario sugerido")]
    if not pack.calendar:
        lines.append("_(sin entradas)_")
        return "\n".join(lines)
    lines.append("| Fecha | Semana | Tipo | Canal | Nota |")
    lines.append("|-------|--------|------|-------|------|")
    for e in pack.calendar:
        ch = e.channel.value if e.channel else "—"
        note = (e.cadence_note or "").replace("|", "\\|")
        lines.append(
            f"| {e.scheduled_for.isoformat()} | {e.week} | `{e.asset_kind.value}` | {ch} | {note} |"
        )
    return "\n".join(lines)


def _render_social_posts(pack: CreativeAssetPack) -> str:
    lines = [_section_h2("03", "Social posts")]
    if not pack.social_posts:
        lines.append("_(sin posts)_")
        return "\n".join(lines)
    for p in pack.social_posts:
        lines.append(
            f"\n### `{p.channel.value}` — {_state_badge(p.state)}"
        )
        if p.scheduled_for:
            lines.append(f"- **Programado**: `{p.scheduled_for.isoformat()}`")
        lines.append("\n**Hook variants**:")
        for h in p.hook_variants:
            lines.append(f"- **{h.variant_id}** _(`{h.angle.value}`)_ — {h.text}")
        lines.append("\n**CTA variants**:")
        for c in p.cta_variants:
            lines.append(f"- **{c.variant_id}** _(`{c.style.value}`)_ — {c.text}")
        lines.append(f"\n**Body**:\n\n{p.body}")
        if p.caption_cross_post:
            lines.append(f"\n**Caption cross-post**: {p.caption_cross_post}")
        if p.hashtags:
            lines.append(f"\n**Hashtags**: {' '.join(p.hashtags)}")
        lines.append("\n**Checklist**:")
        lines.append(_render_checklist(p.checklist))
    return "\n".join(lines)


def _render_emails(pack: CreativeAssetPack) -> str:
    lines = [_section_h2("04", "Emails")]
    if not pack.emails:
        lines.append("_(sin emails)_")
        return "\n".join(lines)
    for e in pack.emails:
        lines.append(
            f"\n### Email #{e.step} — {_state_badge(e.state)}"
        )
        if e.scheduled_for:
            lines.append(
                f"- **Programado**: `{e.scheduled_for.isoformat()}` (`+{e.send_after_days}d`)"
            )
        lines.append("\n**Subject variants**:")
        for s in e.subject_line_variants:
            lines.append(
                f"- **{s.variant_id}** _(`{s.style.value}`)_ — `{s.subject}` · _preview_: {s.preview_text}"
            )
        lines.append(f"\n**Body**:\n\n{e.body}")
        lines.append(f"\n**CTA**: {e.cta}")
        lines.append("\n**Checklist**:")
        lines.append(_render_checklist(e.checklist))
    return "\n".join(lines)


def _render_reels(pack: CreativeAssetPack) -> str:
    lines = [_section_h2("05", "Reels")]
    if not pack.reels:
        lines.append("_(sin reels)_")
        return "\n".join(lines)
    for r in pack.reels:
        lines.append(
            f"\n### {r.title} — {_state_badge(r.state)} _(target {r.target_duration_s}s)_"
        )
        lines.append("\n**Hook variants**:")
        for h in r.hook_variants:
            lines.append(f"- **{h.variant_id}** _(`{h.angle.value}`)_ — {h.text}")
        lines.append("\n**Beats**:")
        lines.append(_bullets(r.beats))
        if r.voiceover_lines:
            lines.append("\n**Voiceover**:")
            lines.append(_bullets(r.voiceover_lines))
        if r.on_screen_text:
            lines.append("\n**Texto en pantalla**:")
            lines.append(_bullets(r.on_screen_text))
        lines.append(f"\n**CTA**: {r.cta}")
        lines.append("\n**Checklist**:")
        lines.append(_render_checklist(r.checklist))
    return "\n".join(lines)


def _render_flyers(pack: CreativeAssetPack) -> str:
    lines = [_section_h2("06", "Flyers copy")]
    if not pack.flyers:
        lines.append("_(sin flyers)_")
        return "\n".join(lines)
    for f in pack.flyers:
        lines.append(
            f"\n### Flyer {f.format.value} — {_state_badge(f.state)}"
        )
        lines.append("\n**Headline variants**:")
        for h in f.headline_variants:
            lines.append(f"- **{h.variant_id}** _(`{h.style.value}`)_ — {h.text}")
        lines.append(f"\n**Subhead**: {f.subhead}")
        lines.append(f"\n**Body**:\n\n{f.body}")
        lines.append(f"\n**CTA**: {f.cta}")
        lines.append("\n**Checklist**:")
        lines.append(_render_checklist(f.checklist))
    return "\n".join(lines)


def _render_image_prompts(pack: CreativeAssetPack) -> str:
    lines = [_section_h2("07", "Prompts para imágenes")]
    if not pack.image_prompts:
        lines.append("_(sin prompts)_")
        return "\n".join(lines)
    for p in pack.image_prompts:
        lines.append(
            f"\n### {p.title} — {_state_badge(p.state)} _(`{p.aspect_ratio}`, `{p.intended_use}`)_"
        )
        if p.style_notes:
            lines.append(f"- **Notas de estilo**: {p.style_notes}")
        if p.palette_hint:
            lines.append("- **Paleta**: " + ", ".join(f"`{c}`" for c in p.palette_hint))
        if p.accessibility_notes:
            lines.append("- **Accesibilidad**:")
            lines.append(_bullets(p.accessibility_notes))
        lines.append(f"\n**Prompt**:\n\n> {p.prompt_text}")
        if p.negative_prompt:
            lines.append(f"\n**Negative prompt**:\n\n> {p.negative_prompt}")
        lines.append("\n**Checklist**:")
        lines.append(_render_checklist(p.checklist))
    return "\n".join(lines)


def _render_checklist(items) -> str:
    if not items:
        return "_(sin items)_"
    out: list[str] = []
    for it in items:
        marker = {"blocker": "🛑", "must": "✅", "should": "🟡"}.get(it.severity, "•")
        line = f"- [ ] {marker} **[{it.severity}]** {it.title}"
        out.append(line)
        if it.notes:
            out.append(f"    - {it.notes}")
    return "\n".join(out)


def _render_footer(pack: CreativeAssetPack) -> str:
    return (
        "---\n\n"
        f"_Generated by `core.creative` engine v1 (`{pack.contract_version}`). "
        "Deterministic, LLM-free. Image generation NOT performed; prompts only. "
        "No piece is published — terminal positive state is `ready_for_publish`._"
    )


__all__ = ["render_markdown_pack"]
