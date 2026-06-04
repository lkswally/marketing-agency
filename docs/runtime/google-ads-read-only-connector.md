# Google Ads Read-only Connector (MKT-6E)

Runtime guide for `mkt analytics-fetch --source google_ads`.
Read-only adapter that imports Google Ads ad-group metrics into
the existing `MetricsSnapshot` model without ever mutating remote
state (no create / pause / budget change / keyword change / ad
edit).

## Quick start

```bash
# Always-safe dry-run (never calls Google Ads):
mkt analytics-fetch --client acme --source google_ads --dry-run

# Real fetch (requires SDK + credentials):
mkt analytics-fetch --client acme --source google_ads
```

Outputs land in
`outputs/analytics-fetch-report-google_ads.{md,json}` and the
report is persisted under
`<root>/<client>/analytics_fetch_report/current.json`.

## SDK & read-only contract

| Component                         | Value                                                  |
|-----------------------------------|--------------------------------------------------------|
| SDK module (lazy)                 | `google.ads.googleads.client.GoogleAdsClient`           |
| Service requested                 | `GoogleAdsService` (the only `get_service` argument)    |
| API method called                 | `GoogleAdsService.search_stream` (**only**)             |
| Query level                       | `ad_group` view                                         |
| Mutation methods referenced       | none — grep-pinned                                      |
| Operation types referenced        | none — grep-pinned                                      |

The single GAQL query is:

```sql
SELECT
  campaign.id, campaign.name, campaign.status,
  ad_group.id, ad_group.name, ad_group.status,
  segments.date,
  metrics.impressions, metrics.clicks, metrics.cost_micros,
  metrics.conversions, metrics.ctr, metrics.average_cpc,
  metrics.conversions_value, metrics.cost_per_conversion
FROM ad_group
WHERE segments.date BETWEEN '{start}' AND '{end}'
  AND campaign.status != 'REMOVED'
  AND ad_group.status != 'REMOVED'
```

`search_terms_view` / `keyword_view` queries are deferred (P-6E.2 /
P-6E.3) — the analyzer for negative-keyword detection ships
later.

## Required environment variables

| Variable                              | Required | Notes |
|---------------------------------------|----------|-------|
| `GOOGLE_ADS_DEVELOPER_TOKEN`          | yes      | Developer token from your MCC. |
| `GOOGLE_ADS_CLIENT_ID`                | yes      | OAuth client id. |
| `GOOGLE_ADS_CLIENT_SECRET`            | yes      | OAuth client secret. |
| `GOOGLE_ADS_REFRESH_TOKEN`            | yes      | Long-lived OAuth refresh token. |
| `GOOGLE_ADS_CUSTOMER_ID`              | yes      | Customer id whose metrics are read. Digits only. Persisted only as SHA-256 fingerprint. |
| `GOOGLE_ADS_LOGIN_CUSTOMER_ID`        | optional | MCC / login customer id (digits only). Required only when reading through an MCC. |

Credentials are read from `os.environ` at fetch time, never
accepted as method arguments, never logged, never echoed in
Markdown reports or audit events.

## Behaviour matrix

| State                                    | Status      | Exit | Audit action     | Snapshot updated |
|------------------------------------------|-------------|------|------------------|------------------|
| SDK + credentials available, rows OK     | `ok`        | 0    | `fetch_ok`       | yes              |
| SDK + credentials available, some bad rows | `partial`  | 0    | `fetch_partial`  | yes (good rows)  |
| SDK + credentials available, SDK raises  | `failed`    | 0    | `fetch_failed`   | no               |
| Missing SDK                              | `skipped`   | 0    | `fetch_skipped`  | no               |
| Missing required env var                 | `skipped`   | 0    | `fetch_skipped`  | no               |
| `--dry-run`                              | `skipped`   | 0    | `fetch_skipped`  | no               |

The system never crashes when credentials or the SDK are missing.
Same first-class skipped path as MKT-6D.

## Normalisation

Each ad-group row produces up to **8 metric rows** tagged with
`MetricSource.GOOGLE_ADS`, channel `google_ads`:

| Google Ads metric           | Persisted `metric_name` | Notes |
|-----------------------------|--------------------------|-------|
| `metrics.impressions`       | `impressions`            | count |
| `metrics.clicks`            | `clicks`                 | count |
| `metrics.cost_micros`       | `cost`                   | **divided by 1_000_000** so the value matches the Ads UI currency |
| `metrics.conversions`       | `conversions`            | count |
| `metrics.ctr`               | `ctr`                    | 0..1 fraction |
| `metrics.average_cpc`       | `cpc`                    | micros (the analyzer's per-channel summary treats it as a rate) |
| `metrics.conversions_value` | `conversions_value`      | currency |
| `metrics.cost_per_conversion` | `cpa`                  | currency |

- `content_ref` encodes `campaign:<id>::ad_group:<id>` so downstream
  rollups can re-segment by campaign or ad group.
- `dimension` carries the human campaign + ad-group names
  (`"Brand Search / Exact Match"`).

## Privacy

| Surface                                       | What is recorded                       |
|-----------------------------------------------|----------------------------------------|
| `AnalyticsFetchReport.identifier_fingerprint` | `sha256(customer_id)[:8]`              |
| Audit event payload                           | fingerprint only (never raw)           |
| Markdown report                               | fingerprint only (never raw)           |
| Failure reason                                | exception *type name* only             |

## Detection downstream (analyzer)

This block ships the connector + normalisation only. The
detections the spec calls out — high spend + low conversion,
under-performing keywords, negative-keyword candidates, low-CTR
ads, pause/review candidates, landing-page opportunities — are
implemented inside `core/analytics/analyzer.py` as enhancements to
the existing channel/content summaries. The `MetricRow` shape this
connector produces is sufficient for:

- **High spend + low conversion**: filter by channel = `google_ads`,
  rank `content_ref` (campaign+ad_group) by `cost` desc and
  `conversions` asc.
- **Low CTR ad groups**: filter `ctr < threshold` per `content_ref`.
- **Pause / review candidates**: rows whose `cost` is in the top
  quartile and `conversions == 0`.
- **CPA outliers**: rank `content_ref` by `cpa` desc.

Search-term level analyses (negative keywords, query-mining)
require the additional `search_terms_view` query — deferred
(P-6E.2).

## Cardinal guarantees

- **Read-only strict** — only `GoogleAdsService.search_stream` is
  called; no mutation method or operation type appears in source.
  Pinned by `test_no_google_ads_mutation_method_in_any_module`,
  `test_google_ads_connector_only_requests_read_service` and
  `test_google_ads_connector_only_calls_search_stream`.
- **No legacy AdWords API** anywhere
  (`test_no_legacy_adwords_anywhere`).
- **No HTTP client library** — only the official SDK on the
  network path (`test_no_http_lib_in_any_connector_module`).
- **No credential field** on the persisted model
  (`test_no_credential_fields_on_fetch_report`).
- **CSV importer + GA4 + Search Console untouched** — only the
  enum set grew (`GOOGLE_ADS` added) and `SUPPORTED_SOURCES` grew
  by one entry.

## Exit codes

- `0` — fetch ran (any of `ok` / `partial` / `failed` / `skipped`).
- `2` — argparse error (missing `--source`, unsupported choice).

## NOT in scope (deferred — see PENDING.md)

- P-6E.1 — Search-terms view query (`FROM search_term_view`) for
  negative-keyword detection.
- P-6E.2 — Keyword-view query (`FROM keyword_view`) for keyword-
  level performance.
- P-6E.3 — Ad-level query (`FROM ad_group_ad`) for low-CTR ad
  detection at the creative level.
- P-6E.4 — Landing-page report (`FROM landing_page_view`).
- P-6E.5 — Audience / demographic segmentation.
- P-6E.6 — Per-customer fan-out (multi-account MCC sweep in one
  CLI call).
- P-6E.7 — Native analyzer enhancements that emit explicit
  "pause this campaign" / "add this as a negative keyword"
  recommendations on top of the normalised rows.

## Hard guarantee (cardinal)

The connector NEVER:

- creates / edits / pauses / removes a campaign;
- adjusts budgets;
- adds, edits, or pauses keywords or negative keywords;
- creates, edits, or pauses ads;
- writes anything to Google Ads.

It only reads.
