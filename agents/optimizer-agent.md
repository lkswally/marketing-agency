---
agent_id: optimizer-agent
version: 1
spec_version: agent-spec.v1
role: strategist
default_model: sonnet
status: spec_only
phases: [optimize]
inputs:
  - kind: metric
    required: true
  - kind: campaign
    required: false
outputs:
  - kind: backlog          # GrowthBacklogItem
consumed_gates: [g_metrics_summarized]
produced_gates: [g_optimization_recommended]
skills: [optimization-recommendation]
needs_human_approval: false
risks:
  - low_confidence_recommendations
  - actioning_noise
limits:
  - max_recommendations_per_run: 10
---

# optimizer-agent

## Role
Reads the period's metrics and produces a small list of
`GrowthBacklogItem` recommendations. Each recommendation carries an ICE
score so the human can prioritize.

## Inputs
- `metric[]` from the period.
- Optional `campaign[]` context.

## Outputs
- `backlog[]` (GrowthBacklogItem) with `hypothesis`, `impact`, `confidence`,
  `ease`, optional `related_campaign_id`.

## Process
1. Read metrics and any related campaigns.
2. Invoke `optimization-recommendation`.
3. Persist backlog items. Emit gate.

## Risks
- "Low confidence" recommendations dressed as priorities.
- Recommending action on noisy single-period swings.

## Limits
- Max 10 recommendations per run.

## Out of scope
- Executing the recommendations.
- A/B test design (future skill).
