# Runtime — Marketing Analytics Manual Import (MKT-6A)

Imports CSV/JSON metrics exports from any source (GA4, Search
Console, social platforms, email tools, manual notes), normalises
them into a single shape, and produces deterministic
optimization recommendations.

**No external API. No MCP. No scraping. No credentials. No HTTP.**
The operator exports data manually from the source platform and
feeds the file path to `mkt import-metrics`.

- **Module:** `core/analytics/`
- **Contracts:** `metrics-snapshot.v1`, `analytics-import-report.v1`,
  `optimization-recommendation-pack.v1`
- **CLIs:** `mkt import-metrics`, `mkt analyze-metrics`
- **Memory kinds:**
  `metrics_snapshot` (append-only per client),
  `analytics_import_report` (latest import),
  `optimization_recommendation_pack` (latest analysis)

## Quick start

```bash
# Import data from each source (append to the per-client snapshot).
mkt import-metrics --client acme --file ga4_export.csv --source ga4
mkt import-metrics --client acme --file sc_export.csv --source search_console
mkt import-metrics --client acme --file social.csv    --source social
mkt import-metrics --client acme --file email.csv     --source email
mkt import-metrics --client acme --file ad_hoc.json   --source manual

# Run the analyzer.
mkt analyze-metrics --client acme
```

Per call, three files land in `--outputs-dir`:

| File                                  | Audience          |
|---------------------------------------|-------------------|
| `analytics-import-report.{md,json}`   | operator review   |
| `analytics-recommendations.{md,json}` | client + team     |

## Supported sources

| Source         | CSV columns recognised                                       |
|----------------|--------------------------------------------------------------|
| `ga4`          | `date, channel, page, sessions, users, conversions, bounce_rate` |
| `search_console` | `date, page, query, clicks, impressions, ctr, position`    |
| `social`       | `date, channel, post_id, impressions, engagement, clicks, reach` |
| `email`        | `date, campaign_id, sent, opens, clicks, unsubscribes`       |
| `manual`       | `date, channel, metric_name, value, content_ref, dimension`  |

The importer is forgiving — unknown columns are ignored, missing
required columns produce per-row rejections (with reasons in the
import report), `"3.5%"` is coerced to `0.035`, properly-quoted
`"1,234"` is coerced to `1234`. JSON inputs can be a flat array
or a `{"rows": [...]}` wrapper.

Each CSV row produces ONE `MetricRow` per numeric column found.
Example: a Search Console row with clicks=10, impressions=1000,
ctr=0.01, position=12.4 produces four metric rows (one per metric)
so the analyzer aggregates them independently.

## Heuristics — what the analyzer answers

| Question                                | How it's answered                                                       |
|-----------------------------------------|-------------------------------------------------------------------------|
| Which channel performed best?           | Channel with highest total clicks + conversions (impressions as tie-breaker). |
| Which content had most engagement?      | Top `content_ref` by clicks + engagement + conversions.                 |
| Which landing had most visits?          | Same as content ranking; sessions/users count as engagement.            |
| Which keyword is an opportunity?        | Search Console rows: `impressions ≥ 100` AND `ctr ≤ 0.02` OR `10 < position ≤ 30`. |
| Which campaign to repeat?               | HIGH-priority `repeat` recommendation for the best channel.             |
| Which campaign to pause?                | `pause` recommendation when a channel has `impressions ≥ 200` AND clicks+conversions ≤ 1. |
| Which content to improve?               | Mid-tier piece below 50% of the leader's engagement.                    |
| What's the next action?                 | A short list derived from best/worst channel + SEO opps + top content.  |

The thresholds are constants in `core/analytics/analyzer.py`. A
future block can revisit them in one place.

## State + contracts

- **`MetricsSnapshot`** is append-only per client. Every
  `mkt import-metrics` invocation extends it.
- **`AnalyticsImportReport`** documents one import: source, file
  path, rows imported, rows rejected, reasons.
- **`OptimizationRecommendationPack`** carries channel
  summaries, content summaries, SEO opportunities and an explicit
  list of `Recommendation` items
  (`kind ∈ {repeat, pause, improve, seo_opportunity, next_action}`,
  `priority ∈ {high, medium, low}`, with rationale + suggested
  action + evidence_refs).

All three contracts are versioned (`.v1`) and forbid extra fields.

## Cardinal guarantees (test-pinned)

- **No HTTP**. Importer + analyzer source code is grep-asserted
  not to import `requests`, `httpx`, `urllib.request`, `anthropic`.
- **No env var read**. Same grep assertion includes `os.environ`.
- **No credential / URL field on any model**. Test rejects
  `token`, `api_key`, `secret`, `credential`, `url`, `webhook_url`
  on every model in the layer.
- **Append-only snapshot**. Two imports double the row count.
- **Pure analyzer**. Same snapshot → same channel rankings + same
  recommendations (modulo fresh ids + timestamps).
- **Audit trail**. Every import + analyze run emits a `note` event
  with the hash chain preserved.

## CLI exit codes

| Command                | Code | Meaning                                              |
|------------------------|------|------------------------------------------------------|
| `import-metrics`       | 0    | Import succeeded (may still have rejected rows).     |
|                        | 2    | File missing, unparseable, or unsupported extension. |
| `analyze-metrics`      | 0    | Analysis succeeded.                                  |
|                        | 2    | No `MetricsSnapshot` for the client (run `import-metrics` first). |

## Smoke verification

Against the fixture set under `tests/fixtures/analytics/`:

```
mkt import-metrics --client qa-client --file ga4_demo.csv          --source ga4
mkt import-metrics --client qa-client --file sc_demo.csv           --source search_console
mkt import-metrics --client qa-client --file social_demo.csv       --source social
mkt import-metrics --client qa-client --file email_demo.csv        --source email
mkt analyze-metrics --client qa-client
```

Result:
- 52 normalised rows across 4 imports
- 6 channels ranked
- 3 SEO opportunities
- 6 recommendations
- `best_channel="linkedin"` · `worst_channel="x"`

## What's NOT in MKT-6A

- No API call to GA4 / Search Console / Google Ads / social /
  email providers (all those are future blocks).
- No MCP.
- No scraping.
- No credentials / token reads.
- No LLM enrichment of recommendations (the analyzer is pure
  heuristics).
- No dashboard / web UI.
- No publishing or sending of anything.

## Follow-ups (PENDING.md → P-6A.*)

- `P-6A.1`: Real GA4 API import block (opt-in, with the same
  pattern as MKT-5B's notion-client extra).
- `P-6A.2`: Real Search Console API import block.
- `P-6A.3`: Multiple snapshots per client (time-ranged) instead of
  one append-only snapshot.
- `P-6A.4`: Tunable thresholds (`_SEO_LOW_CTR` etc.) surfaced as a
  per-tenant config file.
- `P-6A.5`: LLM-enriched rationale for recommendations (opt-in,
  using the MKT-4B Claude invoker pattern).
- `P-6A.6`: Compare two snapshots / two time ranges and produce a
  delta recommendation pack.
- `P-6A.7`: Cross-link recommendations with the original
  `CampaignStrategyReport` so the analyzer can suggest revisions
  to specific strategy sections.
