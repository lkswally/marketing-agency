---
skill_id: hashtag-research
version: 1
spec_version: skill-spec.v1
status: spec_only
deterministic: false
external_dependencies: []
inputs:
  - clusters: list[KeywordCluster]
  - audience: list[Audience]
outputs:
  - hashtags: list[str]
used_by: [keyword-intelligence-agent]
---

# hashtag-research

## What
Produces a short-list of social hashtags relevant to each cluster, weighted
toward the audience's preferred channels.

## When
- W2.keywords (alongside keyword + negative research).

## Heuristics
- 5–15 hashtags total.
- A mix of broad (high volume, low specificity) and niche.
- Lowercase, no leading `#` in the stored list.

## Failure modes
- Cluster topics are abstract → return generic tags and flag
  `confidence: low`.

## Out of scope
- Trending analysis (no live data in v1).
- Reach estimation.
