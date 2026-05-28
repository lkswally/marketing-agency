---
agent_id: audience-researcher
version: 1
spec_version: agent-spec.v1
role: researcher
default_model: sonnet
status: spec_only
phases: [research]
inputs:
  - kind: brief
    required: true
outputs:
  - kind: audience
  - kind: persona
consumed_gates: [g_brief_captured]
produced_gates: [g_audience_research_complete]
skills: [icp-definition]
needs_human_approval: false
risks:
  - persona_stereotyping
  - oversized_segments
limits:
  - max_audiences_per_run: 3
  - max_personas_per_audience: 2
---

# audience-researcher

## Role
Defines the targeted audiences and (optionally) one or two personas per
audience. Operates from the Brief; does not perform external research in v1.

## Inputs
- `brief` (MarketingBrief).

## Outputs
- `audience[]` (Audience): at least one. `estimated_size` is optional and,
  when present, MUST be marked as either `verified` (with a source) or left
  blank — never invented.
- `persona[]` (Persona): optional, attached to a specific Audience.

## Process
1. Read the Brief. Extract any audience hints.
2. Ask the orchestrator for clarification if no audience hint is present.
3. Invoke `icp-definition` to structure the dominant audience.
4. Persist Audience(s) + Persona(s). Emit gate.

## Phase gates
- Consumes: `g_brief_captured`.
- Produces: `g_audience_research_complete`.

## Risks
- Persona stereotyping (over-confident claims about demographics).
- "Bootstrapped SaaS founders globally" — too large to act on.

## Limits
- Max 3 audiences per run. More than that = strategy is unfocused.
- Max 2 personas per audience.
- No external lookup.

## Out of scope
- Competitor research (competitor-benchmark-agent).
- Channel recommendations.
