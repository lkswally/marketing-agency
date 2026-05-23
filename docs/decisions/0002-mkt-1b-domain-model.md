# ADR 0002 — MKT-1B: Canonical Domain Model

- **Status:** Accepted
- **Date:** 2026-05-22
- **Block:** MKT-1B
- **Supersedes:** —
- **Contract:** `domain-model.v1`

## Context

MKT-1A locked architecture and the multi-tenant scoping rule (D3) but left the actual entities undefined. Without a canonical domain model, every future agent and skill would invent its own shape for `Brand`, `Campaign`, `Metric`, etc., and Engram would fragment into inconsistent topic keys.

This block defines the 17 entities, their fields, validation rules, and the boundary between what the model knows and what the runtime knows.

## Decision

### D-2.1 — 17 entities, one file each

One Pydantic class per file in `core/domain/`. The 17 entities are: `Client`, `MarketingBrief`, `Brand` (+ embedded `BrandVoice`), `Audience`, `Persona`, `Competitor`, `Offer`, `Positioning`, `Campaign`, `Channel`, `Asset`, `Claim`, `Evidence`, `Metric`, `DigitalFootprintSnapshot`, `GrowthBacklogItem`, `Report`.

`Persona` lives in its own file (`persona.py`), not folded into `audience.py`. It has its own lifecycle and may be referenced independently by future agents.

### D-2.2 — Pydantic v2 only, no ORM

Models are pure Pydantic. No ORM, no SQLAlchemy, no DB columns. Persistence is deferred to MKT-1D's `Memory` interface.

### D-2.3 — IDs and slugs

- Opaque IDs are UUID4 hex via `new_id()`.
- Slugs are human-readable, lowercase ASCII with dashes, used only at the tenant level (`client_slug`).
- Reserved slugs: `_shared` (cross-client artifacts).

### D-2.4 — References by id, never embedded

Entities reference each other through scalar ids/slugs. Embedded objects are forbidden (except `BrandVoice` inside `Brand`, which has no independent lifecycle).

Rationale: prevents serialization cycles, keeps each entity sovereign, makes per-entity persistence trivial.

### D-2.5 — `extra="forbid"` everywhere

Unknown fields raise. Rationale: catches typos and rogue keys at the boundary, especially when reading external data into the system later.

### D-2.6 — Timezone-aware datetimes only

Every `datetime` field requires `tzinfo`. Naive datetimes are rejected. Rationale: marketing data spans timezones (clients, campaigns, social posts) and naive timestamps cause silent off-by-day bugs.

### D-2.7 — No cross-entity validation in the model

The model validates **one entity at a time**. It does NOT check that `Campaign.audience_ids` point to real `Audience` rows. That responsibility belongs to the repository layer (MKT-1D+).

Rationale: the model has no I/O. Repository checks need lookups. Mixing the two couples the model to storage.

### D-2.8 — Metrics are integration-agnostic

`Metric` carries `MetricSource` (where data came from) and `MetricCategory` (what it measures). Both are enums. No connector code is implemented in MKT-1B; the enums declare what the system **will** support without committing to **when**.

### D-2.9 — DigitalFootprintSnapshot is a container, not a measurement

A snapshot groups `metric_ids` for a `(subject, date)` pair. It does not embed values. Rationale: same metric can appear in multiple snapshots or reports without duplication.

### D-2.10 — Computed fields stripped on input

`GrowthBacklogItem.ice_score` is a `@computed_field` and ships in JSON output. The `from_json` helper strips computed-field keys before validation so round-trips work despite `extra="forbid"`.

## Alternatives considered

- **Dataclasses instead of Pydantic.** Rejected: validation is the point.
- **Single mega-file `domain.py`.** Rejected: 17 entities + 13 enums in one file is unreadable; tooling and git diffs degrade.
- **`Persona` inside `Audience`.** Rejected: user spec lists Persona as an independent entity (#5); independent file matches that.
- **Inline enums per file.** Rejected: `ChannelType`, `SubjectType`, `MetricSource`/`Category` are reused across multiple entities; central `enums.py` avoids drift.
- **Foreign-key style cross-entity validation in the model.** Rejected: requires lookups, couples model to storage.
- **Strict referential integrity via Pydantic validators.** Rejected: same reason; deferred to repository.

## Consequences

- Downstream blocks (agents, skills, workflows) have a single source of truth for entity shapes.
- The `Memory` interface (MKT-1D) can be designed without rewriting models.
- Claim audit (MKT-3A/3B) plugs in cleanly because `Claim` and `Evidence` already exist.
- Future connectors (GA4, Resend, etc.) only add adapters; the `Metric` shape they target is already final.
- Anything that needs cross-entity integrity must do it explicitly at the repo / runtime layer.

## Out of scope for MKT-1B

- Memory backend implementation (MKT-1D).
- Return Envelope, Phase Gates, Audit Trail specs (MKT-1C).
- Any dispatcher or agent runtime code (MKT-2+).
- Connector code for any `MetricSource` (MKT-6A/6B onwards).
- Schema migration policy / versioned storage migrations (PENDING.md).
