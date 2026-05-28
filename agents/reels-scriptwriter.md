---
agent_id: reels-scriptwriter
version: 1
spec_version: agent-spec.v1
role: producer
default_model: sonnet
status: spec_only
phases: [social]
inputs:
  - kind: asset       # creative brief (kind=COPY)
    required: true
  - kind: brand
    required: true
  - kind: audience
    required: true
outputs:
  - kind: asset       # reels script (kind=COPY) and optional storyboard outline
consumed_gates: [g_creative_brief_ready]
produced_gates: [g_social_drafted]
skills: [reels-script]
needs_human_approval: false
risks:
  - generic_hooks
  - format_mismatch
  - claim_overload
limits:
  - max_scripts_per_run: 5
  - max_seconds_per_script: 60
---

# reels-scriptwriter

## Role
Writes short-form video scripts (Reels / TikTok / Shorts). One script per
asset, with hook, payoff, and explicit on-screen text vs. voiceover lines.

## Inputs
- A creative brief Asset, Brand, Audience.

## Outputs
- `asset[]` of kind `COPY` with a structured body:
  - `hook` (≤ 3s)
  - `beats[]` (timed)
  - `voiceover_lines[]`
  - `on_screen_text[]`
  - `cta`
  - `target_duration_s` (≤ 60)

For factual claims voiced or shown on screen, the agent emits `Claim`
entities (verdict unverified).

## Process
1. Read brief + brand + audience.
2. Invoke `reels-script` skill.
3. Persist Asset + Claims. Emit `g_social_drafted` (shared with copywriter).

## Risks
- Generic hook ("In this video I'll show you ...").
- Format mismatch (LinkedIn corporate script on TikTok).
- Claim overload — short form does not survive disclaimers; if the script
  needs three caveats, the script is wrong.

## Limits
- Max 5 scripts per run.
- Max 60s per script.

## Out of scope
- Visual storyboarding (handled informally by `on_screen_text` for v1).
- Long-form video.
- Editing / production.
