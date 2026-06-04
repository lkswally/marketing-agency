# Google Ads Analyzer Rules (MKT-6F)

Runtime guide for `mkt ads-analyze`. Deterministic, LLM-free rule
engine that reads `MetricsSnapshot` rows tagged with
`MetricSource.GOOGLE_ADS`, aggregates them per ad group and
surfaces structured insights with explicit suggested actions.

## Quick start

```bash
# Pre-req: rows in the snapshot (from MKT-6E connector or CSV import)
mkt analytics-fetch --client acme --source google_ads      # or --dry-run
# or:
mkt import-metrics --client acme --source google_ads --file path.csv

# Run the analyzer:
mkt ads-analyze --client acme
```

Outputs land in `outputs/google-ads-insight-pack.{md,json}` and
the pack is persisted under
`<root>/<client>/google_ads_insight_pack/current.json`.

## Rules

| # | Rule                          | Severity | Suggested action      |
|---|-------------------------------|----------|-----------------------|
| 1 | High spend, zero conversions  | HIGH     | `pause_candidate`     |
| 2 | High spend, low conversions   | HIGH     | `review_campaign`     |
| 3 | Low CTR + high impressions    | MEDIUM   | `improve_ad_copy`     |
| 4 | Good CTR + low conversion rate | MEDIUM  | `review_landing`      |
| 5 | High CPA outlier (vs median)  | MEDIUM   | `review_ad_group`     |
| 6 | Scale candidate               | MEDIUM   | `scale_candidate`     |
| 7 | Top-quartile spend            | LOW      | `budget_review`       |

### Thresholds (module constants)

| Rule | Thresholds |
|------|------------|
| 1    | `cost ≥ 50`, `conversions == 0` |
| 2    | `cost ≥ 100`, `0 < conversions < 2` |
| 3    | `impressions ≥ 1000`, `ctr < 0.02` |
| 4    | `ctr ≥ 0.05`, `clicks ≥ 100`, `conversion_rate < 0.01` |
| 5    | `cpa > 2 × median_cpa`, `conversions ≥ 1` |
| 6    | `conversions ≥ 3`, `cpa ≤ 0.7 × median_cpa`, `cost ≤ median_cost` |
| 7    | Campaign total cost in top quartile of all campaigns |

Per-tenant overrides → P-6F.1.

## Aggregation

Rows are grouped by `content_ref` (`campaign:<id>::ad_group:<id>`).
The aggregator sums `impressions`, `clicks`, `cost`,
`conversions`, `conversions_value` and recomputes:

- `ctr = clicks / impressions` (None if no impressions)
- `cpc = cost / clicks` (None if no clicks)
- `cpa = cost / conversions` (None if no conversions)
- `conversion_rate = conversions / clicks` (None if no clicks)

This means existing `ctr` / `cpc` / `cpa` metric rows from the
connector are ignored at aggregation time — the analyzer
recomputes them from the additive base. That keeps math
self-consistent regardless of how many imports stacked up in the
snapshot.

## Suggested actions

The analyzer never applies any change. The action enum is
deliberately advisory:

| Action               | Meaning                                            |
|----------------------|----------------------------------------------------|
| `pause_candidate`    | Operator should consider pausing the ad group.     |
| `review_campaign`    | Operator should review the campaign manually.      |
| `review_ad_group`    | Operator should review the ad group manually.     |
| `review_landing`     | Likely landing-page issue; review CRO.             |
| `scale_candidate`    | Consider scaling budget after operator review.     |
| `improve_ad_copy`    | Refresh headlines / descriptions.                 |
| `budget_review`      | Reconsider budget allocation at campaign level.    |

## Output shapes

**`GoogleAdsInsight`** — one detection, with `kind`, `severity`,
`suggested_action`, `title`, `rationale`, `content_ref`,
`campaign_id`, `ad_group_id`, `dimension`, `evidence` dict
(metric values that fired the rule), `thresholds_used` dict.

**`AdGroupProfile`** — per-ad-group rollup with all aggregated
metrics + recomputed rates.

**`GoogleAdsInsightPack`** — the full output: `pack_id`,
`snapshot_id`, `profiles`, `insights`, `stats`, `created_at`,
`rule_set_id`.

## Cardinal guarantees

- **Read-only** — the analyzer reads `MetricsSnapshot` and never
  modifies it. Pinned by `test_pack_does_not_mutate_snapshot`.
- **No Google Ads SDK reference** — the analyzer module has no
  knowledge of the SDK or any mutation method. Pinned by
  `test_no_mutation_method_in_analyzer_source`.
- **Deterministic** — same snapshot → same insights, same order
  (modulo fresh ids / timestamps). Pinned by
  `test_deterministic_insight_ordering`.
- **No credential fields** on persisted models. Pinned by
  `test_pack_no_credential_fields`.

## Exit codes

- `0` on success.
- `2` when no `MetricsSnapshot` exists for the client.

## NOT in scope (deferred — see PENDING.md)

- P-6F.1 — Per-tenant threshold overrides.
- P-6F.2 — Search-term-level insights (requires P-6E.1).
- P-6F.3 — Ad-creative-level insights (requires P-6E.3).
- P-6F.4 — Landing-page report cross-validation against GA4 rows.
- P-6F.5 — Auto-promotion of insights into the next
  `CampaignFeedbackPack` / `NextCampaignIterationPlan`.
- P-6F.6 — LLM-enriched rationale on opt-in flag.
- P-6F.7 — Native `google_ads_insight_pack.v1` audit envelope.
- P-6F.8 — Multi-period comparison (this cycle vs last cycle).
