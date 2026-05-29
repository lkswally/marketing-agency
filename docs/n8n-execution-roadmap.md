# n8n — Execution Layer Roadmap

> Status: **roadmap only** (MKT-2C). No n8n connection exists, no webhook
> URL is configured, no token is stored.
> Companion to [`n8n-automation-roadmap.md`](n8n-automation-roadmap.md),
> which covers **planning** (what MKT tells n8n to do). This document
> covers **execution** (how an approved action is dispatched to a
> pre-built n8n workflow).

The two roadmaps split the work cleanly:

| Concern | Doc | Block |
|---------|-----|-------|
| MKT produces `n8n_plan` describing future workflows | `n8n-automation-roadmap.md` | MKT-1E (specs) → MKT-MCP-8 (used) |
| MKT triggers an approved workflow that already exists in n8n | this doc | MKT-MCP-8 |

---

## 1. The execution-layer thesis

ADR 0005 D-5.4 decided: **MKT plans, n8n executes**. n8n is mature at
scheduled workflows, retries, multi-provider integrations, queueing.
Re-implementing that inside `core/` would be deep work for zero new
capability. The cleanest split:

- MKT owns strategy, drafts, claims, approvals, audit trail, reports.
- n8n owns scheduled triggers, retries, ESP/CRM/social adapter chains.
- The bridge between them is **one-way and tightly scoped**: a signed
  webhook from MKT to an n8n workflow, only after Approval Center has
  cleared the action.

n8n NEVER calls MKT in the v1 design (D-5.4 unchanged).

---

## 2. Trigger contract (sketch)

When an approved `ProposedAction` targets an external execution (e.g.
"send the approved newsletter", "publish the approved IG post", "add
the approved keyword negation list"), the dispatcher constructs a
trigger payload, signs it, and POSTs to a configured n8n webhook.

```yaml
# Conceptual contract — NOT promoted to Pydantic in MKT-2C
contract_version: n8n-trigger.v0

# Identification
trigger_id: "trg_<uuid>"
client_slug: "demo-co"
issued_at: "2026-06-01T12:00:00+00:00"

# Provenance — everything that led to this trigger
approval_id: "apr_<uuid>"
proposed_action_id: "pa_<uuid>"
recommendation_id: "rec_<uuid>"

# Routing
n8n_workflow_name: "weekly-newsletter-send"   # MUST exist in the n8n registry (§3)
n8n_workflow_version: 7

# Payload — bounded, structured, scrubbed
payload:
  artifact_path: "outputs/demo-co/newsletters/2026-06.md"
  artifact_sha256: "abcd...64hex"
  list_handle: "demo-weekly"
  schedule_at: "2026-06-01T14:00:00+00:00"

# Constraints
constraints:
  max_recipients: 10000           # n8n MUST fail closed if exceeded
  must_match_artifact_sha256: true # n8n verifies before sending
  abort_if_paused: true            # n8n re-reads the abort flag at execution time

# Security
signature:
  algorithm: "hmac-sha256"
  signature: "<hex64>"
  signed_fields_canonical: [trigger_id, client_slug, issued_at, approval_id,
                            n8n_workflow_name, n8n_workflow_version, payload]
  key_ref: "env(MKT_N8N_SIGNING_KEY)"   # NAME only

# Acknowledgement contract
expected_ack_within_seconds: 5
expected_completion_within_seconds: 1800
ack_webhook_url_ref: "env(MKT_N8N_ACK_URL)"  # MKT-side listener for n8n's ack
```

The signature is checked at the n8n side before any action. A failed
signature → n8n drops the trigger and emits its own audit (within n8n).

---

## 3. n8n workflow registry

The set of n8n workflows MKT may trigger is **explicitly enumerated**.
There is no "let MKT specify any workflow name and we'll try it".

```yaml
# config/n8n_registry.yaml (FUTURE — not present in MKT-2C)
contract_version: n8n-registry.v0

workflows:
  - name: "weekly-newsletter-send"
    version: 7
    purpose: "Send the approved newsletter to a list."
    triggers_allowed_from:
      - mkt_event: "approval_granted"
        approval_subject_kinds: ["asset:email_template"]
    expected_payload_keys: ["artifact_path", "artifact_sha256", "list_handle", "schedule_at"]
    rate_limit: { per_client_per_day: 7 }
    revertable: false
    notes: "ESP send. Not revertable. Confirm-twice required upstream."

  - name: "google-ads-pause-campaign"
    version: 2
    purpose: "Pause one Google Ads campaign."
    triggers_allowed_from:
      - mkt_event: "approval_granted"
        approval_subject_kinds: ["proposed_action:gads.campaign.mutate.pause"]
    expected_payload_keys: ["customer_id", "campaign_id"]
    rate_limit: { per_client_per_day: 20 }
    revertable: true
    revert_workflow: "google-ads-enable-campaign"
    notes: "Double-approval required upstream (Google Ads policy)."
```

MKT triggers MUST reference an enumerated `name` + `version`. Unknown
names → trigger refused at MKT side; never POSTed.

---

## 4. Approval coupling

The chain is:

```
ProposedAction (state=APPROVED)
        │
        ▼
n8n trigger constructed + signed
        │
        ▼
POST → n8n webhook
        │
        ▼
n8n verifies signature + re-checks constraints
        │
        ▼  (ack within 5s)
        │
        ▼  (completion within 1800s by default)
n8n → ack webhook → MKT marks ProposedAction.state=EXECUTED
                    OR proposed_action_failed event on timeout / error
```

Behavioral rules:

1. A trigger MUST NOT be sent without a corresponding approved
   `ProposedAction` AND its parent `MarketingRecommendation`.
2. The webhook signing key (`MKT_N8N_SIGNING_KEY`) is configured by env
   and rotated on a schedule (mechanism out of scope for this roadmap).
3. The ack endpoint (`ack_webhook_url_ref`) is the only way n8n
   communicates back. Failure to ack within timeout → MKT marks the
   proposed action as `EXECUTION_TIMED_OUT`, emits an audit event, and
   does NOT retry automatically.
4. Re-triggering an action that timed out requires a new approval. The
   original approval is consumed even on timeout.
5. Trigger payloads MUST NOT contain secrets. Credentials needed by n8n
   live in n8n's own credential store.

---

## 5. Permission policy

Per `permissions-policy.md` §3.7:

| Operation | Status |
|-----------|--------|
| POST a trigger that references an enumerated workflow with a valid signature and an approved `ProposedAction` | ✅ allowed |
| Anything else (raw HTTP to n8n, unsigned trigger, trigger without approval, trigger to unknown workflow) | ❌ forbidden |

The adapter (when it lands, MKT-MCP-8) is a **single function**: given
a `ProposedAction` and its approval, construct + sign + POST. No
general-purpose n8n client surface.

---

## 6. Audit events

When MKT-MCP-8 lands:

| Event type | When |
|------------|------|
| `n8n_trigger_dispatched` | After successful POST + ack within timeout. |
| `n8n_trigger_failed` | Sign error, transport error, no ack within timeout. |
| `n8n_action_completed` | n8n's completion webhook hits the ack endpoint. |
| `n8n_action_failed` | Same but with failure reason. |

All four are additive to `audit-trail.v1`.

---

## 7. Open questions

- **Signing key rotation**: the right interval and the failover policy
  during a rotation window. Deferred.
- **Retries**: MKT does NOT auto-retry a failed trigger in v1. Whether
  to add a "re-propose with retry" affordance is a UX call for the
  Approval Center implementation.
- **Idempotency on n8n side**: a trigger contains `trigger_id`; n8n
  workflows MUST treat it as the idempotency key. The contract for that
  is on n8n's side, documented when MKT-MCP-8 lands.
- **n8n-side workflow updates**: when an enumerated workflow's `version`
  bumps, the MKT registry MUST be updated; old triggers in flight use
  the version they were stamped with.

---

## 8. Out of scope for MKT-2C

- The trigger module.
- The signing implementation.
- The webhook URL.
- The registry YAML.
- The ack listener.
- Any actual n8n connection.
