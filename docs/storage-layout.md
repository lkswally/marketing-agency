# Storage Layout — `JsonFileMemory`

> Backend: `core.memory.JsonFileMemory`.
> Contract: `memory.v1`.
> All paths are relative to the backend's `root` argument (typically
> `data/clients/`).

---

## 1. Tree

```
<root>/
└── <client_slug>/                      # one folder per tenant
    ├── _meta.json                      # backend metadata
    ├── client/                         # one folder per entity kind
    │   └── <entity_id>.json            # one file per entity
    ├── brand/
    │   └── <entity_id>.json
    ├── audience/
    ├── persona/
    ├── brief/
    ├── competitor/
    ├── offer/
    ├── positioning/
    ├── campaign/
    ├── channel/
    ├── asset/
    ├── claim/
    ├── evidence/
    ├── metric/
    ├── footprint/
    ├── backlog/
    ├── report/
    └── audit/
        ├── 2026-05-22.jsonl            # one JSONL per UTC day, append-only
        ├── 2026-05-23.jsonl
        └── _chain_tail.txt             # hex hash of the latest appended event
```

A folder for a given `<kind>` is created lazily on first `put`. Kinds with no
entities yet do not appear on disk.

The `_meta.json`, `audit/` directory, and `_chain_tail.txt` are all owned by
the backend. Callers should not edit them manually.

---

## 2. File formats

### 2.1 Entity file — `<kind>/<entity_id>.json`

Pretty-printed JSON (2-space indent, sorted keys, trailing newline). The
payload is exactly what was passed to `put`; the backend adds no envelope.

Example:

```json
{
  "created_at": "2026-05-22T12:00:00+00:00",
  "id": "9f4e7a2c1b3d4e5f6a7b8c9d0e1f2a3b",
  "name": "Demo Co.",
  "slug": "demo-co",
  "updated_at": "2026-05-22T12:00:00+00:00"
}
```

Writes are atomic: a temporary file is created in the same directory and
then renamed via `os.replace`. Readers either see the previous version or
the new one, never a half-written file.

### 2.2 `_meta.json`

Created on the first `put` for a client.

```json
{
  "client_slug": "demo-co",
  "contract_version": "memory.v1",
  "created_at": "2026-05-22T12:00:00-03:00"
}
```

Not rewritten on subsequent writes. Acts as a version marker for future
migrations.

### 2.3 Audit JSONL — `audit/YYYY-MM-DD.jsonl`

One audit event per line, each line a single-line JSON serialization of an
`AuditTrailEvent` (see `audit-trail.md`). Lines are appended in the order
they are received and never rewritten.

Example (single line shown wrapped for readability):

```jsonc
{"contract_version":"audit-trail.v1","event_id":"9f4e...","event_type":"workflow_started",
 "client_slug":"demo-co","actor":"orchestrator","occurred_at":"2026-05-22T12:00:00+00:00",
 "payload":{"workflow":"onboarding"},"prev_hash":null,"hash":"7d3a..."}
```

### 2.4 `audit/_chain_tail.txt`

Single-line text file with the SHA-256 hex hash of the last appended event,
followed by a newline:

```
7d3a8c5b... (64 hex chars)
```

Updated atomically after each successful append. Allows `last_audit_hash`
to return in O(1) without re-reading the entire chain.

---

## 3. Rotation

Audit JSONL files rotate by UTC date: an event with
`occurred_at.date() == 2026-05-23` lands in `audit/2026-05-23.jsonl`. There
is no size-based rotation in `memory.v1`. If a workload produces enough
events per day to make a file unwieldy, that is a signal to revisit (likely
beyond `v1`).

Entity files never rotate — one file per entity, lifetime-of-the-client.

---

## 4. Naming rules

| Token | Rule | Enforced by |
|-------|------|-------------|
| `<client_slug>` | `^[a-z0-9]+(?:-[a-z0-9]+)*$` minus reserved `_shared` | `core.domain.base.validate_slug` |
| `<kind>` | `^[a-z][a-z0-9_]{0,63}$` | `core.memory.validate_kind` |
| `<entity_id>` | `^[A-Za-z0-9._-]{1,128}$` | `core.memory.json_file._validate_entity_id` |

These rules block directory traversal and path injection attacks at the
backend layer; callers do not need to sanitize.

---

## 5. Concurrency

`memory.v1` assumes **single-process** sequential access:

- Multiple readers in one process: safe.
- Multiple writers in one process, serialized: safe.
- Multiple processes writing concurrently: undefined. Use external locking
  or upgrade to a backend designed for concurrent access (out of scope).
- A single audit chain across processes: undefined. The chain tail file is
  not locked.

---

## 6. Layout independence from the contract

The layout described here is specific to `JsonFileMemory`. Other backends
(e.g. `EngramMemory` once implemented) are free to use any storage they want
as long as they uphold the `memory.v1` interface. Callers should never
read or write these paths directly — always go through the `Memory` API.

---

## 7. Example: full session

Working directory `D:\ProyectosIA\MARKETING-AGENCY-OS\` (example path):

```python
from datetime import UTC, datetime
from pathlib import Path

from core.contracts import AuditEventType, AuditTrailEvent
from core.memory import JsonFileMemory

mem = JsonFileMemory(Path("data/clients"))

# Write a client.
mem.put("demo-co", "client", "c1", {"slug": "demo-co", "name": "Demo Co."})

# Append an audit event.
ev = AuditTrailEvent.build(
    event_type=AuditEventType.MEMORY_WRITTEN,
    actor="orchestrator",
    occurred_at=datetime.now(UTC),
    client_slug="demo-co",
    payload={"kind": "client", "id": "c1"},
    prev_hash=mem.last_audit_hash("demo-co"),
)
mem.append_audit_event(ev)
```

Disk state after the snippet:

```
data/clients/demo-co/
├── _meta.json
├── client/
│   └── c1.json
└── audit/
    ├── 2026-05-22.jsonl
    └── _chain_tail.txt
```
