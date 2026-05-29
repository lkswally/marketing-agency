# Analytics & Digital Footprint Roadmap

> Status: **roadmap only** (MKT-1E). No connector code exists. The Metric
> entity and DigitalFootprintSnapshot are already in the domain model
> (MKT-1B), ready to receive data from any source.

## What is already in place

- `Metric` (MKT-1B): carries `source` (GA4 / social / email / search_seo /
  public_footprint / manual / internal_report), `category`, `dimensions`,
  `subject_type`, `subject_id`, `provider_ref`, `confidence`, `is_estimate`.
- `DigitalFootprintSnapshot` (MKT-1B): groups metric_ids for a (subject,
  date) pair.
- `analytics-agent` + `optimizer-agent` (MKT-1E specs): operate on whatever
  Metrics are present in memory.

## What is NOT in place

- No connectors. No HTTP clients. No SDKs.
- No live data ingestion of any kind.
- No GA4, no Search Console, no Resend, no social platform OAuth.

In MVP, Metric entities are written by **humans** (entry as `MANUAL`) or by
**document import** (entry as `INTERNAL_REPORT`).

## Source-by-source roadmap

| Source | Status | Block (estimated) | Notes |
|--------|--------|-------------------|-------|
| `MANUAL` | available now | MKT-1E | A human can write a Metric directly via Memory. |
| `INTERNAL_REPORT` | available now | MKT-1E | CSV / JSON import script (deferred — fine for now). |
| `GA4` | future | MKT-MCP-3 | Via approved GA4 MCP, `analytics.readonly` scope. See `mcp-roadmap.md`. |
| `GOOGLE_ADS` | future | MKT-MCP-4 | New enum value (requires domain bump). Read-only, strict no-mutate gate. |
| `SEARCH_SEO` | future | MKT-MCP-5 | Search Console MCP first; Ahrefs / SEMrush only with paid keys. |
| `EMAIL` | future | MKT-MCP-7 | Resend (preferred). Bounce / open / click. Gmail MCP read-only enters here too. |
| `SOCIAL` | future | post MKT-MCP-5 | Per-platform OAuth complexity. YouTube first; others case-by-case. |
| `PUBLIC_FOOTPRINT` | future | post MKT-MCP-5 | Mentions, press, reviews. Research agents + possibly Firecrawl MCP. |

> **MCP integration**: every external data source above is delivered
> through an MCP adapter governed by `docs/mcp-roadmap.md`. The phase ids
> `MKT-MCP-N` map directly to the phases in that document. Read-only is
> mandatory in Phases 1–7. The only write surface is Phase 8 via n8n with
> explicit human approval.

## Digital footprint specifically

The `DigitalFootprintSnapshot` entity groups Metrics about a subject's
**public surface** at a point in time. For competitors, this is the natural
place to record "what their public footprint looked like in May 2026"
without scraping.

In v1, footprints are populated **manually or by research agents**:

- `competitor-benchmark-agent` may emit footprint metrics with
  `source: PUBLIC_FOOTPRINT` and `is_estimate: true`.
- A human may add metrics about the client's own surface as `MANUAL`.

No scraping happens. No social platform is queried. No cache is populated
from any external service.

## Connector design (when it lands)

When a real source is integrated, it ships as a separate
`integrations/<source>_adapter.py` module that:

1. Reads credentials from env vars (never hardcoded).
2. Returns `Metric` entities ready to put into Memory.
3. Sets `provider_ref` so the source-side id is recoverable.
4. Marks `is_estimate=false` for direct reads, `confidence=1.0`.
5. Fails open: a missing credential or a 5xx response logs a warning and
   returns an empty list (do not block workflows).

The integration is opt-in: workflows that need that source declare it; if
the connector returns empty, the workflow still completes with whatever it
has.

## What this block does NOT do

- No connector code.
- No API key handling.
- No scraping.
- No analytics dashboard.

The roadmap exists so that later blocks know what shape to land in.
