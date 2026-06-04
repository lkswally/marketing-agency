"""Markdown renderer for :class:`AdsFeedbackBridgePack`."""

from __future__ import annotations

from .models import (
    AdsFeedbackBridgePack,
    AdsRecommendation,
    AdsRecommendationPriority,
)

_PRIO_LABEL = {
    AdsRecommendationPriority.HIGH: "HIGH",
    AdsRecommendationPriority.MEDIUM: "MEDIUM",
    AdsRecommendationPriority.LOW: "LOW",
}


def render_markdown_ads_bridge(pack: AdsFeedbackBridgePack) -> str:
    lines: list[str] = []
    lines.append(f"# Ads Insights → Feedback Bridge — `{pack.client_slug}`")
    lines.append("")
    lines.append(f"- **Pack id:** `{pack.pack_id}`")
    lines.append(f"- **Insight pack id:** `{pack.insight_pack_id}`")
    if pack.snapshot_id:
        lines.append(f"- **Snapshot id:** `{pack.snapshot_id}`")
    if pack.feedback_pack_id:
        lines.append(f"- **Feedback pack id:** `{pack.feedback_pack_id}`")
    if pack.execution_task_pack_id:
        lines.append(
            f"- **Execution task pack id:** `{pack.execution_task_pack_id}`"
        )
    if pack.iteration_plan_id:
        lines.append(f"- **Iteration plan id:** `{pack.iteration_plan_id}`")
    lines.append(f"- **Created:** `{pack.created_at.isoformat()}`")
    lines.append(f"- **Rule set:** `{pack.rule_set_id}`")
    lines.append("")

    if pack.executive_summary:
        lines.append("## Executive summary")
        lines.append("")
        lines.append(pack.executive_summary)
        lines.append("")

    lines.append("## Stats")
    lines.append("")
    s = pack.stats
    lines.append(f"- Insights consumed: **{s.insights_consumed}**")
    lines.append(f"- Recommendations: **{s.total_recommendations}**")
    lines.append(f"- Campaign adjustments: **{s.total_campaign_adjustments}**")
    lines.append(f"- Keyword proposals: **{s.total_keyword_proposals}**")
    lines.append(f"- Suggested tasks: **{s.total_suggested_tasks}**")
    if s.by_recommendation_priority:
        parts = ", ".join(
            f"{k}={v}" for k, v in sorted(s.by_recommendation_priority.items())
        )
        lines.append(f"- By priority: {parts}")
    lines.append("")

    lines.append("## Recommendations")
    lines.append("")
    if not pack.recommendations:
        lines.append("_(no recommendations — empty insight pack)_")
    else:
        for r in pack.recommendations:
            lines.extend(_render_recommendation(r))
    lines.append("")

    lines.append("## Campaign adjustments")
    lines.append("")
    if not pack.campaign_adjustments:
        lines.append("_(no campaign-level adjustments)_")
    else:
        for adj in pack.campaign_adjustments:
            lines.append(
                f"- **[{adj.kind.value}]** "
                f"{adj.dimension or f'campaign:{adj.campaign_id}'} — "
                f"{adj.rationale} _(next step: {adj.suggested_next_step})_"
            )
    lines.append("")

    lines.append("## Negative keyword proposals")
    lines.append("")
    if not pack.keyword_proposals:
        lines.append(
            "_(none — search-term data not yet in snapshot; see P-6E.1)_"
        )
    else:
        for kp in pack.keyword_proposals:
            lines.append(
                f"- `{kp.keyword}` — {kp.rationale} _(proposed only; "
                "operator applies manually)_"
            )
    lines.append("")

    lines.append("## Suggested tasks")
    lines.append("")
    if not pack.suggested_tasks:
        lines.append("_(no tasks)_")
    else:
        for t in pack.suggested_tasks:
            lines.append(
                f"- **[{_PRIO_LABEL[t.priority]}]** ({t.category}) "
                f"{t.title}"
            )
    lines.append("")

    lines.append("---")
    lines.append("")
    lines.append(
        "_Read-only bridge. No campaign / keyword / budget mutation. "
        "Suggestions only; the operator applies them manually in the Ads "
        "UI after review._"
    )
    lines.append("")
    return "\n".join(lines)


def _render_recommendation(r: AdsRecommendation) -> list[str]:
    lines: list[str] = []
    lines.append(f"### [{_PRIO_LABEL[r.priority]}] {r.title}")
    lines.append("")
    lines.append(f"- **Kind:** `{r.kind.value}`")
    if r.dimension:
        lines.append(f"- **Where:** {r.dimension}")
    if r.content_ref:
        lines.append(f"- **Content ref:** `{r.content_ref}`")
    lines.append(f"- **Why:** {r.rationale}")
    lines.append(f"- **Suggested action:** {r.suggested_action}")
    if r.evidence_refs:
        lines.append(f"- **Evidence refs:** {', '.join(r.evidence_refs)}")
    lines.append("")
    return lines


__all__ = ["render_markdown_ads_bridge"]
