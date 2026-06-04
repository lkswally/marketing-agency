# Ads Insights → Feedback Bridge (MKT-6G)

Runtime guide for `mkt ads-feedback`. Deterministic translator
that consumes the MKT-6F `GoogleAdsInsightPack` and emits an
`AdsFeedbackBridgePack` with recommendations, campaign
adjustments, negative-keyword proposals (proposals only) and
suggested tasks the operator reviews before touching the Ads UI.

## Quick start

```bash
# Pre-req: a persisted GoogleAdsInsightPack
mkt analytics-fetch --client acme --source google_ads      # or import-metrics
mkt ads-analyze --client acme

# Bridge insights into the feedback loop:
mkt ads-feedback --client acme
```

Outputs land in `outputs/ads-feedback-bridge-pack.{md,json}` and
the pack is persisted under
`<root>/<client>/ads_feedback_bridge_pack/current.json`.

## Insight kind → bridge mapping

| Insight kind (MKT-6F) | Recommendation kind        | Campaign adjustment    |
|-----------------------|----------------------------|------------------------|
| `high_spend_zero_conv`| `pause_review`             | `pause_review`         |
| `high_spend_low_conv` | `review_campaign`          | `optimize_review`      |
| `low_ctr_high_impr`   | `improve_ad_copy`          | — (ad-group only)      |
| `good_ctr_low_conv_rate` | `review_landing`        | — (landing focus)      |
| `high_cpa_outlier`    | `review_ad_group`          | — (ad-group only)      |
| `scale_candidate`     | `scale_opportunity`        | `scale_review`         |
| `budget_review`       | `budget_review`            | `reallocate_review`    |

Campaign adjustments are deduplicated per `(campaign_id, kind)` —
multiple ad-group insights on the same campaign emit one
adjustment.

## Recommendation priority

Mirrors the insight severity 1:1:

| Insight severity | Recommendation priority |
|------------------|--------------------------|
| `high`           | `HIGH`                   |
| `medium`         | `MEDIUM`                 |
| `low`            | `LOW`                    |

## Suggested task categories

Mirrors the MKT-6B `SuggestedTaskCategory` enum (compatible with
MKT-4E `ExecutionTask` shape, so a future opt-in promoter is a
trivial mapping):

| Recommendation kind        | Task category   |
|----------------------------|------------------|
| `pause_review`             | `optimization`   |
| `review_campaign`          | `optimization`   |
| `review_ad_group`          | `optimization`   |
| `review_landing`           | `optimization`   |
| `scale_opportunity`        | `optimization`   |
| `improve_ad_copy`          | `content`        |
| `budget_review`            | `operational`    |
| `negative_keyword_proposal`| `operational`    |

Plus one trailing `measurement` task: "Review Google Ads bridge
pack with account lead".

## Negative keyword proposals

The bridge persists negative-keyword candidates **as text
proposals only**. It never adds them to Google Ads. With the
current data set (ad-group-level only) the bridge surfaces zero
proposals — the wiring is in place but the source data lives in
the search-term view, deferred to P-6E.1 / P-6F.2.

## Cross-references (best-effort)

The bridge looks up these optional artifacts and records their
ids on the pack for traceability. They are NEVER required:

| Pack                              | Field on bridge pack         |
|-----------------------------------|------------------------------|
| `CampaignFeedbackPack` (MKT-6B)   | `feedback_pack_id`           |
| `CampaignExecutionTaskPack` (MKT-4E) | `execution_task_pack_id`  |
| `NextCampaignIterationPlan` (MKT-6C) | `iteration_plan_id`       |

All three default to `None` when the corresponding pack does not
exist for the client.

## Cardinal guarantees

- **No campaign mutation** — the bridge never calls Google Ads.
- **No keyword execution** — proposals only.
- **Upstream packs read-only** — pinned by
  `test_bridge_does_not_mutate_upstream_packs`.
- **No Google Ads SDK reference** — pinned by
  `test_no_google_ads_sdk_reference_in_bridge_source`.
- **Deterministic** — same insight pack → same recommendation
  ordering (pinned by
  `test_deterministic_recommendation_ordering`).
- **No credential fields** on persisted models — pinned by
  `test_no_credential_fields_on_pack` and `…_on_recommendation`.

## Exit codes

- `0` on success.
- `2` when no `GoogleAdsInsightPack` exists for the client (the
  bridge can't translate nothing).

## NOT in scope (deferred — see PENDING.md)

- P-6G.1 — Opt-in promotion of `AdsSuggestedTask` into the next
  `CampaignFeedbackPack` (auto-merge into
  `SuggestedTask[]`).
- P-6G.2 — Opt-in promotion into the next
  `CampaignExecutionTaskPack` (lift to `ExecutionTask`).
- P-6G.3 — Opt-in promotion into the next
  `NextCampaignIterationPlan` (lift to `IterationAction`).
- P-6G.4 — Real negative-keyword candidate extraction (needs
  P-6E.1 search-term data + P-6F.2 rule).
- P-6G.5 — Cross-channel comparison: insights vs GA4 / Search
  Console (e.g. organic vs paid CPA).
- P-6G.6 — LLM-enriched rationale on opt-in flag.
- P-6G.7 — Native `ads_feedback_bridge_pack.v1` audit envelope.
- P-6G.8 — Multi-period delta (this cycle vs last cycle).
