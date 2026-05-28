---
skill_id: paid-ads-plan
version: 1
spec_version: skill-spec.v1
status: spec_only
deterministic: false
external_dependencies: []
inputs:
  - audience: list[Audience]
  - positioning: Positioning
  - keyword_universe: dict (optional)
outputs:
  - plan: PaidAdsPlan       # not a domain entity; structured memory payload
used_by: [paid-ads-strategist]
---

# paid-ads-plan

## What
Drafts the paid-ads plan: campaigns × ad groups × targeting × exclusions.
v1 outputs structure only, no bids, no creatives.

## When
- W3.channel_mix when at least one paid Channel is recommended.

## Heuristics
- One ad group per keyword cluster (when keywords are available).
- Geo and language inferred from `audience.demographics` when present.
- Negative keywords from `negative-keywords` are attached automatically.

## Failure modes
- No keyword universe → use Positioning + Audience to draft thematic ad
  groups without keyword lists.

## Out of scope
- Bid management.
- Live account integration.
- Budget allocation.
