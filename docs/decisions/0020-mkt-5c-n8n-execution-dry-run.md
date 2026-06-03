# ADR 0020 — MKT-5C: n8n Execution Payload Dry Run

- **Status:** Accepted
- **Date:** 2026-06-02
- **Block:** MKT-5C
- **Supersedes:** —
- **Contract:** `n8n-execution-payload.v1` (new, Pydantic, in
  `core/n8n_sync/models.py`).

## Context

After MKT-5A (Notion plan) and MKT-5B (Notion writer with opt-in
write), the system can describe + execute one downstream
integration (Notion). The next logical target is n8n: the user
already uses n8n to dispatch emails, social posts, telegram
alerts, drive folder setup, etc.

MKT-5C ships the **dry-run payload** for that future integration.
The user repeated three times: "no real n8n", "no webhooks",
"no HTTP". The block is data-only — same shape as the future
real-sync block will consume.

## Decision

### D-20.1 — New module `core/n8n_sync/`

Parallel to `core/notion_sync/`. Same conventions: Pydantic
models with `extra="forbid"`, planner class with
`plan/persist/load_latest`, dedicated renderer, exported through
`__init__.py`. Memory kind: `n8n_execution_payload`. Singleton id:
`current`.

Rejected alternative: extend `core/notion_sync/` to add n8n
actions. n8n covers six action types beyond Notion sync; mixing
them would dilute the Notion module's tight contract.

### D-20.2 — Six action types, one shape

`N8nActionType` enumerates exactly the six values the user spec'd:

| Action type                    | Source                           |
|--------------------------------|----------------------------------|
| `campaign_report_notification` | CampaignRunSummary               |
| `telegram_notification`        | CampaignRunSummary               |
| `email_draft`                  | CreativeAssetPack.emails         |
| `social_post_draft`            | CreativeAssetPack.social_posts   |
| `drive_asset_folder`           | VisualDirectionPack.directions   |
| `notion_status_update`         | NotionSyncReport.records         |

Each becomes one `N8nAction` with: `action_type`, `status`,
`target_webhook` (logical name), `source_kind`, `source_ref`,
`payload` (free dict shaped per-type by the planner),
`blocked_reason`.

Rejected alternative: a Pydantic subclass per action type. Too
much ceremony for a planner whose only job is to emit consistent
dicts; the future real sync tool will validate per-webhook on its
own side.

### D-20.3 — Logical webhook names, never URLs

`N8nAction.target_webhook` is a short logical identifier
(`"email_drafts"`, `"telegram_alerts"`). It is NOT a URL. The
future sync tool maps each name to a real URL from its own
config — never from this module.

Test-pinned: `test_payload_models_have_no_url_or_secret_fields`
rejects any field whose name could hold a URL or credential.

### D-20.4 — Blocking semantics

Send-side actions (`email_draft`, `social_post_draft`) → BLOCKED
when any of `CampaignRunSummary`,
`CampaignExecutionTaskPack`, `CreativeAssetPack` carries
`blocks_publish=True`. With explicit `blocked_reason`.

Notification + setup actions (`telegram_notification`,
`campaign_report_notification`, `drive_asset_folder`,
`notion_status_update`) → stay PLANNED even when publish is
blocked. The whole point of the telegram alert in that case is to
loud-warn the team that the campaign is blocked. The text payload
flips from `✅` to `🛑` accordingly.

Cardinal rule (test-pinned): the team is alerted regardless;
only the *sending* of customer-facing content is blocked.

### D-20.5 — Draft-only convention for send actions

`email_draft` + `social_post_draft` payloads carry `draft_only=True`.
This is a hint for the future n8n flow: it MUST create a draft
in the corresponding tool (Mailchimp draft, Buffer draft) and
NEVER auto-send. The convention is documented in the runtime doc
and pinned by tests that assert the field is always present.

### D-20.6 — `notion_status_update` carries `advance_status=False`

The Notion sync block already creates pages with the right
initial Status. The n8n flow that hears about new pages must NOT
advance their state. The `advance_status=False` field makes the
do-not-advance contract explicit at the payload level.

### D-20.7 — Partial inputs handled gracefully

Each upstream artifact (creative pack, visual pack, notion
report) is optional. The planner uses `_try_load` to swallow
`EntityNotFound` and emits zero actions of the missing kind. The
only minimum input is `CampaignRunSummary` (the CLI returns exit
2 without it; the planner returns an empty payload without it).

Test-pinned:
`test_missing_creative_pack_skips_email_actions`,
`test_missing_every_artifact_emits_empty_payload`.

### D-20.8 — Pure planner, pure renderer

Both `N8nPayloadPlanner.plan()` and `render_markdown_payload()`
are deterministic. Same inputs → same payload (modulo fresh
`payload_id` + `created_at`). The renderer is byte-pure over the
payload.

`plan()` itself does NOT persist. `persist()` is a separate call
that also emits the audit event. The CLI calls both; tests can
verify pure behaviour separately.

### D-20.9 — Hard guarantee: no HTTP / no env var read

Test-pinned at three layers:

- `test_planner_does_not_import_requests_or_httpx` — no top-level
  import of `requests`, `httpx`, `urllib.request` in the planner
  source.
- `test_planner_does_not_read_webhook_envs` — no reference to
  `N8N_WEBHOOK`, `N8N_TELEGRAM`, `N8N_EMAIL`, `os.environ` in the
  planner source.
- `test_renderer_source_does_not_read_env_or_http` — same checks
  on the renderer source.

The future real sync block (P-5C.1) will live in a separate
module (`core/n8n_sync/sender.py`) with its own opt-in extra,
following the same pattern as MKT-4B (Anthropic SDK) and MKT-5B
(Notion client).

### D-20.10 — CLI `mkt n8n-plan`

Subcommand args: `--client` (required), `--root`, `--outputs-dir`.
Exit codes: 0 (ok), 2 (no run summary for client). Outputs:
`n8n-execution-plan.md` + `n8n-execution-payload.json` + one
audit event. Matches the conventions of `notion-plan`.

## Consequences

### Positive

- One command takes a campaign to a complete dry-run payload for
  six n8n action types. Deterministic, 0 external calls, 0
  credentials.
- The payload stays usable by any transport (n8n direct, Make,
  Zapier, a custom HTTP client). The factory has zero opinion.
- Operators can review the plan locally before any production
  webhook is wired.
- Send-blocking is conservative by default — customer-facing
  drafts are blocked when approval blocks publish, but the team
  is still alerted.

### Negative / accepted trade-offs

- The payload dict for each action_type is loosely typed. A
  future block could add Pydantic models per action_type if a
  validation gap appears.
- `target_webhook` is a logical name; the future sync tool
  needs its own URL config. Acceptable: hardcoded URLs in the
  payload would be a leak vector.
- Channel options for emails/social are not split (no Mailchimp
  vs Resend hint, no Buffer vs Later hint). Tracked as P-5C.3.
- The planner doesn't know about n8n's specific webhook URL
  naming conventions — it just emits logical names. The future
  sync tool is responsible for the mapping.
- The plan overwrites on re-build. Historical plans live only
  in the audit trail.

## Out of scope (explicit)

- Real n8n call (P-5C.1).
- Webhook URLs of any kind.
- HTTP client of any kind.
- Notion MCP write (separate block, MKT-5B already shipped
  notion-client direct).
- GA4, Google Ads, Search Console.
- Publishing, email send, image generation.

## Validation

- 44 new tests
  (`tests/n8n_sync/test_models.py` 14 +
   `tests/n8n_sync/test_planner.py` 17 +
   `tests/n8n_sync/test_renderer.py` 9 +
   `tests/cli/test_cli_n8n_plan.py` 4).
- Full suite: **1149 passed**.
- Ruff: clean.
- ATLAS core: untouched.
- Smoke verified on dogfood intake: 23 actions across 5 types
  (drive_asset_folder=11 due to a rich visual pack). Risky intake:
  10 blocked (all email_draft + social_post_draft) + 13 planned
  (notifications + drive folders + notion updates).

## Related

- Depends on MKT-5A (notion plan), MKT-5B (notion writer),
  MKT-4E (task pack), MKT-3F (run summary), MKT-3C / 3D
  (creative + visual packs).
- Future work tracked as `P-5C.*` in `PENDING.md`.
- Runtime doc: `docs/runtime/n8n-execution-dry-run.md`.
