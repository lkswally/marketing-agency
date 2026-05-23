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
