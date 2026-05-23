# ADR 0003 — MKT-1C: Operational Contracts

- **Status:** Accepted
- **Date:** 2026-05-22
- **Block:** MKT-1C
- **Supersedes:** —
- **Contracts:** `envelope.v1`, `phase-gate.v1`, `audit-trail.v1`, `claim-audit.v1`, `workflow-run.v1`

## Context

MKT-1B locked the domain model (entities). MKT-1C locks the **operational
contracts** — the shapes used by future workflows, agents and the dispatcher
to communicate with each other.

Without these contracts the dispatcher (MKT-2A) would invent ad-hoc envelopes
and gate shapes, audit trails would lack a tamper-evident structure, and
compliance enforcement (MKT-3A/3B) would have nowhere to plug in.

## Decision

### D-3.1 — One contract version per concern

Each contract is versioned independently: `envelope.v1`, `phase-gate.v1`,
`audit-trail.v1`, `claim-audit.v1`, `workflow-run.v1`. Every payload carries a
`contract_version` field pinned by a `Literal["..."]` type. A wrong value is
rejected with `version_mismatch`.

Rationale: a breaking change in one contract should not force a major bump in
the others. Mixed-version corpuses can be dispatched by reading
`contract_version`.

### D-3.2 — Validators are pure functions

Every validator in `core/contracts/validators.py` is `dict -> (ok, errors)` or
`dict -> instance | raise`. Zero I/O, zero filesystem, zero network. They
can be safely called in tight loops and from any context (CI, dispatcher,
inline checks).

### D-3.3 — `ContractError` is dual: exception and payload

`ContractErrorPayload` is a Pydantic model (serializable, hashable into the
audit trail). `ContractError` is a Python exception that wraps a payload.
This lets the same error be `raise`d at workflow boundaries and `return`ed at
batch boundaries without translation.

### D-3.4 — Hash chain over canonical JSON

The audit trail chain hashes SHA-256 over a canonical JSON serialization:
sorted keys, no whitespace, UTF-8, `default=str` for non-natively-serializable
values, and the dependency on the **ISO 8601 string** of `occurred_at` (not
the raw datetime). The canonical form is documented in
`docs/contracts/audit-trail.md` so any future implementation in another
language produces identical hashes.

### D-3.5 — Hash verification is a model invariant, not a flag

`AuditTrailEvent` re-verifies its own hash on construction. There is no
"trust me" mode. To build a fresh event with the hash auto-computed, use
`AuditTrailEvent.build(...)`.

Rationale: events read from disk are validated by the same code path that
produced them, eliminating drift.

### D-3.6 — Envelope statuses keep ATLAS-compatible vocabulary

`completado`, `fallido`, `PASS`, `FAIL`. `completado/fallido` for generic
agents, `PASS/FAIL` for validators. This intentionally mirrors ATLAS's
existing Return Envelope vocabulary so that a future bridge (MKT-6C) does not
need value translation. We inherit the **shape** discipline of ATLAS without
inheriting its code (`ARCHITECTURE.md` D6).

### D-3.7 — Failure envelopes MUST explain themselves

When `status` is `fallido`/`FAIL`, the envelope must carry at least one
`bloqueadores` entry or a non-empty `notes`. Silent failures produce silent
audit trails; silent audit trails are how compliance work rots.

### D-3.8 — Strictness modes are caller policy, not schema

The base envelope schema is the same regardless of mode. Modes like
`qa_strict`, `dev_strict`, `design_strict`, `claim_strict` are **additional
rules layered on by the caller** (dispatcher). They are documented in
`docs/contracts/return-envelope.md` §3 for consistency but not implemented
inside the model.

Rationale: modes change more often than schemas. Keeping them out of the
model lets us tune dispatcher policy without bumping `envelope.v1`.

### D-3.9 — `ClaimAudit` is a block, not a top-level entity

It lives **inside** an envelope, not as a standalone artifact. The shape
exists as a contract (transport) and not as a `core.domain` entity because
audits are produced and consumed in the same exchange. The repository can
still persist the underlying `Claim`/`Evidence` entities; the audit block is
the join-friendly view passed across the wire.

### D-3.10 — No cross-contract referential integrity

`gate_id` referenced in a `PhaseGateResult` may not correspond to any
`PhaseGate`. `claim_id` in a `ClaimAuditItem` may not correspond to any
stored `Claim`. The contracts do NOT verify these joins. The repository
layer (MKT-1D+) is responsible.

Rationale: the contracts have no access to storage. Lifting integrity into
them would couple them to a backend.

### D-3.11 — `predicate_kind` catalogue is open but additive

A new `PredicateKind` enum member is an additive change (still `v1`).
Removing a kind is breaking. The catalogue is intentionally small in v1;
each future block that introduces a phase will add the kinds it needs.

### D-3.12 — `WorkflowRunStatus` distinguishes "running" from terminal states

`running` is not terminal and does not require `finished_at`. The three
terminal statuses (`succeeded`, `failed`, `cancelled`) all require
`finished_at`. Additionally, `succeeded` rejects any step in a failed
envelope status — a "succeeded" run with a failed step is a contradiction.

### D-3.13 — Hash classifier inspects the message first

Pydantic's `model_validator` emits a generic `value_error` type regardless of
the semantic problem. The classifier in `validators.py` therefore inspects
the message text first (for known substrings: "hash mismatch",
"timezone-aware", "duplicate"), then falls back to the `error.type` map.
This is fragile to message changes; the tests pin the classification.

## Alternatives considered

- **One unified contract for everything.** Rejected: coupling forces lockstep
  versioning; ergonomics worsen as the surface grows.
- **JSON Schema as the source of truth, Pydantic generated from it.**
  Rejected for v1: Pydantic-first keeps the round-trip and the validators
  inline with the model. JSON Schema export remains available via
  `model_json_schema()` and is listed in PENDING for on-demand use.
- **HMAC-based audit chain instead of SHA-256.** Rejected: an HMAC needs a
  key; key management is out of scope for `v1`. SHA-256 over canonical JSON
  detects tampering in the absence of an attacker who can replay the entire
  chain. External anchoring is a future concern.
- **Modes implemented inside the envelope model.** Rejected: ties dispatcher
  policy to the schema; both evolve at different speeds.
- **`ClaimAudit` as a `core.domain` entity.** Rejected: audits are
  transport-shaped (denormalized for one exchange); persisting them duplicates
  data already present in `Claim`/`Evidence`.

## Consequences

- The dispatcher (MKT-2A) can be written against five stable contracts.
- The claim-validator subsystem (MKT-3A) plugs in by emitting `ClaimAudit`
  blocks; the dispatcher already knows how to read them.
- The audit trail (MKT-1D persistence) only needs to specify file layout —
  the event shape is fixed.
- Workflow summaries (MKT-2C+) plug in without further contract changes.
- Any future ATLAS bridge (MKT-6C) maps to envelope+claim_audit one-to-one.

## Out of scope for MKT-1C

- Memory backend / persistence of any contract artifact (MKT-1D).
- Dispatcher code or workflow execution (MKT-2A).
- Claim-validator implementation (MKT-3A).
- ATLAS bridge surface (MKT-6C).
- JSON-Schema export to disk (PENDING.md, P-1B.3 still applies).
