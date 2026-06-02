# Runtime — Notion Sync Dry Run (MKT-5A)

Converts a persisted :class:`CampaignExecutionTaskPack` (MKT-4E)
into a Notion sync plan — describes WHAT a future synchroniser
would do, without doing it.

**Cardinal rule: this module never talks to Notion.** No SDK, no
HTTP, no credential, no page creation. The plan is just data and
lives in our own memory + on-disk outputs.

- **Module:** `core/notion_sync/`
- **Contract:** `notion-sync-plan.v1` (`core/notion_sync/models.py`)
- **CLI:** `mkt notion-plan --client <slug>`
- **Memory kind:** `notion_sync_plan` / singleton id `current`

## Usage

```bash
# 1. Have a campaign + task pack (from previous blocks).
mkt run-campaign --intake examples/intake/marketing-agency-os.json
mkt build-tasks  --client marketing-agency-os

# 2. Plan the Notion sync (dry run).
mkt notion-plan  --client marketing-agency-os \
                 --outputs-dir outputs/marketing-agency-os
```

Two files are written:

| File                      | Audience                                 |
|---------------------------|------------------------------------------|
| `notion-sync-plan.md`     | operator review (mappings, records, issues) |
| `notion-sync-plan.json`   | machine consumer (future sync tool)      |

Stdout prints a small JSON summary (plan_id, stats, file paths).

## What the plan contains

1. **Recommended database schema** — title, icon, description, list
   of 13 property mappings, operator notes.
2. **Property mappings** — for each of the 13 Notion properties:
   notion_name, notion_type, source_field, required flag, select
   options (when applicable), per-property notes.
3. **Per-record action plan** — one entry per ExecutionTask with:
   `task_id`, `title`, `action` (`create` / `skip_blocked` /
   `skip_invalid`), proposed status/priority/category,
   `field_count`, optional `reason`.
4. **Validation issues** — typed (`error` / `warning` / `info`),
   each with a stable `code` so a future sync tool can filter
   them. Examples:
   - `value_too_long` (rich_text > 2000 chars)
   - `depends_on_too_long` (joined deps > 2000 chars)
   - `missing_required_field` (empty title)
   - `task_blocked` (INFO; blocked upstream)
   - `empty_pack` (no tasks at all)
5. **Stats** — totals + breakdown by action, by issue severity,
   by category, by priority, by state.

## Property mapping (the 13 columns)

| Notion property   | Notion type | Source field                       | Required |
|-------------------|-------------|------------------------------------|----------|
| Task Name         | `title`     | `title`                            | ✅       |
| Client            | `rich_text` | `pack.client_slug`                 | ✅       |
| Campaign          | `rich_text` | `pack.report_id`                   | ✅       |
| Category          | `select`    | `category` (TaskCategory enum)     | ✅       |
| Channel           | `select`    | `channel` (open options)           | —        |
| Priority          | `select`    | `priority` (high/medium/low)       | ✅       |
| Status            | `select`    | `state` (6 values)                 | ✅       |
| Due Date          | `date`      | `due_date`                         | —        |
| Depends On        | `rich_text` | `depends_on` (joined)              | —        |
| Blocked Reason    | `rich_text` | `blocked_reason`                   | —        |
| Asset Ref         | `rich_text` | `asset_ref`                        | —        |
| Approval State    | `select`    | derived from `upstream_overall_state` | —     |
| Notes             | `rich_text` | `notes + description`              | —        |

The mapping mirrors the spec in the MKT-5A request, pinned by
tests.

## Action semantics

| Action          | When                                                  |
|-----------------|-------------------------------------------------------|
| `create`        | Task is clean — sync would create a page with full props. |
| `skip_blocked`  | Task is `state=blocked` — sync creates the page with `Status=blocked` but MUST NOT auto-advance it. |
| `skip_invalid`  | Task has at least one `error`-severity validation issue — sync skips rather than fail mid-batch. |

Cardinal rule: **`skip_blocked` ≠ "do not create"** — the operator
still wants the blocked task visible in Notion. The label
communicates "do not progress this".

## Notion limits enforced

| Limit                          | Threshold | Severity                   |
|--------------------------------|-----------|----------------------------|
| Title content                  | 2000 chars| `error` → `skip_invalid`   |
| Rich text content per block    | 2000 chars| `error` → `skip_invalid`   |
| `depends_on` joined string     | 2000 chars| `warning`                  |
| Empty title                    | n/a       | `error` → `skip_invalid`   |
| Blocked task                   | n/a       | `info`                     |
| Empty pack                     | n/a       | `info`                     |

## Audit + persistence

- The plan is persisted to memory under
  `<client>/notion_sync_plan/current.json`.
- One `note` audit event is emitted with payload
  `{"notion_sync_plan": {"action": "planned", ...}}`. The hash
  chain remains valid.
- Re-planning overwrites the latest pack but the audit log keeps
  every prior planning event.

## Determinism

Same inputs → same plan structure (modulo fresh `plan_id` +
`created_at`). The property mapping, record actions and stats are
all deterministic. Pinned by `test_two_plans_produce_same_record_count`.

## Constraints

- **No Notion SDK import** — pinned by
  `test_planner_does_not_import_notion_sdk` (rejects `notion_client`,
  `notion`, `requests`, `httpx`).
- No MCP, no n8n, no GA4, no Google Ads, no Search Console.
- No publishing, no email send, no image generation.
- No LLM, no prompt construction, no claim audit override.
- Multi-tenant by construction (slug-scoped memory + outputs).
- Backward compatible: works with any task pack from MKT-4E,
  including risky packs where every publishing task is BLOCKED.

## Smoke verification on real data

`mkt notion-plan --client marketing-agency-os` (dogfood intake):

```
total_tasks: 78
would_create: 78
skip_blocked: 0
skip_invalid: 0
issues_total: 0
```

Risky intake (synthetic "resultados garantizados" claim):

```
total_tasks: 77
would_create: 61
skip_blocked: 16
skip_invalid: 0
issues_info: 16  ← one per blocked task
```

## Follow-ups (PENDING.md → P-5A.*)

- `P-5A.1`: Promote `depends_on` from rich_text to a Notion
  `relation` property pointing at the same database. Requires the
  sync tool to do a two-pass create (pages first, relations
  second).
- `P-5A.2`: Real Notion sync block — consume this plan, call the
  Notion API behind an opt-in flag with the same fallback pattern
  as `--backend claude` (env var + optional extra).
- `P-5A.3`: `Channel` property options are open — first occurrence
  adds the option. Could be pinned by introspecting all channels
  in the strategy report.
- `P-5A.4`: Notes property concatenates description + notes
  blindly. A future revision could split into two rich_text blocks
  to respect the 2000-char-per-block limit explicitly.
- `P-5A.5`: Date-range view for the recommended database (one row
  per scheduled week).
- `P-5A.6`: Per-tenant Notion workspace mapping (database id,
  parent page, icon overrides).
