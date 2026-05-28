---
skill_id: competitor-benchmark
version: 1
spec_version: skill-spec.v1
status: spec_only
deterministic: false
external_dependencies: []
inputs:
  - positioning: Positioning
  - brief: MarketingBrief
outputs:
  - competitors: list[Competitor]
used_by: [competitor-benchmark-agent]
---

# competitor-benchmark

## What
Surfaces up to 8 plausible competitors. For each: name, URL, a one-line
`positioning_summary`, observed claims with sources, strengths, weaknesses.

## When
- W2.competitor.

## Heuristics
- Prefer competitors the brief explicitly mentions over inferred ones.
- For each `observed_claim`, the source MUST be a URL or a quoted
  in-brief reference. No bare assertion.

## Failure modes
- Cannot identify competitors → return empty list, do not invent.
- Source attribution missing → mark the claim `unverified` and surface it.

## Out of scope
- Pricing teardown.
- Feature matrix (future skill).
