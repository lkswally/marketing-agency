# MCP Integration Roadmap

> Status: **roadmap only**. No MCP connection exists today; no credentials
> are stored; nothing in `core/` imports an MCP client. Implementation is
> deferred until **post MKT-2C** at the earliest.

## Why this document exists

MARKETING-AGENCY-OS is the strategic brain. To do its job properly
(analyze, report, optimize, recommend) it eventually needs to read real
marketing data: traffic, conversions, ad spend, keywords, SEO position,
inbox stats. The natural way to do that without hand-rolling 8 SDK clients
is through MCP (Model Context Protocol) servers that already exist.

This roadmap documents which MCPs we plan to integrate, in what order, with
what permissions, and what we explicitly will NOT do in the first phase.

The roadmap exists so that later blocks know what shape to land in.

## Hard rules (apply to every MCP, every phase)

These are non-negotiable. Any MCP that cannot meet them is rejected.

| Rule | Why |
|------|-----|
| **Phase 1 is read-only** | A failed read is recoverable; a wrong write is not. No `mutate / create / delete / send` calls until Phase 8 with explicit human approval. |
| **No credentials in repo** | Tokens, refresh tokens, service-account JSONs live in env vars or in the MCP server's own credential store. Never in git. |
| **No hardcoded sensitive URLs** | Account IDs, property IDs, customer IDs come from env or per-client config in `data/clients/<id>/`, never inline. |
| **Granular scopes** | When an MCP supports OAuth scopes, request the narrowest possible (e.g. `analytics.readonly`, not `analytics`). |
| **Fail-open** | If the MCP is unreachable, MKT degrades to whatever Metrics it already has in memory; it does NOT block workflows. |
| **Approval before connection** | Before any MCP is enabled in a live environment, the user sees: read/write status, scopes, data accessible, actions executable. Approval is explicit. |
| **Audit trail** | Every MCP call emits an `audit-trail.v1` event with source, query, byte count, and (later) approval reference. |

## Architecture role

```
MARKETING-AGENCY-OS  =  strategic brain
        ↓
   Metric / DigitalFootprintSnapshot  (domain entities — MKT-1B)
        ↑
   ExternalDataSource / MCPToolRef / ReadOnlyMetricQuery / MCPInsight
        ↑
   MCP servers  (external read-only data sources, Phase 1)
        ↓
   n8n  (execution layer, Phase 8+, never as primary MCP)
        ↓
   user  (approves write actions)
```

MKT does NOT execute campaigns. MKT recommends, the user approves, n8n (or
direct platform actions with human in loop) executes.

## Priority MCPs

The user-prioritized list, evaluated honestly. "Stable" means actively
maintained with public source, recent releases, and a community presence.
"Unstable" means single-author repo with no recent commits or unclear
governance.

### Priority 1 — Read-only data sources for Phase 1

| # | MCP | Maturity (as of now) | Read-only feasible? | Phase | Notes |
|---|-----|---------------------|---------------------|-------|-------|
| 1 | **GA4 (Google Analytics 4)** | Multiple options exist; official Google MCP not yet public, community implementations available | ✅ via `analytics.readonly` scope or service-account with `Viewer` role | MKT-MCP-3 | Highest signal-to-effort. Read traffic, conversions, audience, retention. |
| 2 | **Google Ads** | Community MCPs exist; Google Ads API itself supports `read` scope | ✅ via `adwords` scope without `mutate` permission | MKT-MCP-4 | Critical for campaign analysis. **Strict no-mutate gate.** |
| 3 | **Google Search Console** | Community MCPs exist; GSC API has clear read-only scope | ✅ via `webmasters.readonly` | MKT-MCP-5 | SEO position, queries, click-through rate, impressions. |
| 4 | **Google Drive / Sheets** | Multiple stable MCPs; official-ish via gdrive packages | ✅ via `drive.readonly` + `spreadsheets.readonly` | MKT-MCP-3 (parallel) | Reports, calendars, asset metadata. Write to Sheets ONLY in Phase 8 with approval. |
| 5 | **Gmail / Email drafts** | Multiple Gmail MCPs exist | ⚠️ partial — read drafts is read-only; create-draft is write but recoverable (drafts are not sent) | MKT-MCP-7 onwards | First phase: read inbox stats and existing drafts. Create-draft requires explicit per-action approval. **No send.** |
| 6 | **YouTube / Social analytics** | YouTube Data API has stable MCPs; other socials (Meta, LinkedIn) less mature | ✅ for YouTube; mixed for others | post MKT-MCP-5 | Evaluate per-platform. Skip platforms without granular read-only scopes. |
| 7 | **n8n** | n8n itself is mature; "n8n as MCP" varies | N/A — n8n is the EXECUTION layer, not a primary data MCP | MKT-MCP-8 | See `n8n-automation-roadmap.md`. n8n is the controlled action layer, NOT a data source. |

### Priority 2 — Additional MCPs to evaluate

These were NOT in the user's initial list but are worth checking against
the 7 evaluation criteria when Phase 1 lands. Listed for transparency, not
yet endorsed.

| MCP | Use case | Eval criteria status (preliminary) |
|-----|----------|-----------------------------------|
| Plausible / Fathom analytics MCP | Privacy-first analytics alternative to GA4 | Only if client uses these. Otherwise skip. |
| Resend MCP | Email broadcast metrics (open / click / bounce) | Already planned in `analytics-roadmap.md` `EMAIL` source. Read-only is achievable. Worth integrating in MKT-MCP-7. |
| Slack MCP (read-only) | Read team channel mentions of campaign performance | Marginal. Skip unless explicit need. |
| Stripe MCP (read-only) | Revenue attribution to campaigns | High value but high sensitivity. Defer to post MKT-MCP-5 and only with strict scoping. |
| Notion / Airtable MCP | If client uses these as their campaign tracker | Defer — only integrate when a specific client needs it. |
| Brave Search / Perplexity MCP | Research, competitor analysis | Already discussed in ATLAS context (deferred there too). Re-evaluate post Phase 5. |
| Firecrawl MCP | Competitor footprint extraction (public surface only) | Worth integrating in `PUBLIC_FOOTPRINT` source path (analytics-roadmap). Defer to post MKT-MCP-5. |

## Evaluation criteria (the 7 filters, formalized)

Before any MCP graduates from "evaluation" to "integration", it must pass
all 7 filters. A single fail means deferral or rejection.

1. **Active maintenance** — commits within the last 90 days, open issues
   getting responses, declared maintainer.
2. **Clear documentation** — auth flow, scopes, tool list, example calls
   all documented.
3. **Granular permissions** — supports a read-only scope distinct from
   write. An MCP that only offers full account access is rejected for
   Phase 1.
4. **Read-only operation possible** — the MCP can be configured to refuse
   write tool calls, OR we wrap it in a `ReadOnlyMetricQuery` adapter that
   filters tool names client-side.
5. **No credentials in repo** — supports env-var-based auth or a
   credential file outside the repo.
6. **Low operational risk** — incidents involving the MCP's vendor are
   public knowledge; no recent security advisories unaddressed.
7. **Direct utility** — produces data or actions that map to one of: GA4
   traffic, Google Ads campaigns, Search Console SEO, asset storage,
   email metrics, social analytics. Tangentially-useful MCPs are
   deferred.

## Permissions plan template

Before connecting any MCP in a real environment, MKT presents this to the
user and waits for approval. Implementation deferred to MKT-MCP-1.

```
MCP: <name>
Version: <repo + commit>
Operation mode: READ-ONLY | READ + WRITE (per-action approval)

Scopes requested:
  - <scope-1>  (purpose: <what data this unlocks>)
  - <scope-2>  ...

Data this MCP can read:
  - <category>: <example fields>
  - ...

Actions this MCP can execute (if any):
  - <action>: <what it does> [REQUIRES PER-CALL APPROVAL]
  - ...

Credentials source: env(<VAR_NAME>) | external file: <path outside repo>

Audit policy: every call emits audit-trail.v1 event with
  source=mcp:<name>, query=<sanitized>, byte_count=<n>

Approval required: YES / NO
User confirmation: ____________
```

## Phases (none implemented today)

### MKT-MCP-1 — MCP registry + permissions schema (DOCUMENTATION ONLY)

- Document the MCP registry format: which MCPs MKT knows about, their
  status (planned / evaluating / approved / live / deprecated), and their
  permissions plan template.
- Define `docs/mcp-registry.md` (will be a new doc, separate from this
  roadmap) listing every MCP MKT will ever consider, with the 7-filter
  evaluation status.
- No code. No SDK imports. Outcome: the registry exists as a doc, future
  blocks know where to add entries.
- Prerequisite: post MKT-2C (we need the contracts layer ready first).

### MKT-MCP-2 — Domain contracts for external data

Adds these contracts to `core/domain/` (specs, not implementations):

- `ExternalDataSource` — a value object describing an MCP source: name,
  version, operation mode (`read_only` | `write_with_approval`), scopes
  granted, credential reference (env var name only — never the value).
- `MCPToolRef` — a value object: `(mcp_name, tool_name)`. Used in audit
  events.
- `ReadOnlyMetricQuery` — a contract: a query that can only produce
  `Metric` entities, never mutate state. Includes guard methods that
  reject queries containing write verbs in tool names.
- `MCPInsight` — a contract: the structured output an MCP-backed agent
  produces from a query. References its source `Metric` ids.

No connector code. No HTTP. No SDK. Pure Pydantic contracts + tests.

### MKT-MCP-3 — GA4 read-only integration

- First real MCP. Uses an evaluated and approved community GA4 MCP.
- New module `integrations/ga4_adapter.py` that wraps the MCP and produces
  `Metric` entities with `source=GA4`, `is_estimate=false`,
  `confidence=1.0`.
- Strictly `analytics.readonly`. No event-mutation. No property-mutation.
- Audit: every read produces an `mcp.read` event.
- Fails open: missing credential → warning + empty list, workflow continues.
- Parallel scope: Google Drive / Sheets read-only for report fetching.

### MKT-MCP-4 — Google Ads read-only

- Same shape as MKT-MCP-3, but with Google Ads.
- Strict no-mutate gate: the adapter rejects any tool name containing
  `create`, `update`, `delete`, `pause`, `resume`, `mutate`, `add`,
  `remove`. Even if the MCP exposes them, the adapter filters them out.
- Produces `Metric` with `source=GOOGLE_ADS` (new enum value) — requires
  domain model bump, tracked separately.

### MKT-MCP-5 — Search Console + SEO data

- Same shape, Search Console first.
- Read queries, impressions, CTR, position by page.
- Produces `Metric` with `source=SEARCH_SEO`.

### MKT-MCP-6 — Automated reporting

- `analytics-agent` (already specced in MKT-1E) becomes "live": it now has
  real Metrics from MCP sources and emits monthly reports.
- New skill: `mcp-report-generator` that fans out queries to every active
  `ExternalDataSource` and produces a unified `MCPInsight`.
- Output: a versioned `report.v1` memory entity. Still no actions.

### MKT-MCP-7 — Actionable recommendations (still read-only on the MCP side)

- `optimizer-agent` consumes `MCPInsight`s and produces structured
  recommendations: "campaign X has CPA 3x the account average — recommend
  pausing or reducing budget by Y%."
- Recommendations are recorded as `recommendation.v1` entities. They are
  NOT executed automatically.
- Gmail MCP integration (read-only) lands here: read existing drafts +
  inbox stats; do not create drafts yet.

### MKT-MCP-8 — Approved actions via n8n / action layer

- The first write surface. Recommendations from MKT-MCP-7 can be queued
  for execution via n8n workflows (per `n8n-automation-roadmap.md` D-5.4
  decision).
- Per-action human approval is mandatory. Approval lives in MKT's
  `approval-center` (see `docs/approval-center.md`).
- Gmail draft creation, ad budget changes, keyword additions, all go
  through this gate.
- This is the only phase where MKT participates in mutating external
  state, and even then indirectly.

## Forbidden in Phase 1 (MKT-MCP-1 through MKT-MCP-7)

Explicit list. If any of these are attempted, the adapter must raise.

- Pausing or resuming campaigns
- Changing budgets
- Creating ads, ad groups, or campaigns
- Deleting any object
- Adding or removing keywords (including negative keywords)
- Sending emails (Gmail send, ESP broadcasts)
- Publishing posts (social, blog)
- Modifying account settings, conversion settings, audiences
- Storing any credential in the repo
- Hardcoding tokens, customer IDs, property IDs, or account URLs

Allowed in Phase 1:

- Reading metrics
- Generating reports
- Detecting opportunities
- Drafting recommendations (as memory entities, not actions)
- Preparing data for human review

## Relation to ATLAS

ATLAS has its own MCP evaluation (see `bloque-1L` ATLAS analysis: Firecrawl
deferred, Perplexity postponed, Playwright integrated, Glif discarded,
Chrome DevTools postponed). MARKETING-AGENCY-OS MCP roadmap is independent:

- ATLAS MCPs serve the **development** pipeline (research, browser QA,
  scraping for reference extraction during design).
- MKT MCPs serve the **marketing analysis** pipeline (read campaign /
  traffic / SEO data, produce reports).
- Overlap: Firecrawl could be useful in both worlds. If ATLAS integrates
  it first, MKT can reuse the same adapter pattern (not the same binary).

See `docs/relation-to-atlas.md` for the broader boundary.

## What this roadmap does NOT do

- No code.
- No MCP connection.
- No credential setup.
- No registry implementation.
- No domain contract additions.
- No `Metric` enum bumps.
- No promise that any specific MCP will be integrated. Each must pass the
  7-filter evaluation at the time of its phase.

The roadmap exists so that when the marketing analysis blocks land
(post MKT-2C), the shape is already agreed.

## Open questions (for future ADRs)

- Should `ReadOnlyMetricQuery` be enforced at the contract level (reject
  at construction) or at the adapter boundary (reject at call site)? Both
  has been considered; deferred to MKT-MCP-2 implementation.
- Per-client vs global MCP config? GA4 properties are per-client, OAuth
  tokens may be shared (agency-wide) or per-client (client-managed).
  Defer to ADR when MKT-MCP-3 lands.
- Caching: do we cache MCP reads locally? Trade-off between cost (API
  quota) and freshness (stale metrics). Defer.
- Multi-tenancy: can the same MCP serve multiple agency clients in the
  same MKT instance, or does each client need a separate adapter
  instance? Defer.

## References

- `analytics-roadmap.md` — the `Metric` source enum and per-source landing
  plan (MCP-MKT-3/4/5 produce data into this model).
- `n8n-automation-roadmap.md` — D-5.4 boundary: MKT plans, n8n executes.
  MKT-MCP-8 is where the bridge lands.
- `relation-to-atlas.md` — ATLAS / MKT boundary.
- `approval-center.md` — where Phase 8 write approvals are recorded.
- `PENDING.md` — MKT-MCP-1 through MKT-MCP-8 entries.
