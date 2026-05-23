# ADR 0004 — MKT-1D: Storage / Memory Layer + Referential Integrity

- **Status:** Accepted
- **Date:** 2026-05-22
- **Block:** MKT-1D
- **Supersedes:** —
- **Contract:** `memory.v1`

## Context

MKT-1B locked the domain model and MKT-1C locked the operational contracts.
Both blocks deliberately left storage unspecified. A future dispatcher
(MKT-2A) and every agent that needs state will go through this layer, so its
shape directly constrains what becomes easy or painful later.

The block also resolves two items previously deferred:

- **P-1B.2** — Cross-entity referential integrity (now lives in
  `core/memory/referential_integrity.py`).
- **P-1C.1** — Audit trail JSONL persistence (now lives in
  `core/memory/json_file.py`).

## Decision

### D-4.1 — `Memory` is an ABC, not a `Protocol`

Abstract Base Class forces implementations to be explicit. Protocols accept
duck typing and let drift in silently; in a system that aims to swap
backends (JSON ↔ Engram) the cost of forgetting a method must be loud.

### D-4.2 — Generic `(client_slug, kind, entity_id, data)` interface

Instead of typed methods per entity (`put_client`, `put_brand`, …), the
interface is generic. 17 entities × 5 methods = 85 method stubs to maintain;
not worth the IDE convenience. Callers that want typed access build a thin
repository on top.

The interface is also **domain-agnostic**: `core.memory` does not import
`core.domain`. This lets the memory layer evolve independently of model
changes.

### D-4.3 — One JSON file per entity

Alternatives considered:

- **One JSON per kind** (e.g. `clients.json` holding all clients). Rejected:
  every write becomes a read-modify-write of the whole list, contention
  rises sharply with entity count, and there is no path for atomic per-entity
  updates.
- **SQLite single file.** Rejected for `v1`: adds a runtime dep, tooling
  becomes opaque to `cat` / `git diff`, and per-tenant isolation requires
  filtering instead of a separate file tree.

One file per entity gives us cheap per-entity atomic writes, trivial
tailing, and git-friendly diffs during development.

### D-4.4 — Atomic writes via "temp + `os.replace`"

Every entity write goes to a uniquely-named `.tmp` file in the same
directory, is `fsync`'d, then renamed via `os.replace`. This works on POSIX
and Windows, and guarantees that readers see either the previous payload or
the new one — never a half-written file.

### D-4.5 — Audit trail rotates by UTC day, with a `_chain_tail.txt` shortcut

JSONL files are append-only (`mode="a"`, `O_APPEND` semantics on POSIX,
equivalent on Windows). The cost of recomputing `last_audit_hash` from the
JSONL on every append would be O(N); the small `_chain_tail.txt` file stores
the last hash so the operation is O(1) regardless of trail length.

Size-based rotation is out of scope for `v1`. Daily UTC rotation is enough
for any realistic per-client volume.

### D-4.6 — `EngramMemory` scaffolding, no SDK import

`EngramMemory` inherits `Memory` and raises `NotImplementedError` with a
pointer to MKT-2C on every method. The module does NOT import any Engram
SDK or MCP client. Two benefits:

1. Downstream code can be written against `Memory` today and switched to
   Engram by env var later, without an import cycle on the way.
2. The standalone guarantee (`ARCHITECTURE.md` D2) remains true: a clone of
   the repo runs without Engram on disk or installed.

### D-4.7 — Referential integrity via a hardcoded `REFERENCE_MAP`

Alternative considered: annotate Pydantic model fields with metadata
(`Field(json_schema_extra={"ref_to": "audience"})`). Rejected — it would
require modifying every model in MKT-1B retroactively and would couple the
domain model to a concern (storage refs) it deliberately avoids.

Instead, the map lives in one file (`core/memory/referential_integrity.py`)
alongside its tests. Adding a reference takes one entry in the map + one
test. This is the right friction level: integrity rules are rare enough
that a central registry stays small, and the map is the only thing a
reviewer must read to understand cross-entity wiring.

### D-4.8 — `Metric.subject_id` not in the map

`Metric.subject_type` selects the target kind dynamically (client,
competitor, channel, campaign, asset, persona, audience). A simple
`(field, target_kind)` rule cannot express the variability. A dedicated
helper (`validate_metric_subject(memory, metric)`) is reasonable but out of
scope for `v1`; it is recorded in PENDING as **P-1D.1**.

### D-4.9 — Errors with `MemoryBackendError` base, not `MemoryError`

Python's builtin `MemoryError` represents out-of-memory conditions. Naming a
storage exception the same would shadow it and confuse readers. The base is
`MemoryBackendError`; subclasses are `EntityNotFound`, `IntegrityError`,
`AuditChainError`.

The `EntityNotFound` name is kept (ruff N818 silenced via per-line `noqa`)
because it mirrors the idiomatic pattern used by SQLAlchemy
(`NoResultFound`) and Django (`DoesNotExist`) — readers recognize the
shape.

### D-4.10 — Schema migration policy is deferred

`_meta.json` carries `contract_version` so future code can detect old client
folders. No migration runner ships in `v1`. When the layout needs to
change, the migration will live in `core/memory/migrations/` — that is the
agreed home, not a decision to be made then.

### D-4.11 — Storage requires `event.client_slug` for audit events

The audit contract (`audit-trail.v1`) allows `event.client_slug == None`
because some events are cross-tenant in theory. The JSON file storage,
however, is per-tenant by design and has nowhere to route `None` events
without picking a default. `JsonFileMemory.append_audit_event` therefore
raises `ValueError` when `client_slug` is `None`. A future backend that
supports a `_shared` tenant could relax this.

## Alternatives considered

- **`Protocol` instead of `ABC`.** Too permissive; loses explicit
  implementation contract. (D-4.1)
- **Typed-per-entity API.** Too much boilerplate, wrong layer. (D-4.2)
- **Aggregated JSON per kind / SQLite single file.** Higher contention, no
  per-entity atomic writes, weaker dev ergonomics. (D-4.3)
- **Annotate Pydantic models for refs.** Couples domain to storage concerns
  and forces retro-edits to MKT-1B. (D-4.7)
- **Compute `last_audit_hash` from JSONL every time.** O(N) appends → O(N²)
  workload. The tail file is a small win that pays for itself. (D-4.5)

## Consequences

- A dispatcher (MKT-2A) can spin up against a temp dir and produce a fully
  audited transcript with no external dependencies.
- An EngramMemory implementation later only has to satisfy the same eight
  methods to swap in.
- Migrations are constrained to live in one place when they appear.
- Cross-process concurrency remains explicitly unsupported — when it
  becomes a need (multi-worker dispatcher, web entry point) a new ADR will
  govern the upgrade.

## Out of scope for MKT-1D

- CLI for memory operations (a `mkt memory inspect` command would be useful
  but lives in MKT-2A).
- Encryption at rest.
- Cross-process / cross-host concurrency.
- Real `EngramMemory` implementation (MKT-2C).
- Migration runner (deferred until a real migration appears).
- Dynamic `Metric.subject_id` validation (PENDING P-1D.1).
