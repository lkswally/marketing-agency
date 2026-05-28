---
agent_id: keyword-intelligence-agent
version: 1
spec_version: agent-spec.v1
role: researcher
default_model: sonnet
status: spec_only
phases: [keywords]
inputs:
  - kind: positioning
    required: true
  - kind: audience
    required: true
outputs:
  - kind: keyword_universe   # persisted as a single memory entity (kind="keyword_universe")
consumed_gates: [g_positioning_drafted]
produced_gates: [g_keywords_drafted]
skills: [keyword-research, negative-keywords, hashtag-research]
needs_human_approval: false
risks:
  - hallucinated_search_volumes
  - keyword_stuffing_clusters
limits:
  - no_external_apis
  - max_clusters: 12
  - max_keywords_per_cluster: 25
---

# keyword-intelligence-agent

## Role
Produces the keyword universe for the campaign: thematic clusters, negative
keywords, and a short-list of hashtags. In v1, sources are limited to the
agent's reasoning over Positioning + Audience; live tools (GSC, Ahrefs,
SEMrush) are deferred to MKT-6B (see `analytics-roadmap.md`).

## Inputs
- `positioning` (Positioning).
- `audience[]` (Audience).

## Outputs
- A single `keyword_universe` memory entity with:
  - `clusters: list[{label, intent, keywords[], suggested_match}]`
  - `negatives: list[str]`
  - `hashtags: list[str]`
  - `source: "reasoning_only"` (will become `"gsc"`, `"ahrefs"`, etc. later).

## Process
1. Read Positioning + Audience.
2. Invoke `keyword-research` to generate clusters and per-cluster keywords.
3. Invoke `negative-keywords` to identify exclusion terms.
4. Invoke `hashtag-research` for social applicability.
5. Persist as `kind=keyword_universe`. Emit gate.

## Phase gates
- Consumes: `g_positioning_drafted`.
- Produces: `g_keywords_drafted`.

## Risks
- Inventing search volumes — DO NOT include numeric volume in v1.
- Cluster collapse: every cluster ending up about the same topic.

## Limits
- No external API calls in v1.
- Max 12 clusters, max 25 keywords per cluster.

## Out of scope
- SERP scraping.
- Ad bid recommendations (paid-ads-strategist).
