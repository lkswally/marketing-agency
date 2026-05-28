---
skill_id: keyword-research
version: 1
spec_version: skill-spec.v1
status: spec_only
deterministic: false
external_dependencies: []
inputs:
  - positioning: Positioning
  - audience: list[Audience]
outputs:
  - clusters: list[{label, intent, keywords[], suggested_match}]
used_by: [keyword-intelligence-agent]
---

# keyword-research

## What
Produces thematic keyword clusters keyed by search intent (informational,
navigational, transactional). v1 operates from reasoning over the inputs;
live tooling (GSC, Ahrefs) is post-MVP.

## When
- W2.keywords.
- Refresh cycles (TBD when scheduling exists).

## Heuristics
- Cluster label is the shortest noun phrase that captures the cluster.
- Each cluster carries one intent label.
- `suggested_match` is `"broad" | "phrase" | "exact"` — for future paid use.
- **No volume numbers in v1.**

## Failure modes
- Empty Positioning → no clusters; return empty.
- Audience too broad → cluster sprawl; cap at 12 clusters and surface the
  pruning decision in the agent's notes.

## Out of scope
- SERP analysis.
- Volume / CPC estimation.
