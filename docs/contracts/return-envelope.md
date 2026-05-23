# Return Envelope — Contract `envelope.v1`

> Version: **v1** (MKT-1C).
> Implementation: `core/contracts/envelope.py`.
> Breaking changes bump to `envelope.v2`.

Every agent in MKT must return a Return Envelope. The envelope is the single
handoff between an agent and the dispatcher, and between the dispatcher and the
audit trail.

---

## 1. Schema

```jsonc
{
  "contract_version": "envelope.v1",        // required, pinned
  "status": "completado|fallido|PASS|FAIL", // required, enum
  "agent": "copywriter",                    // required, 1..200 chars
  "task": "draft Q3 hero copy",             // required, min 1 char
  "client_slug": "demo-co",                 // optional, slug rules
  "artifacts": [                            // optional
    {
      "path": "outputs/demo-co/copy.md",
      "kind": "file|memory|url|inline",
      "sha256": "<64 hex chars>",           // optional
      "bytes": 1234,                        // optional, >=0
      "description": "draft v1"             // optional
    }
  ],
  "memory_writes": [                        // optional
    {
      "topic_key": "marketing-agency-os/demo-co/brand",
      "backend": "json|engram|memory",
      "bytes": 512
    }
  ],
  "claims_audit": {                         // optional; required by claim_strict mode
    "contract_version": "claim-audit.v1",
    "claims": [...],
    "overall_severity": "...",
    "overall_verdict": "..."
  },
  "bloqueadores": ["..."],                  // optional; required when status is FAIL/fallido
  "notes": "...",                           // optional; required when status is FAIL/fallido (if no bloqueadores)
  "produced_at": "2026-05-22T12:00:00+00:00" // required, timezone-aware
}
```

### 1.1 Field rules

| Field | Required | Rule |
|-------|----------|------|
| `contract_version` | Yes | Must equal `"envelope.v1"`. Wrong value → `version_mismatch`. |
| `status` | Yes | Enum. `completado`/`fallido` for generic agents; `PASS`/`FAIL` for validators. |
| `agent` | Yes | Non-empty, ≤200 chars. |
| `task` | Yes | Non-empty. |
| `client_slug` | No | If present, must satisfy slug rules (lowercase, dashes, not `_shared`). |
| `produced_at` | Yes | Timezone-aware ISO 8601. Naive → `naive_datetime`. |
| `artifacts[*].sha256` | No | Must match `^[a-fA-F0-9]{64}$` if present. |
| `memory_writes[*].topic_key` | Yes (inside the write) | Unique across the envelope. Duplicates → `duplicate_ref`. |
| `bloqueadores` / `notes` | Conditional | When `status` is `fallido`/`FAIL`, at least one of them MUST be non-empty. |
| Extra fields | — | Rejected (`extra_field`). |

### 1.2 Status semantics

| Status | Used by | Meaning |
|--------|---------|---------|
| `completado` | Generic agents | Task finished normally. |
| `fallido` | Generic agents | Task did NOT finish. Requires explanation. |
| `PASS` | Validator agents (QA, claim-validator, reality-checker) | Output passes the check. |
| `FAIL` | Validator agents | Output fails the check. Requires explanation. |

---

## 2. Validators

`core/contracts/validators.py` exposes:

| Function | Returns / Raises |
|----------|------------------|
| `validate_envelope(payload)` | `(bool, list[ContractErrorPayload])` |
| `validate_envelope_strict(payload)` | `ReturnEnvelope` or raises `ContractError` |

Both are pure (no I/O).

---

## 3. Strictness modes (informational)

The validator code itself is single-mode (the model). Strictness modes are
**enforced by callers** that compose extra rules on top of the model. The
modes below are documented so downstream dispatchers (MKT-2A+) implement them
consistently.

| Mode | Extra rules on top of `envelope.v1` schema |
|------|---------------------------------------------|
| `standard` | None — schema only. |
| `qa_strict` | `status` must be `PASS` or `FAIL`. `bloqueadores` non-empty when `FAIL`. |
| `dev_strict` | `artifacts` non-empty. Every `file` artifact must have a `sha256`. |
| `design_strict` | At least one artifact of kind `file` whose path matches `**/*.css` or `**/*.tsx`. |
| `claim_strict` | `claims_audit` MUST be present. `claims_audit.blocks_emission` MUST be `False`. |

These modes are *additive* — none of them weaken the base schema.

---

## 4. Examples

### 4.1 Minimal valid envelope

```json
{
  "contract_version": "envelope.v1",
  "status": "completado",
  "agent": "strategist",
  "task": "draft positioning",
  "produced_at": "2026-05-22T12:00:00+00:00"
}
```

### 4.2 Failed envelope (must include explanation)

```json
{
  "contract_version": "envelope.v1",
  "status": "fallido",
  "agent": "copywriter",
  "task": "draft Q3 hero copy",
  "produced_at": "2026-05-22T12:00:00+00:00",
  "bloqueadores": ["brand voice cache missing"]
}
```

### 4.3 Envelope with claims audit

```json
{
  "contract_version": "envelope.v1",
  "status": "completado",
  "agent": "copywriter",
  "task": "draft Q3 hero copy",
  "produced_at": "2026-05-22T12:00:00+00:00",
  "artifacts": [
    {"path": "outputs/demo-co/hero.md", "kind": "file", "sha256": "a1b2..."}
  ],
  "claims_audit": {
    "contract_version": "claim-audit.v1",
    "claims": [
      {
        "claim_id": "c1",
        "text": "3x faster delivery",
        "severity": "caveat",
        "verdict": "partial",
        "evidence_refs": [{"evidence_id": "e1", "trust_level": 0.8}]
      }
    ],
    "overall_severity": "caveat",
    "overall_verdict": "partial"
  }
}
```

### 4.4 Invalid — failure without explanation

```json
{
  "contract_version": "envelope.v1",
  "status": "fallido",
  "agent": "x",
  "task": "y",
  "produced_at": "2026-05-22T12:00:00+00:00"
}
```

→ `ContractError(code=invariant_violation, path=, message="envelope with status=fallido requires at least one bloqueadores entry or notes")`.

---

## 5. Versioning

- Additive change (new optional field): stays within `v1`.
- Breaking change (rename / remove / type change): bump to `envelope.v2` and write a new spec file.
- Envelopes always carry `contract_version` — a dispatcher reading mixed versions can dispatch by that field.
