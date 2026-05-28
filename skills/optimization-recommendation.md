---
skill_id: optimization-recommendation
version: 1
spec_version: skill-spec.v1
status: spec_only
deterministic: false
external_dependencies: []
inputs:
  - metrics: list[Metric]
  - campaign: Campaign (optional)
outputs:
  - backlog_items: list[GrowthBacklogItem]
used_by: [optimizer-agent]
---

# optimization-recommendation

## What
Produces ICE-scored recommendations as `GrowthBacklogItem` entities.

## When
- W6.optimize.

## Heuristics
- Each recommendation cites the metric(s) it responds to (in `notes`).
- Confidence ≤ 5 when based on a single period's data.
- Ease score discounts work that needs human approval per item (e.g.
  "rewrite landing" is not ease=8).

## Failure modes
- Flat metrics → return 0–2 items rather than padding.

## Out of scope
- Executing the recommendations.
- A/B test design.
