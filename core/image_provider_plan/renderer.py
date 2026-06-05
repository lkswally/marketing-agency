"""Markdown renderer for :class:`ImageProviderRecommendationPack`."""

from __future__ import annotations

from .models import (
    ImageProviderRecommendation,
    ImageProviderRecommendationPack,
    ProviderDryRunReceipt,
    ProviderDryRunStatus,
    ProviderEvaluation,
)


def render_markdown_provider_plan(
    pack: ImageProviderRecommendationPack,
) -> str:
    lines: list[str] = []
    lines.append(f"# Image Provider Plan — `{pack.client_slug}`")
    lines.append("")
    lines.append(f"- **Pack id:** `{pack.pack_id}`")
    lines.append(f"- **Job pack id:** `{pack.job_pack_id}`")
    if pack.visual_pack_id:
        lines.append(f"- **Visual pack id:** `{pack.visual_pack_id}`")
    if pack.approval_pack_id:
        lines.append(f"- **Approval pack id:** `{pack.approval_pack_id}`")
    lines.append(f"- **Blocks publish:** `{pack.blocks_publish}`")
    lines.append(f"- **Created:** `{pack.created_at.isoformat()}`")
    lines.append(f"- **Rule set:** `{pack.rule_set_id}`")
    lines.append("")

    lines.append("## Stats")
    lines.append("")
    s = pack.stats
    lines.append(f"- Total jobs analysed: **{s.total_jobs}**")
    if s.by_recommended_provider:
        parts = ", ".join(
            f"{k}={v}" for k, v in sorted(s.by_recommended_provider.items())
        )
        lines.append(f"- By recommended provider: {parts}")
    if s.by_dry_run_status:
        parts = ", ".join(
            f"{k}={v}" for k, v in sorted(s.by_dry_run_status.items())
        )
        lines.append(f"- By dry-run status: {parts}")
    lines.append(
        f"- Overrode job suggestion: **{s.overrode_job_suggestion}**"
    )
    lines.append(f"- Skipped (blocked): **{s.skipped_blocked}**")
    lines.append(f"- Skipped (manual): **{s.skipped_manual}**")
    lines.append(
        f"- Total estimated cost (USD): **${s.total_estimated_cost_usd:.4f}**"
    )
    lines.append("")

    lines.append("## Provider evaluations")
    lines.append("")
    for evaluation in pack.evaluations:
        lines.extend(_render_evaluation(evaluation))

    lines.append("## Per-job recommendations")
    lines.append("")
    if not pack.recommendations:
        lines.append("_(no jobs to recommend on)_")
    else:
        for rec in pack.recommendations:
            lines.extend(_render_recommendation(rec))

    lines.append("## Dry-run receipts")
    lines.append("")
    if not pack.dry_run_receipts:
        lines.append("_(no receipts)_")
    else:
        for receipt in pack.dry_run_receipts:
            lines.extend(_render_receipt(receipt))

    lines.append("---")
    lines.append("")
    lines.append(
        "_Pure analysis + dry-run preview. No HTTP, no SDK, no "
        "credential read, no image generation. The operator decides "
        "when to enable the future real-integration block._"
    )
    lines.append("")
    return "\n".join(lines)


def _render_evaluation(evaluation: ProviderEvaluation) -> list[str]:
    lines = [f"### `{evaluation.provider}`", ""]
    lines.append(
        f"- **Estimated cost per image (USD):** "
        f"`${evaluation.estimated_cost_usd_per_image:.4f}`"
    )
    lines.append(f"- **Commercial use OK:** `{evaluation.commercial_use_ok}`")
    lines.append(
        f"- **Integration difficulty:** `{evaluation.integration_difficulty}`"
    )
    lines.append(
        f"- **External dependency risk:** `{evaluation.external_dependency_risk}`"
    )
    if evaluation.credentials_required:
        lines.append(
            f"- **Credentials required:** `{', '.join(evaluation.credentials_required)}`"
        )
    if evaluation.supported_aspect_ratios:
        lines.append(
            f"- **Aspect ratios:** `{', '.join(evaluation.supported_aspect_ratios)}`"
        )
    if evaluation.supported_formats:
        lines.append(
            f"- **Formats:** `{', '.join(evaluation.supported_formats)}`"
        )
    if evaluation.notes:
        lines.append(f"- **Notes:** {evaluation.notes}")
    if evaluation.scores:
        lines.append("")
        lines.append("| Criterion | Score | Note |")
        lines.append("|---|---:|---|")
        for s in evaluation.scores:
            note = s.note or ""
            lines.append(f"| {s.criterion} | {s.score} | {note} |")
    lines.append("")
    return lines


def _render_recommendation(rec: ImageProviderRecommendation) -> list[str]:
    lines = [
        f"### Job `{rec.job_id}` — `{rec.piece_type}` ({rec.job_state})",
        "",
        f"- **Recommended provider:** `{rec.recommended_provider}` "
        f"(score `{rec.recommended_score}`)",
        f"- **Job hint:** `{rec.job_provider_suggestion}`",
        f"- **Fallback:** `{rec.fallback_provider}`",
        f"- **Estimated cost (USD):** `${rec.estimated_cost_usd:.4f}`",
    ]
    if rec.alternative_providers:
        lines.append(
            f"- **Alternatives:** `{', '.join(rec.alternative_providers)}`"
        )
    lines.append(f"- **Rationale:** {rec.rationale}")
    if rec.risk_notes:
        lines.append("- **Risk notes:**")
        for n in rec.risk_notes:
            lines.append(f"  - {n}")
    lines.append("")
    return lines


def _render_receipt(receipt: ProviderDryRunReceipt) -> list[str]:
    label = {
        ProviderDryRunStatus.DRY_RUN: "DRY-RUN",
        ProviderDryRunStatus.SKIPPED_BLOCKED: "SKIPPED (blocked)",
        ProviderDryRunStatus.SKIPPED_MANUAL: "SKIPPED (manual)",
    }[receipt.status]
    lines = [
        f"### [{label}] Job `{receipt.job_id}` → `{receipt.provider}`",
        "",
        f"- **Model hint:** `{receipt.model_hint}`",
        f"- **Aspect ratio:** `{receipt.aspect_ratio}`",
        f"- **Dimensions:** `{receipt.dimensions_px}`",
        f"- **Prompt length:** `{receipt.prompt_length_chars}` chars",
        f"- **Simulated output filename:** `{receipt.simulated_output_filename}`",
    ]
    if receipt.reason:
        lines.append(f"- **Reason:** {receipt.reason}")
    if receipt.notes:
        lines.append(f"- **Notes:** {receipt.notes}")
    lines.append("")
    return lines


__all__ = ["render_markdown_provider_plan"]
