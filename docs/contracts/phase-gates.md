# Phase Gates — Contract `phase-gate.v1`

> Version: **v1** (MKT-1C).
> Implementation: `core/contracts/phase_gate.py`.
> Breaking changes bump to `phase-gate.v2`.

A phase gate is a **predicate** evaluated between workflow phases. If it
fails, the workflow halts with explicit blockers.

This contract defines three shapes:

| Shape | What it is |
|-------|------------|
| `PhaseGate` | The declaration of a check (no evaluation). |
| `PhaseGateResult` | The outcome of evaluating a gate. |
| `PhaseTransition` | A bundle of gate results that decides a phase advance. |

The contract is **descriptive only**. It does NOT evaluate predicates.
Evaluation lives in the future dispatcher (MKT-2A+).

---

## 1. `PhaseGate`

```jsonc
{
  "contract_version": "phase-gate.v1",
  "id": "g_envelope_present_fase_3",     // unique within a workflow
  "name": "Envelope present after agent run",
  "phase": "fase_3",
  "predicate_kind": "envelope_present",
  "params": { "agent": "copywriter" },   // kind-specific
  "severity": "blocking|warning",
  "description": "..."
}
```

### 1.1 Field rules

| Field | Required | Rule |
|-------|----------|------|
| `contract_version` | Yes | Must equal `"phase-gate.v1"`. |
| `id` | Yes | Non-empty, ≤200 chars. Unique within a workflow (the model does NOT enforce uniqueness across gates — the workflow loader does). |
| `name` | Yes | Non-empty, ≤300 chars. Human-readable. |
| `phase` | Yes | Phase identifier (free-form string). |
| `predicate_kind` | Yes | One of the values in §2. |
| `params` | No | `dict[str, str]`. Kind-specific arguments. |
| `severity` | No | `blocking` (default) halts the phase; `warning` only logs. |

---

## 2. Predicate catalogue

The `predicate_kind` field is an enum. Each value names a class of check the
future dispatcher will know how to evaluate. Adding a kind is additive (still
`v1`); removing one is breaking.

| Kind | Params | Meaning |
|------|--------|---------|
| `envelope_present` | `agent` | An envelope from this agent has been emitted in the current phase. |
| `status_equals` | `agent`, `expected_status` | The envelope from this agent has the given status (`completado`/`PASS`/etc.). |
| `claims_audit_present` | `agent` | The envelope from this agent carries a non-null `claims_audit`. |
| `no_unsafe_claims` | `agent` | The envelope from this agent has `claims_audit.blocks_emission == False`. |
| `memory_key_exists` | `topic_key`, `backend` | A given memory key has been written by some agent. |
| `artifact_exists` | `path` (relative to client root) | A file artifact exists on disk. |
| `custom` | arbitrary | Escape hatch; the dispatcher resolves the implementation by `params["fn_name"]`. |

Specific gates per phase are not declared in MKT-1C — each future block that
introduces a phase will add its own gate set.

---

## 3. `PhaseGateResult`

```jsonc
{
  "contract_version": "phase-gate.v1",
  "gate_id": "g_envelope_present_fase_3",
  "passed": true,
  "blockers": [],                         // required non-empty when passed=false
  "evaluated_at": "2026-05-22T12:00:00+00:00",
  "details": {                            // optional, arbitrary str->str
    "envelope_id": "abc123"
  }
}
```

### 3.1 Field rules

| Field | Required | Rule |
|-------|----------|------|
| `gate_id` | Yes | References a `PhaseGate.id`. Existence NOT enforced by the model. |
| `passed` | Yes | Boolean. |
| `blockers` | Conditional | When `passed=False`, MUST be non-empty. |
| `evaluated_at` | Yes | Timezone-aware ISO 8601. |
| `details` | No | `dict[str, str]`. Diagnostic info for the audit trail. |

---

## 4. `PhaseTransition`

```jsonc
{
  "contract_version": "phase-gate.v1",
  "from_phase": "fase_2",
  "to_phase": "fase_3",
  "gate_results": [ ...PhaseGateResult... ]
}
```

### 4.1 Field rules

| Field | Required | Rule |
|-------|----------|------|
| `gate_results` | No | `gate_id` values MUST be unique across the list. |

`PhaseTransition.passed` is a computed property: true iff every result passed.

---

## 5. Severity policy

| Severity | When a gate of this severity fails |
|----------|------------------------------------|
| `blocking` | The transition fails. The dispatcher MUST halt. |
| `warning` | The transition still passes if all *blocking* gates passed. The warning is logged to the audit trail. |

A `PhaseTransition.passed` reflects the all-gates view. Callers that wish to
separate blocking from warning failures must inspect each `PhaseGateResult`'s
gate severity (lookup via the workflow definition).

---

## 6. Validators

| Function | Returns / Raises |
|----------|------------------|
| `validate_phase_gate(payload)` | `(bool, list[ContractErrorPayload])` |
| `validate_phase_gate_result(payload)` | same |
| `validate_phase_transition(payload)` | same |
| `validate_phase_transition_strict(payload)` | `PhaseTransition` or `ContractError` |

---

## 7. Examples

### 7.1 Passing transition

```json
{
  "contract_version": "phase-gate.v1",
  "from_phase": "fase_2",
  "to_phase": "fase_3",
  "gate_results": [
    {"contract_version": "phase-gate.v1", "gate_id": "g1", "passed": true, "evaluated_at": "2026-05-22T12:00:00+00:00", "blockers": []},
    {"contract_version": "phase-gate.v1", "gate_id": "g2", "passed": true, "evaluated_at": "2026-05-22T12:00:01+00:00", "blockers": []}
  ]
}
```

### 7.2 Failing result (invalid — blocker missing)

```json
{"contract_version": "phase-gate.v1", "gate_id": "g1", "passed": false, "evaluated_at": "2026-05-22T12:00:00+00:00", "blockers": []}
```

→ `ContractError(code=invariant_violation, message="failed gate result must include at least one blocker")`.

---

## 8. Versioning

- New `predicate_kind` value: additive, still `v1`.
- Removing or renaming any field or kind: bump to `phase-gate.v2`.
