# Portal / Landing Roadmap

> Status: **roadmap only** (MKT-1E). No UI exists, no `apps/portal/` folder
> is created in this block.

## What the portal is for

The Portal is the human-facing surface for the agency team and the client:

- Submit / refine the brief.
- See the Approval Center queue.
- Review compliance findings.
- See period reports.
- See the audit trail (filtered, paginated).

This is a separate concern from the agent runtime and the storage layer.
Putting UI inside `core/` would couple the engine to a presentation
choice; we keep it out.

## Where it will live

When implemented, the Portal lives in `apps/portal/` (a subfolder, not a
separate repo) or — if the team prefers — in a sibling repo. The decision
is deferred to whenever the Portal is approved as a block; nothing in v1
forces it.

The Portal will consume the Memory layer through a thin **read-only API**
to be defined when needed (post-MKT-2A). It will NOT bypass the audit
trail: every approval action goes through `approval-manager` so audit
events are emitted.

## Views (informational)

| View | Audience | Reads |
|------|----------|-------|
| Brief intake | Account lead | `kind: brief` |
| Approval queue | Account lead + Client | `kind: approval` |
| Asset review | Account lead + Client | `kind: asset` + linked `claim_audit` snapshot |
| Report viewer | Client | `kind: report` |
| Audit log | Account lead | `audit/` JSONL |
| Backlog | Account lead | `kind: backlog` |

## Public landing (the marketing site for the agency itself)

A separate concern from the client portal. Spec for it is also out of
scope for v1; it lives behind its own roadmap when it gets one.

## Roadmap

| Phase | Goal |
|-------|------|
| **P1 — Read-only portal** (deferred) | Static SSG site that reads `data/clients/<slug>/` and renders Approval queue + Report viewer. No write actions. |
| **P2 — Approval actions** | Approve / reject buttons that POST through the future MKT API and trigger `approval-manager`. |
| **P3 — Brief intake** | Web form that produces a `brief` payload and writes it through the API. |
| **P4 — Per-client subdomains / multi-tenant routing** | Far future. |

## What this block does NOT do

- No `apps/portal/` scaffold.
- No JS / React / Next dep added.
- No API.
- No CSS.

The roadmap exists so subsequent blocks know what they're not blocking.
