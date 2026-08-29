# MKT-11B — Approval Operations: Domain Inventory

> **Status:** analysis complete — implementation NOT started, awaiting approval.
> **Method:** static analysis of `core/approval/`, `core/application/services/approvals.py`
> (already shipped in MKT-11A), `core/pipeline/orchestrator.py`, `core/memory/`,
> `core/contracts/audit_trail.py`, and every existing test file that touches
> approvals.

---

## 0. Critical framing: MKT-11A already shipped a first cut

Before analysing the domain, one fact reshapes the rest of this document:
**`core/application/services/approvals.py` already exists**, with
`list_pending`, `show`, `approve`, `reject`, wired to CLI commands
`mkt approvals list`, `mkt approvals show`, `mkt approve`, `mkt reject`.
It already implements idempotent approve/reject and a mandatory
non-empty rejection reason.

MKT-11B is therefore **not a green-field build** — it is a gap-closing
pass against a real, working implementation. §7 maps every MKT-11B
requirement to "already done" / "needs extending" / "not supportable by
the domain as it exists". Re-implementing what already works would
violate "no duplicar `approve()` ni `reject()` existentes" one level up
— duplicating the *service* that already wraps them.

---

## 1. Where `approve()` and `reject()` live today

| # | Question | Answer |
|---|---|---|
| 1 | Where do `approve()`/`reject()` live | `core/approval/approval_pack.py`, methods on `ApprovalPackBuilder` (lines 202–246). Both delegate to a private `_transition()` (line 250) that persists **and** emits the audit event in one call. |
| 2 | What model represents an approval | `core.approval.models.ApprovalPack` (`approval-pack.v1`). It is a bundle: strategy-report reference + claim detections + a checklist + a lifecycle state + an optional `ApprovalDecision`. It is explicitly **not** the formal `Approval` entity from `docs/approval-center.md` (a documented, un-implemented future design with its own 5-state machine). |
| 3 | How is an approval identified | **`client_slug` is the identity.** `ApprovalPack.pack_id` (a UUID) exists as a field but is **not used as a storage key**. Persistence is a memory singleton: `kind="approval_pack"`, `entity_id="current"` — **one pack per client, always**. There is no multi-approval history and no lookup-by-`pack_id` path in the domain today. |
| 4 | What states exist | `ApprovalState`: `DRAFT → NEEDS_REVIEW → APPROVED \| REJECTED` (`core/approval/models.py:29`). `APPROVED` and `REJECTED` are terminal (`_TERMINAL_STATES`). |
| 5 | What transitions are permitted | `submit_for_review`: `DRAFT → NEEDS_REVIEW` only (raises `ApprovalStateError` from any other state). `approve`: refuses if already `APPROVED`; refuses if `REJECTED`; **succeeds from `DRAFT` or `NEEDS_REVIEW`** (submission is not enforced as a precondition). `reject`: mirror image — refuses if already `REJECTED`; refuses if `APPROVED`; succeeds from `DRAFT` or `NEEDS_REVIEW`. |
| 6 | What persistence | `core.memory.Memory` (`JsonFileMemory` in practice) — `APPROVAL_PACK_KIND = "approval_pack"`, `SINGLETON_ID = "current"`. Standard `validate_slug`-gated per-client directory layout, same as every other pack kind. |
| 7 | What audit events | Every `persist()` and every `_transition()` call emits one `AuditTrailEvent` (`event_type=NOTE`, `actor="approval_pack_builder"` **— not the human reviewer**, payload wrapped under `payload.approval_pack.{pack_id, report_id, state, overall_severity, blocks_publish, action, reviewer}`). `action` is `"created"` / `"updated"` / `"submitted"` / `"approved"` / `"rejected"`. |
| 8 | Relation to `ApprovalPack` | N/A — `ApprovalPack` **is** the approval entity in this codebase today. There is no separate "Approval" wrapping it. |
| 9 | Relation to `blocks_publish` | Computed by `_blocks_publish(state, overall_severity)` (line 103): `APPROVED` → never blocks. `REJECTED` → **always** blocks (rejecting is itself a block). Any other state → blocks iff `overall_severity` is `RISKY` or `UNSAFE`. |
| 10 | Relation to blocked campaigns | `PipelineOrchestrator._stage_approval` (`core/pipeline/orchestrator.py:512`) calls `ApprovalPackBuilder.build_from_report(...).persist(...)` **on every `run-campaign` invocation** — the pack is rebuilt from scratch (state `DRAFT`) each run, not loaded from a prior decision. **Consequence: an operator's `approve`/`reject` decision does not survive the next `run-campaign` call** — the next run persists a fresh `DRAFT` pack, overwriting the terminal state. This is pre-existing behaviour; MKT-11B must not change it (no requirement asked for it, and doing so would be an undocumented scope expansion). |
| 11 | Actor data today | `ApprovalDecision.reviewer: str` (free text, `min_length=1`) + `decided_at: datetime` + optional `notes: str`. No structured actor id, no role field, no source field at the domain layer — MKT-11A's `OperationContext.actor_id` is passed through as `reviewer` already. |
| 12 | Real gaps | See §5. |

---

## 2. `ApprovalPack` field inventory (verbatim from `core/approval/models.py`)

```
pack_id, client_slug, report_id, report_contract_version, state,
detections, overall_severity, blocks_publish, checklist,
created_at, updated_at, decision, rule_set_id
```

**Not present:** `campaign_id`, `approval_type`, any per-approval history,
any actor role field. This directly constrains what `list`/`show` can
filter or return (§4).

---

## 3. What MKT-11A already shipped (verified against the current file)

`core/application/services/approvals.py`:

| Function | Behaviour | Status vs. MKT-11B spec |
|---|---|---|
| `list_pending(*, root)` | Cross-tenant scan; returns packs in `{DRAFT, NEEDS_REVIEW}` or with `blocks_publish=True`. Returns `PendingApprovalSummary` rows (not the full pack). | Filters by nothing yet — no `status`, `campaign_id`, date-range, or `limit`. |
| `show(ctx)` | Loads the client's current pack. | No `--approval-id` concept — matches domain reality (§1.3). |
| `approve(ctx, *, notes)` | Idempotent on `APPROVED`; maps `ApprovalStateError` → `INVALID_STATE_TRANSITION`; `audit_event_id` is populated from `memory.last_audit_hash(...)` — **this is the chain **hash**, not `AuditTrailEvent.event_id`.** Real bug, see §5.3. | No authorization check — any `ctx.role` succeeds. |
| `reject(ctx, *, reason)` | Same shape; `reason` mandatory, enforced before touching memory. | Same audit-id issue; same missing authorization. |

CLI already wired: `mkt approvals list`, `mkt approvals show --client`,
`mkt approve --client --actor --notes`, `mkt reject --client --actor --reason`.
75 tests already pass (`tests/application/test_approvals_service.py`,
`tests/cli/test_cli_approvals.py`), all green as of `0af839e`.

**Not yet present anywhere:** `--status`, `--campaign-id`, `--limit`,
`--json`, `--correlation-id`, `--approval-id` flags; role enforcement;
a documented exit-code table; `event_id`-correct audit references.

---

## 4. List/filter feasibility — checked against the actual persistence shape

| Requested filter | Feasible? | Why |
|---|:--:|---|
| `client_slug` / tenant | ✅ already implemented (the entire cross-tenant scan is built around it) |
| `status` (state) | ✅ trivial — filter the same rows already loaded, by `ApprovalState` |
| `campaign_id` | ❌ **field does not exist** on `ApprovalPack`. Closest proxy is `report_id`, which identifies a `CampaignStrategyReport`, not a campaign run. Faking a `campaign_id` filter by aliasing `report_id` would be inventing a name the domain doesn't use — not permitted per "no inventar filtros". |
| "tipo de aprobación" | ❌ there is exactly one approval type (`ApprovalPack`) in this codebase. No type field exists or is needed. |
| date range | ⚠️ partially feasible: `created_at` / `updated_at` exist on the pack. But since only the **current** pack per client is ever persisted (no history), a date-range filter over a single-row-per-client dataset filters out entire clients rather than selecting among multiple approvals — different semantics than the spec likely intends ("approvals opened between X and Y"). Feasible to implement literally (filter on `updated_at`), but its usefulness is limited until per-approval history exists. |
| `limit` | ✅ trivial — slice the cross-tenant result list |

**Recommendation:** implement `status`, `limit`, and `updated_at`
range filters (literal, honestly scoped). Do **not** implement
`campaign_id` or "tipo" filters — document them as infeasible without a
domain change, per the instruction not to invent what persistence
cannot reasonably support.

---

## 5. Real gaps (not assumptions — traced to code)

### 5.1 — Authorization is not enforced anywhere

`OperationContext.role` (`OperationRole` enum) has existed since MKT-11A
but **no service reads it**. `approve()`/`reject()` succeed regardless of
`ctx.role`. This is the single biggest gap MKT-11B must close per its own
"Roles" section.

### 5.2 — `--approval-id` has no real referent

There is no per-approval identifier index in the domain (§1.3). The
closest honest behaviour: accept `--approval-id` as an **optional
verification** parameter — if supplied, the service checks it against
the loaded pack's `pack_id` and returns `NOT_FOUND` on mismatch (guards
against an operator approving the wrong campaign's pack by typo, without
inventing a lookup path that doesn't exist). This is the conservative
reading; needs your confirmation before implementing (§9 D-11B.2).

### 5.3 — `audit_event_id` is currently the wrong field

MKT-11A's `approve`/`reject` populate `OperationResult.audit_event_id`
from `memory.last_audit_hash(client_slug)` — the **hash chain tail**,
not `AuditTrailEvent.event_id`. `ApprovalPackBuilder._transition()` does
not return the event object it builds, so the application service cannot
grab the real `event_id` directly without either (a) a small domain
change to return the event, or (b) reading the event back via
`memory.read_audit_events(client_slug)` and taking the last one. Fixing
this is in-scope for MKT-11B (the spec explicitly lists `audit_event_id`
as a required result field) — recommend (b), zero domain changes,
documented as a known single-writer assumption (matches P-1D.3, already
accepted project-wide).

### 5.4 — Idempotency policy already exists; MKT-11B asks to "define" it

MKT-11A already implemented the exact policy MKT-11B describes as
open ("no asumir — usar las reglas reales, o proponer una política
conservadora y esperar aprobación"): idempotent success + warning on
re-reaching the same terminal state; structured error on a genuinely
invalid cross-transition (`APPROVED → REJECTED` or vice versa). **This
document proposes keeping that policy unchanged** — it already matches
"usar las reglas reales del dominio" (the domain's own
`ApprovalStateError` messages are the source of truth for what's
invalid) plus a conservative addition (idempotent no-op) that the domain
leaves unspecified. Confirmation requested in §9 D-11B.1.

### 5.5 — Actor recorded as free text, not a structured id

`ApprovalDecision.reviewer` is `str`. MKT-11A already passes
`ctx.actor_id` through as `reviewer`. No change needed — flagging only
because the MKT-11B brief asks to document actor-data gaps explicitly.

### 5.6 — `blocks_publish` reset on every `run-campaign`

Documented in §1 row 10. Not a gap to fix — a fact to preserve.
`approve`/`reject` only ever affect the state **until the next campaign
run rebuilds the pack**. No test currently pins this interaction from
the approvals-service side; MKT-11B's required test #24 ("blocks_publish
permanece correcto") should pin exactly this, not a claim that approval
survives across runs (it doesn't, by design, today).

---

## 6. Exit codes — current CLI-wide conventions (surveyed)

| Code | Existing meaning across the CLI (from `docs/MKT-11A-Application-Services-Inventory.md` §1 + direct grep) |
|---|---|
| 0 | success |
| 2 | generic error — file not found, invalid argument, not found, invalid state (today `_cmd_approve`/`_cmd_reject` map **every** error to 2, no differentiation) |
| 3 | `run-campaign` only: `--require-approval` set AND blocked |
| 4 | `run-campaign` / `intake --strict`: strict failure |

**No command in the CLI today distinguishes "not found" from "invalid
transition" from "insufficient permission" from "persistence error" —
`return 2` is the universal error code.** MKT-11B's requirement to
"distinguish input inválido / no encontrada / transición inválida /
permiso insuficiente / error de persistencia / error inesperado" is a
**new precedent**, not a convention to reuse. Proposed mapping in §9.

---

## 7. Requirement-by-requirement disposition

| MKT-11B ask | Disposition |
|---|---|
| List/get/approve/reject services | ✅ exist (MKT-11A) — extend, don't rebuild |
| Filter by `client_slug`, `status`, `limit` | feasible — add |
| Filter by `campaign_id`, "tipo" | ❌ infeasible — no domain field; document, don't fake |
| Filter by date range | ⚠️ feasible but low-value given no history — implement literally on `updated_at`, document the limitation |
| Idempotency policy | ✅ already implemented — proposal: keep as-is |
| Mandatory non-empty reject reason | ✅ already implemented |
| `audit_event_id` correctness | ❌ gap — currently the chain hash, not `event_id` — fix |
| Role-based authorization | ❌ gap — nothing enforces `ctx.role` today — add a minimal policy function |
| `--approval-id` CLI flag | needs a decision — optional verification-only param (§9 D-11B.2) |
| `--correlation-id` CLI flag | not present today — trivial to add (`OperationContext.correlation_id` already exists, just not settable from the CLI) |
| `--json` CLI flag | **no existing CLI command has a `--json` flag — every command always prints JSON to stdout already.** Adding a no-op flag would be inconsistent with every other command. Recommend NOT adding it (§9 D-11B.3). |
| Documented exit-code table | new precedent — proposed in §9 |
| Multi-tenant isolation | ✅ already covered (per-client directories + existing tests) |
| Path traversal protection | ✅ inherited for free — `client_slug` always goes through `validate_slug`, which forbids `/`, `..`, and any path-hostile character (regex `^[a-z0-9]+(?:-[a-z0-9]+)*$`) |

---

## 8. Test surface already green (do not re-derive, extend)

`tests/application/test_approvals_service.py` (18 tests) and
`tests/cli/test_cli_approvals.py` (14 tests) already cover: show
happy/not-found, list-pending cross-tenant + blocked-terminal inclusion,
approve happy/idempotent/invalid-transition/not-found, reject
happy/idempotent/invalid-transition/not-found/empty-reason/whitespace-reason,
audit-event-created (payload shape, not yet `event_id` correctness),
multi-tenant isolation, CLI happy paths + exit codes for all four
commands. These stay as regression pins; MKT-11B adds tests for the
genuinely new surface (filters, roles, `event_id` correctness,
`correlation_id` propagation, `--approval-id` verification).
