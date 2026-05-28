# Approval Center

> Status: **spec only** (MKT-1E). Not implemented.
> Real persistence and UI live in a later block (MKT-2B+).

The Approval Center is the queue where human owners (agency staff, client)
sign off on artifacts that workflows produce. It is the single mediator
between "draft" and "ship".

---

## 1. Why a separate subsystem

Workflows produce assets at high velocity. Without a queue with explicit
states and audit-trail integration, "approved" becomes a verbal claim. The
Approval Center exists so that:

- Every shipped asset has a recorded approver + timestamp + hash of the
  approved version.
- Reverts are explicit (a `REJECTED` decision must say why).
- Compliance findings (claim audit, brand voice deviations) are visible at
  the approval moment, not buried in an envelope.

---

## 2. State machine

States and allowed transitions:

```
PROPOSED ──▶ IN_REVIEW ──▶ APPROVED
    │             │
    │             ├──▶ REJECTED
    │             │
    │             └──▶ NEEDS_REVISION ──▶ IN_REVIEW
    │
    └──▶ (cancelled before review never enters the system)
```

| State | Set by | Meaning |
|-------|--------|---------|
| `PROPOSED` | The originating agent. | Agent's draft, ready for human attention. |
| `IN_REVIEW` | Approval Center on first human view. | A human has started reviewing. |
| `APPROVED` | Human approver. | Asset may ship. Emits `g_approval_granted`. |
| `REJECTED` | Human approver. | Asset will not ship. Workflow may halt. |
| `NEEDS_REVISION` | Human approver. | Asset must be revised. Returns to the producing agent with the human's notes. |

### 2.1 Disallowed transitions

- `APPROVED → *`. Once approved, an asset is locked. A new version requires a
  new entry (`PROPOSED` again).
- `REJECTED → *`. Same lock semantics. New version = new entry.
- Any backwards transition that would erase the previous human decision.

---

## 3. Approval Item shape (spec only)

```yaml
approval_id: string                      # uuid
client_slug: string
created_at: ISO 8601 UTC
state: PROPOSED | IN_REVIEW | APPROVED | REJECTED | NEEDS_REVISION
artifact_refs:
  - kind: asset|campaign|positioning|report
    entity_id: string
    sha256: string                       # of the approved version
proposed_by: string                      # agent_id or "human:<actor>"
reviewer: string | null                  # filled when state moves out of PROPOSED
decided_at: ISO 8601 UTC | null
decision_notes: string | null
related_workflow_run_id: string | null
related_claim_audit:                     # snapshot of the audit at decision time
  contract_version: claim-audit.v1
  ...
```

Persistence will use the Memory layer (kind: `approval`) and an audit-trail
event of type `note` referencing the approval id. **Not implemented in
MKT-1E.**

---

## 4. Coupling with workflows

A workflow opts in by declaring `approval.human_required_at: [phase_id]`. At
the end of that phase, the workflow stops, an `approval` entity is created in
state `PROPOSED`, and execution does not resume until that approval is in
state `APPROVED`.

If the state lands in `REJECTED`, the workflow run records `status: cancelled`.
If `NEEDS_REVISION`, the producing phase is re-entered with the notes
attached.

---

## 5. Who approves what (default policy)

| Workflow | Phase requiring approval | Default approver role |
|----------|--------------------------|------------------------|
| W1 | `strategy` | Account lead. |
| W3 | `assemble` | Account lead. |
| W4 | — | (none — drafts) |
| W5 | `approval` | Client side + Account lead. |
| W6 | — | (none) |

Roles are informational. v1 does not enforce role membership; the human at
the keyboard is the approver of record.

---

## 6. Audit integration

Every state transition emits an `AuditTrailEvent`:

| Transition | `event_type` | `payload` |
|------------|--------------|-----------|
| `→ IN_REVIEW` | `note` | `{approval_id, action: "review_started", reviewer}` |
| `→ APPROVED` | `note` | `{approval_id, action: "approved", reviewer, sha256_at_decision}` |
| `→ REJECTED` | `note` | `{approval_id, action: "rejected", reviewer, reason}` |
| `→ NEEDS_REVISION` | `note` | `{approval_id, action: "needs_revision", reviewer, notes}` |

Hash chain anchors each decision to its predecessor.

---

## 7. Out of scope for v1

- UI (lives in the Portal — see `portal-roadmap.md`).
- Email/Slack notifications.
- Role-based access enforcement.
- SLA timers / aging policies.
- Bulk approval / multi-artifact bundles.
