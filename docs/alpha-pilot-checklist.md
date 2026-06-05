# CLI Checklist — Alpha Pilot (MKT-8A)

Every `mkt` subcommand the operator may invoke during a real
pilot, grouped by phase. Each row lists what the command does
and what side effects it does **not** have.

| # | Command | Phase | Writes (locally) | Does NOT |
|---|---------|-------|-------------------|----------|
| 1 | `mkt intake --file <path>` | Pre-flight | Intake + brief JSON | Call any external service |
| 2 | `mkt run-strategy --brief <path>` | Strategy | Strategy report | LLM call (unless backend opt-in) |
| 3 | `mkt run-campaign --intake <path>` | Strategy → creative | Strategy + creative + visual + approval packs | Publish anything |
| 4 | `mkt build-tasks --client <slug>` | Operational | Execution task pack | Touch Notion / n8n |
| 5 | `mkt build-tasks ... --include-ads-bridge` | Operational + Ads fold | Same + ads-bridge tasks | Touch Google Ads |
| 6 | `mkt notion-plan --client <slug>` | Operational preview | Notion payload preview JSON | Write to Notion |
| 7 | `mkt n8n-plan --client <slug>` | Operational preview | n8n payload preview JSON | Touch n8n |
| 8 | `mkt import-metrics --client <slug> --source <X> --file <csv>` | Analytics import | MetricsSnapshot + import report | Fetch from any API |
| 9 | `mkt analytics-fetch --client <slug> --source ga4` | Analytics fetch (optional) | Fetch report (skipped if no creds) | Mutate GA4 |
| 10 | `mkt analytics-fetch --client <slug> --source search_console` | Analytics fetch (optional) | Fetch report (skipped if no creds) | Mutate Search Console |
| 11 | `mkt analytics-fetch --client <slug> --source google_ads` | Analytics fetch (optional) | Fetch report (skipped if no creds) | Mutate Google Ads |
| 12 | `mkt analyze-metrics --client <slug>` | Analytics analysis | Optimization recommendation pack | Modify any campaign |
| 13 | `mkt feedback-plan --client <slug>` | Feedback loop | Campaign feedback pack | Auto-mutate any pack |
| 14 | `mkt feedback-plan ... --include-ads-bridge` | Feedback + Ads fold | Same + ads-bridge entries | Apply suggestions |
| 15 | `mkt apply-feedback --client <slug>` | Iteration plan | Next-campaign iteration plan | Apply iterations automatically |
| 16 | `mkt apply-feedback ... --include-ads-bridge` | Iteration + Ads fold | Same + ads-bridge actions | Apply iterations automatically |
| 17 | `mkt ads-analyze --client <slug>` | Ads insights | Google Ads insight pack | Touch Google Ads |
| 18 | `mkt ads-feedback --client <slug>` | Ads bridge | Ads feedback bridge pack | Touch Google Ads |
| 19 | `mkt image-jobs --client <slug>` | Image jobs prep | Image generation job pack | Generate any image |
| 20 | `mkt image-provider-plan --client <slug>` | Image provider plan | Image provider recommendation pack | Call any provider |
| 21 | `mkt atlas-brief --client <slug> --kind <K>` | ATLAS bridge | ATLAS handoff brief | Reach into ATLAS |

## Recommended end-to-end order (single pilot)

```
1. intake
2. run-campaign           (= run-strategy + creative + visual + approval)
3. build-tasks
4. notion-plan + n8n-plan (preview only)
5. image-jobs
6. image-provider-plan
7. atlas-brief --kind landing       (when applicable)
8. atlas-brief --kind branding      (when applicable)
9. (operator runs the real campaign — outside MARKETING-AGENCY-OS)
10. import-metrics  ×N sources
11. analytics-fetch ×N sources         (optional — read-only)
12. analyze-metrics
13. ads-analyze
14. ads-feedback
15. feedback-plan  (optionally --include-ads-bridge)
16. apply-feedback (optionally --include-ads-bridge)
17. build-tasks    (optionally --include-ads-bridge)   for next cycle
```

## Exit-code conventions

| Code | Meaning |
|------|---------|
| `0`  | Command finished — including degraded paths (`skipped`, `failed` reports). |
| `2`  | Required input missing (no upstream pack, missing argument, unsupported flag value). |
| `3`+ | Reserved for per-command failure modes (rare — see ADRs). |

## What every command writes

- A file under `data/<slug>/<kind>/current.json` (the persisted artifact).
- A Markdown + JSON deliverable under `outputs/<slug>/<file>.{md,json}`.
- One append-only audit JSONL entry under
  `data/<slug>/audit/<yyyy-mm-dd>.jsonl`.

## What no command does

- No real HTTP call to a provider that mutates state.
- No real image generation.
- No real publication / email send / Ads write.
- No silent data deletion. Every overwrite is intentional and
  records an audit entry.
