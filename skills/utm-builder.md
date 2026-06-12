---
skill_id: utm-builder
version: 1
spec_version: skill-spec.v1
status: implemented
deterministic: true
external_dependencies: []
inputs:
  - client_slug: str
  - base_url: str
  - period: str  # optional; defaults to current YYYY-MM
outputs:
  - plan: UTMPlan
used_by: [utm-tracking-agent]
cli_command: "mkt utm-plan --client <slug>"
---

# utm-builder

## What
Generates a `UTMPlan` containing one `UTMTaggedLink` per channel × piece
combination derived from the client's `CampaignStrategyReport`.

UTM parameter rules:
- `utm_source`   = channel platform (e.g. `instagram`, `google`, `email`)
- `utm_medium`   = content type (e.g. `social`, `cpc`, `email`)
- `utm_campaign` = `<client_slug>-<period>` slug
- `utm_content`  = piece type slug (e.g. `instagram-carousel`)
- `utm_term`     = primary keyword when channel is `cpc` or `seo`

Outputs:
- `outputs/<client_slug>/utm-plan.md`
- `outputs/<client_slug>/utm-plan.json`

## When
- After strategy pipeline completes.
- When the client needs tracking links for a new campaign.

## Heuristics
- If no strategy report exists → produce fallback plan with a single
  recommendation to run the strategy pipeline first.
- One link per unique (channel, piece_type) pair. No duplicates.
- UTM values must be URL-safe slugs: lowercase, hyphens, no spaces.

## Failure modes
- Invalid `client_slug` → raise `ValueError` (validated by `validate_slug`).
- `base_url` missing scheme → accept as-is; operator is responsible for URL validity.

## Out of scope
- URL shortener integration (future).
- UTM auto-injection into Notion / n8n payloads (future).
