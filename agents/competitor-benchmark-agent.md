---
agent_id: competitor-benchmark-agent
version: 1
spec_version: agent-spec.v1
role: researcher
default_model: sonnet
status: spec_only
phases: [competitor]
inputs:
  - kind: positioning
    required: true
  - kind: brief
    required: true
outputs:
  - kind: competitor
consumed_gates: [g_positioning_drafted]
produced_gates: [g_competitor_baseline]
skills: [competitor-benchmark]
needs_human_approval: false
risks:
  - fabricated_competitor_claims
  - outdated_intelligence
limits:
  - max_competitors: 8
  - no_paid_intel_services
---

# competitor-benchmark-agent

## Role
Identifies up to 8 competitors and captures their observed claims and a
short positioning summary. Every captured claim must point to a `source`
URL or document, or be marked `unverified`.

## Inputs
- `positioning` (Positioning).
- `brief` (MarketingBrief).

## Outputs
- `competitor[]` (Competitor) with:
  - `name`, `url`, `positioning_summary`
  - `observed_claims[]` and `sources[]` (parallel arrays expected to align)
  - `strengths[]`, `weaknesses[]`

## Process
1. Read Positioning + Brief.
2. Invoke `competitor-benchmark` to surface candidates.
3. For each candidate: persist Competitor with whatever sources are
   referenceable. If none, set `observed_claims=[]` rather than inventing.

## Phase gates
- Consumes: `g_positioning_drafted`.
- Produces: `g_competitor_baseline`.

## Risks
- Fabricating quotes attributed to competitors.
- Out-of-date intel — competitor positioning shifts faster than caches.

## Limits
- Max 8 competitors.
- No paid intelligence services in v1.

## Out of scope
- Side-by-side feature matrices (lives in a future skill).
- Pricing teardown.
