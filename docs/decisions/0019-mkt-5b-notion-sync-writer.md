# ADR 0019 — MKT-5B: Notion Sync Writer

- **Status:** Accepted
- **Date:** 2026-06-02
- **Block:** MKT-5B
- **Supersedes:** —
- **Contract:** `notion-sync-report.v1` (new, Pydantic, in
  `core/notion_sync/sync_report.py`).

## Context

MKT-5A shipped the dry-run plan: a deterministic description of
what a future synchroniser WOULD do, with zero Notion calls.
MKT-5B is the future synchroniser — but locked behind multiple
explicit safety gates. The user repeated three times: "no
write by default", "no MCP write", "only with explicit
confirmation".

The block delivers a real write path that is mechanically
impossible to trigger by accident.

## Decision

### D-19.1 — Four gates between the operator and a real Notion call

A real `client.pages.create(...)` only happens when all four
conditions hold:

1. **CLI flag `--write` is present.**
2. **CLI flag `--confirm` is present.** Without it, the CLI
   exits with code 3 and writes nothing — even `--write` alone
   is not enough.
3. **Env vars `NOTION_TOKEN` AND `NOTION_TASKS_DATABASE_ID` are
   set.** Missing either falls back to dry-run with a stderr
   warning.
4. **The persisted `NotionSyncPlan` has zero ERROR-severity
   issues.** Any error issue blocks the entire batch.

If any of the four gates fails, the executor still runs through
every task and produces a complete report — just with
`write_attempted=False` and outcome `skipped_refused` (or
`skipped_blocked` for upstream-blocked tasks).

### D-19.2 — Writer ABC with three implementations

Same pattern as MKT-4B's `ClaudeInvoker`:

- `RefusingNotionWriter` — safe default. Always raises
  `NoNotionCredentialsError`. The executor catches and records
  `skipped_refused`.
- `ScriptedNotionWriter` — test-only. Canned `page_id`s keyed by
  `task_id`, optional per-task errors.
- `NotionClientWriter` — production. Lazy-imports
  `notion-client`; constructor raises `NoNotionCredentialsError`
  if the SDK is missing OR token missing OR database id missing.

The CLI wires `RefusingNotionWriter` by default. Only when all
four gates pass does it instantiate `NotionClientWriter` with
the real env-resolved token + database id.

### D-19.3 — Only `create_page`

The `NotionWriter` ABC declares exactly one method:
`create_page`. No `update_page`, no `archive_page`, no
`delete_page`. The executor cannot mutate or remove pages in
Notion. Once a page is created, it lives.

This is a deliberate floor. Update/delete are deferred to
P-5B.3 with explicit idempotency design.

### D-19.4 — Idempotency via a per-client task_id → page_id map

The executor maintains
`<client>/notion_synced_pages/current.json`, a Pydantic
`NotionSyncedPagesIndex`. After every successful create, the
executor appends an entry. On the next run, any task already in
the map is skipped with outcome `skipped_already_synced` and
the writer is never called.

This guarantees that re-running the CLI does not duplicate
pages and does not advance any state — the operator's manual
edits in Notion are safe.

To force a re-sync, the operator clears the map. No CLI helper
ships in this block.

### D-19.5 — Blocked tasks are CREATED with Status=blocked

Inherited from MKT-5A: blocked tasks are visible in the Notion
view, so the operator sees what's blocking the campaign. The
executor calls `create_page` with `Status=blocked` and records
outcome `skipped_blocked` (the "do not advance" signal).

Test-pinned: `test_blocked_pages_carry_status_blocked_property`.

### D-19.6 — One attempt per task; failures don't abort the batch

When the writer raises `NotionWriteError`, the executor records
the task as `failed` (with `error_type` + sanitised
`error_message`) and continues. No retries (deferred to P-5B.1).

A high failure rate is still observable in the report stats and
the audit trail, so an operator can decide to stop manually.

### D-19.7 — Credential boundary

Same model as MKT-4B's Anthropic SDK invoker:

- Token is read **once** at writer construction.
- Stored only as an instance attribute on the SDK client (not on
  the writer itself).
- `__repr__` redacts to `***redacted***`.
- Error wrapping caps error messages at 200 chars.
- The `NotionSyncReport` schema has no token field.
- The CLI reads env vars and passes resolved values to the
  executor as kwargs — the executor itself does not read
  `os.environ`.

Test-pinned at every layer:
- `test_repr_redacts_token`
- `test_error_does_not_leak_token`
- `test_report_has_no_token_field`
- `test_renderer_does_not_leak_token`

### D-19.8 — `notion-client` is an OPTIONAL extra

```toml
[project.optional-dependencies]
notion = ["notion-client>=2.0,<3.0"]
```

The dry-run path runs with zero LLM/SDK deps. The write path
requires `pip install -e .[notion]`. Missing SDK at write time
falls back cleanly to dry-run (the lazy import inside the
writer catches `ImportError` and re-raises as
`NoNotionCredentialsError`).

### D-19.9 — Two contracts

The block introduces two Pydantic contracts:

- `notion-sync-report.v1` — the executor's output.
- `notion_synced_pages` (no version pin; internal index, not a
  shared contract).

The plan (`notion-sync-plan.v1` from MKT-5A) is consumed as-is.
The task pack (`campaign-execution-task-pack.v1` from MKT-4E)
is consumed via `to_notion_payload()` so the writer gets the
same shape the dry-run validated.

### D-19.10 — CLI exit codes

- 0 — sync completed (dry-run or real write)
- 2 — no `NotionSyncPlan` for the client
- 3 — `--write` without `--confirm` (safety gate)

`--write --confirm` with missing token/SDK/etc returns 0
because the operator's intent is to sync; the fallback to
dry-run is still a successful execution.

## Consequences

### Positive

- Real Notion sync is one command away when needed, and
  impossible to trigger by accident.
- Every gate failure produces a clean report + stderr warning;
  no silent failures.
- The idempotency map makes re-running safe and observable.
- Operators can install the SDK only when they actually need it.
- The credential boundary is identical to MKT-4B, so anyone
  who knows the Anthropic story knows this one.

### Negative / accepted trade-offs

- No retries. A rate-limited operator sees `failed` records, not
  a recovered sync. Acceptable for v1; observable in stats.
- No `update_page`. State changes upstream (a task moving from
  `todo` to `done` inside MAOS) do NOT propagate to Notion. The
  operator updates Notion manually. P-5B.3 will revisit.
- The blocked-task UX in Notion depends on the database view
  having a "Status = blocked" filter; we cannot create views
  via this writer.
- The idempotency map is local to MAOS memory. If the operator
  deletes pages in Notion, they must also clear the map manually
  to force a re-sync.
- Cost of token leak from an SDK error is theoretically
  present — capped at 200 chars in audit + report, never
  transmitted off-host.

## Out of scope (explicit)

- Real Notion `update_page` / `archive_page` / `delete_page`.
- Bidirectional sync (Notion → MAOS).
- MCP server.
- n8n integration.
- GA4 / Google Ads / Search Console.
- Publishing, email send, image generation.
- LLM calls of any kind.
- Cron / scheduling. The CLI is one-shot per invocation.

## Validation

- 64 new tests
  (`tests/notion_sync/test_writer.py` 22 +
   `tests/notion_sync/test_executor.py` 17 +
   `tests/notion_sync/test_sync_report.py` 15 +
   `tests/notion_sync/test_sync_renderer.py` 10 +
   `tests/cli/test_cli_notion_sync.py` 10 — approximately).
- Full suite: **1105 passed**.
- Ruff: clean.
- ATLAS core: untouched.
- Smoke verified end-to-end:
  - Dry-run on dogfood intake: 78 records, all
    `skipped_refused`, zero writer calls.
  - Risky intake dry-run: skipped_blocked emitted for the 16
    blocked tasks.
  - Mocked write path (CLI test): all 78 tasks created in the
    mocked Notion DB; re-run shows 78 `skipped_already_synced`.

## Related

- Depends on MKT-5A (plan), MKT-4E (task pack), MKT-1D (memory).
- Mirrors the safety pattern from MKT-4B (Anthropic SDK).
- Future work tracked as `P-5B.*` in `PENDING.md`.
- Runtime doc: `docs/runtime/notion-sync-writer.md`.
