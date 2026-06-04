# ADR 0024 — MKT-6D: Google Analytics + Search Console Read-only Connectors

- **Status:** Accepted
- **Date:** 2026-06-04
- **Block:** MKT-6D
- **Supersedes:** —
- **Contract:** `analytics-fetch-report.v1` (new, Pydantic, in
  `core/analytics/connectors/models.py`).

## Context

After MKT-6A (manual CSV import), MKT-6B (feedback pack) and
MKT-6C (next-iteration plan) the analytics loop was complete on
paper but still required the operator to *manually* export CSVs
from Google Analytics 4 and Search Console. The user asked for
the first real-source connectors — strictly read-only — without
opening the door to write APIs, Google Ads, MCP, or n8n.

The non-negotiables from the spec:

- Read-only against GA4 and Search Console.
- Manual CSV importer must keep working unchanged.
- No Google Ads. No MCP. No n8n. No HTTP manual. No scraping.
- No credentials in repo. No logging of credentials. No
  hardcoded sensitive ids.
- Tests must use mocks; CI runs without Google SDKs and without
  credentials.

## Decision

### D-24.1 — Abstract `AnalyticsConnector` ABC + lazy SDK adapters

Concrete classes (`GA4ReadOnlyConnector`,
`SearchConsoleReadOnlyConnector`) implement an ABC with just three
methods: `source`, `availability()`, `fetch(...)`. SDKs are
imported lazily inside `_build_client` / `_build_service` so the
modules load (and tests pass) without the SDKs installed.

The ABC deliberately does NOT declare any write-style verb. The
safety test `test_abc_only_declares_read_methods` pins this
against a forbidden-set of names (`create`, `update`, `delete`,
`write`, `put`, `patch`, `submit`, `insert`, `post`, `add`).

### D-24.2 — Read-only SDK surface, grep-pinned

- GA4: only `BetaAnalyticsDataClient.run_report` is referenced.
- Search Console: only `searchanalytics().query()` is referenced.

`test_no_ga4_mutation_method_referenced` and
`test_no_search_console_mutation_method_referenced` grep the
module source for a curated list of mutation methods and fail the
build if any appears.

### D-24.3 — Service layer chooses connector + persists report

`AnalyticsFetchService` orchestrates: availability check →
optional `fetch` → normalisation → snapshot append → audit event.
On any exception from the SDK, the service captures it and emits
a `FetchStatus.FAILED` report carrying only the exception's *type
name* (never the message — Google SDK exception messages can
contain raw URLs / property paths).

`resolve_connector(source, dry_run=...)` is the single entry point
for picking a concrete adapter; CLI tests assert it raises
`ValueError` on unsupported sources.

### D-24.4 — Skipped path is the default-safe behaviour

When the SDK is missing, an env var is missing, or
`--dry-run` is set, the service emits a `FetchStatus.SKIPPED`
report with a clear reason and exit code 0. The audit event
fires (`fetch_skipped`) so the operator's attempts are still
traceable. **No crash, no exception leak.**

Rejected alternative: returning exit 2 on missing credentials.
That would force the operator to wire credentials before they
can even confirm the pipeline shape. The current design lets
them shake out the workflow first.

### D-24.5 — Sensitive identifiers stored as 8-hex SHA-256

`AnalyticsFetchReport.identifier_fingerprint` is
`sha256(property_id_or_site_url)[:8]`. The audit event payload
carries only the fingerprint. The Markdown report shows only the
fingerprint. Tests pin both surfaces against the raw value.

The model carries zero fields whose name suggests credentials
(`token`, `api_key`, `secret`, `credential`, `url`,
`webhook_url`, `site_url`, `property_id`). Pinned by
`test_no_credential_fields_on_fetch_report`.

### D-24.6 — Normalisation reuses the manual importer's shape

GA4 / Search Console rows are normalised to `MetricRow` instances
with the exact same `MetricSource` enum values used by the manual
CSV importer. Downstream analyzer / feedback planner / iteration
planner code stays unchanged.

GA4 channel labels are slugified (`Organic Search` →
`organic_search`) so aggregations group correctly with CSV data
that already uses snake_case channel names.

### D-24.7 — 28-day rolling lookback default

`DEFAULT_LOOKBACK_DAYS = 28`. End date is *yesterday* (not today)
because GA4 / Search Console partial aggregations for the current
day are misleading. The `--lookback-days` CLI flag overrides for
quick iteration; explicit `--from` / `--to` is deferred to P-6D.2.

### D-24.8 — `--source` is required, no auto-discovery

The CLI does NOT print an "available sources" listing when
`--source` is omitted; argparse rejects with exit 2. The constant
`SUPPORTED_SOURCES = ("ga4", "search_console")` is the single
source of truth; tests assert this exact tuple.

### D-24.9 — `--dry-run` flag

Forces `DryRunConnector` regardless of SDK / credential
availability. The service still emits a complete `SKIPPED`
report + audit event. Useful for QA, CI, and operator dry runs.

### D-24.10 — Manual CSV importer untouched

`core/analytics/importer.py`, `core/analytics/models.py` and
`core/analytics/analyzer.py` are not modified. The connectors
live in their own subpackage `core/analytics/connectors/` and
write to the same `MetricsSnapshot` via the same memory primitive,
so existing analyzer / feedback / iteration code keeps working
identically.

## Consequences

### Positive

- One CLI command takes the analytics loop from "manual export +
  upload" to "fetch on demand" without breaking the existing
  manual flow.
- The system is deployable today even without Google credentials
  configured — the skipped path is a first-class outcome.
- Tests do NOT require the Google SDKs; CI stays lean.
- Sensitive identifiers never leak to disk / audit / Markdown.

### Negative / accepted trade-offs

- No explicit `--from` / `--to` date range; deferred (P-6D.2).
- No multi-property fan-out — one call = one property / site
  (P-6D.3).
- No per-fetch cache; repeated calls within the same hour hit the
  upstream service (P-6D.4).
- The failure reason is restricted to the exception type name
  (deliberate — accepts opacity in exchange for privacy).
- Google Ads is intentionally not addressed; the user excluded
  it explicitly for this block.

## Out of scope (explicit)

- Any mutation of GA4, Search Console, or Google Ads state.
- OAuth onboarding flow / credentials wizard.
- Multi-property / multi-site fan-out.
- Per-fetch cache.
- Bing Webmaster / Meta Insights / TikTok connectors.
- Real n8n / Notion / publishing tie-ins.

## Validation

- 6 new test modules under `tests/analytics/connectors/` +
  `tests/cli/test_cli_analytics_fetch.py`.
- 73 new tests dedicated to MKT-6D.
- Full suite: **1374 passed** (1301 from previous blocks + 73 new).
- Ruff: clean (`core/analytics/connectors`,
  `tests/analytics/connectors`, `tests/cli/test_cli_analytics_fetch.py`,
  `cli/main.py`).
- ATLAS core: untouched.
- Smoke verified end-to-end via `mkt analytics-fetch --dry-run`
  for both `ga4` and `search_console`: status `skipped`, exit 0,
  audit event `fetch_skipped` recorded, no env values leaked.

## Related

- Builds on MKT-6A (`MetricsSnapshot`, `MetricRow`,
  `MetricSource`).
- Depended on by MKT-6B (`OptimizationRecommendationPack`) /
  MKT-6C (`NextCampaignIterationPlan`) — neither needs change.
- Runtime doc:
  `docs/runtime/google-analytics-search-console-connectors.md`.
- Future work tracked as `P-6D.*` in `PENDING.md`.
