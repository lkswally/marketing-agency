# External Data Sources

> Status: **specs only** (MKT-2C). No source is connected; no MCP is imported.
> Companion to [`mcp-roadmap.md`](mcp-roadmap.md), which defines the phased
> integration sequence (MKT-MCP-1 through MKT-MCP-8).

This document is the **taxonomy** layer: which external sources exist for
MKT, what they map to in the domain model, and the conceptual contracts the
runtime will use to talk to them.

---

## 1. The seven priority sources

In phasing order from `mcp-roadmap.md`:

| Source | `MetricSource` value | First fully-connected block | Primary domain entities touched |
|--------|----------------------|------------------------------|----------------------------------|
| Google Analytics 4 | `ga4` | MKT-MCP-3 | `Metric`, `Report` |
| Google Drive / Sheets | (n/a — surface for `Asset`) | MKT-MCP-3 (parallel) | `Asset`, `Report` |
| Google Ads | `social` (paid) — or a new `google_ads` enum value, see §4 | MKT-MCP-4 | `Metric`, `Campaign`, `Channel` |
| Search Console | `search_seo` | MKT-MCP-5 | `Metric`, `DigitalFootprintSnapshot` |
| YouTube / social analytics | `social` | post MKT-MCP-5 | `Metric`, `DigitalFootprintSnapshot` |
| Gmail / email | `email` | MKT-MCP-7 onwards | `Metric` (deliverability), `Asset` (drafts) |
| n8n (execution layer) | n/a — not a data source | MKT-MCP-8 | None as data; consumes `ProposedAction` |

Cross-reference: every source-specific roadmap (`google-analytics-roadmap.md`,
`google-ads-roadmap.md`, `search-console-roadmap.md`,
`n8n-execution-roadmap.md`) details the exact data shape and the
read-permission scope.

---

## 2. Mapping to the domain model

The contract is: **external sources do not introduce new entities**. They
produce instances of the entities `core.domain` already defines
(MKT-1B). Everything else lives in memory under runtime kinds the
dispatcher already understands (MKT-2A).

### 2.1 Metric

Most reads land here. Every fetched data point becomes a `Metric` with:

| Field | Value |
|-------|-------|
| `source` | `MetricSource` enum value (`ga4`, `social`, `email`, `search_seo`, `public_footprint`, `manual`, `internal_report`) |
| `category` | `acquisition`, `engagement`, `conversion`, `reach`, `retention`, `brand`, `seo` |
| `subject_type` + `subject_id` | The entity the metric is about: `campaign`, `channel`, `asset`, `audience`, `competitor`, `client` |
| `provider_ref` | The external system's identifier (e.g. `ga4:propertyId/123`, `gads:campaign/4567`) — required when present, used for reconciliation |
| `dimensions` | Cuts: `{device: mobile, country: AR}`, `{utm_source: newsletter}`, etc. |
| `confidence` | 0..1, optional. R3 reads from official APIs get `confidence: 1.0`. R2 manual entries get whatever the human chose. Public-footprint estimates get `< 1.0`. |
| `is_estimate` | `true` for public footprint reads, `false` for owned data sources |
| `measured_at` | Always UTC. The source's own timestamp, not the fetch time. |

### 2.2 DigitalFootprintSnapshot

Used when a fetch produces a coherent point-in-time bundle (e.g. "Acme's
public surface on 2026-06-01"). Holds metric_ids; values live in `Metric`.

### 2.3 Asset

Drive / Sheets / email-drafts produce `Asset` entities with `kind=COPY`,
`kind=DECK`, etc. The `path` field references the external resource
(`gdrive://fileId/abc`). Hashes are computed when content is fetched into
the tenant folder; absent when only metadata was read.

### 2.4 Report

`Report` entities reference the metric_ids that fed them. The narrative
is authored by `analytics-agent`; the metric_ids it points at must already
be in memory (no on-the-fly fetches inside the report).

### 2.5 Campaign / Channel

Only modified by humans (or by approved `ProposedAction`s in R4). A read
from Google Ads does NOT create or update a `Campaign` automatically.
Reads land as `Metric`s whose `subject_type=campaign` and `subject_id`
points to the corresponding MKT-managed `Campaign`.

---

## 3. Conceptual contracts

Sketches only. NOT promoted to Pydantic in MKT-2C. They are documented
here so the eventual contract layer has a head start.

### 3.1 `ExternalDataSource`

A value object describing a configured source:

```yaml
contract_version: external-data-source.v0   # promoted when implemented
source_id: "ga4-acme-property"              # opaque, unique per tenant per source
provider: "ga4"                              # one of the recognised provider keys
provider_ref: "properties/123456"            # the external identifier
mode: "read_only" | "write_with_approval"   # MKT-MCP-3 → read_only; MKT-MCP-8 → write_with_approval
scopes:
  - "analytics.readonly"
credentials_ref: "env(GA4_SERVICE_ACCOUNT_JSON)"   # by NAME only, never the value
client_slug: "demo-co"                       # multi-tenant scope
status: "spec_only" | "connected" | "deprecated"
notes: |
  Free-form. Useful for documenting "evaluated 2026-06; awaiting approval".
```

### 3.2 `MCPToolRef`

A reference used in audit events and `ProposedAction`s to point at the
exact tool that will execute (or did):

```yaml
contract_version: mcp-tool-ref.v0
mcp_name: "ga4"
tool_name: "runReport"
tool_version: "v1beta"    # optional
```

### 3.3 `ReadOnlyMetricQuery`

A query that returns `Metric`s and is guaranteed to be side-effect-free.
The adapter validates that the resolved tool is read-only before
dispatching.

```yaml
contract_version: read-only-metric-query.v0
source_id: "ga4-acme-property"
tool: { mcp_name: "ga4", tool_name: "runReport" }
metric_category: "acquisition"
subject_type: "campaign"
subject_id: "camp_q3_launch"
date_range: { start: "2026-05-01", end: "2026-05-31" }
dimensions: ["device", "country"]
metrics_requested: ["sessions", "engagedSessions"]
max_rows: 10000
```

### 3.4 `ExternalInsight`

The structured output an MCP-backed agent (e.g. `analytics-agent`)
produces from one or more `ReadOnlyMetricQuery` runs:

```yaml
contract_version: external-insight.v0
insight_id: "ins_2026_06_q3_launch_acquisition"
source_ids: ["ga4-acme-property"]
metric_ids: ["m_abc", "m_def", ...]      # the underlying Metric entities
generated_by: "analytics-agent"
generated_at: "2026-06-01T12:00:00+00:00"
summary: "Q3 launch acquisition flat MoM..."
recommendations: ["recommend_pause_campaign_X", ...]   # references to MarketingRecommendation ids
```

### 3.5 `DataPermissionPolicy`

See [`permissions-policy.md`](permissions-policy.md) §2 for the full
shape. Briefly:

```yaml
contract_version: data-permission-policy.v0
source_id: "gads-acme"
allowed_reads: [...]
allowed_writes: []                           # always empty until R4
forbidden_tools: ["mutate*", "create*", "pause*", "delete*"]
approval_required_for: []                    # populated only at R4
```

### 3.6 `MarketingRecommendation`

Produced by `optimizer-agent` from `ExternalInsight`s. Always recorded as
data; never auto-executed.

```yaml
contract_version: marketing-recommendation.v0
recommendation_id: "rec_pause_camp_q3"
client_slug: "demo-co"
generated_by: "optimizer-agent"
generated_at: "2026-06-01T12:00:00+00:00"
title: "Pause campaign Q3 launch in markets with CPA > 3x avg"
rationale: |
  GA4 + Google Ads correlation shows ...
evidence:
  insight_ids: ["ins_..."]
  metric_ids: ["m_..."]
proposed_actions: ["pa_pause_camp_q3"]       # references ProposedAction ids
ice_score: { impact: 8, confidence: 6, ease: 7 }
status: "draft" | "submitted_for_approval" | "approved" | "rejected"
```

### 3.7 `ProposedAction`

The bridge between a recommendation and an external mutation. Only
executes after Approval Center sign-off (Approval policy in
`approval-center.md`).

```yaml
contract_version: proposed-action.v0
proposed_action_id: "pa_pause_camp_q3"
client_slug: "demo-co"
source_id: "gads-acme"                       # which ExternalDataSource will execute it
tool: { mcp_name: "gads", tool_name: "campaignService.mutate" }
operation: "PAUSE"
target:
  kind: "campaign"
  external_id: "gads:campaign/4567"
  internal_id: "camp_q3_launch"
parameters:
  status: "PAUSED"
diff_summary: |
  Before: campaign 4567 status=ENABLED with daily budget $200
  After:  campaign 4567 status=PAUSED, budget unchanged
state: "PROPOSED"
approval_id: null                            # set when packaged for approval
executed_at: null
execution_result: null
```

A `ProposedAction.state` enum mirrors the Approval Center:
`PROPOSED → IN_REVIEW → APPROVED → EXECUTING → EXECUTED` (or `REJECTED`,
`EXECUTION_FAILED`). Transitions emit audit events.

---

## 4. Open questions reserved for future ADRs

- **New `MetricSource` enum values** for Google Ads, YouTube as
  first-class sources, vs reusing `social`/`paid_social` with a `provider`
  dimension. Reusing avoids a domain-model bump; first-classing makes
  cross-source queries cleaner. Defer to the block that ships the first
  Google Ads adapter.
- **Per-client vs agency-wide credentials**: GA4 properties belong to
  clients; OAuth tokens often live in the agency identity. Specs allow
  both via the `credentials_ref` field but no resolver exists yet.
- **Caching policy for read fetches**: MCP cost vs metric freshness. The
  `Metric` entity stores `measured_at` so cache hits are detectable, but
  the cache itself is out of scope.
- **Multi-source insights**: an `ExternalInsight` may consume metrics
  from several `ExternalDataSource`s. The cross-source join policy
  (timezone normalization, attribution windows) is not specified.

---

## 5. What this document does NOT do

- No connector code.
- No registry implementation.
- No Pydantic models.
- No `Metric` enum bumps.
- No declaration that any specific source has been or will be evaluated
  to pass the 7 filters in `mcp-roadmap.md`.
