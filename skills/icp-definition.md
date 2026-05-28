---
skill_id: icp-definition
version: 1
spec_version: skill-spec.v1
status: spec_only
deterministic: false
external_dependencies: []
inputs:
  - brief: MarketingBrief
  - audience_hints: list[str]
outputs:
  - audience: Audience
  - persona: Persona (optional)
used_by: [audience-researcher, brand-strategist]
---

# icp-definition

## What
Defines the Ideal Customer Profile (ICP) for the campaign as a structured
`Audience` (and optional `Persona`).

## When
- W1.research first ICP draft.
- Re-runs when the Brief's audience hints change materially.

## Heuristics
- `estimated_size` is left blank unless the brief provides a sourced number.
- `preferred_channels` favors channels the audience already uses
  (not channels the agency wants to push).

## Failure modes
- Audience hints contradict each other ("everyone" + "C-suite") → return
  the most specific one, raise a clarifying question via the agent.

## Out of scope
- Buying intent scoring.
- Market sizing.
