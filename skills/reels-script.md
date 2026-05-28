---
skill_id: reels-script
version: 1
spec_version: skill-spec.v1
status: spec_only
deterministic: false
external_dependencies: []
inputs:
  - brand: Brand
  - audience: Audience
  - creative_brief: Asset
outputs:
  - asset: Asset (kind=COPY, structured as a reels script)
  - claims: list[Claim]
used_by: [reels-scriptwriter]
---

# reels-script

## What
A single short-form video script with hook, beats, voiceover lines,
on-screen text, CTA. Target duration ≤ 60s.

## When
- W4.social (the reels-scriptwriter flavor).

## Heuristics
- Hook is the first 3 seconds. Replace anything weaker with a question or
  contrast.
- Beats are timed.
- On-screen text repeats the key claim once for accessibility.

## Failure modes
- Brief asks for >3 claims in <30s → return a single script + a note
  saying "split into multiple videos".

## Out of scope
- Storyboarding visuals.
- Music selection.
