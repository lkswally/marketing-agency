# Domain Model — Contract `domain-model.v1`

> Version: **v1** (MKT-1B).
> Implementation: `core/domain/*.py`. Pydantic v2.
> Backward compatibility: breaking changes bump to `v2`.

This document is the canonical reference for the 17 entities, their fields, and the rules each must satisfy.

---

## 1. Universal rules

All entities inherit from `TimestampedModel`, which inherits from `DomainModel`.

### 1.1 `DomainModel` config

| Setting | Value | Meaning |
|---------|-------|---------|
| `extra` | `"forbid"` | Unknown fields raise `ValidationError`. |
| `str_strip_whitespace` | `True` | Strings are stripped on input. |
| `validate_assignment` | `True` | Mutations re-run validators. |

### 1.2 Common helpers

| Helper | Purpose |
|--------|---------|
| `new_id()` | UUID4 hex (32 chars). Default for every `id` field. |
| `utcnow()` | Timezone-aware UTC `datetime`. |
| `validate_slug(value)` | Lowercase ASCII + dashes; rejects reserved (`_shared`). |

### 1.3 Timestamps

`TimestampedModel` adds:

- `created_at: datetime` — default `utcnow()`, **must be timezone-aware**.
- `updated_at: datetime` — same rules.

All `datetime` fields elsewhere in the model are **required to be timezone-aware** when present.

### 1.4 References

Entities reference each other by **id or slug**, never by embedded object. Referential integrity is **NOT** enforced by the model — that is a repository-layer concern (MKT-1D+).

### 1.5 Serialization

- `Entity.to_json()` → JSON string.
- `Entity.from_json(payload)` → instance. Computed fields are stripped from the input so round-trips work.
- All enums serialize to plain lowercase strings.
- Datetimes serialize as ISO 8601 with explicit offset.

---

## 2. The 17 entities

| # | Entity | File | Anchors |
|---|--------|------|---------|
| 1 | `Client` | `client.py` | root of multi-tenancy |
| 2 | `MarketingBrief` | `brief.py` | workflow input |
| 3 | `Brand` (+ `BrandVoice`) | `brand.py` | identity & voice |
| 4 | `Audience` | `audience.py` | who we target |
| 5 | `Persona` | `persona.py` | archetype within audience |
| 6 | `Competitor` | `competitor.py` | rivals |
| 7 | `Offer` | `offer.py` | what we sell |
| 8 | `Positioning` | `positioning.py` | how we stake claim |
| 9 | `Campaign` | `campaign.py` | bounded effort |
| 10 | `Channel` | `channel.py` | distribution surface |
| 11 | `Asset` | `asset.py` | content artifact |
| 12 | `Claim` | `claim.py` | factual assertion |
| 13 | `Evidence` | `evidence.py` | source backing a claim |
| 14 | `Metric` | `metric.py` | a measurement |
| 15 | `DigitalFootprintSnapshot` | `footprint.py` | grouped public-surface reading |
| 16 | `GrowthBacklogItem` | `backlog.py` | ICE-scored hypothesis |
| 17 | `Report` | `report.py` | narrative deliverable |

### 2.1 Reference graph (id-based)

```
Client (slug) ─── tenant scope for every other entity ───────────────┐
                                                                      │
Brand ── logo_asset_ids ──> Asset                                     │
                                                                      │
Audience ── persona_ids ──> Persona                                   │
                                                                      │
MarketingBrief ── audience_ids ──> Audience                           │
                                                                      │
Campaign ─┬── brief_id ──> MarketingBrief                             │
          ├── audience_ids ──> Audience                                │
          ├── channel_ids ──> Channel                                  │
          ├── asset_ids ──> Asset                                      │
          └── offer_ids ──> Offer                                      │
                                                                      │
Asset ─┬── campaign_id ──> Campaign                                   │
       └── claim_ids ──> Claim                                         │
                                                                      │
Claim ── evidence_ids ──> Evidence                                    │
                                                                      │
Metric ── subject_type/subject_id ──> {Client|Competitor|Channel|     │
                                       Campaign|Asset|Persona|         │
                                       Audience}                       │
                                                                      │
DigitalFootprintSnapshot ─┬── subject_type/subject_id (as above)      │
                          └── metric_ids ──> Metric                    │
                                                                      │
Report ─┬── metric_ids ──> Metric                                     │
        └── campaign_ids ──> Campaign                                  │
                                                                      │
GrowthBacklogItem ─┬── related_campaign_id ──> Campaign               │
                   └── related_audience_ids ──> Audience               │
```

---

## 3. Sources & Categories Taxonomy

Both apply to `Metric` (and transitively to `DigitalFootprintSnapshot`, which groups metrics).

### 3.1 `MetricSource`

| Value | Meaning | Future connector (deferred) |
|-------|---------|------------------------------|
| `ga4` | Google Analytics 4 | MKT-6B |
| `social` | IG / LinkedIn / X / TikTok / FB / YouTube | post-MKT-6 |
| `email` | Resend / Mailchimp / etc. | MKT-6A |
| `search_seo` | GSC / Bing WMT / Ahrefs / SEMrush | MKT-6B |
| `public_footprint` | Mentions, reviews, press | post-MKT-6 (research agents) |
| `manual` | Human entry | MKT-2A |
| `internal_report` | Client CRM / ERP exports | MKT-2A |

### 3.2 `MetricCategory`

| Value | Examples |
|-------|----------|
| `acquisition` | sessions, signups, downloads |
| `engagement` | likes, shares, time-on-page, opens, clicks |
| `conversion` | purchases, leads, demos booked |
| `reach` | impressions, followers, audience size |
| `retention` | churn, repeat rate, LTV |
| `brand` | sentiment, mentions, share of voice |
| `seo` | rankings, backlinks, organic traffic |

### 3.3 Subject scoping

Every `Metric` carries `(subject_type, subject_id)` so the same model supports:

- Owned metrics ("our IG followers")
- Campaign-scoped metrics ("Q3 launch sessions")
- Competitor footprint metrics ("Acme's mentions this week")
- Persona-level signals ("Solo Founder Sam engagement")

`DigitalFootprintSnapshot` bundles a set of metrics taken (roughly) at the same date about the same subject. Snapshots are pure containers — values live in `Metric`.

### 3.4 Estimates & confidence

For sources where exact values are unobtainable (public footprint, social scraping that doesn't yet exist), `Metric` carries:

- `is_estimate: bool` — defaults to `False`.
- `confidence: float | None` — 0..1, optional.

These are advisory; the model does not enforce thresholds.

---

## 4. Future-integration matrix (informative)

| MetricSource | Required keys (future) | Owner |
|--------------|------------------------|-------|
| `ga4` | `GA4_PROPERTY_ID`, `GA4_SERVICE_ACCOUNT_JSON` | MKT-6B |
| `email` | `RESEND_API_KEY` (or provider equivalent) | MKT-6A |
| `search_seo` | TBD | MKT-6B+ |
| `social` | per-platform OAuth tokens | post-MKT-6 |
| `public_footprint` | research-agent driven, no keys | post-MKT-6 |
| `manual` | — | MKT-2A |
| `internal_report` | — | MKT-2A |

**No connector code lives in MKT-1B.** This matrix is documentation only.

---

## 5. Versioning

- This contract is **`domain-model.v1`**.
- Breaking changes (field rename, type change, removal) require a new ADR and a `v2` document.
- Additive changes (new optional field, new enum member) stay within `v1`.

---

## 6. Out of scope for this contract

- Repository / persistence interface → MKT-1D.
- Cross-entity referential integrity checks → MKT-1D / runtime.
- Schema migration policy for stored entities → deferred (see PENDING.md).
- JSON-Schema dump to disk for external consumers → optional, MKT-1C / on-demand.
