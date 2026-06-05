"""Markdown renderer for :class:`AtlasHandoffBrief`."""

from __future__ import annotations

from .models import (
    AtlasHandoffBrief,
    AtlasHandoffKind,
    BrandingBrief,
    HandoffAssetReference,
    LandingBrief,
    PageDesignBrief,
    SEOGEOTargets,
)


def render_markdown_atlas_handoff(handoff: AtlasHandoffBrief) -> str:
    lines: list[str] = []
    lines.append(f"# ATLAS Handoff — `{handoff.client_slug}` ({handoff.kind.value})")
    lines.append("")
    lines.append(f"- **Handoff id:** `{handoff.handoff_id}`")
    if handoff.strategy_report_id:
        lines.append(f"- **Strategy report id:** `{handoff.strategy_report_id}`")
    if handoff.creative_pack_id:
        lines.append(f"- **Creative pack id:** `{handoff.creative_pack_id}`")
    if handoff.visual_pack_id:
        lines.append(f"- **Visual pack id:** `{handoff.visual_pack_id}`")
    if handoff.approval_pack_id:
        lines.append(f"- **Approval pack id:** `{handoff.approval_pack_id}`")
    if handoff.image_job_pack_id:
        lines.append(f"- **Image job pack id:** `{handoff.image_job_pack_id}`")
    lines.append(f"- **Blocks publish:** `{handoff.blocks_publish}`")
    lines.append(f"- **Created:** `{handoff.created_at.isoformat()}`")
    lines.append(f"- **Rule set:** `{handoff.rule_set_id}`")
    lines.append("")
    if handoff.blocks_publish:
        lines.append(
            "> **WARNING — upstream packs flag `blocks_publish=True`.** "
            "Resolve the block in MARKETING-AGENCY-OS before ATLAS ships."
        )
        lines.append("")

    if handoff.kind is AtlasHandoffKind.LANDING and handoff.landing_brief:
        lines.extend(_render_landing(handoff.landing_brief))
    elif handoff.kind is AtlasHandoffKind.BRANDING and handoff.branding_brief:
        lines.extend(_render_branding(handoff.branding_brief))
    elif handoff.kind is AtlasHandoffKind.PAGE_DESIGN and handoff.page_design_brief:
        lines.extend(_render_page_design(handoff.page_design_brief))

    lines.append("---")
    lines.append("")
    lines.append(
        "_Plain handoff artifact. MARKETING-AGENCY-OS does NOT reach "
        "into ATLAS — operator copies/pastes this brief into the "
        "ATLAS workflow manually._"
    )
    lines.append("")
    return "\n".join(lines)


def _render_landing(brief: LandingBrief) -> list[str]:
    lines: list[str] = []
    lines.append(f"## Landing brief `{brief.brief_id}`")
    lines.append("")
    lines.append(f"- **Page objective:** {brief.page_objective}")
    lines.append(f"- **Target audience:** {brief.target_audience}")
    lines.append(f"- **Primary CTA:** `{brief.primary_cta_label}`")
    if brief.secondary_cta_label:
        lines.append(f"- **Secondary CTA:** `{brief.secondary_cta_label}`")
    lines.append("")
    lines.extend(_render_seo(brief.seo_geo))
    lines.append("### Visual style notes")
    lines.append("")
    lines.append(brief.visual_style_notes)
    lines.append("")
    if brief.reference_links:
        lines.append("### Reference links")
        lines.append("")
        for ref in brief.reference_links:
            lines.append(f"- {ref}")
        lines.append("")
    lines.append("### Sections")
    lines.append("")
    for sec in brief.sections:
        lines.append(f"#### `{sec.name}` — {sec.objective}")
        lines.append("")
        lines.append("**Copy:**")
        lines.append("")
        lines.append(f"> {sec.body_copy}")
        lines.append("")
        if sec.visual_notes:
            lines.append(f"- **Visual notes:** {sec.visual_notes}")
        if sec.cta_label:
            lines.append(
                f"- **CTA:** `{sec.cta_label}`"
                + (f" → {sec.cta_target}" if sec.cta_target else "")
            )
        if sec.assets:
            lines.append("- **Assets:**")
            for a in sec.assets:
                lines.append(f"  - {_format_asset(a)}")
        lines.append("")
    lines.extend(_render_constraints_acceptance(
        brief.constraints, brief.acceptance_criteria,
    ))
    return lines


def _render_branding(brief: BrandingBrief) -> list[str]:
    lines: list[str] = []
    lines.append(f"## Branding brief `{brief.brief_id}`")
    lines.append("")
    lines.append(f"- **Brand objective:** {brief.brand_objective}")
    lines.append(f"- **Target audience:** {brief.target_audience}")
    lines.append(f"- **Positioning:** {brief.positioning_statement}")
    if brief.competitor_landscape:
        lines.append(f"- **Competitor landscape:** {brief.competitor_landscape}")
    lines.append("")
    t = brief.tokens
    lines.append("### Tokens")
    lines.append("")
    if t.palette_primary:
        lines.append(f"- **Primary palette:** {', '.join(t.palette_primary)}")
    if t.palette_accent:
        lines.append(f"- **Accent palette:** {', '.join(t.palette_accent)}")
    if t.typography_principles:
        lines.append(
            "- **Typography principles:** "
            + "; ".join(t.typography_principles)
        )
    if t.voice_tone_principles:
        lines.append(
            "- **Voice / tone principles:** "
            + "; ".join(t.voice_tone_principles)
        )
    if t.logo_usage_principles:
        lines.append(
            "- **Logo usage:** " + "; ".join(t.logo_usage_principles)
        )
    if t.do_use:
        lines.append("- **Do use:** " + "; ".join(t.do_use))
    if t.do_not_use:
        lines.append("- **Do NOT use:** " + "; ".join(t.do_not_use))
    lines.append("")
    lines.append("### Deliverables requested")
    lines.append("")
    for d in brief.deliverables_requested:
        lines.append(f"- `{d}`")
    lines.append("")
    if brief.reference_links:
        lines.append("### Reference links")
        lines.append("")
        for ref in brief.reference_links:
            lines.append(f"- {ref}")
        lines.append("")
    lines.extend(_render_constraints_acceptance(
        brief.constraints, brief.acceptance_criteria,
    ))
    return lines


def _render_page_design(brief: PageDesignBrief) -> list[str]:
    lines: list[str] = []
    lines.append(
        f"## Page design brief `{brief.brief_id}` — `{brief.page_name}`"
    )
    lines.append("")
    lines.append(f"- **Page objective:** {brief.page_objective}")
    lines.append(f"- **Target audience:** {brief.target_audience}")
    lines.append("")
    lines.extend(_render_seo(brief.seo_geo))
    lines.append("### Visual style notes")
    lines.append("")
    lines.append(brief.visual_style_notes)
    lines.append("")
    if brief.reference_links:
        lines.append("### Reference links")
        lines.append("")
        for ref in brief.reference_links:
            lines.append(f"- {ref}")
        lines.append("")
    lines.append("### Blocks")
    lines.append("")
    for block in brief.blocks:
        lines.append(f"#### `{block.name}` — {block.intent}")
        lines.append("")
        lines.append(f"> {block.body_copy}")
        lines.append("")
        if block.visual_notes:
            lines.append(f"- **Visual notes:** {block.visual_notes}")
        if block.assets:
            lines.append("- **Assets:**")
            for a in block.assets:
                lines.append(f"  - {_format_asset(a)}")
        lines.append("")
    lines.extend(_render_constraints_acceptance(
        brief.constraints, brief.acceptance_criteria,
    ))
    return lines


def _render_seo(seo: SEOGEOTargets) -> list[str]:
    lines = ["### SEO / GEO targets", ""]
    if seo.primary_keyword:
        lines.append(f"- **Primary keyword:** `{seo.primary_keyword}`")
    if seo.secondary_keywords:
        lines.append(
            f"- **Secondary keywords:** {', '.join(seo.secondary_keywords)}"
        )
    if seo.target_locations:
        lines.append(
            f"- **Target locations:** {', '.join(seo.target_locations)}"
        )
    if seo.title_tag_hint:
        lines.append(f"- **Title tag hint:** `{seo.title_tag_hint}`")
    if seo.meta_description_hint:
        lines.append(
            f"- **Meta description hint:** {seo.meta_description_hint}"
        )
    if seo.schema_org_types:
        lines.append(
            f"- **Schema.org types:** {', '.join(seo.schema_org_types)}"
        )
    if len(lines) == 2:
        lines.append("_(no SEO/GEO hints — operator to add manually)_")
    lines.append("")
    return lines


def _render_constraints_acceptance(
    constraints: list[str], acceptance: list[str],
) -> list[str]:
    lines: list[str] = []
    if constraints:
        lines.append("### Constraints")
        lines.append("")
        for c in constraints:
            lines.append(f"- {c}")
        lines.append("")
    if acceptance:
        lines.append("### Acceptance criteria")
        lines.append("")
        for a in acceptance:
            lines.append(f"- {a}")
        lines.append("")
    return lines


def _format_asset(asset: HandoffAssetReference) -> str:
    bits: list[str] = [f"`{asset.asset_kind}`"]
    if asset.label:
        bits.append(asset.label)
    if asset.asset_id:
        bits.append(f"(id: `{asset.asset_id}`)")
    if asset.filename_hint:
        bits.append(f"file hint: `{asset.filename_hint}`")
    return " — ".join(bits)


__all__ = ["render_markdown_atlas_handoff"]
