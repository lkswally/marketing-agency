# ADR 0017 — MKT-4E: Campaign Execution Task Pack

- **Status:** Accepted
- **Date:** 2026-06-02
- **Block:** MKT-4E
- **Supersedes:** —
- **Contract:** `campaign-execution-task-pack.v1` (new, Pydantic,
  in `core/execution/models.py`).

## Context

After MKT-3F (orchestrator), MKT-4A (Claude scaffolding), MKT-4B
(Anthropic SDK invoker), MKT-4C (real-campaign QA) and MKT-4D
(template content quality), the system produces a complete
campaign — strategy + claim audit + approval + creative + visual.

What it did NOT produce was the **operational plan**: the list of
tasks an agency uses to actually ship the campaign — per-asset
QA, per-channel setup, per-piece publishing, calendar
checkpoints, measurement specs.

Agencies typically build this list manually in Notion / Linear /
Asana. MKT-4E generates it deterministically from the existing
packs, ready to import.

The cardinal constraint, set by the user: **build the list, do not
execute it.** No Notion API call. No publishing. No email send.
No GA4. The pack is data; downstream tools act.

## Decision

### D-17.1 — New module `core/execution/`

Parallel to `core/creative/` and `core/visual/`. Same conventions:
Pydantic models with `extra="forbid"`, factory class with
`build` + `persist` + `load_latest`, dedicated renderer, exported
through `__init__.py`. Memory kind:
`campaign_execution_task_pack`. Singleton id: `current`.

### D-17.2 — `ExecutionTask` is the unit of work

A single Pydantic model captures every kind of task. Fields:

- Identity: `task_id`, `title`, `description`, `notes`.
- Routing: `category` (9 values), `priority` (3 values), `state`
  (6 values), `channel`, `asset_kind`, `asset_ref`, `owner_hint`.
- Scheduling: `due_date`, `depends_on[]`, `blocked_reason`.

Rejected alternative: one Pydantic class per category (one for
`PublishTask`, one for `QATask`, etc.). Too much ceremony for a
~200-line factory; the discriminator (`category`) already covers
the routing.

### D-17.3 — State machine

```
todo → ready → done
 │      ▲
 │      │
 └─ needs_review → approved → ┘

blocked (terminal until manually moved)
```

The factory only emits `todo` or `blocked`. The other four states
are downstream-tool concerns (Notion column, kanban swimlane).
Mirroring them in the contract makes the Notion payload a clean
mapping.

### D-17.4 — Two cardinal blocking rules

Both enforced in the factory, both verified by tests:

1. **ApprovalPack.blocks_publish OR any CreativeAssetState.BLOCKED
   → every `publishing`-category task is BLOCKED** with an
   explicit `blocked_reason`. This is the safety floor: nothing
   that involves shipping a piece can be `todo` while the upstream
   pack is blocking.
2. **Transitive blocking** — `_propagate_blocking` walks the
   dependency graph to a fixed point. If `B.depends_on = [A]` and
   `A.state = BLOCKED`, then `B.state = BLOCKED` too with a
   `blocked_reason` naming `A`.

Cycles are impossible by construction: the factory builds the
dependency graph top-down (approval tasks → QA tasks → publish
tasks; channel setup tasks → email/social setup tasks).

### D-17.5 — Notion payload as data, not an API call

`to_notion_payload(pack) -> dict` is a pure function. It builds
the dict in the shape Notion's `databases.create` +
`pages.create` endpoints expect, including the colored select
options for Status / Priority / Category. The module does NOT
import any Notion SDK. A test asserts this invariant.

The dict has its own `schema_version` (`notion-export.v1`)
independent from the pack contract version, so we can evolve the
Notion shape (e.g. switch to multi-select for Category, or add a
Files property) without bumping the pack contract.

Rejected alternative: ship a `core/execution/notion_sync.py` that
calls Notion directly. Out of scope; would import `notion-client`
and require an API key — and the user explicitly said "no Notion
real" in this block.

### D-17.6 — Markdown renderer for the operator

`render_markdown_pack(pack) -> str` is pure. It writes one
section per category (in a fixed order), with a table per
section that lists tasks sorted as: BLOCKED first (loud), then
by priority (HIGH→LOW), then by title (stability). Each
category section appends a "Bloqueos" callout for the blocked
tasks and a "Dependencias" list for tasks with `depends_on`.

This document is for the client/team review — the JSON pack and
the Notion payload are for tooling.

### D-17.7 — Three priority levels (HIGH / MEDIUM / LOW)

Picked over a numeric scale to keep the operator focus on a small
ranking. The factory assigns:

- HIGH: tasks that gate the launch (approval items at
  blocker/high/unsafe/risky severity, the "approve visual
  direction" gate, the "resolve approval-pack block" task).
- MEDIUM: per-channel setup, per-piece QA, ESP setup, KPI spec.
- LOW: calendar weekly checkpoints, hashtag review, secondary
  KPI specs.

### D-17.8 — Owner hints, not assignments

Every task carries an `owner_hint` (`"copywriter"`,
`"account_lead"`, `"creative_director"`, `"compliance_lead"`,
`"email_specialist"`, `"seo_specialist"`, `"analytics_lead"`,
`"designer"`). Never a real person. The downstream sync tool /
human assigns the actual owner.

### D-17.9 — Calendar tasks from CampaignSchedule

One task per scheduled week, dated to `schedule.start_date +
(week - 1) * 7d`. Title: `"Checkpoint semana N: revisar piezas
planeadas"`. Priority LOW, owner_hint `account_lead`. Gives the
operator a fixed cadence of review without auto-generating one
task per scheduled piece (which would explode the list).

### D-17.10 — Pack is persisted via the standard memory layer

Same JsonFileMemory + audit trail as every other pack. The CLI
emits a `note` event with payload
`{"execution_task_pack": {"action": "built", ...}}`. Hash chain
preserved. Pack overwrites on re-build but the audit log keeps
the history.

## Consequences

### Positive

- One command takes a campaign from "all the deliverables exist"
  to "operational task list with dependencies, priorities and
  blocking semantics", in 1 second, deterministic, 0 LLM calls,
  0 external services.
- The Notion payload is just data, so it can be imported with
  any tool (the official Notion SDK, n8n, Make, a one-off
  Python script). The factory has zero opinion about the sync
  mechanism.
- Multi-tenant by construction — slug-scoped memory + slug-scoped
  outputs directory.
- Audit trail integration means a re-build is observable; the
  blocking semantics surface in both the persisted pack and the
  audit events.

### Negative / accepted trade-offs

- The factory doesn't know about specific tools (Buffer, Hootsuite,
  Mailchimp, GA4). Tasks reference categories and channels; the
  operator fills in tooling.
- No effort estimate or SLA per task. Adding it later is additive
  (P-4E.4).
- The Markdown view is category-led, not date-led. A date-led
  view would be useful for weekly stand-ups (P-4E.2).
- `VisualDirection.title` rendering shows empty for a few
  directions because the upstream model uses different field
  names in some cases. Needs introspection (P-4E.1).
- Pack overwrites on re-build. Historical task pack states are
  only visible via the audit trail (same trade-off as every
  other pack).

## Out of scope (explicit)

- No Notion API call.
- No n8n integration.
- No MCP.
- No GA4 / Google Ads / Search Console.
- No publishing, no email sending, no image generation.
- No external HTTP at all (the notion_payload module is
  test-pinned to not import any SDK).
- No automatic task ordering inside a category beyond the
  blocked-first + priority + title sort.

## Validation

- 44 new tests (`tests/execution/*` + `tests/cli/test_cli_build_tasks.py`).
- Full suite: **992 passed**.
- Ruff: clean.
- ATLAS core: untouched.
- Smoke verified: dogfood intake produces 78 tasks (1 high, 61
  medium, 16 low) across 8 categories; risky intake produces 66
  tasks with 16 in BLOCKED state (all `publishing`).

## Related

- Depends on MKT-3A (strategy report), MKT-3B (approval pack),
  MKT-3C (creative pack), MKT-3D (visual pack), MKT-1D (memory).
- Future work tracked as `P-4E.*` in `PENDING.md`.
- Future Notion sync block will consume `to_notion_payload(pack)`.
- Runtime doc: `docs/runtime/campaign-execution-task-pack.md`.
