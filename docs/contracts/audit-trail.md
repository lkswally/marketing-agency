# Audit Trail — Contract `audit-trail.v1`

> Version: **v1** (MKT-1C).
> Implementation: `core/contracts/audit_trail.py`.
> Breaking changes bump to `audit-trail.v2`.

The audit trail is an **append-only**, tamper-evident log of significant
events: envelopes received, gates evaluated, phase transitions, claim
verdicts, workflow lifecycle, memory writes, errors.

Each event carries a SHA-256 `hash` over its canonical contents plus the
previous event's hash. This produces a chain that breaks if any past event is
modified.

This contract specifies the **format** of an event and the **hash algorithm**.
It does NOT specify storage. Persistence (JSONL files, rotation, retention)
is deferred to MKT-1D.

---

## 1. Schema

```jsonc
{
  "contract_version": "audit-trail.v1",
  "event_id": "uuid4-hex-32",
  "event_type": "envelope_received|gate_evaluated|phase_transitioned|claim_verdict|workflow_started|workflow_finished|memory_written|error_raised|note",
  "client_slug": "demo-co",          // optional
  "actor": "orchestrator",
  "occurred_at": "2026-05-22T12:00:00+00:00",
  "payload": { /* arbitrary JSON-serializable */ },
  "prev_hash": "<64 hex chars or null>",
  "hash": "<64 hex chars>"
}
```

### 1.1 Field rules

| Field | Required | Rule |
|-------|----------|------|
| `contract_version` | Yes | Must equal `"audit-trail.v1"`. |
| `event_id` | Yes | Non-empty. UUID4-hex when produced via `AuditTrailEvent.build`. |
| `event_type` | Yes | Enum from §2. |
| `client_slug` | No | If present, must satisfy slug rules. |
| `actor` | Yes | Identifier of who emitted the event (agent name or `"human:lucas"`). |
| `occurred_at` | Yes | Timezone-aware ISO 8601 UTC. |
| `payload` | No | Any JSON-serializable dict. |
| `prev_hash` | No | Null for the first event of a chain; otherwise the previous event's `hash`. Pattern: `^[a-f0-9]{64}$`. |
| `hash` | Yes | SHA-256 hash computed per §3. Pattern: `^[a-f0-9]{64}$`. Validated on construction. |

---

## 2. Event type vocabulary

| Type | Emitted when |
|------|--------------|
| `envelope_received` | Dispatcher accepts an agent's Return Envelope. |
| `gate_evaluated` | A `PhaseGate` produced a `PhaseGateResult`. |
| `phase_transitioned` | A `PhaseTransition` advanced (or failed to advance). |
| `claim_verdict` | A claim was audited (severity + verdict assigned). |
| `workflow_started` | A workflow run began. |
| `workflow_finished` | A workflow run reached a terminal status. |
| `memory_written` | A memory write occurred (any backend). |
| `error_raised` | A `ContractError` (or any other tracked error) was raised. |
| `note` | Free-form annotation. Used for human notes and non-categorized events. |

Adding a new event type is additive within `v1`. Removing or renaming an
existing type is breaking.

---

## 3. Hash algorithm

The hash is **SHA-256** over a **canonical JSON** serialization of the event's
core fields.

### 3.1 Canonical form

```
core = {
  "contract":    "audit-trail.v1",
  "event_id":    <event_id>,
  "event_type":  <event_type-string>,
  "client_slug": <client_slug or null>,
  "actor":       <actor>,
  "occurred_at": <occurred_at as ISO 8601 string>,
  "payload":     <payload dict>,
  "prev_hash":   <prev_hash or null>
}
```

Serialized with: `json.dumps(core, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)`.

Notes:
- `occurred_at` is hashed as its **ISO 8601 string**, NOT the raw datetime.
  Same instant, different timezone string → different hash.
- `payload` is serialized recursively with the same canonical rules.
- `default=str` allows hashing payloads that contain `datetime`/UUID values
  by stringifying them.

### 3.2 Construction

```python
from datetime import UTC, datetime
from core.contracts import AuditTrailEvent, AuditEventType

ev = AuditTrailEvent.build(
    event_type=AuditEventType.WORKFLOW_STARTED,
    actor="orchestrator",
    occurred_at=datetime.now(UTC),
    client_slug="demo-co",
    payload={"workflow": "onboarding"},
    prev_hash=last_event_hash,  # or None for the first event
)
# ev.hash is auto-computed and verified by the model.
```

Direct construction (e.g. when reading from disk) re-verifies `hash` against
the computed value and raises if they disagree.

---

## 4. Chain semantics

A chain is a list of events `[e_0, e_1, ..., e_N]` such that:

1. `e_0.prev_hash == null`
2. For all `i > 0`: `e_i.prev_hash == e_{i-1}.hash`

`core.contracts.verify_chain(events) -> list[int]` returns the indices where
the chain is broken (empty list = valid chain).

The chain detects:
- Modifications to past events (hash no longer matches).
- Insertions (`prev_hash` of next event mismatches).
- Deletions (same as insertions, detected at the next index).

It does NOT detect:
- A consistent replay of the entire chain (the chain itself is internally
  valid). External anchoring is out of scope for `v1`.

---

## 5. Persistence (out of scope for `v1`)

`v1` does not specify how events are stored. MKT-1D will define:

- File layout: `data/clients/<slug>/audit/<YYYY-MM-DD>.jsonl`
- Append-only write semantics with `O_APPEND`.
- Rotation, retention, and read-back routines.

Until MKT-1D ships, events are emitted in-memory only.

---

## 6. Validators

| Function | Returns / Raises |
|----------|------------------|
| `validate_audit_event(payload)` | `(bool, list[ContractErrorPayload])` |
| `validate_audit_event_strict(payload)` | `AuditTrailEvent` or `ContractError` |
| `verify_chain(events)` | `list[int]` of break indices |

---

## 7. Example

```json
{
  "contract_version": "audit-trail.v1",
  "event_id": "9f4e7a2c1b3d4e5f6a7b8c9d0e1f2a3b",
  "event_type": "workflow_started",
  "client_slug": "demo-co",
  "actor": "orchestrator",
  "occurred_at": "2026-05-22T12:00:00+00:00",
  "payload": {"workflow": "onboarding", "run_id": "abc"},
  "prev_hash": null,
  "hash": "7d3a..."  // SHA-256 of canonical(core)
}
```

---

## 8. Versioning

- New `event_type` value: additive, still `v1`.
- Change in hashing algorithm or canonical form: breaking → `audit-trail.v2`.
