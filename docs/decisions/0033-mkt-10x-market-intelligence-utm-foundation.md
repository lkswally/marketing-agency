# ADR-0033 — MKT-10X: Market Intelligence + UTM Foundation

**Date:** 2026-06-12
**Status:** Accepted
**Block:** MKT-10X

---

## Context

MAOS had reached MKT-9D with a solid pipeline for generating marketing
deliverables. However, it operated as a closed system with no awareness of
the competitive landscape, market trends, or tracking effectiveness. Every
campaign output was based only on the client's own data.

To evolve toward a learning marketing agency, we need:

1. A market intelligence layer that gathers signals from external sources.
2. A UTM tracking plan generator that enables attribution of campaign traffic.
3. A dry-run-first design so the feature ships safely before any real HTTP
   calls are made.

---

## Decision

### D1 — New module: `core/intelligence/`

A dedicated module separate from `core/analytics/` (which is metrics-in,
aggregation-out) and `core/domain/` (entity definitions). Intelligence is
about external signals, not internal client data.

### D2 — Pydantic contracts first

Seven new contracts in `core/intelligence/models.py`:
- `TrendSignal`, `CompetitorSignal`, `ContentGap` — individual observations
- `MarketIntelligencePack` — consolidated snapshot (same singleton pattern)
- `UTMTaggedLink`, `TrackingRecommendation`, `UTMPlan` — UTM tracking

All models are frozen (immutable), validated at construction, versioned.

### D3 — IntelligenceConnector ABC mirrors AnalyticsConnector

Same two-method contract: `availability()` + `fetch()`. Same
`DryRunIntelligenceConnector` base. No mutation methods on any connector.
Five adapters ship in MKT-10X, all dry-run: Google Trends, Competitor
Monitor, Reddit, YouTube, Meta Ads Library.

### D4 — Dry-run fixtures, no real HTTP in MKT-10X

External sources involve rate limits, auth, legal/ToS constraints. MKT-10X
defines the interfaces and ships fixture data so the pipeline can be built
and tested end-to-end without any network dependency. Real connectors are
gated behind future optional extras.

### D5 — UTM Builder reads existing strategy report from memory

`UTMBuilder.build()` reads `campaign_strategy_report/current` from
`JsonFileMemory`. If absent, it produces a fallback plan with a
recommendation. This keeps the builder stateless and testable without
mocking the strategy pipeline.

UTM parameter derivation rules (deterministic, documented in code):
- `utm_source` = channel platform (instagram, google, email, …)
- `utm_medium` = content type (social, cpc, email, seo, …)
- `utm_campaign` = `<client_slug>-<period>` slug
- `utm_content` = piece type slug
- `utm_term` = primary keyword (search/CPC channels only)

### D6 — UTM Plan persists to memory + outputs/

Pattern consistent with all other packs:
- `memory.put(client_slug, "utm_plan", "current", …)` (singleton)
- `outputs/<client_slug>/utm-plan.md` + `utm-plan.json`
- Audit trail event emitted on persist

### D7 — CLI command: `mkt utm-plan --client <slug>`

Standard flags: `--root`, `--outputs-dir`, `--base-url`, `--period`.
Returns JSON summary to stdout. Exit 0 always (fallback plan is valid).

### D8 — Seven skill specs (spec_only status except utm-builder)

`competitor-intelligence`, `trend-detector`, `content-gap-finder`,
`creative-fatigue-scorer`, `budget-pacer`, `weekly-executive-report` — all
`status: spec_only`. `utm-builder` — `status: implemented`.

---

## Consequences

### Positive
- Market intelligence contracts established; future real connectors drop in
  without breaking the pipeline.
- UTM plan generation is immediately usable against real client data
  (e.g. `mkt utm-plan --client legalcase-demo`).
- Dry-run-first means no credentials, no network, no ToS issues in CI.
- All new tests pass without mocks for network calls.

### Risks / Deferred
- Fixture data is generic; a real connector must be wired to get
  client-specific signals.
- `MarketIntelligencePack` uses `SINGLETON_ID = "current"` — same
  cross-cycle history gap as other packs (tracked as P-6A.3 pending).
- `utm_term` is derived from the first keyword cluster only; a future
  version should allow per-piece keyword assignment.

---

## Files Added / Modified

| Path | Change |
|------|--------|
| `core/intelligence/__init__.py` | New module |
| `core/intelligence/models.py` | 7 Pydantic contracts |
| `core/intelligence/utm_builder.py` | UTM builder + persist |
| `core/intelligence/adapters/__init__.py` | Adapter package |
| `core/intelligence/adapters/base.py` | ABC + DryRunIntelligenceConnector |
| `core/intelligence/adapters/trends.py` | DryRunTrendsConnector |
| `core/intelligence/adapters/competitor_monitor.py` | DryRunCompetitorMonitor |
| `core/intelligence/adapters/reddit.py` | DryRunRedditConnector |
| `core/intelligence/adapters/youtube.py` | DryRunYouTubeConnector |
| `core/intelligence/adapters/meta_ads.py` | DryRunMetaAdsConnector |
| `cli/main.py` | `_cmd_utm_plan` + `utm-plan` subparser |
| `skills/competitor-intelligence.md` | New spec |
| `skills/trend-detector.md` | New spec |
| `skills/content-gap-finder.md` | New spec |
| `skills/creative-fatigue-scorer.md` | New spec |
| `skills/budget-pacer.md` | New spec |
| `skills/weekly-executive-report.md` | New spec |
| `skills/utm-builder.md` | New spec (implemented) |
| `tests/intelligence/test_market_intelligence_models.py` | New tests |
| `tests/intelligence/test_intelligence_adapters.py` | New tests |
| `tests/intelligence/test_utm_builder.py` | New tests |
| `docs/decisions/0033-mkt-10x-market-intelligence-utm-foundation.md` | This ADR |
