# MKT-11E — Versioned Approval History: Domain Inventory

> **Status:** analysis complete — implementation NOT started, awaiting approval.
> **Method:** direct read of `core/approval/models.py`, `core/approval/approval_pack.py`,
> `core/application/services/approvals.py`, `core/pipeline/orchestrator.py`,
> `core/jobs/operations/campaign.py`, `cli/main.py`, and an exhaustive
> repo-wide grep for every reader of the `approval_pack` memory kind. Every
> claim below is traceable to a file and line number, not assumed.

---

## 1. The core problem, confirmed in code (not conceptual)

`core/pipeline/orchestrator.py::_stage_approval` (line 523):

```python
def _stage_approval(self, client_slug: str, report):
    builder = ApprovalPackBuilder(memory=self._memory)
    pack = builder.build_from_report(report)   # ALWAYS state=DRAFT
    builder.persist(pack)                       # ALWAYS overwrites "current"
```

Every `run-campaign` / `campaign.run` invocation **unconditionally rebuilds**
the pack from the strategy report and **overwrites** `approval_pack/current`.
An operator's prior `approve`/`reject` decision on that client is silently
discarded the next time the pipeline runs. This is not a corner case — it
is the *normal* behaviour of the only two things that ever create an
approval pack today.

**The bug this milestone must fix, confirmed at the exact line:**
`core/jobs/operations/campaign.py:71` —

```python
result_ref=(
    f"{ctx.client_slug}/approval_pack/current"
    if approval_pack_id else None
),
```

A job that reaches `WAITING_APPROVAL` points its `result_ref` at the
literal string `"current"`. If a second `campaign.run` job runs for the
same client before the first is resolved, the first job's reference now
resolves to a *different* pack (or a DRAFT-state rebuild), silently. This
is exactly the referential-integrity failure MKT-11D flagged as known
debt and deferred to this milestone.

---

## 2. `ApprovalPack` — confirmed field inventory (`core/approval/models.py:139-172`)

```
contract_version, pack_id, client_slug, report_id, report_contract_version,
state, detections, overall_severity, blocks_publish, checklist,
created_at, updated_at, decision, rule_set_id
```

`pack_id` **exists** as a field (`Field(default_factory=new_id)`, the same
UUID4-hex `new_id()` every other MAOS entity uses) but is **never used as
a storage key** — persistence is always `kind="approval_pack"`,
`entity_id="current"` (`approval_pack.py:35-36`).

`ApprovalDecision` (line 122): `reviewer`, `decided_at`, `notes` — no
`job_id`, no `correlation_id`, no `campaign_run_id`, no `strategy_id`, no
`operation` field anywhere on either model.

## 3. States and transitions — confirmed unchanged from MKT-11B

`ApprovalState` (`models.py:29-43`): exactly `DRAFT`, `NEEDS_REVIEW`,
`APPROVED`, `REJECTED`. `_TERMINAL_STATES = {APPROVED, REJECTED}`
(line 46).

`ApprovalPackBuilder` transitions (`approval_pack.py:188-246`):
- `submit_for_review`: `DRAFT → NEEDS_REVIEW` only.
- `approve`: refuses if already `APPROVED`; refuses if `REJECTED`;
  succeeds from `DRAFT` or `NEEDS_REVIEW`.
- `reject`: mirror image.

`_blocks_publish(state, overall_severity)` (line 103): `APPROVED` never
blocks; `REJECTED` always blocks; any other state blocks iff
`overall_severity` is `RISKY`/`UNSAFE`. **Unchanged by this milestone.**

MKT-11B's idempotency policy (`core/application/services/approvals.py`,
confirmed in current file): re-approving an `APPROVED` pack → `ok` +
warning, no new audit event; re-rejecting `REJECTED` → same; cross-terminal
(`APPROVED→REJECTED` or reverse) → `ErrorCode.INVALID_STATE_TRANSITION`.
**Nothing here needs to change — §7 of the brief is already satisfied by
existing code.**

## 4. Permissions — confirmed unchanged

`core/application/policies.py::check_can_decide_approval` — allowed roles
`{OPERATOR, APPROVER, ADMIN}`; `VIEWER`/`ANALYST` blocked. The module
docstring already documents *why* `OPERATOR` stays allowed (pre-11B
compatibility, not an oversight). **No RBAC change needed or proposed.**

## 5. Every real consumer of `approval_pack/current` (exhaustive grep)

| # | File:line | What it does | Read-only or authoritative? |
|---|---|---|---|
| 1 | `core/approval/approval_pack.py:181-184` (`ApprovalPackBuilder.load`) | The one function everything else routes through | Authoritative — the domain's own accessor |
| 2 | `core/pipeline/orchestrator.py:523-556` (`_stage_approval`) | Builds + persists a **new** pack every run | **Writer** — the root cause (§1) |
| 3 | `core/application/services/approvals.py` (`show`/`approve`/`reject`) | Loads via `ApprovalPackBuilder.load`, `--approval-id` verification-only (D-11B.2) | Reader + mutator, already `pack_id`-aware in spirit |
| 4 | `core/jobs/operations/campaign.py:71` | Hardcodes `"current"` into `result_ref` | **The bug** (§1) |
| 5 | `cli/main.py:270,295` (`_cmd_build_creatives`) | `memory.get(client, APPROVAL_PACK_KIND, "current")` — required, hard-fails if absent | Reader, required |
| 6 | `cli/main.py:350,377` (`_cmd_build_visuals`) | Same pattern | Reader, required |
| 7 | `cli/main.py:446,478` (`_cmd_build_tasks`) | Same pattern | Reader, required |
| 8 | `core/atlas_bridge/factory.py:75` | `_optional_load(..., "current", ...)` — soft, `None` if absent | Reader, optional/informational |
| 9 | `core/image_jobs/factory.py:130` | Same soft-load pattern, checks `approval.blocks_publish` for context | Reader, optional/informational |
| 10 | `core/image_provider_plan/planner.py:121` | Same soft-load pattern | Reader, optional/informational |

**Not real consumers** (pass-through of an already-resolved `approval_pack_id`
*string*, no independent memory read): `core/creative/factory.py`,
`core/execution/task_factory.py`, `core/visual/prompt_factory.py`,
`core/n8n_sync/planner.py`, `core/execution/notion_payload.py`,
`core/pipeline/renderer.py`, `cli/main.py:1885,2006,2332`. These take an
already-loaded `ApprovalPack` object or its `pack_id` as a parameter from
their caller — no change needed.

**Test blast radius:** 30 test files reference `approval_pack`/`ApprovalPack`
in some form (`grep -rl`, counted, not read individually yet).

## 6. Audit — confirmed shape

`ApprovalPackBuilder._emit_event` (`approval_pack.py:286-298`):
`event_type=NOTE`, `actor="approval_pack_builder"`,
`payload={"approval_pack": {pack_id, report_id, state, overall_severity,
blocks_publish, action, reviewer}}`. **No `job_id`, no `correlation_id`,
no `approval_id`-as-a-distinct-field** (it's called `pack_id` here, not
`approval_id` — naming to reconcile). The MKT-11D job/campaign-pipeline
correlation mechanism (`job_id`/`correlation_id` on `OperationContext`,
threaded into `PipelineOrchestrator`) exists and works for
`campaign_pipeline.*` events — it was never wired into
`ApprovalPackBuilder`'s own events.

## 7. Data reality check (§20 of the brief)

This is a local, single-operator development repository
(`data/clients/` is gitignored per MKT-10A; no client data is committed).
**No real persisted approval packs exist in version control to migrate.**
Any pack on a developer's local disk is disposable dev/test state. No
destructive-migration risk exists; no migration script is required beyond
"the new code writes the new shape going forward."

---

## Summary for the design proposal that follows

- The domain (states, transitions, idempotency, permissions) needs **no
  change** — MKT-11B already built it correctly for a *versioned* world;
  it was only ever wired to a singleton.
- The real work is: (a) make `persist()` write to `<approval_id>`, never
  `"current"`; (b) add a repository-level `list`/`get-latest` so the 6
  read-only/soft consumers keep working without a second write path; (c)
  fix the one hardcoded `"current"` bug in the job handler; (d) thread
  `job_id`/`correlation_id` into approval audit events, mirroring what
  MKT-11D already did for pipeline audit events.
- No data migration is needed (§7 above).
