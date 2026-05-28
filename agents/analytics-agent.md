---
agent_id: analytics-agent
version: 1
spec_version: agent-spec.v1
role: analyst
default_model: sonnet
status: spec_only
phases: [analyze, report]
inputs:
  - kind: metric
    required: true
  - kind: campaign
    required: false
  - kind: footprint
    required: false
outputs:
  - kind: report
consumed_gates: []
produced_gates: [g_metrics_summarized, g_report_drafted]
skills: []
needs_human_approval: false
risks:
  - cherry_picking_metrics
  - bad_period_comparisons
limits:
  - no_live_data_sources
  - max_metrics_per_report: 50
---

# analytics-agent

## Role
Aggregates Metric entities into period summaries and authors the Report
narrative. In v1, operates only on Metrics already persisted to memory
(sources `MANUAL` or `INTERNAL_REPORT`). Live connectors are deferred (see
`analytics-roadmap.md`).

## Inputs
- `metric[]` filtered by `client_slug` and (optional) `subject_id`.
- `campaign[]` to contextualize.
- `footprint[]` for public-surface context.

## Outputs
- `report` (Report) with narrative, highlights, metric_ids, next_steps.

## Process
1. **analyze** — group metrics by category × source × period. Compute
   deltas vs. prior period when prior values exist. Surface anomalies.
   Emit `g_metrics_summarized`.
2. **report** — assemble the Report entity. Emit `g_report_drafted`.

## Risks
- Cherry-picking metrics that flatter the period.
- Comparing periods of unequal length.

## Limits
- No live data sources in v1.
- Max 50 metrics per report (more = aggregate first, report later).

## Out of scope
- Optimization recommendations (optimizer-agent).
- Data ingestion (future connectors).
