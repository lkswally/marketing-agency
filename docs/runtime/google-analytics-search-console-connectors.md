# Google Analytics + Search Console Read-only Connectors (MKT-6D)

Runtime guide for `mkt analytics-fetch`. Read-only adapters that
import metrics from Google Analytics 4 and Search Console into the
existing `MetricsSnapshot` model without ever mutating remote
state.

## Quick start

```bash
# Dry-run (always safe, never calls Google):
mkt analytics-fetch --client acme --source ga4 --dry-run

# Real fetch (requires SDK + credentials):
mkt analytics-fetch --client acme --source ga4
mkt analytics-fetch --client acme --source search_console
```

Outputs land in `outputs/analytics-fetch-report-<source>.{md,json}`
and the report is persisted under
`<root>/<client>/analytics_fetch_report/current.json`.

## Sources supported

| `--source`        | SDK lazy-imported                                    | API method called |
|-------------------|------------------------------------------------------|-------------------|
| `ga4`             | `google.analytics.data_v1beta.BetaAnalyticsDataClient` | `run_report` only |
| `search_console`  | `googleapiclient.discovery.build("searchconsole", "v1", ...)` | `searchanalytics().query()` only |

Both adapters are **read-only strict** — no other SDK method is
referenced anywhere in the connector source. The safety test suite
grep-asserts this on every run.

## Required environment variables

| Variable                           | Used by         | Notes |
|------------------------------------|-----------------|-------|
| `GOOGLE_APPLICATION_CREDENTIALS`   | both connectors | Path to a service-account JSON. The file's *existence* is checked; its contents are never read by this module — Google's SDK consumes them. |
| `GA4_PROPERTY_ID`                  | GA4             | Numeric property id. Persisted only as a SHA-256 fingerprint (first 8 hex chars). |
| `SEARCH_CONSOLE_SITE_URL`          | Search Console  | Verified site (`https://...` or `sc-domain:...`). Persisted only as a SHA-256 fingerprint. |

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
| Missing env var                          | `skipped`   | 0    | `fetch_skipped`  | no               |
| Credentials path missing                 | `skipped`   | 0    | `fetch_skipped`  | no               |
| `--dry-run`                              | `skipped`   | 0    | `fetch_skipped`  | no               |
| Unsupported `--source`                   | —           | 2    | none             | no               |
| Missing `--source`                       | —           | 2 (argparse) | none      | no               |

**Important:** the system never crashes when credentials or the
SDK are missing. It degrades to a `skipped` report with a clear
reason, writes the MD/JSON outputs and exits 0. This is on
purpose — the operator can wire credentials later without losing
the audit trail of attempts.

## Normalisation

GA4 row → 4 `MetricRow` instances (`sessions`, `users`,
`conversions`, `bounce_rate`), tagged `MetricSource.GA4`. Channel
labels (`Organic Search`, `Paid Search/Brand`, …) are slugified
(`organic_search`, `paid_search_brand`).

Search Console row → 4 `MetricRow` instances (`clicks`,
`impressions`, `ctr`, `position`), tagged
`MetricSource.SEARCH_CONSOLE`, channel `organic_search`.

The shape matches the manual importer exactly — downstream
analysis is identical regardless of how rows entered the snapshot.

## Privacy

| Surface              | What is recorded                                       |
|----------------------|--------------------------------------------------------|
| `AnalyticsFetchReport.identifier_fingerprint` | `sha256(property_id_or_site_url)[:8]` |
| Audit event payload  | `identifier_fingerprint` only (never raw)              |
| Markdown report      | `identifier_fingerprint` only (never raw)              |
| Failure reason       | Exception *type name* only — the SDK error message is dropped to avoid leaking URLs or ids in stack traces |

Pinned by `test_audit_does_not_carry_raw_identifier` and
`test_dry_run_report_does_not_leak_env_keys`.

## Cardinal guarantees

- **Read-only strict** — no SDK mutation method appears in source
  (`test_no_ga4_mutation_method_referenced`,
  `test_no_search_console_mutation_method_referenced`).
- **No Google Ads** anywhere in the connector module
  (`test_no_google_ads_anywhere`).
- **No HTTP client library** (`requests`, `httpx`, `urllib.request`,
  `aiohttp`) is imported — the only network goes through the
  official Google SDK (`test_no_http_lib_in_any_connector_module`).
- **No credential field** on the persisted model
  (`test_no_credential_fields_on_fetch_report`).
- **CSV importer untouched** — `mkt import-metrics` keeps working
  exactly as before (`test_csv_importer_module_unchanged_shape`).

## Smoke verification (no credentials)

```bash
mkt analytics-fetch --client acme --source ga4 --dry-run \
  --root data/qa-mkt-6d --outputs-dir data/qa-mkt-6d/out
```

Expected: exit 0, JSON shows `status="skipped"`, `dry_run=true`,
`rows_normalized=0`, and the Markdown/JSON files exist under
`data/qa-mkt-6d/out/`.

## Exit codes

- `0` — fetch ran (any of `ok` / `partial` / `failed` / `skipped`).
- `2` — argparse error (missing `--source`, unsupported choice)
  or `resolve_connector` raised `ValueError`.

## NOT in scope (deferred — see PENDING.md)

- P-6D.1 — OAuth flow / service-account JSON onboarding helper.
- P-6D.2 — `--from` / `--to` explicit date range (today: rolling
  28-day lookback only).
- P-6D.3 — Multi-property / multi-site fan-out in one CLI call.
- P-6D.4 — Per-fetch cache (avoid re-pulling the same window
  within an hour).
- P-6D.5 — `analytics-fetch.v1` native audit envelope (currently
  wrapped in `note`).
- P-6D.6 — Bing Webmaster Tools / Meta Insights / TikTok Insights
  connectors (same ABC, different source string).
- P-6D.7 — Google Ads connector (intentionally out of scope; the
  user explicitly forbade it for now).
