---
skill_id: negative-keywords
version: 1
spec_version: skill-spec.v1
status: spec_only
deterministic: false
external_dependencies: []
inputs:
  - clusters: list[KeywordCluster]
  - positioning: Positioning
outputs:
  - negatives: list[str]
used_by: [keyword-intelligence-agent]
---

# negative-keywords

## What
Identifies search terms to EXCLUDE: free-only intent, irrelevant industries,
jobseeker queries, competitor brand names the client cannot target.

## When
- Always immediately after `keyword-research`.

## Heuristics
- Exclude "free", "jobs", "salary", "course", "torrent" unless the
  positioning explicitly targets them.
- Exclude competitor brand names (sourced from `competitor.name`) unless
  the campaign is explicitly a conquesting effort.

## Failure modes
- Aggressive exclusions kill addressable volume — return a list with
  rationale per item so a human can prune.

## Out of scope
- Country / language exclusions (handled at the channel level).
