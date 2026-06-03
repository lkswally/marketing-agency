# ADR 0021 — MKT-6A: Manual Marketing Analytics Import

- **Status:** Accepted
- **Date:** 2026-06-02
- **Block:** MKT-6A
- **Supersedes:** —
- **Contracts:** `metrics-snapshot.v1`, `analytics-import-report.v1`,
  `optimization-recommendation-pack.v1` (all new, Pydantic, in
  `core/analytics/models.py`).

## Context

After MKT-5C the system can plan downstream integrations
(Notion, n8n) but has no way to read marketing performance back
and make data-driven decisions. The natural next step is
analytics — but the user repeated three times: "no GA4 real",
"no Search Console real", "no credentials". The block must let
operators import data manually from CSV/JSON exports first.

MKT-6A ships the manual-import layer: importer, normalised data
model, analyzer with deterministic heuristics, recommendation
pack, two CLI commands. Real-API import blocks for each source
are catalogued as future P-6A.* work.

## Decision

### D-21.1 — New module `core/analytics/`

Parallel to every other domain module. Pydantic models with
`extra="forbid"`, importer class with `import_file/persist`
semantics (memory-keyed), analyzer class with
`analyze/persist/load_latest`, dedicated renderer, exported
through `__init__.py`.

### D-21.2 — One normalised row shape across all sources

`MetricRow` is the lowest common denominator:
`(source, event_date, channel, content_ref, query, metric_name,
value, dimension)`. Every source-specific parser produces zero
or more rows in this shape per input row.

Rejected alternative: per-source dataclasses (GA4Row,
SearchConsoleRow, etc.). The analyzer would then need source
branches everywhere; the heuristics aggregate by `channel` and
`content_ref` regardless of source, so the unified shape is
strictly simpler.

Field-name pitfall (fixed during smoke): the field cannot be
named `date` because `from __future__ import annotations` plus a
default of `None` confuses Pydantic v2's forward-ref resolution
(it ends up evaluating `date | None` with `date == None`).
Renamed to `event_date`.

### D-21.3 — One CSV row → multiple metric rows

A GA4 row with sessions, users, conversions, bounce_rate produces
four `MetricRow` instances. This lets the analyzer aggregate
each metric independently without per-source branches, and lets
imports from different sources accumulate cleanly even when they
report the same metric at different granularities.

### D-21.4 — Append-only snapshot per client

Every `mkt import-metrics` invocation extends
`<client>/metrics_snapshot/current.json`. Two imports double the
row count. No delete / replace / overwrite path ships in this
block (P-6A.3 tracks time-ranged snapshots).

The trade-off: a sloppy operator who imports the same file twice
inflates rows. The mitigation is the import report: the operator
sees `rows_imported` per call and can audit the chain via the
audit events.

### D-21.5 — Two CLI commands, not one orchestrator

`mkt import-metrics` does parsing + normalisation + persistence.
`mkt analyze-metrics` consumes the snapshot. Splitting them
matches how real ops works (import data over a week, then run an
analysis when you're ready) and keeps each command focused.

### D-21.6 — Forgiving CSV parsing, strict Pydantic shape

The CSV parser is permissive: header-case insensitive, `"3.5%"`
coerced to `0.035`, properly-quoted `"1,234"` coerced to `1234`,
unknown columns ignored. Per-row rejections (missing required
field, unparseable value) are collected in the import report,
not raised.

The Pydantic models that consume the parsed rows are strict
(`extra="forbid"`). The boundary is clean: messy data stays at
the file layer; once a row reaches `MetricRow`, it has been
normalised.

### D-21.7 — Deterministic heuristics, not LLM

The analyzer answers the eight questions in the spec ("which
channel performed best", "which campaign to pause", etc.) with
explicit deterministic rules. No LLM. No external API.

Each rule lives as a constant in `analyzer.py`
(`_SEO_LOW_CTR = 0.02`, `_PAUSE_MIN_IMPRESSIONS = 200.0`, etc.)
so a future tuning block can revisit them in one place
(P-6A.4).

LLM-enriched rationale text is explicitly out of scope; future
P-6A.5 may add it behind the same opt-in pattern as MKT-4B's
Anthropic invoker.

### D-21.8 — Three priority levels for recommendations

`Recommendation.priority ∈ {high, medium, low}`. Matches the
existing convention from MKT-4E (task pack). High priority is
reserved for "the campaign launch will fail without this"
(repeat-best-channel, ERROR-severity SEO opportunities); medium
for "this matters but won't block" (pause-bad-channel, mid-tier
SEO opps); low for "informational" (next_action fallback when
data is too thin).

### D-21.9 — Six recommendation kinds match the user's questions

`Recommendation.kind ∈ {repeat, pause, improve, seo_opportunity,
next_action}`. One per spec question:

| Question                                | Kind                |
|-----------------------------------------|---------------------|
| Which campaign to repeat?               | `repeat`            |
| Which campaign to pause?                | `pause`             |
| Which content to improve?               | `improve`           |
| Which keyword is an opportunity?        | `seo_opportunity`   |
| What's the next action?                 | `next_action`       |

"Which channel performed best?" and "which content had most
engagement?" are answered by the structured pack fields
(`best_channel`, `worst_channel`, `top_content`) rather than as
recommendations — they're observations, not actions.

### D-21.10 — Two contracts on disk + one in memory only

`metrics-snapshot.v1` and `optimization-recommendation-pack.v1`
are the long-lived contracts a downstream tool would consume.
`analytics-import-report.v1` is per-invocation bookkeeping;
useful for the operator but not part of any future cross-block
integration surface. All three are versioned and forbid extra
fields.

### D-21.11 — Hard guarantee: no external service

Test-pinned at three layers:

- `test_importer_does_not_import_http_clients`
- `test_analyzer_does_not_import_http_or_env`
- `test_*_has_no_credential_fields` on every model

The future real-API import blocks (P-6A.1, P-6A.2) will live in
separate modules (`core/analytics/sources/ga4_real.py` etc.)
with their own opt-in extras, following the MKT-4B / MKT-5B
pattern.

## Consequences

### Positive

- One command (per source) imports a CSV. One command analyses.
  Zero credentials, zero HTTP, zero LLM, zero external state.
- The operator can audit every recommendation against the
  underlying snapshot via memory inspection or the persisted
  import reports.
- Heuristics are explicit constants — a future tuning block
  changes them in one place.
- The data model is reusable: real-API import blocks just need
  to produce `MetricRow` instances.

### Negative / accepted trade-offs

- Manual export is tedious. Operators have to run it on a
  schedule. Mitigated by tracking real-API imports as the
  natural next blocks (P-6A.1, P-6A.2).
- Append-only snapshots can be polluted by duplicate imports.
  Mitigation: the import report shows row counts and the audit
  trail records every import for review.
- Thresholds are global constants. A tenant with very different
  volumes (a niche B2B vs a viral consumer brand) may need
  different cutoffs. P-6A.4 tracks per-tenant config.
- No time-range support — the snapshot is one append-only blob.
  Time-aware analysis (compare last week vs week before) needs
  P-6A.3.
- The analyzer's heuristics are intentionally simple. For
  campaigns with thin data they produce a single `next_action`
  recommendation telling the operator to import more data. This
  is honest but unhelpful for a single-import-then-analyze flow
  with little data.

## Out of scope (explicit)

- Real API calls (GA4, Search Console, Google Ads, social
  platforms, email tools).
- MCP.
- Scraping.
- Credentials of any kind.
- LLM enrichment.
- Publishing, email send, image generation.
- Dashboards or web UI of any kind.

## Validation

- 64 new tests (`tests/analytics/*` + `tests/cli/test_cli_analytics.py`).
- Full suite: 1213 passed (1149 from previous blocks + 64 new).
- Ruff: clean.
- ATLAS core: untouched.
- Smoke verified end-to-end on `tests/fixtures/analytics/`:
  52 normalised rows across 4 imports, 6 channels ranked,
  3 SEO opps, 6 recommendations.

## Related

- Future work tracked as `P-6A.*` in `PENDING.md`.
- Future real-API import blocks (P-6A.1 / P-6A.2) will consume
  the same `MetricRow` shape.
- Runtime doc:
  `docs/runtime/marketing-analytics-manual-import.md`.
