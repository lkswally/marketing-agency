# Memory — Contract `memory.v1`

> Version: **v1** (MKT-1D).
> Implementation: `core/memory/` (`base.py`, `json_file.py`, `engram.py`).
> Breaking changes bump to `memory.v2`.

The Memory contract is the **single interface** that callers use to read and
write per-client state and to append events to the audit trail. It is
domain-agnostic: the interface deals in plain `dict` payloads and string
``kind`` labels. Pydantic ↔ dict conversion is the caller's job (a future
repository layer will own that, MKT-2A+).

---

## 1. Interface

```python
class Memory(ABC):
    # Entity CRUD
    def put(self, client_slug: str, kind: str, entity_id: str, data: dict) -> None: ...
    def get(self, client_slug: str, kind: str, entity_id: str) -> dict: ...
    def list(self, client_slug: str, kind: str) -> list[dict]: ...
    def exists(self, client_slug: str, kind: str, entity_id: str) -> bool: ...
    def delete(self, client_slug: str, kind: str, entity_id: str) -> None: ...

    # Audit trail (append-only)
    def append_audit_event(self, event: AuditTrailEvent) -> None: ...
    def read_audit_events(self, client_slug: str, day: date | None = None) -> list[AuditTrailEvent]: ...
    def last_audit_hash(self, client_slug: str) -> str | None: ...
```

### 1.1 Parameter rules

| Parameter | Rule |
|-----------|------|
| `client_slug` | Must satisfy slug rules (`core.domain.base.validate_slug`). Reserved (`_shared`) is rejected. |
| `kind` | Must match `^[a-z][a-z0-9_]{0,63}$` (`core.memory.validate_kind`). Lowercase, alphanumeric, underscore. |
| `entity_id` | Must match `^[A-Za-z0-9._-]{1,128}$`. Prevents directory traversal. |
| `data` | JSON-serializable dict. The contract does not enforce schema — that is the caller's responsibility. |
| `event` (in `append_audit_event`) | A valid `AuditTrailEvent` (audit-trail.v1). `event.client_slug` MUST be set; storage rejects `None`. |

---

## 2. Behavioral guarantees

| Concern | Guarantee |
|---------|-----------|
| **Atomicity** | Every entity write is atomic: callers reading concurrently see either the old payload or the new one, never a partial write. (Backed by write-to-temp + `os.replace` in `JsonFileMemory`.) |
| **Append-only audit** | Audit JSONL files are opened in append mode (`O_APPEND`). Past lines are never rewritten by the backend. |
| **Hash chain** | `append_audit_event` rejects an event whose `prev_hash` does not match the stored chain tail for that client (`AuditChainError`). |
| **Multi-tenant isolation** | All state for client `<slug>` lives under a folder/path keyed by `<slug>`. Two clients cannot collide on a `(kind, entity_id)` pair. |
| **Stable list order** | `list(...)` returns entities in sorted-by-id order. |
| **Idempotent put** | `put` overwrites silently. Callers that need optimistic concurrency must layer it on top (out of scope for v1). |

What this contract does **not** promise:

- Cross-process concurrency safety.
- Cross-entity referential integrity at write time (see `referential_integrity.py` for explicit checks).
- Schema validation of the payload (use `core.domain` / `core.contracts` on the caller side).
- Encryption at rest.

---

## 3. Exceptions

| Exception | Raised when |
|-----------|-------------|
| `MemoryBackendError` | Base class; not raised directly. |
| `EntityNotFound` | `get` or `delete` cannot find the entity. |
| `IntegrityError` | Backend invariants are violated (reserved for future use). |
| `AuditChainError` | The audit chain tail disagrees with the event's `prev_hash`, or a JSONL file is unreadable. |

Validation errors (bad slug, bad kind, bad id, naive datetime) surface as
plain `ValueError` so callers can catch them uniformly via Python's standard
exception flow.

---

## 4. Backends

### 4.1 `JsonFileMemory` (default)

Local filesystem backend. See `docs/storage-layout.md` for the on-disk layout.

```python
from pathlib import Path
from core.memory import JsonFileMemory

mem = JsonFileMemory(Path("data/clients"))
mem.put("demo-co", "client", "c1", {"slug": "demo-co", "name": "Demo Co."})
```

### 4.2 `EngramMemory` (scaffolding, not implemented in v1)

Exists only so callers can import the symbol today. Every method raises
`NotImplementedError` with a pointer to MKT-2C. Activation will be via
`MKT_MEMORY_BACKEND=engram` (see `ARCHITECTURE.md` D2).

---

## 5. Referential integrity (helper API)

Outbound references are NOT enforced by the model layer (ADR 0002 D-2.7).
Pure helpers in `core.memory.referential_integrity` let callers verify them
on demand:

```python
from core.memory import check_client_integrity, find_missing_references

# One entity at a time:
issues = find_missing_references(mem, "demo-co", "campaign", campaign_payload)

# Or the whole tenant:
issues = check_client_integrity(mem, "demo-co")
```

Each issue is a `MissingReference(source_kind, source_id, field_path,
target_kind, target_id, reason)`. The helpers are **read-only** and never
raise — violations are returned, not thrown.

Coverage is defined in `REFERENCE_MAP` and exposed via `ALL_KINDS`. Adding a
new outbound reference between entities requires updating both `REFERENCE_MAP`
and the tests in `tests/memory/test_referential_integrity.py`.

---

## 6. Versioning

- Adding a new method to the ABC: breaking (subclasses must implement). Bump to `memory.v2`.
- Adding optional parameters to existing methods (defaulted): additive within `v1`.
- Changing on-disk layout or filename conventions: breaking → `v2` plus a migration plan.

The version string lives in `core.memory.MEMORY_CONTRACT_VERSION` and is
written into every `_meta.json` so existing client folders can be detected
and migrated when the layout changes.
