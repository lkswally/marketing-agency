# Runtime — n8n Execution Payload Dry Run (MKT-5C)

Builds the per-action payloads a future n8n integration would
POST to its webhooks — **without making any HTTP call, reading
any webhook URL, or sending anything**. The payload is data on
disk + memory; a future block (or external sync tool) is the one
that would actually trigger n8n.

- **Module:** `core/n8n_sync/`
- **Contract:** `n8n-execution-payload.v1`
- **CLI:** `mkt n8n-plan --client <slug>`
- **Memory kind:** `n8n_execution_payload` / singleton id `current`

## Quick start

```bash
# Pre-requisites: full pipeline + at least the run summary.
# Notion sync is optional — its records feed notion_status_update.
mkt run-campaign --intake examples/intake/marketing-agency-os.json
mkt build-tasks  --client marketing-agency-os
mkt notion-plan  --client marketing-agency-os
mkt notion-sync  --client marketing-agency-os         # dry-run

mkt n8n-plan     --client marketing-agency-os
```

Two files are written to `--outputs-dir`:

| File                          | Audience                       |
|-------------------------------|--------------------------------|
| `n8n-execution-plan.md`       | operator review                |
| `n8n-execution-payload.json`  | future n8n sync tool           |

## Six action types

| Action type                   | Source                          | Webhook (logical)   | Default status |
|-------------------------------|---------------------------------|---------------------|----------------|
| `campaign_report_notification`| CampaignRunSummary              | `campaign_reports`  | planned        |
| `telegram_notification`       | CampaignRunSummary              | `telegram_alerts`   | planned        |
| `email_draft`                 | CreativeAssetPack.emails        | `email_drafts`      | planned/blocked|
| `social_post_draft`           | CreativeAssetPack.social_posts  | `social_drafts`     | planned/blocked|
| `drive_asset_folder`          | VisualDirectionPack.directions  | `drive_folders`     | planned        |
| `notion_status_update`        | NotionSyncReport.records        | `notion_updates`    | planned        |

`target_webhook` is a **logical name**, never a URL. A future sync
tool maps each name to a real URL from its own config — this
module has zero opinion about transport.

## Blocking semantics

If the campaign blocks publish (any of `CampaignRunSummary`,
`CampaignExecutionTaskPack`, `CreativeAssetPack` has
`blocks_publish=True`), the planner emits:

- `email_draft` actions → `status="blocked"` with explicit
  `blocked_reason`.
- `social_post_draft` actions → `status="blocked"` with explicit
  `blocked_reason`.
- `telegram_notification` → stays `planned` (the team must be
  alerted that the campaign is blocked). Text changes from
  `✅` to `🛑`.
- `campaign_report_notification` → stays `planned`.
- `drive_asset_folder` → stays `planned` (folder setup is safe
  regardless of approval state).
- `notion_status_update` → stays `planned` (reflects what already
  happened upstream).

Test-pinned: `test_risky_pack_blocks_email_and_social_drafts`,
`test_notifications_remain_planned_when_blocked`.

## Cardinal guarantees

- **No HTTP call.** Test-pinned:
  `test_planner_does_not_import_requests_or_httpx`.
- **No webhook URL read.** Test-pinned:
  `test_planner_does_not_read_webhook_envs`. No `os.environ` read
  anywhere in the planner.
- **No credential/URL field on any model.** Test-pinned:
  `test_payload_models_have_no_url_or_secret_fields`.
- **No state advancement.** `notion_status_update` actions
  carry `advance_status=False` to communicate "this is a sync
  hint, do not progress the task".
- **Drafts are never sent.** `email_draft` and
  `social_post_draft` actions carry `draft_only=True` in their
  payload so a future n8n flow MUST create a draft, never send.
- **Pure planner.** Same upstream artifacts → same payload
  (modulo fresh `payload_id` + `created_at`).
- **Multi-tenant by construction** (slug-scoped memory + outputs).

## Partial inputs

Each upstream artifact is optional. The planner skips its actions
silently when missing:

- No `CreativeAssetPack` → zero `email_draft` + zero
  `social_post_draft` actions.
- No `VisualDirectionPack` → zero `drive_asset_folder` actions.
- No `NotionSyncReport` → zero `notion_status_update` actions.
- No `CampaignRunSummary` → zero notifications either. (The CLI
  refuses with exit 2 in this case — the run summary is the
  minimum input.)

A campaign without any creative pack still gets a campaign report
and a telegram notification. Test-pinned:
`test_missing_creative_pack_skips_email_actions`.

## Audit trail

One `note` event per `mkt n8n-plan` run with payload
`{"n8n_execution_payload": {"action": "planned", ...}}`.
Hash chain preserved. Test-pinned:
`test_persist_emits_audit_event`.

## What's NOT in MKT-5C

- No HTTP call. No webhook trigger. No real n8n connection.
- No webhook URL env var read.
- No retries, no batching, no async (not relevant — no real calls).
- No dispatch / failed status (those are reserved for a future
  real-sync block).
- No MCP, no GA4, no Google Ads, no Search Console.
- No publishing, no email send, no image generation.

## Smoke verification

Dogfood intake (clean):

```
total_actions: 23
planned: 23  blocked: 0
by_type:
  campaign_report_notification: 1
  telegram_notification: 1
  email_draft: 4
  social_post_draft: 6
  drive_asset_folder: 11
```

Risky intake (synthetic guarantees claim):

```
blocks_publish: True
planned: 13  blocked: 10
  email_draft: 4 (all blocked)
  social_post_draft: 6 (all blocked)
  telegram_notification: 1 planned (with 🛑 prefix)
  campaign_report_notification: 1 planned
  drive_asset_folder: still planned
```

## Tracked follow-ups (PENDING.md → P-5C.*)

- `P-5C.1`: Real n8n sync block (`--push-to-n8n` flag, opt-in,
  with the same gates as `notion-sync --write --confirm`).
- `P-5C.2`: Per-tenant webhook URL mapping
  (`data/clients/<slug>/n8n.json`).
- `P-5C.3`: Per-channel email/social tool selection
  (Mailchimp vs Resend, Buffer vs Later) surfaced in the payload.
- `P-5C.4`: Action subtypes for `telegram_notification`
  (`alert` vs `summary` vs `reminder`).
- `P-5C.5`: `Drive` folder permissions hint (who shares with
  whom).
- `P-5C.6`: Action-level dispatch tracking (when the real sync
  block lands).
