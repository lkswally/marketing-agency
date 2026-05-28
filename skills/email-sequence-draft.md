---
skill_id: email-sequence-draft
version: 1
spec_version: skill-spec.v1
status: spec_only
deterministic: false
external_dependencies: []
inputs:
  - brand: Brand
  - audience: Audience
  - offer: Offer
  - creative_brief: Asset
outputs:
  - assets: list[Asset]    # kind=EMAIL_TEMPLATE, one per step
  - claims: list[Claim]
used_by: [copywriter]
---

# email-sequence-draft

## What
Drafts a multi-step nurture sequence (default 4 emails: welcome, value,
proof, offer). Each step is a separate `Asset` of kind `EMAIL_TEMPLATE`.

## When
- W4.email.

## Heuristics
- Subject line ≤ 50 chars.
- Preview text ≤ 90 chars.
- One CTA per email.
- Day-of-send is documented in `notes`, not enforced.

## Failure modes
- No Offer → produce only the first two emails (welcome + value) and stop.

## Out of scope
- Real send / ESP integration.
- Drip scheduling.
