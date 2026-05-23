# PENDING — Items detected but deferred

Things noticed during a block that are out of scope for that block. Each item
must say which block introduced it and which (estimated) block will resolve it.

---

## From MKT-1B (domain model)

### P-1B.1 — Schema versioning / migration policy
- **Introduced:** MKT-1B
- **Why deferred:** No persistence layer exists yet. Migration only matters once we store entities.
- **Resolves at:** MKT-1D (Memory backend) at the earliest, more likely a dedicated block before MKT-3.
- **Sketch:** Each persisted entity payload should carry the `domain-model.vN` it was written with. The repository layer is responsible for upgrading on read.

### P-1B.2 — Cross-entity referential integrity
- **Introduced:** MKT-1B
- **Why deferred:** The domain model has no I/O and cannot look up other entities.
- **Resolves at:** MKT-1D (Memory backend / repository).
- **Sketch:** Repository helpers like `assert_audience_exists(audience_id)` invoked from a thin validation service before persisting `Campaign`, `Metric`, etc.

### P-1B.3 — JSON Schema export to disk for external consumers
- **Introduced:** MKT-1B
- **Why deferred:** Optional. No external consumer exists yet.
- **Resolves at:** MKT-1C (contracts block) or on-demand.
- **Sketch:** `python -m core.domain export-schemas > docs/contracts/schemas/*.json`.

### P-1B.4 — Seed / fixture loader CLI
- **Introduced:** MKT-1B
- **Why deferred:** No runtime in MKT-1B. Demo fixtures live in `tests/domain/conftest.py` only.
- **Resolves at:** MKT-2A (minimal dispatcher).
- **Sketch:** A CLI that takes the test fixtures and writes a demo client to `data/clients/default/`.

### P-1B.5 — `.env.example` (carry-over from MKT-1A)
- **Introduced:** MKT-1A (hook blocked write).
- **Why deferred:** `config-protection.js` hook refuses to let Claude write `.env*` files.
- **Resolves at:** anytime (manual user action).
- **Sketch:** Template should include `MKT_MEMORY_BACKEND=json`, `MKT_LOG_LEVEL=INFO`, `MKT_BRIDGE_ATLAS=0`. Future blocks will append provider keys.

### P-1B.6 — Engram session registration for `marketing-agency-os` project
- **Introduced:** MKT-1A (Engram rejected the project name).
- **Why deferred:** `.engram/config.json` is now in place but Engram won't register the project until Claude Code is opened from the repo root once.
- **Resolves at:** anytime (manual user action — open Claude Code from `D:\ProyectosIA\MARKETING-AGENCY-OS\`).

---

## From MKT-1C (operational contracts)

### P-1C.1 — Audit trail JSONL persistence
- **Introduced:** MKT-1C
- **Why deferred:** `audit-trail.v1` defines the event shape and hash chain; storage (file layout, append-only writes, rotation, retention) is a memory-backend concern.
- **Resolves at:** MKT-1D (Memory backend).
- **Sketch:** `data/clients/<slug>/audit/<YYYY-MM-DD>.jsonl`, `O_APPEND`, daily rotation, retention configurable per client.

### P-1C.2 — Strictness mode enforcers (qa_strict / dev_strict / design_strict / claim_strict)
- **Introduced:** MKT-1C
- **Why deferred:** Modes are caller policy (D-3.8), not schema. They belong in the dispatcher.
- **Resolves at:** MKT-2A (minimal dispatcher) for the first mode, the rest as agents land.

### P-1C.3 — `predicate_kind` evaluators
- **Introduced:** MKT-1C
- **Why deferred:** The contract declares the kinds; evaluating them needs runtime state (envelopes seen, memory, filesystem).
- **Resolves at:** MKT-2A onwards. Each block that introduces a phase ships the predicate(s) it needs.

### P-1C.4 — Hash classifier fragility
- **Introduced:** MKT-1C
- **Why deferred:** `_classify` in `validators.py` matches on Pydantic error message substrings ("hash mismatch", "timezone-aware", "duplicate"). If the message wording in our own validators changes, classification silently degrades.
- **Resolves at:** as needed. Tests pin the current behavior. A more robust path would surface a custom error type from each `model_validator`, but that's overhead disproportionate to the risk at this stage.

### P-1C.5 — Human override field for blocked claim audits
- **Introduced:** MKT-1C
- **Why deferred:** The `blocks_emission` policy is strict by design in `v1`. A human override (signed acknowledgement of a risky claim) is a workflow concern.
- **Resolves at:** MKT-3B (claim audit enforcement in envelope) at earliest.

### P-1C.6 — External anchoring of audit chain
- **Introduced:** MKT-1C
- **Why deferred:** The hash chain detects in-place tampering but not a wholesale replay. Anchoring (e.g. publishing daily root hashes to a trusted store) is out of scope.
- **Resolves at:** not scheduled. Revisit when compliance requirements demand it.
