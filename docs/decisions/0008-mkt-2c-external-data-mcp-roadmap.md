# ADR 0008 — MKT-2C: External Data & MCP Roadmap

- **Status:** Accepted
- **Date:** 2026-05-29
- **Block:** MKT-2C
- **Supersedes:** —
- **Contracts:** none introduced in code; conceptual contracts
  (`ExternalDataSource`, `MCPToolRef`, `ReadOnlyMetricQuery`,
  `ExternalInsight`, `DataPermissionPolicy`, `MarketingRecommendation`,
  `ProposedAction`) are documented in `external-data-sources.md` and
  `permissions-policy.md`. Promotion to Pydantic is deferred to the block
  that ships the first adapter.

## Context

MKT-1B–2B delivered a self-contained, mock-only system: domain model,
operational contracts, storage, dispatcher, agent specs, agent backend
interface. Useful for analysis on data that exists; useless for an agency
that needs GA4, Google Ads, Search Console, etc.

Before any of that lands, the integration shape must be settled. This
block answers: which sources, which phases, which permissions, how MCP
plugs in, where credentials live, what stays out of scope forever.

The block produces ONLY documentation. No code, no MCP connection, no
credentials.

## Decision

### D-8.1 — Read-only first, always

Every new external source MUST start in `mode: read_only`. Write
capability requires a dedicated ADR per source AND per write operation,
with explicit human approval at execution time. There is no "general
write mode".

### D-8.2 — MCP is transport, not policy

Connecting an MCP server does NOT authorize its capabilities. The
adapter is bound by `DataPermissionPolicy` evaluated at every call.
An MCP that exposes 30 tools but is configured with 5 allowed reads
exposes 5 reads.

### D-8.3 — Default deny

Any tool name not in `allowed_reads` or `allowed_writes` is rejected
even when the MCP exposes it. `on_unknown_tool` defaults to
`fail_closed_audit`. There is no catch-all.

### D-8.4 — `ProposedAction` ≠ execution

An agent (or human) can propose an action; only Approval Center can
transition it to `EXECUTED`. The two states are kept distinct in the
data model so the audit trail records both the proposal and the
execution separately.

### D-8.5 — Mapping to existing domain entities, no new kinds

External reads produce `Metric` and (optionally)
`DigitalFootprintSnapshot` entities — both already in `core.domain`
(MKT-1B). No new domain entity is added per source. This keeps the
domain model stable across the integration arc.

### D-8.6 — Four promotion phases per MCP: R1 → R2 → R3 → R4

| Phase | Meaning |
|-------|---------|
| R1 | Spec only (this block does R1 for all 7 priority sources). |
| R2 | Read-only manual — humans enter data as `Metric` with `source=MANUAL`/`INTERNAL_REPORT`. |
| R3 | Read-only programmatic — first real MCP connection. |
| R4 | Write with explicit approval — opens only per source on its own ADR. |

Skipping a phase requires its own ADR. (The MKT-MCP-1 through
MKT-MCP-8 milestones in `mcp-roadmap.md` are the implementation
schedule; R1–R4 are the permission posture per source. They map
roughly 1:1 but the vocabulary is intentionally distinct.)

### D-8.7 — Google Ads is the highest-risk source

Reads are valuable; writes are spend events. Default posture is
read-only forever. If a future ADR opens R4 for Google Ads, it MUST
include:

- Enumerated allowed `mutate` tools.
- Double approval (account lead + client side).
- Per-call caps on budget delta.
- One-click revert.
- Permanent forbidden list (account / billing / conversion settings).

Until that ADR exists, every Google-Ads `mutate*` tool is rejected.

### D-8.8 — n8n is the execution layer of choice

When an approved `ProposedAction` requires hitting an external API to
mutate state, the chosen execution path is **a signed trigger to an
enumerated n8n workflow**, not a direct call from `core/`. This:

- Keeps third-party credentials out of MKT.
- Reuses n8n's mature retry / queue / scheduling infra.
- Leaves a clean cross-system audit (MKT proposes + approves; n8n
  executes + acks).

The n8n workflow registry is finite and enumerated; MKT does not
trigger arbitrary workflow names.

### D-8.9 — Credentials live outside MKT

No secret value appears in:

- Specs (workflow, agent, skill).
- Configs (any YAML in the repo).
- Envelopes.
- Audit payloads.
- Test fixtures.

Specs reference credentials by env-var name only (`env(GA4_SERVICE_ACCOUNT_JSON)`).
Resolution happens at call site, in the adapter or the MCP server.

### D-8.10 — Conceptual contracts are NOT promoted to Pydantic in MKT-2C

`ExternalDataSource`, `MCPToolRef`, `ReadOnlyMetricQuery`,
`ExternalInsight`, `DataPermissionPolicy`, `MarketingRecommendation`,
`ProposedAction` are documented as YAML sketches. Promotion to
Pydantic models lives in the block that ships the first adapter
(MKT-MCP-2 in `mcp-roadmap.md` terms). This matches the MKT-1E pattern
(specs as docs first, contracts later).

### D-8.11 — Audit additions are reserved, not implemented

Every external integration will need new audit event types
(`external_fetch`, `external_fetch_failed`, `proposed_action_*`,
`n8n_trigger_*`, etc.). These are listed in `permissions-policy.md`
§6 and `n8n-execution-roadmap.md` §6 so the implementing block has a
ready inventory. They are additive to `audit-trail.v1`.

### D-8.12 — `mcp-roadmap.md` is the canonical phasing document

A detailed `mcp-roadmap.md` (304 lines, MKT-MCP-1..8 phasing, 7-filter
evaluation criteria, explicit forbidden lists) already existed in the
repo at the start of MKT-2C. Rather than overwrite it, MKT-2C keeps it
as the canonical phasing source and complements it with seven new docs:
this ADR, `external-data-sources.md`, `permissions-policy.md`, and the
four source-specific roadmaps (GA4, Ads, GSC, n8n execution). All new
docs reference `mcp-roadmap.md` for the phasing schedule.

## Alternatives considered

- **Open a write phase immediately.** Rejected — D-8.1 is the entire
  point. The system has no way to recover from a wrong write without
  human approval today, and we don't ship hope.
- **Use a single "marketing MCP" that aggregates multiple sources.**
  Rejected — blast radius of one credential becomes the sum of the
  blast radii of every wrapped source. Single-source MCPs preserve
  isolation.
- **Promote conceptual contracts to Pydantic now.** Rejected (D-8.10).
  The right shape will reveal itself when the first adapter consumes
  them.
- **Hardcode credentials in per-client config files inside the repo
  with `.gitignore` shielding.** Rejected — `.gitignore` is a tripwire,
  not a guarantee. Credentials live elsewhere, period.
- **Let MKT call n8n's HTTP API directly with a single global token.**
  Rejected — same blast-radius argument. Triggers go to enumerated
  workflows via signed payloads.

## Consequences

- The integration arc has an unambiguous reference. The block that
  ships GA4 can quote this ADR and `google-analytics-roadmap.md` instead
  of relitigating the shape.
- Compliance review can audit `permissions-policy.md` once and trust
  the per-source roadmaps to instantiate it correctly.
- Approval Center work (P-1E.5) can now refer to `ProposedAction` as a
  defined concept.
- The first adapter block will be lighter than it would otherwise have
  been — only the code, not the policy.

## Out of scope for MKT-2C

- Any adapter (`integrations/*_adapter.py`).
- Any MCP server import or invocation.
- Any credential setup, OAuth flow, service-account configuration.
- Any audit event implementation.
- Any new `MetricSource` enum value.
- Any `ProposedAction` entity in `core.domain`.
- The n8n workflow registry as a versioned YAML.
- The n8n trigger signing implementation.
- Any test of an external surface.
- Decisions about caching, multi-property reconciliation, attribution
  windows, signing key rotation.

These are the dependencies of the next blocks, not of MKT-2C.
