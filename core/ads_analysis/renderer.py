"""Markdown renderer for :class:`GoogleAdsInsightPack`."""

from __future__ import annotations

from .models import (
    AdsInsightSeverity,
    GoogleAdsInsight,
    GoogleAdsInsightPack,
)

_SEVERITY_LABEL = {
    AdsInsightSeverity.HIGH: "HIGH",
    AdsInsightSeverity.MEDIUM: "MEDIUM",
    AdsInsightSeverity.LOW: "LOW",
}


def render_markdown_ads_insights(pack: GoogleAdsInsightPack) -> str:
    """Render a :class:`GoogleAdsInsightPack` to Markdown."""

    lines: list[str] = []
    lines.append(f"# Google Ads Insight Pack — `{pack.client_slug}`")
    lines.append("")
    lines.append(f"- **Pack id:** `{pack.pack_id}`")
    lines.append(f"- **Snapshot id:** `{pack.snapshot_id}`")
    lines.append(f"- **Created:** `{pack.created_at.isoformat()}`")
    lines.append(f"- **Rule set:** `{pack.rule_set_id}`")
    lines.append("")
    lines.append("## Stats")
    lines.append("")
    s = pack.stats
    lines.append(f"- Total insights: **{s.total_insights}**")
    lines.append(f"- Ad groups profiled: **{s.ad_groups_profiled}**")
    lines.append(f"- Rows analyzed: **{s.rows_analyzed}**")
    if s.by_severity:
        sev_parts = ", ".join(
            f"{k}={v}" for k, v in sorted(s.by_severity.items())
        )
        lines.append(f"- By severity: {sev_parts}")
    if s.by_action:
        act_parts = ", ".join(
            f"{k}={v}" for k, v in sorted(s.by_action.items())
        )
        lines.append(f"- By action: {act_parts}")
    lines.append("")

    if not pack.insights:
        lines.append("_No insights triggered against the current snapshot._")
        lines.append("")
    else:
        lines.append("## Insights")
        lines.append("")
        for insight in pack.insights:
            lines.extend(_render_insight(insight))

    if pack.profiles:
        lines.append("## Ad group profiles")
        lines.append("")
        lines.append(
            "| Campaign / Ad group | Impr | Clicks | Cost | Conv | CTR | CPA |"
        )
        lines.append("|---|---:|---:|---:|---:|---:|---:|")
        for p in pack.profiles[:20]:  # cap to keep MD readable
            label = p.dimension or p.content_ref
            ctr = f"{p.ctr:.4f}" if p.ctr is not None else "—"
            cpa = f"{p.cpa:.2f}" if p.cpa is not None else "—"
            lines.append(
                f"| {label} | {p.impressions:.0f} | {p.clicks:.0f} | "
                f"{p.cost:.2f} | {p.conversions:.0f} | {ctr} | {cpa} |"
            )
        if len(pack.profiles) > 20:
            lines.append(
                f"\n_{len(pack.profiles) - 20} additional profiles omitted_"
            )
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append(
        "_Read-only analysis. No campaign / budget / keyword mutation. "
        "Suggested actions are advisory; an operator decides what to "
        "apply in the Ads UI._"
    )
    lines.append("")
    return "\n".join(lines)


def _render_insight(insight: GoogleAdsInsight) -> list[str]:
    lines: list[str] = []
    sev = _SEVERITY_LABEL[insight.severity]
    lines.append(f"### [{sev}] {insight.title}")
    lines.append("")
    lines.append(f"- **Kind:** `{insight.kind.value}`")
    lines.append(f"- **Suggested action:** `{insight.suggested_action.value}`")
    if insight.content_ref:
        lines.append(f"- **Content ref:** `{insight.content_ref}`")
    if insight.dimension:
        lines.append(f"- **Where:** {insight.dimension}")
    lines.append(f"- **Why:** {insight.rationale}")
    if insight.evidence:
        ev = ", ".join(
            f"{k}={v}" for k, v in sorted(insight.evidence.items())
        )
        lines.append(f"- **Evidence:** {ev}")
    if insight.thresholds_used:
        th = ", ".join(
            f"{k}={v}" for k, v in sorted(insight.thresholds_used.items())
        )
        lines.append(f"- **Thresholds:** {th}")
    lines.append("")
    return lines


__all__ = ["render_markdown_ads_insights"]
