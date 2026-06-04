"""Markdown renderer for :class:`ImageGenerationJobPack`."""

from __future__ import annotations

from .models import (
    ImageGenerationJob,
    ImageGenerationJobPack,
    ImageJobState,
)

_STATE_LABEL = {
    ImageJobState.DRAFT: "DRAFT",
    ImageJobState.NEEDS_REVIEW: "NEEDS REVIEW",
    ImageJobState.BLOCKED: "BLOCKED",
    ImageJobState.READY_FOR_GENERATION: "READY",
    ImageJobState.GENERATED: "GENERATED",
}

_SEVERITY_PREFIX = {
    "blocker": "[BLOCKER]",
    "warning": "[WARN]",
    "info": "[INFO]",
}


def render_markdown_image_jobs(pack: ImageGenerationJobPack) -> str:
    lines: list[str] = []
    lines.append(f"# Image Generation Jobs — `{pack.client_slug}`")
    lines.append("")
    lines.append(f"- **Pack id:** `{pack.pack_id}`")
    lines.append(f"- **Visual pack id:** `{pack.visual_pack_id}`")
    if pack.creative_pack_id:
        lines.append(f"- **Creative pack id:** `{pack.creative_pack_id}`")
    if pack.approval_pack_id:
        lines.append(f"- **Approval pack id:** `{pack.approval_pack_id}`")
    if pack.run_summary_id:
        lines.append(f"- **Run summary id:** `{pack.run_summary_id}`")
    lines.append(f"- **Blocks publish:** `{pack.blocks_publish}`")
    lines.append(f"- **Created:** `{pack.created_at.isoformat()}`")
    lines.append(f"- **Rule set:** `{pack.rule_set_id}`")
    lines.append("")

    lines.append("## Stats")
    lines.append("")
    s = pack.stats
    lines.append(f"- Directions consumed: **{s.directions_consumed}**")
    lines.append(f"- Total jobs: **{s.total_jobs}**")
    if s.by_state:
        parts = ", ".join(f"{k}={v}" for k, v in sorted(s.by_state.items()))
        lines.append(f"- By state: {parts}")
    if s.by_provider_suggestion:
        parts = ", ".join(
            f"{k}={v}" for k, v in sorted(s.by_provider_suggestion.items())
        )
        lines.append(f"- By provider suggestion: {parts}")
    if s.by_piece_type:
        parts = ", ".join(
            f"{k}={v}" for k, v in sorted(s.by_piece_type.items())
        )
        lines.append(f"- By piece type: {parts}")
    lines.append(
        f"- Blocked by approval: **{s.blocked_due_to_approval}** | "
        f"by direction: **{s.blocked_due_to_direction}**"
    )
    lines.append("")

    if pack.review_checklist:
        lines.append("## Pack-level review checklist")
        lines.append("")
        for item in pack.review_checklist:
            prefix = _SEVERITY_PREFIX.get(item.severity, "[INFO]")
            lines.append(f"- {prefix} {item.title}")
        lines.append("")

    lines.append("## Jobs")
    lines.append("")
    if not pack.jobs:
        lines.append("_(no jobs — visual pack had no directions)_")
    else:
        for job in pack.jobs:
            lines.extend(_render_job(job))

    lines.append("---")
    lines.append("")
    lines.append(
        "_Jobs are NOT generated images. No provider was called. "
        "Operator reviews prompts + checklist; a future block will "
        "integrate a real provider._"
    )
    lines.append("")
    return "\n".join(lines)


def _render_job(job: ImageGenerationJob) -> list[str]:
    lines: list[str] = []
    state_label = _STATE_LABEL[job.state]
    lines.append(
        f"### [{state_label}] {job.piece_type} / variant `{job.variant_id}`"
    )
    lines.append("")
    lines.append(f"- **Job id:** `{job.job_id}`")
    lines.append(f"- **Direction id:** `{job.direction_id}`")
    if job.channel:
        lines.append(f"- **Channel:** `{job.channel}`")
    if job.creative_ref:
        lines.append(f"- **Creative ref:** `{job.creative_ref}`")
    if job.image_prompt_ref:
        lines.append(f"- **Image prompt ref:** `{job.image_prompt_ref}`")
    lines.append(f"- **Aspect ratio:** `{job.aspect_ratio}`")
    lines.append(f"- **Dimensions:** `{job.dimensions_px}`")
    lines.append(f"- **Provider suggestion:** `{job.provider_suggestion.value}`")
    if job.provider_rationale:
        lines.append(f"- **Provider rationale:** {job.provider_rationale}")
    lines.append(
        f"- **Output filename suggestion:** `{job.output_filename_suggestion}`"
    )
    if job.in_image_text:
        lines.append(f"- **In-image text:** {job.in_image_text}")
    if job.intended_use:
        lines.append(f"- **Intended use:** {job.intended_use}")
    if job.blocked_reason:
        lines.append(f"- **Blocked reason:** {job.blocked_reason}")
    lines.append("")
    lines.append("**Prompt:**")
    lines.append("")
    lines.append(f"> {job.prompt}")
    lines.append("")
    lines.append("**Negative prompt:**")
    lines.append("")
    lines.append(f"> {job.negative_prompt}")
    lines.append("")
    if job.review_checklist:
        lines.append("**Review checklist:**")
        lines.append("")
        for item in job.review_checklist:
            prefix = _SEVERITY_PREFIX.get(item.severity, "[INFO]")
            lines.append(f"- {prefix} {item.title}")
        lines.append("")
    return lines


__all__ = ["render_markdown_image_jobs"]
