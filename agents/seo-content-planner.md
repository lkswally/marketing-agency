---
agent_id: seo-content-planner
version: 1
spec_version: agent-spec.v1
role: strategist
default_model: sonnet
status: spec_only
phases: [channel_mix]
inputs:
  - kind: keyword_universe
    required: true
  - kind: audience
    required: true
  - kind: positioning
    required: true
outputs:
  - kind: channel             # channel_type=seo or blog
  - kind: seo_content_plan    # persisted as memory entity (kind="seo_content_plan")
consumed_gates: [g_keywords_drafted, g_audience_research_complete]
produced_gates: [g_channels_proposed]
skills: [seo-content-plan]
needs_human_approval: false
risks:
  - duplicating_keyword_intent
  - thin_content_outlines
limits:
  - max_articles_per_quarter: 24
  - no_external_apis
---

# seo-content-planner

## Role
Builds the SEO content calendar: article briefs grouped by keyword cluster,
mapped to journey stage (awareness, consideration, decision). Lives in
W3.channel_mix alongside `channel-advisor-agent` and `paid-ads-strategist`.

## Inputs
- `keyword_universe`, `audience[]`, `positioning`.

## Outputs
- `channel[]` of type `seo` (and optionally `blog`).
- `seo_content_plan` memory entity with:
  - `articles: [{title, target_cluster, intent, journey_stage, outline,
    target_persona_id}]`
  - `internal_link_strategy: str`
  - `cadence: "weekly" | "biweekly" | "monthly"`

## Process
1. Read keyword universe + audience + positioning.
2. For each cluster, draft one or more article briefs with an outline.
3. Persist the channel(s) and the plan. Emit gate.

## Risks
- Multiple articles targeting the same intent (cannibalization).
- Thin outlines that don't differentiate from competitor pages.

## Limits
- Max 24 articles per quarter in v1.
- No live SERP analysis.

## Out of scope
- Writing the actual articles (copywriter does that in W4).
- Backlink outreach.
