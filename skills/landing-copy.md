---
skill_id: landing-copy
version: 1
spec_version: skill-spec.v1
status: spec_only
deterministic: false
external_dependencies: []
inputs:
  - brand: Brand
  - positioning: Positioning
  - offer: Offer
  - audience: Audience
  - creative_brief: Asset
outputs:
  - asset: Asset (kind=LANDING)
  - claims: list[Claim]
used_by: [copywriter]
---

# landing-copy

## What
Drafts a single landing page: hero, supporting sections, social proof slots,
FAQ, CTA. Output is structured into a Landing asset.

## When
- W4.copy.

## Heuristics
- Hero answers "what + for whom + why now" in three lines.
- Every numeric claim becomes a `Claim` with verdict `unverified`.
- CTA copy avoids "Submit"; uses the offer name.

## Failure modes
- No Offer → return a draft with a TODO marker; do not invent the offer.

## Out of scope
- Layout / design.
- A/B test variant generation.
