# Runtime — Notion Sync Writer (MKT-5B)

The MKT-5B writer is the opt-in counterpart to the MKT-5A dry-run
plan. It actually creates pages in a Notion database — but ONLY
when the operator explicitly opts in with `--write --confirm` AND
both env vars are set AND the SDK is installed AND the plan has
no ERROR-severity issues.

In every other case the executor falls back to dry-run with a
clear stderr warning. The default behaviour without any flag is
identical to MKT-5A: zero Notion calls.

- **Modules:** `core/notion_sync/writer.py`,
  `core/notion_sync/executor.py`, `core/notion_sync/sync_report.py`,
  `core/notion_sync/sync_renderer.py`
- **Contract:** `notion-sync-report.v1`
- **CLI:** `mkt notion-sync --client <slug> [--dry-run | --write --confirm]`
- **Memory kinds:**
  `notion_sync_report` (latest report),
  `notion_synced_pages` (idempotency index of task_id → page_id)

## Quick start

```bash
# Optional: install the Notion SDK only when you actually need it.
pip install -e .[notion]

# Required env vars for real writes.
export NOTION_TOKEN="secret_..."
export NOTION_TASKS_DATABASE_ID="abcd1234..."

# Pre-requisites: a campaign with a task pack + sync plan.
mkt run-campaign --intake examples/intake/marketing-agency-os.json
mkt build-tasks  --client marketing-agency-os
mkt notion-plan  --client marketing-agency-os

# Dry-run (default).
mkt notion-sync  --client marketing-agency-os

# Real write — requires BOTH --write AND --confirm.
mkt notion-sync  --client marketing-agency-os --write --confirm
```

## CLI safety gates

| Invocation                                  | Behaviour | Exit |
|---------------------------------------------|-----------|------|
| no flags                                    | dry-run   | 0    |
| `--dry-run`                                 | dry-run   | 0    |
| `--write` (no `--confirm`)                  | error, no writes | 3 |
| `--write --confirm`, missing `NOTION_TOKEN` | warning to stderr, dry-run | 0 |
| `--write --confirm`, missing `NOTION_TASKS_DATABASE_ID` | warning to stderr, dry-run | 0 |
| `--write --confirm`, SDK missing            | warning to stderr, dry-run | 0 |
| `--write --confirm`, plan has ERROR issues  | dry-run with `write_blocked_reason` | 0 |
| `--write --confirm`, everything in place    | real write | 0 |

The CLI prints a small JSON summary on stdout. Warnings go to
**stderr** so a parser of stdout always gets valid JSON.

## State machine guarantees

The executor only ever emits one of six outcomes per task:

| Outcome                  | Notion page? | When                                                  |
|--------------------------|--------------|-------------------------------------------------------|
| `created`                | created      | Real write, task clean, plan action = `create`        |
| `skipped_blocked`        | created      | Task is BLOCKED upstream; page has `Status=blocked`   |
| `skipped_invalid`        | not created  | Plan action = `skip_invalid` (validation error)       |
| `skipped_already_synced` | not created  | Idempotency: page already exists                       |
| `skipped_refused`        | not created  | Dry-run, missing creds, SDK missing, plan has errors  |
| `failed`                 | not created  | Writer raised; error captured                          |

Cardinal rule: **no outcome advances a task to `ready` / `approved` /
`done`**. The executor only ever creates pages. Status field is
copied verbatim from the upstream task state.

Test-pinned: `test_no_status_advanced_in_records`.

## What the writer NEVER does

- **No `update_page`.** Once a page is created, the executor
  refuses to touch it again. The idempotency map under
  `<client>/notion_synced_pages/current.json` is the gate.
- **No `delete_page`, no `archive_page`.** The
  `NotionWriter` ABC only declares `create_page`.
  `ScriptedNotionWriter` (test fixture) has no other methods —
  any attempt to call them in the executor would raise
  `AttributeError`.
- **No `databases.create`.** The writer requires an existing
  database id from the operator (env var). Creating workspaces is
  out of scope.
- **No retries.** One attempt per task. If the SDK raises, the
  task lands as `failed` and the batch continues. Adding retries
  is deferred to `P-5B.x`.

## Credential safety

- `NOTION_TOKEN` is read **once** at writer construction and
  handed to the SDK client. The writer keeps no long-lived
  reference to the raw value.
- `__repr__` redacts to `***redacted***`. Test-pinned:
  `test_repr_redacts_token`.
- Error wrapping is sanitised — `NotionWriteError` carries
  `type(exc).__name__: str(exc)[:200]`. The token never appears
  in our own constructed strings. If an SDK error echoes the
  token, the 200-char cap limits exposure inside the local
  audit/report only.
- `NotionSyncReport` has NO `token` / `api_key` / `secret` /
  `credential` field — leak-by-serialisation is mechanically
  impossible. Test-pinned: `test_report_has_no_token_field`.
- No env var read happens inside the `notion_sync` package
  except in `NotionClientWriter.__init__`. The CLI reads them
  and passes the values explicitly to the executor.

## Idempotency

After every successful create, the executor appends an entry to
`<client>/notion_synced_pages/current.json`:

```json
{
  "task_id": "abcd...",
  "page_id": "p123...",
  "synced_at": "2026-06-02T12:30:00+00:00",
  "sync_report_id": "rep456..."
}
```

On the next run, any task already in this map is skipped with
outcome `skipped_already_synced`. The writer is never called.

To force a re-sync (e.g. after deleting pages in Notion by hand),
the operator removes the entry from the index — no CLI helper
ships in this block.

## Audit trail

One `notion_sync.started` event (with mode, confirmed, write
attempted, env presence flags, plan id, task pack id), one
`notion_sync.record` per task (with outcome + page_id +
error_type), one `notion_sync.finished` event (with stats).

The append-only hash chain remains valid. Test-pinned:
`test_audit_records_started_record_and_finished`.

## Testing without burning real Notion writes

Two layers of defence:

1. **Dependency injection.** `NotionClientWriter.__init__` accepts
   a `client=` kwarg. Tests pass a `MagicMock`. The real
   `notion_client.Client(...)` construction is gated on
   `client is None`.
2. **Lazy import.** `import notion_client` only runs inside the
   constructor when `client is None`. Mocking suppresses the
   import path entirely. Test-pinned:
   `test_dependency_injection_short_circuits_sdk_import`.

CI runs the full pytest suite without `NOTION_TOKEN` and without
the SDK installed. The dry-run path is exercised end-to-end; the
write path is exercised via mocked clients.

## Cost ceiling

Real writes cost nothing per page (the Notion API is free), but
the operator's Notion workspace has rate limits (3 requests/sec
on the standard plan). One pack of ~80 tasks completes in
~27 seconds at full throttle. The writer makes one call per
task with no retries; bursts are limited by Python's serial
execution. A future block can add explicit backoff (`P-5B.1`).

## Anti-patterns

- Do not commit `NOTION_TOKEN` to the repo. The `.gitignore`
  already excludes `.env`.
- Do not echo `os.environ["NOTION_TOKEN"]` anywhere in your code
  or in print/log statements.
- Do not bypass the safety gate by calling `NotionSyncExecutor`
  directly with `mode=WRITE, confirmed=True`. The CLI is the
  only blessed entry point because it also writes the warning
  message and persists the report on disk.
- Do not promote the writer to do `update_page` without a
  matching ADR explaining bidirectional sync semantics. Today
  the contract is strictly create-only.

## What's NOT in MKT-5B

- No retries (P-5B.1).
- No streaming or batch endpoints (P-5B.2).
- No `update_page` (P-5B.3).
- No `archive_page` / `delete_page` (out of scope, ever).
- No bidirectional sync (Notion → MAOS).
- No per-tenant database_id mapping (P-5B.4).
- No MCP server, no n8n, no other providers.
- No GA4 / Google Ads / Search Console.

## Smoke verification

Dogfood intake, `mkt notion-sync` (no flags):

```
mode: dry_run
write_attempted: False
total_records: 78
skipped_refused: 78
```

Dogfood intake, `mkt notion-sync --write --confirm` with mocked
SDK (in tests):

```
mode: write
write_attempted: True
created: 78
```

Risky intake, `mkt notion-sync --write --confirm` with mocked SDK:

```
created: 61
skipped_blocked: 16   # pages created, Status=blocked
```

## Tracked follow-ups in PENDING.md → P-5B.*

- `P-5B.1`: Retry policy with backoff for transient errors.
- `P-5B.2`: Batch / streaming endpoints if the volume justifies.
- `P-5B.3`: `update_page` for the subset of fields that change
  upstream (state, due_date), with explicit idempotency design.
- `P-5B.4`: Per-tenant `database_id` mapping (today only the
  global env var is used).
- `P-5B.5`: Promote `Depends On` to a Notion `relation` property
  once `P-5A.1` lands (depends on the planner change).
- `P-5B.6`: Cost / rate-limit dashboard.
- `P-5B.7`: Real integration smoke test against a sandbox Notion
  workspace; CI-gated behind a marker.
