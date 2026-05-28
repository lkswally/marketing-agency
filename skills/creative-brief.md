---
skill_id: creative-brief
version: 1
spec_version: skill-spec.v1
status: spec_only
deterministic: false
external_dependencies: []
inputs:
  - campaign: Campaign
  - brand: Brand
  - positioning: Positioning
outputs:
  - asset: Asset (kind=COPY)
used_by: [creative-director]
---

# creative-brief

## What
Drafts the creative brief: goal, audience, tone, key message, claims to
support / avoid, CTA, channel-specific dos and don'ts.

## When
- W4.brief.

## Heuristics
- ≤ 800 words.
- Explicit "must not say" section drawn from `brand.voice.banned_words`
  and `claim_style`.
- One CTA, testable.

## Failure modes
- Missing positioning → produce a brief flagged `incomplete: true` and
  surface the gap.

## Out of scope
- Writing the actual copy.
- Visual direction (no design layer in v1).
