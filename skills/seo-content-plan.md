---
skill_id: seo-content-plan
version: 1
spec_version: skill-spec.v1
status: spec_only
deterministic: false
external_dependencies: []
inputs:
  - keyword_universe: dict
  - audience: list[Audience]
  - positioning: Positioning
outputs:
  - plan: SeoContentPlan    # structured memory payload
used_by: [seo-content-planner]
---

# seo-content-plan

## What
Outputs the SEO content calendar: article briefs grouped by cluster +
journey stage, with cadence and internal linking strategy.

## When
- W3.channel_mix when an SEO channel is recommended.

## Heuristics
- One article per (cluster × journey stage) combination, capped at the
  agent's `max_articles_per_quarter`.
- Internal links flow awareness → consideration → decision.
- Each article carries an outline (H2 list) — not full copy.

## Failure modes
- Sparse keyword universe → produce fewer articles rather than padding.

## Out of scope
- Writing the articles themselves.
- Backlink strategy.
