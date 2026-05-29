# Google Search Console — Roadmap

> Status: **roadmap only** (MKT-2C). No GSC connection exists.
> Phasing follows [`mcp-roadmap.md`](mcp-roadmap.md) MKT-MCP-5.

Search Console is read-by-nature: its API does not expose tools that
mutate ranking or content. The risk profile is therefore the lowest of
the priority sources. It also produces the closest thing MKT has to a
direct **organic visibility** signal.

---

## 1. Why GSC after GA4 and Google Ads

- **Closes the SEO loop**. GA4 shows post-click behavior; GSC shows
  pre-click (impressions, queries, positions).
- **No write surface**. The `webmasters` API has scopes for verification
  and sitemap submission; `webmasters.readonly` covers everything MKT
  needs. R4 not planned.
- **Cheap to operate**. Quota is generous; payloads are small.

---

## 2. Domain mapping

### 2.1 Metrics

Reads land as `Metric` with:

| Field | Value |
|-------|-------|
| `source` | `MetricSource.SEARCH_SEO` |
| `category` | `seo` for ranking-related metrics; `acquisition` for click counts |
| `subject_type` + `subject_id` | usually `client` or `asset` (when the query lands on a specific URL → linked `Asset`) |
| `provider_ref` | `gsc:site/<encodedSiteUrl>;query/<query>;page/<encodedPageUrl>;date/<YYYY-MM-DD>` |
| `dimensions` | `device`, `country`, `searchAppearance` |
| `measured_at` | the row's date (UTC) |
| `confidence` | `1.0` |
| `is_estimate` | `false` |

### 2.2 DigitalFootprintSnapshot

GSC fits the snapshot pattern well: "organic visibility for `client_slug`
on date X" is a natural bundle. The adapter MAY generate a
`DigitalFootprintSnapshot` with `subject_type=client` per fetched period.

### 2.3 Mapping to Assets

When a `Metric`'s page URL maps to a known `Asset` (e.g. an SEO article
the agency wrote), the adapter SHOULD set
`subject_type=asset, subject_id=<Asset.id>`. The mapping is configured
per client (§5).

---

## 3. Metric vocabulary (starter)

| GSC metric | `MetricCategory` | Notes |
|------------|------------------|-------|
| `clicks` | `acquisition` | |
| `impressions` | `seo` | |
| `ctr` | `seo` | computed by GSC; adapter stores as-is |
| `position` | `seo` | lower is better — consumers handle inversion |

The full mapping ships with the first adapter (post MKT-MCP-5) — this
table is the seed.

---

## 4. `provider_ref` canonical form

```
gsc:site/<urlencoded site_url>;query/<urlencoded query>;page/<urlencoded page_url>;date/<YYYY-MM-DD>
```

Dimensions and metric name are NOT embedded in the ref — the same
(site, query, page, date) tuple can carry clicks, impressions, ctr,
position. The metric name lives in `Metric.name` as today.

---

## 5. Per-client mapping

Each MKT client owns one or more GSC properties (verified site URLs):

```yaml
# data/clients/<client_slug>/external/gsc.yaml (FUTURE)
contract_version: external-data-source.v0
source_id: "gsc-acme"
provider: "gsc"
provider_ref: "https://acme.example/"
mode: "read_only"
credentials_ref: "env(GSC_SERVICE_ACCOUNT_JSON)"   # or GSC_OAUTH_REFRESH_TOKEN
scopes: ["webmasters.readonly"]
status: "spec_only"
url_to_asset_map:
  - url: "https://acme.example/articles/q3-launch"
    asset_id: "as_seo_q3_launch"
  - url: "https://acme.example/articles/founders-guide"
    asset_id: "as_seo_founders_guide"
```

---

## 6. Permission policy (R3)

Per `permissions-policy.md` §3.2:

| Operation | Status |
|-----------|--------|
| `searchanalytics.query` | ✅ allowed |
| `sitemaps.list`, `sitemaps.get` | ✅ allowed |
| `sites.list` | ✅ allowed |
| `urlInspection.index.inspect` | ✅ allowed |
| `sitemaps.submit`, `sitemaps.delete` | ❌ forbidden in R3 (these are writes, even if low-impact) |
| Any other tool | ❌ forbidden by default-deny |

---

## 7. Credentials

Two acceptable shapes:

1. **Service-account JSON** (`GSC_SERVICE_ACCOUNT_JSON`): requires
   adding the service account as a verified user on the property.
   Recommended for agency-managed sites.
2. **OAuth user token** (`GSC_OAUTH_REFRESH_TOKEN`): per-client. Useful
   when the client owns the property directly.

Both referenced by name only.

---

## 8. Behavior

When MKT-MCP-5 lands, the adapter follows the same template as
`ga4_adapter.py`:

- Fail-open on reads.
- Idempotent persistence keyed by `provider_ref`.
- `external_fetch` audit event per call.
- Maps URLs to `Asset` ids when the per-client mapping has an entry;
  otherwise leaves `subject_type=client`.

---

## 9. Open questions

- **Query-level granularity vs aggregation**: GSC returns per-query
  data up to API quota limits. Storing every (query, page, date) tuple
  produces many `Metric` entities. The adapter MAY aggregate by query
  cluster or top-N. Decision deferred to the adapter block.
- **Country and device pivots**: stored as `dimensions`, but consumers
  need to be aware that GSC's "average position" is averaged across all
  rows that match the filter. Misleading cuts are possible — the
  `analytics-agent` spec must call this out.

---

## 10. Out of scope for MKT-2C

- The adapter module.
- Any fetch.
- Credentials.
- Sitemap submission (would be R4 if ever; currently not planned).
- Indexing API (separate API, separate scopes, not in scope).
