---
skill_id: channel-recommendation
version: 1
spec_version: skill-spec.v1
status: spec_only
deterministic: false
external_dependencies: []
inputs:
  - audience: list[Audience]
  - brand: Brand
  - positioning: Positioning
outputs:
  - channels: list[Channel]
used_by: [channel-advisor-agent]
---

# channel-recommendation

## What
Picks the owned + earned channels best suited to the audience and brand
voice. Caps at the agent's `max_channels_per_campaign` limit.

## When
- W3.channel_mix.

## Heuristics
- Match `audience.preferred_channels` first.
- Eliminate channels incompatible with brand voice (e.g. very formal brand
  on TikTok).
- Prefer owned channels over earned when budget is unknown.

## Failure modes
- Audience preferred channels are not implemented anywhere → fall back to
  a generic owned default (newsletter + blog) and surface the gap.

## Out of scope
- Paid surfaces (paid-ads-plan).
- SEO content cadence (seo-content-plan).
