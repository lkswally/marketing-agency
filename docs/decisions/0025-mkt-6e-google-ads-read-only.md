# ADR 0025 — MKT-6E: Google Ads Read-only Connector

- **Status:** Accepted
- **Date:** 2026-06-04
- **Block:** MKT-6E
- **Supersedes:** —
- **Contract:** `analytics-fetch-report.v1` (reused from MKT-6D —
  the report's `source` field now accepts `"google_ads"`).

## Context

After MKT-6D wired GA4 + Search Console as read-only connectors,
the natural next step was Google Ads — the highest-signal,
highest-cost source most agencies care about. The user explicitly
excluded it in MKT-6D ("No Google Ads todavía"); MKT-6E adds it
back under the same strict read-only contract.

The cardinal constraints, repeated three times in the spec: no
campaign creation, no campaign editing, no pause, no budget
change, no keyword add, no negative-keyword add, no ad edit, no
write of any kind.

## Decision

### D-25.1 — Extend MKT-6D's ABC, do NOT fork the shape

`GoogleAdsReadOnlyConnector` subclasses the same
`AnalyticsConnector` ABC introduced in MKT-6D. Same `source`,
`availability`, `fetch` contract. Same `FetchResult` shape. Same
`AnalyticsFetchService` orchestrates skipped / partial / failed /
ok paths. Same `analytics-fetch-report.v1` contract.

Rejected: a separate "ads connector" module hierarchy. Reusing
MKT-6D's surface keeps the CLI, audit trail, persistence, and
report rendering identical across all three sources — the only
thing that grows is the source string set and the normaliser
switch.

### D-25.2 — `SUPPORTED_SOURCES` grows by one entry

`("ga4", "search_console")` → `("ga4", "search_console", "google_ads")`.

`MetricSource` enum (MKT-6A) grows by one value: `GOOGLE_ADS`.

Both additions are non-breaking — existing analyzer / importer /
feedback / iteration code keeps compiling and behaving identically.

### D-25.3 — Single read service, single read method

The connector calls `client.get_service("GoogleAdsService")` and
nothing else. From that service it invokes `search_stream` and
nothing else.

Test pins:
- `test_google_ads_connector_only_requests_read_service` greps the
  module source for any other `get_service("<Name>")` invocation
  and fails on any match.
- `test_google_ads_connector_only_calls_search_stream` greps for
  the read method's presence.
- `test_no_google_ads_mutation_method_in_any_module` greps for any
  of 13 known mutation methods / operation types (`mutate_campaigns`,
  `mutate_ad_groups`, `mutate_ad_group_criteria`, `CampaignOperation`,
  `AdGroupOperation`, etc.).

### D-25.4 — One GAQL query at `ad_group` level

Single GAQL query against the `ad_group` view, with metrics:
impressions, clicks, cost_micros, conversions, ctr, average_cpc,
conversions_value, cost_per_conversion. Filters exclude
`REMOVED` campaigns and ad groups.

Rejected alternative: ship multiple queries (ad_group + search_term
+ keyword) in this block. Out of scope per the user's stated
detection requirements which can be derived from ad_group-level
data initially. Search-term and keyword-level queries are deferred
(P-6E.1 / P-6E.2 / P-6E.3 / P-6E.4).

### D-25.5 — `cost_micros` → `cost` in whole units

Google Ads expresses cost in micros (`cost / 1_000_000` = currency
units). The normaliser divides during persistence so the analyzer
sees comparable cost values to the GA4 conversion-value rows that
already arrive in whole units.

### D-25.6 — `content_ref` encodes campaign + ad_group

`content_ref` is the string `campaign:<id>::ad_group:<id>`. This
lets the downstream analyzer:

- Group by campaign by parsing the prefix.
- Group by ad_group as the unit.
- Cross-reference back to Google Ads UI by id.

`dimension` carries the human campaign+ad_group names for the
Markdown report.

### D-25.7 — `GOOGLE_ADS_LOGIN_CUSTOMER_ID` is optional

Five env vars are required (developer token, OAuth quad,
customer id). The login customer id is required only when
authenticating through an MCC; we tolerate its absence so direct
(non-MCC) accounts work too. Pinned by
`test_availability_login_customer_id_is_optional`.

### D-25.8 — Skipped path is first-class (same as MKT-6D)

Missing SDK or missing any required env var → status `skipped`,
audit event `fetch_skipped`, exit 0. Same behaviour the operator
saw on MKT-6D — no surprises, no new path to learn.

### D-25.9 — Detection downstream, NOT in this block

The spec listed detection cases (high spend low conv, bad-perf
keywords, negative-keyword candidates, low-CTR ads, pause/review
candidates, landing-page opportunities). MKT-6E ships the
*connector* that makes those detections possible. The detection
*logic* lives in `core/analytics/analyzer.py` and `core/feedback/`,
which already consume `MetricRow` rows tagged with channel /
content_ref / metric_name. The normalised shape this block ships
is sufficient for the high-spend-low-conversion, CPA-outlier and
low-CTR detections at ad-group level. Search-term-level detection
(negative keywords) requires the query deferred as P-6E.1.

This separation is deliberate: the connector stays narrow and
safe to mock; analyser enhancements ship as their own block when
the operator hits a concrete case.

## Consequences

### Positive

- The system now reads from the three most important Google
  surfaces (GA4, Search Console, Google Ads) under one CLI, one
  audit trail, one report contract.
- The `MetricRow` shape carries enough information for the
  analyzer to surface high-spend / low-conversion campaigns
  without needing the connector to change.
- The cardinal "no campaign mutation" guarantee is structurally
  enforced — the connector module imports nothing that could
  write, and the safety tests grep-pin it on every CI run.
- Zero impact on existing GA4 / Search Console / CSV pipelines.

### Negative / accepted trade-offs

- Single ad_group-level query means search-term, keyword-level and
  ad-level detail is unavailable until P-6E.1-P-6E.4 ship.
- Multi-account MCC sweep is one-account-per-call only (P-6E.6).
- Audit envelope still wrapped in `note` payload (same as every
  previous block).
- The failure reason carries only the exception type — Google Ads
  SDK exceptions can carry customer ids and account paths in their
  messages, so dropping the message is deliberate.

## Out of scope (explicit)

- Any mutation of Google Ads state.
- Search-term / keyword / ad-level queries.
- Landing-page report.
- Audience / demographic segmentation.
- Multi-customer fan-out.
- Native analyzer enhancements for the new detections.
- Google Ads MCP integration.

## Validation

- 19 new tests in MKT-6E surface
  (`tests/analytics/connectors/test_google_ads.py` + extensions to
  `test_normalizer.py`, `test_safety.py`, `test_service.py`,
  `tests/cli/test_cli_analytics_fetch.py`).
- Full suite: **1393 passed** (1374 from previous blocks + 19 net
  new).
- Ruff: clean across all touched files.
- ATLAS core: untouched.
- Smoke verified via `mkt analytics-fetch --source google_ads
  --dry-run`: status `skipped`, exit 0, audit `fetch_skipped`
  recorded, no env values leaked.

## Related

- Reuses everything from MKT-6D (ABC, service, report contract,
  CLI shape).
- Depends on MKT-6A (`MetricSource`, `MetricRow`, `MetricsSnapshot`).
- Future work tracked as `P-6E.*` in `PENDING.md`.
- Runtime doc: `docs/runtime/google-ads-read-only-connector.md`.
