# Google Analytics 4 — Roadmap

> Status: **roadmap only** (MKT-2C). No GA4 connection exists. No
> service-account JSON is stored.
> Phasing follows [`mcp-roadmap.md`](mcp-roadmap.md) MKT-MCP-3.

GA4 is the highest signal-to-effort source: it covers acquisition,
engagement, conversion, retention out of the box, and Google's API has a
clean read-only scope (`analytics.readonly`). It is the first MCP
candidate to graduate from R2 (manual) to R3 (read-only programmatic).

---

## 1. Why GA4 first

| Reason | Detail |
|--------|--------|
| Coverage | Sessions, users, conversions, channel attribution — five `MetricCategory` values covered by one source. |
| Read-only feasibility | `analytics.readonly` scope or service-account with `Viewer` role. No tools mutate GA4 from this scope. |
| Low blast radius | Worst case is a stale or wrong report. No financial or public action. |
| Adapter shape is generic | The pattern (fetch → `Metric` → audit) becomes the template for the other Google sources. |

---

## 2. What GA4 produces in MKT's domain model

Every fetched row becomes a `Metric` with:

| Metric field | Value |
|--------------|-------|
| `source` | `MetricSource.GA4` |
| `category` | mapped per metric name (see §3) |
| `subject_type` + `subject_id` | inferred from dimensions; defaults to `client` if no campaign tag present |
| `provider_ref` | `ga4:property/<propertyId>;metric/<name>;...` (canonical form §4) |
| `dimensions` | the GA4 dimensions as key/value pairs |
| `measured_at` | the row's date (UTC, midnight) |
| `confidence` | `1.0` (direct read) |
| `is_estimate` | `false` |

Optionally, when fetching a coherent multi-metric snapshot (e.g. "the
last 30 days of acquisition for client X"), the adapter MAY also create
a `DigitalFootprintSnapshot` referencing the new metric_ids.

---

## 3. Metric mapping (starter table)

The adapter maps GA4 metric names to `MetricCategory`. Examples:

| GA4 metric | `MetricCategory` | Notes |
|------------|------------------|-------|
| `sessions` | `acquisition` | |
| `totalUsers`, `newUsers` | `acquisition` | |
| `engagedSessions`, `engagementRate`, `averageEngagementTime` | `engagement` | |
| `conversions`, `purchases`, `eventCount` (with conversion filter) | `conversion` | Distinguish via `eventName` dimension. |
| `userEngagementDuration`, `screenPageViews` | `engagement` | |
| `bounceRate` | `engagement` | Inverse signal — adapter does NOT invert; consumers do. |
| `retentionRate28d` (if available in property) | `retention` | |

The full mapping ships with the first adapter (post MKT-MCP-3) — this
table is the seed.

---

## 4. `provider_ref` canonical form

The string is opaque to consumers but stable enough to reconcile against
GA4:

```
ga4:property/<propertyId>;metric/<name>;dim/<sortedKey=value...>;date/<YYYY-MM-DD>
```

Examples:

```
ga4:property/123456789;metric/sessions;dim/sessionDefaultChannelGroup=Organic+Search;date/2026-05-31
ga4:property/123456789;metric/conversions;dim/eventName=purchase,country=AR;date/2026-05-31
```

This stays stable across re-fetches; an idempotent `put` against the
same `provider_ref` updates the metric in place.

---

## 5. Read-only enforcement

GA4 has no write surface in the `analytics.readonly` scope, but the
adapter still enforces it client-side:

- The `DataPermissionPolicy` for the GA4 `source_id` lists explicit
  allowed reads (`runReport`, `runRealtimeReport`, `runPivotReport`,
  `batchRunReports`, `getMetadata`).
- Every other tool name → `external_action_rejected` audit event.
- `allowed_writes: []` is hardcoded for GA4 (no R4 planned).

---

## 6. Credentials

Two acceptable shapes when MKT-MCP-3 lands:

1. **Service-account JSON** (`GA4_SERVICE_ACCOUNT_JSON`): per-tenant or
   agency-wide. JSON content lives outside the repo (e.g. in the MCP
   server's secret store, or referenced by absolute path in an env var).
   Recommended for agencies managing many clients.
2. **OAuth user token** (`GA4_OAUTH_REFRESH_TOKEN`): per-client. Useful
   when the agency does not have admin access; the client grants a
   refresh token. Adds rotation complexity.

In both cases:

- The credentials reference (`credentials_ref` in the
  `ExternalDataSource` spec) is the env var name, never the value.
- Specs / docs / configs never contain the JSON or token body.

---

## 7. Per-client property mapping

Each MKT client has one or more GA4 properties. The mapping is
configured per-client (not globally):

```yaml
# data/clients/<client_slug>/external/ga4.yaml (FUTURE, not present in MKT-2C)
contract_version: external-data-source.v0
source_id: "ga4-acme"
provider: "ga4"
provider_ref: "properties/123456789"
mode: "read_only"
credentials_ref: "env(GA4_SERVICE_ACCOUNT_JSON)"
scopes: ["analytics.readonly"]
status: "spec_only"
notes: "Awaiting client consent (R2 manual mode in the meantime)."
```

The future `mkt memory inspect --client <slug>` would list these.

---

## 8. Adapter behavior (MKT-MCP-3 sketch)

```python
# integrations/ga4_adapter.py — DOES NOT EXIST in MKT-2C
class GA4Adapter:
    def __init__(self, source: ExternalDataSource, policy: DataPermissionPolicy): ...

    def fetch_metrics(self, query: ReadOnlyMetricQuery) -> list[Metric]:
        # 1. policy.assert_read_allowed(query.tool)
        # 2. resolve credentials via env
        # 3. call MCP; map rows to Metric
        # 4. emit external_fetch audit event
        # 5. return list[Metric]
        ...
```

Behavioral guarantees:

- **Fail-open**: missing credentials → warning logged, returns `[]`.
- **Idempotent persistence**: same `provider_ref` → same metric_id
  (caller's repository layer decides upsert vs new).
- **No background calls**: every call originates from an explicit
  `ReadOnlyMetricQuery` produced by an agent.

---

## 9. Out of scope for MKT-2C

- The adapter module.
- Any actual fetch.
- Any credential setup.
- The OAuth flow.
- Caching of fetched metrics.
- Reconciliation across multiple GA4 properties.
- Real-time fetches (`runRealtimeReport`) — deferred to a later block;
  the agent flows MKT runs today are not real-time.
