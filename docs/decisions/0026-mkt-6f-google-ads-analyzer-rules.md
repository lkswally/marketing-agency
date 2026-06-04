# ADR 0026 — MKT-6F: Google Ads Analyzer Rules

- **Status:** Accepted
- **Date:** 2026-06-04
- **Block:** MKT-6F
- **Supersedes:** —
- **Contract:** `google-ads-insight-pack.v1` (new, Pydantic, in
  `core/ads_analysis/models.py`).

## Context

MKT-6E added the read-only Google Ads connector and produced
normalised `MetricRow` entries tagged `MetricSource.GOOGLE_ADS`.
The rows were sufficient to feed the existing generic analyzer
(`core/analytics/analyzer.py`), but that analyzer only does
channel-level summaries — it does not surface Ads-specific
detections (high spend / zero conv, CPA outliers, scale
candidates, budget review).

MKT-6F ships a dedicated analyzer for Google Ads with explicit
rules and explicit suggested actions, deliberately separated from
the generic analyzer so:

- the Google Ads rules can evolve independently (per-rule
  thresholds, new detections);
- the generic analyzer keeps its narrow scope;
- the output pack is a clear deliverable an operator can hand
  to the agency PM.

## Decision

### D-26.1 — Separate module `core/ads_analysis/`

Parallel to `core/analytics/`, `core/feedback/`, `core/iteration/`.
Same conventions: Pydantic models, deterministic analyzer class,
dedicated renderer, CLI subcommand.

Rejected alternative: extend
`OptimizationRecommendationPack`. That pack is generic across all
sources; adding Ads-specific kinds / actions would either bloat
the union types or force the generic analyzer to know about Ads.
Keeping them separate gives both packs the freedom to grow.

### D-26.2 — Twelve `AdsInsightKind` values

Covers all the cases the spec listed: `high_spend_zero_conv`,
`high_spend_low_conv`, `low_ctr_high_impr`,
`good_ctr_low_conv_rate`, `high_cpa_outlier`, `scale_candidate`,
`review_campaign`, `review_ad_group`, `review_landing`,
`pause_candidate`, `improve_ad_copy`, `budget_review`.

Seven of those are used as `kind` values by the current rule set.
The others (`review_campaign`, `review_ad_group`, `review_landing`,
`pause_candidate`, `improve_ad_copy`) overlap with the
`suggested_action` enum and are reserved for kinds we may emit
explicitly in future rules (e.g. an explicit `review_landing`
insight kind separate from rule 4's `good_ctr_low_conv_rate`).

### D-26.3 — `AdsInsightAction` is the operator's next step

Seven values, each is an action the operator may take in the Ads
UI: `review_campaign`, `review_ad_group`, `review_landing`,
`pause_candidate`, `scale_candidate`, `improve_ad_copy`,
`budget_review`. None of them is ever applied by the system —
the cardinal "no campaign mutation" rule from MKT-6E is preserved.

### D-26.4 — Aggregation per `content_ref`

Rows are grouped by the `content_ref` shape MKT-6E emits
(`campaign:<id>::ad_group:<id>`). The aggregator sums the additive
metrics (`impressions`, `clicks`, `cost`, `conversions`,
`conversions_value`) and **recomputes** the ratio metrics
(`ctr`, `cpc`, `cpa`, `conversion_rate`) from the sums. Existing
`ctr` / `cpc` / `cpa` rows in the snapshot are ignored at
aggregation time — recomputing avoids double-counting when
multiple imports stacked up.

### D-26.5 — Seven rules with module-constant thresholds

Thresholds live in module constants in `analyzer.py`. P-6F.1
tracks per-tenant overrides via a config file. The thresholds
encode the user's spec verbatim:

1. High spend zero conv: `cost ≥ 50`, `conversions == 0`.
2. High spend low conv: `cost ≥ 100`, `0 < conversions < 2`.
3. Low CTR + high impr: `impressions ≥ 1000`, `ctr < 0.02`.
4. Good CTR + low conv rate: `ctr ≥ 0.05`, `clicks ≥ 100`,
   `conv_rate < 0.01`.
5. High CPA outlier: `cpa > 2 × median_cpa`, `conversions ≥ 1`.
6. Scale candidate: `conversions ≥ 3`, `cpa ≤ 0.7 × median_cpa`,
   `cost ≤ median_cost`.
7. Budget review (campaign-level): top quartile of campaign cost.

### D-26.6 — Rules 1 and 2 are mutually exclusive

Per-profile, rule 2 is in an `elif` against rule 1 because they
detect overlapping cost ranges. Rule 1 (zero conversions) wins
when both could match — the operator sees the worst case.

### D-26.7 — Median-driven outlier detection

Rules 5 and 6 compare each ad group's CPA against the median CPA
across the snapshot. The analyzer computes the median once per
analyze() call. This is intentionally simple — a future block
can switch to per-campaign medians (P-6F.2 spinoff) or
per-channel medians.

When fewer than 2 ad groups have a CPA, the median rules do not
fire (insufficient data). This avoids false positives on
single-ad-group snapshots.

### D-26.8 — Budget review is campaign-level

The `budget_review` rule aggregates cost per campaign (not per
ad group) and triggers on campaigns whose total cost falls in the
top quartile. Emits at most one `BUDGET_REVIEW` insight per
campaign. Requires at least 2 campaigns to have meaningful
quartiles.

### D-26.9 — Deterministic ordering

Insights are sorted by `(severity_rank, kind, content_ref)` so
two runs over the same snapshot return the same order (modulo
fresh insight ids and timestamps). Pinned by
`test_deterministic_insight_ordering`.

### D-26.10 — Persistence + audit

Pack is persisted under
`google_ads_insight_pack/current.json`. Audit event payload:

```json
{
  "google_ads_insight_pack": {
    "action": "analyzed",
    "pack_id": "...",
    "snapshot_id": "...",
    "ad_groups_profiled": N,
    "total_insights": M,
    "rule_set_id": "ads-analyzer.v1"
  }
}
```

Audit envelope still wrapped in `note` (P-6F.7 tracks the v2
bump).

### D-26.11 — CLI subcommand `mkt ads-analyze`

`--client` required. `--root` + `--outputs-dir` follow the
convention of every other analyzer CLI. Exit 0 on success, exit
2 when no `MetricsSnapshot` exists for the client.

### D-26.12 — Hard guarantee preserved

The analyzer does NOT import `google.ads`, does NOT reference any
mutation method, does NOT mutate the snapshot. Pinned by
`test_no_mutation_method_in_analyzer_source` and
`test_pack_does_not_mutate_snapshot`.

## Consequences

### Positive

- One command transforms `MetricsSnapshot` rows into a complete,
  client-ready Google Ads insight document.
- Rules are explicit, deterministic, easy to test individually.
- The `suggested_action` enum is the bridge to a future
  promotion block (P-6F.5) that lifts insights into the
  `CampaignFeedbackPack`.
- Zero impact on existing connectors / importer / generic
  analyzer / feedback / iteration code.

### Negative / accepted trade-offs

- Thresholds are hard-coded module constants. Per-tenant
  overrides are P-6F.1.
- The analyzer only sees ad-group-level metrics. Search-term,
  keyword and creative-level rules wait for P-6E.1 / P-6E.3
  data, then P-6F.2 / P-6F.3 rules.
- Median-driven outliers are coarse; better outlier detection
  (z-score, IQR) is future work.
- Audit-trail envelope still wrapped in `note` (same trade-off
  as every previous block).

## Out of scope (explicit)

- Any mutation of Google Ads state.
- Search-term-level / keyword-level / ad-creative-level rules.
- Auto-injection of insights into other packs.
- LLM enrichment.
- Multi-period comparison.
- Per-tenant config of thresholds.

## Validation

- 33 new tests across `tests/ads_analysis/*` +
  `tests/cli/test_cli_ads_analyze.py`.
- Full suite: green.
- Ruff: clean.
- ATLAS core: untouched.

## Related

- Depends on MKT-6A (`MetricsSnapshot`, `MetricRow`,
  `MetricSource.GOOGLE_ADS`).
- Depends on MKT-6E (`google_ads` source + `content_ref` shape).
- Future work tracked as `P-6F.*` in `PENDING.md`.
- Runtime doc: `docs/runtime/google-ads-analyzer-rules.md`.
