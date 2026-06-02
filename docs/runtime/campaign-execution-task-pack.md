# Runtime — Campaign Execution Task Pack (MKT-4E)

Turns a completed campaign (strategy + approval + creative + visual
packs) into an operational task list — Notion-ready, but NOT sent
to Notion. Deterministic, multi-tenant, audit-trail-aware.

- **Module:** `core/execution/`
- **Contract:** `campaign-execution-task-pack.v1` (`core/execution/models.py`)
- **CLI subcommand:** `mkt build-tasks --client <slug>`
- **Memory kind:** `campaign_execution_task_pack` / singleton id `current`

## Usage

```bash
# 1. Build a campaign (or have it already in memory).
mkt run-campaign --intake examples/intake/marketing-agency-os.json

# 2. Generate the task pack.
mkt build-tasks --client marketing-agency-os --outputs-dir outputs/marketing-agency-os
```

Three files are written to `--outputs-dir`:

| File                              | Audience                             |
|-----------------------------------|--------------------------------------|
| `campaign-execution-tasks.md`     | client + internal team (operational) |
| `campaign-execution-tasks.json`   | machine consumers                    |
| `notion-task-payload.json`        | downstream Notion sync tool          |

Stdout prints a small JSON summary (pack_id, counts by state /
priority / category, file paths, blocks_publish flag).

## What goes in the pack

The factory walks the upstream packs and emits tasks in nine
categories:

| Category        | Source                                  | Typical count |
|-----------------|-----------------------------------------|---------------|
| `approval`      | ApprovalPack claims + blocking         | 1–10          |
| `design`        | VisualDirectionPack + image_prompts     | 5–20          |
| `seo`           | suggested_pieces (blog/article)         | 1–5           |
| `email`         | CreativeAssetPack.emails                | 1–6 + setup   |
| `social`        | CreativeAssetPack.social_posts          | 1 per post + 2 ops |
| `publishing`    | one per shippable asset                 | 1 per asset   |
| `measurement`   | primary + secondary KPIs                | 1–4           |
| `operational`   | per-channel setup                       | 1 per channel |
| `calendar`      | one checkpoint per scheduled week       | 4–12          |

Each task carries: title, description, category, priority
(high / medium / low), state, channel, asset_kind, asset_ref,
due_date, depends_on, blocked_reason, owner_hint, notes.

## Blocking semantics

The factory enforces two cardinal rules:

1. **ApprovalPack blocks publish → every `publishing` task is
   emitted with `state="blocked"`** and an explicit
   `blocked_reason`. The upstream QA / approval / design tasks
   stay in `todo` so the operator can resolve the block.

2. **Transitive dependency blocking** — if task B depends on
   task A and A is `blocked`, B inherits `blocked` (with a
   `blocked_reason` that names the upstream blocker). Applied to
   a fixed point so chains propagate correctly.

Example on a risky intake (`product_or_service` contains
"resultados garantizados"):

```
blocks_publish: True
total tasks: 66
blocked tasks: 16
counts by state: {todo: 50, blocked: 16, ...}
blocked categories: {publishing: 16}
```

The 16 `publishing` tasks (one per asset) are all blocked. The
50 `todo` tasks (approval, design, QA, channel setup, calendar,
measurement) remain actionable.

## State machine

```
todo ── ready ── done
 │       ▲
 │       │
 └─ needs_review ── approved ──┘

blocked ← terminal until manually unblocked
```

The factory only emits `todo` or `blocked`. The other states
(`needs_review`, `approved`, `ready`, `done`) are for downstream
tools (Notion, kanban) to move tasks through as humans review and
ship.

## Notion-ready payload

`to_notion_payload(pack)` builds a dict with three top-level keys:

- `schema_version`: `"notion-export.v1"` (separate from the pack
  contract version)
- `source_pack`: pack id, client slug, contract references,
  generation timestamp
- `database`: properties schema (Name, Status, Priority, Category,
  Channel, Asset Kind, Asset Ref, Due Date, Depends On, Owner Hint,
  Description, Blocked Reason, Task ID) with color-coded select
  options for the enums
- `pages`: one entry per task, shaped exactly like Notion's
  `pages.create` properties payload

The renderer does **not** import any Notion SDK. It does **not**
make any HTTP call. A future MKT-* block (or n8n / MCP) can feed
the dict to Notion's API; today the payload is just data on disk.

## Determinism + audit

- Same inputs → same task count, same category distribution, same
  Notion payload shape (modulo fresh `task_id`s and timestamps).
- `mkt build-tasks` records one `note` audit event with payload
  `{"execution_task_pack": {"action": "built", ...}}`. The audit
  hash chain stays valid.
- The pack is persisted to memory under the standard
  `<client>/campaign_execution_task_pack/current.json` path.

## Constraints

- No external services. No Notion API. No n8n. No MCP. No GA4.
  No Google Ads.
- No image generation. No publishing. No email sending.
- No LLM. No prompt construction. The factory is pure Python.
- Backward compatible with every upstream pack — supports running
  with only the strategy report present, even if approval,
  creative or visual are missing.

## Testing

- `tests/execution/test_models.py` — 17 tests, Pydantic validation
  + helper methods.
- `tests/execution/test_task_factory.py` — 11 tests, end-to-end
  against the demo intake including blocking semantics +
  determinism + partial input.
- `tests/execution/test_notion_payload.py` — 11 tests for the
  Notion shape; explicit assertion that no Notion SDK is imported.
- `tests/cli/test_cli_build_tasks.py` — 5 tests for the CLI.

Total new tests: **44**. Full suite: **992 passed**. Ruff: clean.

## Follow-ups (tracked in PENDING.md)

- `P-4E.1`: Visual direction titles read empty because
  `VisualDirection.title` field name may differ — needs
  introspection.
- `P-4E.2`: The Markdown output uses
  `pack.tasks_in_category(...)` ordering which is stable but not
  scheduled-by-date; a date-led view could be useful.
- `P-4E.3`: Notion payload schema_version is hardcoded — should
  live next to the contract pin.
- `P-4E.4`: No per-task SLA / time estimate; would be useful for
  capacity planning.
- `P-4E.5`: No "owner" assignment helper — only `owner_hint` is
  populated.
