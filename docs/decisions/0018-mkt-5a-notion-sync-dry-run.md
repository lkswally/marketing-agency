# ADR 0018 — MKT-5A: Notion Sync Dry Run Plan

- **Status:** Accepted
- **Date:** 2026-06-02
- **Block:** MKT-5A
- **Supersedes:** —
- **Contract:** `notion-sync-plan.v1` (new, Pydantic, in
  `core/notion_sync/models.py`).

## Context

MKT-4E shipped the `CampaignExecutionTaskPack` and its
Notion-shaped payload (`to_notion_payload`). What it did NOT do
was reason about WHAT the future synchroniser would actually do:
which tasks would be created, which skipped, which would fail
validation against Notion's per-field limits, and what the
database schema should look like.

MKT-5A adds that planning layer — strictly as a dry run. The
constraint set by the user, repeated three times across the
request: **no real Notion call, no credentials, no MCP write, no
n8n**. The plan is data on disk.

## Decision

### D-18.1 — New module `core/notion_sync/`

Parallel to `core/execution/`. Same conventions: Pydantic models
with `extra="forbid"`, planner class with `plan` + `persist` +
`load_latest`, dedicated renderer, exported through `__init__.py`.
Memory kind: `notion_sync_plan`. Singleton id: `current`.

### D-18.2 — Plan as a versioned artifact

`NotionSyncPlan` is a Pydantic model with its own
`contract_version = "notion-sync-plan.v1"`. The plan carries:

- Source references (`task_pack_id`,
  `task_pack_contract_version`, `notion_payload_schema_version`)
  — every plan must name the snapshot it was built from.
- The recommended database (`NotionRecommendedDatabase`) with
  property mappings.
- The list of `NotionPlannedRecord` (one per task).
- The list of `NotionPlanIssue` (typed `info`/`warning`/`error`,
  each with a stable `code`).
- `NotionSyncStats` aggregating actions + issues + per-pack
  distributions.

The plan is persisted alongside every other pack in the same
JsonFileMemory and emits one `note` audit event per build.

### D-18.3 — 13 mapped properties match the user's spec

`Task Name`, `Client`, `Campaign`, `Category`, `Channel`,
`Priority`, `Status`, `Due Date`, `Depends On`, `Blocked Reason`,
`Asset Ref`, `Approval State`, `Notes`. The mapping is built by
`_build_property_mappings()` and pinned by
`test_recommended_database_has_13_properties`.

Select options for `Status`, `Priority`, `Category` are pulled
from the `TaskState`, `TaskPriority`, `TaskCategory` enums via
list comprehension, so a future enum addition propagates without
manual edits. Pinned by `test_select_options_match_enums`.

### D-18.4 — Three-action vocabulary

`PlannedAction` enumerates exactly three values:

- `create` — clean task; the sync would create a page with the
  full property set.
- `skip_blocked` — task is `state=blocked` upstream. The page
  IS created (with `Status=blocked`) but the sync MUST NOT
  auto-advance it.
- `skip_invalid` — task has at least one `error`-severity
  validation issue. The sync skips it rather than crash the
  batch.

Rejected alternative: a richer state machine with
`create_with_warnings`. The 3-value vocab matches Notion's batch
semantics (each call is independent; the sync tool decides what to
do per page) and keeps the dry-run output narrow.

### D-18.5 — Notion limits enforced as validations

The planner emits `value_too_long` errors when a field exceeds
Notion's documented 2000-char ceilings for title / rich_text /
url. `missing_required_field` for empty titles.
`depends_on_too_long` as a WARNING (not error) because the
mitigation is to promote to a `relation` property, not to truncate.

Notion limits referenced inline: title 2000, rich_text 2000 per
block, url 2000, select option name 100, max 100 properties per
database. The `_SELECT_OPTION_MAX` and `_URL_MAX` constants live
next to the planner for forward use.

### D-18.6 — Blocked tasks are CREATED, not skipped

This is the only counterintuitive decision. The label
`skip_blocked` reads like "do not write" but semantically means
"create the page so the operator sees it in Notion, AND do not
let the sync progress it". The renderer + tests make this
explicit.

Rejected alternative: drop blocked tasks from the create batch.
That would hide the block from the operator's Notion view, which
defeats the purpose of having Notion as the operations dashboard.

### D-18.7 — Pure planner, pure renderer

Both `NotionSyncPlanner.plan()` and `render_markdown_plan()` are
deterministic. The planner takes a `CampaignExecutionTaskPack`
and returns a `NotionSyncPlan`; same inputs → same plan
(modulo fresh ids + timestamps). The renderer is byte-pure over
the plan.

`plan()` itself does NOT persist. `persist()` is a separate call
that also emits the audit event. The CLI calls both; tests can
verify pure behaviour separately.

### D-18.8 — Hard guarantee: no Notion SDK

The module file `core/notion_sync/planner.py` is pinned by
`test_planner_does_not_import_notion_sdk` to never reference
`notion_client`, `notion`, `requests`, or `httpx`. The same
guarantee already exists for the MKT-4E `to_notion_payload`
renderer; together they form a "Notion-aware but Notion-free"
boundary.

A future block (P-5A.2) can add the SDK behind an opt-in extra
(same pattern as `--backend claude` and the `anthropic` extra in
MKT-4B) without touching this module.

### D-18.9 — CLI `mkt notion-plan` follows the standard shape

Subcommand args: `--client` (required), `--root`, `--outputs-dir`.
Exit codes: 0 ok, 2 when no task pack exists for the client.
Outputs: `notion-sync-plan.md` + `notion-sync-plan.json` + one
audit event. Matches the conventions of `build-tasks`,
`build-creatives`, `build-visuals`.

### D-18.10 — Property mappings carry source field as a string

`NotionPropertyMapping.source_field` is a free-form string (e.g.
`"title"`, `"pack.client_slug"`, `"(derived: pack.upstream_overall_state)"`).
Rejected alternative: an enum of source field references.

The string form lets the planner document derived / computed
fields (`"notes + description"`) without forcing every mapping
into a strict reference syntax. The future real sync tool can
parse the string with its own heuristics.

## Consequences

### Positive

- One command takes a task pack to "ready-to-import Notion plan
  with explicit error and blocked tracking". Deterministic, 0
  external calls, 0 credentials.
- The plan stays usable by any sync transport — Notion SDK direct,
  Notion MCP, n8n, Make. The factory has zero opinion about which.
- Operators can review the plan locally before any production
  Notion workspace is touched.
- Forward-compatible: every prefix (mapping, options, source
  fields) is set up so the future synchroniser is a thin layer
  over this plan.

### Negative / accepted trade-offs

- `depends_on` is a rich_text string today; a real sync would
  prefer a `relation` property. Tracked as P-5A.1.
- `Channel` select options are NOT pre-pinned because real
  intakes may declare arbitrary channels. The sync tool will
  need to add options on first occurrence. Tracked as P-5A.3.
- The plan overwrites on re-build. Historical plans are only
  visible via the audit trail.
- The Markdown renderer doesn't link tasks to their source assets
  via Notion page links — there are no page ids yet.

## Out of scope (explicit)

- Real Notion API call (P-5A.2).
- Notion MCP (write).
- n8n integration.
- GA4 / Ads / Search Console.
- Publishing, email send, image generation.
- Credentials of any kind. No `NOTION_TOKEN` env var read.
- Database creation in any real workspace.

## Validation

- 44 new tests (`tests/notion_sync/*` + `tests/cli/test_cli_notion_plan.py`).
- Full suite: **1036 passed**.
- Ruff: clean.
- ATLAS core: untouched.
- Smoke verified on dogfood intake: 78/78 tasks → `create`, 0
  issues. Risky intake: 61 `create` + 16 `skip_blocked`, 16
  `task_blocked` info issues.

## Related

- Depends on MKT-4E (`CampaignExecutionTaskPack`,
  `to_notion_payload`).
- Future work tracked as `P-5A.*` in `PENDING.md`.
- Future real sync block (P-5A.2 / future MKT-5B) will consume
  the persisted plan and call Notion behind an opt-in flag.
- Runtime doc: `docs/runtime/notion-sync-dry-run.md`.
