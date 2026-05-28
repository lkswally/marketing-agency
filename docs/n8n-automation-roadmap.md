# n8n Automation Roadmap

> Status: **roadmap only** (MKT-1E). No n8n connection exists; no
> credentials are stored; nothing in `core/` imports an n8n client.

## Why n8n at all

A marketing agency needs to keep things moving on a schedule: posts go out,
broadcasts get sent, leads are captured, webhooks ping CRMs. Building that
plumbing inside MKT would duplicate what n8n already does well.

The decision (ADR 0005 D-5.4) is: **MKT plans, n8n executes**. MKT produces
an `n8n_plan` (kind: `n8n_plan` in memory) that a human builds in n8n —
later replaced by a programmatic builder.

## Boundary

| Concern | Owner |
|---------|-------|
| Strategy, content drafts, audit, approval | MKT |
| Cron scheduling, multi-step recurring workflows, webhook receivers, ESP/CRM integration | n8n |
| Triggering a one-off n8n workflow from MKT | A future bridge (post-MVP). NOT in scope for any MKT-1* block. |
| Storing n8n credentials | n8n itself. **Never in MKT.** |

## What MKT produces today

The `n8n-automation-planner` agent emits an `n8n_plan` memory entity with
this shape (spec only — no Pydantic contract):

```yaml
contract_version: n8n-plan.draft.v0   # promoted to versioned spec when implemented
workflows:
  - name: "Weekly newsletter send"
    trigger:
      kind: cron
      schedule: "0 13 * * THU"
    steps:
      - kind: read_from_mkt
        source: "outputs/<client>/newsletters/latest.md"
      - kind: send_email
        provider: resend
        list_id: env(RESEND_LIST_ID)
      - kind: notify
        provider: slack
        channel: "#marketing-ops"
    expected_credentials:
      - RESEND_API_KEY
      - SLACK_WEBHOOK_URL
    notes: "Approval is in MKT; n8n only executes the approved file."
delegations_from_mkt:
  - mkt_event: g_approval_granted
    n8n_workflow_name: "Weekly newsletter send"
```

The plan is a description, not an export. The first iteration of the n8n
build is **manual**: someone reads the plan and reproduces it in n8n.

## Roadmap

| Phase | Goal |
|-------|------|
| **R1 — Plan-only (this block)** | MKT produces `n8n_plan`. Humans translate to n8n. |
| **R2 — Export** | A skill that exports the `n8n_plan` as importable n8n JSON. Out of scope for any MKT-1* block. |
| **R3 — Trigger-only bridge** | A bridge module (`bridge/n8n_adapter.py`, opt-in) that POSTs to an n8n webhook to trigger a pre-built workflow. Off by default via `MKT_BRIDGE_N8N=0`. |
| **R4 — Two-way** | n8n can call back into MKT via the future Bridge API. Far future; no commitment. |

## What this block does NOT do

- No `bridge/n8n_adapter.py` (R3+ only).
- No n8n webhook URL stored.
- No JSON export.
- No assumed cron syntax beyond standard 5-field crontab.

## Security

When a bridge exists (R3+):

- Credentials referenced by name (`RESEND_API_KEY`), never by value.
- Webhook URL configured per environment; never committed.
- n8n→MKT direction (R4) requires signed payloads.

For v1, none of this matters because nothing connects.
