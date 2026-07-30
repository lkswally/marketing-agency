# MKT-11A — CLI Responsibility Inventory

> **Status:** analysis complete — implementation NOT started, awaiting approval.
> **Method:** static analysis of `cli/main.py` (2,785 LOC, 27 `_cmd_*` functions,
> 28 subparsers), cross-referenced against `core/` domain services and
> `portal/` read-only helpers.

---

## 1. Duplication census (measured, not estimated)

| Pattern | Occurrences | Notes |
|---|---:|---|
| `JsonFileMemory(Path(args.root))` | 23 | client-root resolution |
| `print(json.dumps(payload, …))` | 21 | stdout payload shaping |
| `md_path.write_text(render_…(pack))` | 18 | Markdown artifact write |
| `pack.to_json(indent=2)` | 18 | JSON serialisation |
| `outputs_dir.mkdir(parents=True, exist_ok=True)` | 17 | directory creation |
| `json_path.write_text(…)` | 16 | JSON artifact write |
| `return 2` | 39 | error exit mapping |
| `AuditTrailEvent.build(...)` **inside the CLI** | 3 | lines 526, 1012, 1770 |

**The canonical duplicated block** (verbatim in ~15 commands):

```python
outputs_dir = Path(args.outputs_dir)
outputs_dir.mkdir(parents=True, exist_ok=True)
md_path = outputs_dir / "<name>.md"
md_path.write_text(render_markdown_x(pack), encoding="utf-8")
json_path = outputs_dir / "<name>.json"
json_path.write_text(pack.to_json(indent=2), encoding="utf-8")
```

---

## 2. Findings that constrain the design

### F-1 — Two incompatible output-path conventions (must NOT be "fixed" silently)

| Convention | Commands | Resulting path |
|---|---|---|
| **Flat** | ~15 commands incl. `seo-report`, `ads-analyze`, `analyze-metrics` | `<outputs_dir>/<file>.md` |
| **Per-client** | `intake` (line 1791), `run-campaign`, `utm-plan` | `<outputs_dir>/<slug>/<file>.md` |

`portal/pack_loader._find_markdown` looks **only** in
`Path(outputs_dir) / client_slug` (line 164). Consequence: the portal
discovers Markdown for per-client commands but **not** for flat ones,
unless the operator manually passes `--outputs-dir outputs/<slug>`.

**Implication for MKT-11A:** the artifact writer must accept the layout as
an explicit, per-command parameter and reproduce today's behaviour exactly.
Unifying the conventions is a *behaviour change* and is therefore **out of
scope** for 11A. Recorded as a follow-up (see §6).

### F-2 — `--overwrite` and `--dry-run` are near-absent

- `--overwrite`: **1** command (`seo-report`, MKT-10C).
- `--dry-run`: **3** commands (`seo-report`, `notion-sync`, `n8n-plan`) with
  *different* semantics each (skip-write vs. skip-external-call).

The writer must support both, but migrated commands keep their current
flag surface — no flag is added to a command that lacks it today.

### F-3 — Audit is already well-placed

19 `core/` modules build their own `AuditTrailEvent` inside `.persist()`.
Only 3 CLI commands hand-roll audit (`build-tasks`, `analyze-metrics`,
`intake`) — none of which are in the 11A migration scope. **No audit
refactor is needed in this milestone.**

### F-4 — Approvals: domain is complete, no refactor required

`ApprovalPackBuilder` already provides `load`, `submit_for_review`,
`approve(client_slug, *, reviewer, notes)`, `reject(...)`, and a private
`_transition()` that persists **and** emits the audit event. State
validation raises `ApprovalStateError`.

Mapped against D-11.5:

| D-11.5 requirement | Status |
|---|---|
| validate tenant | `validate_slug` via memory — ✓ |
| validate state / transition | `ApprovalStateError` — ✓ domain |
| register actor | `reviewer` field — ✓ |
| register timestamp | `decided_at=utcnow()` — ✓ |
| audit event | `_transition()` — ✓ |
| **require reason on reject** | ✗ `notes` is optional → **enforce in app layer** |
| **idempotency** | ✗ re-approving raises → **decide at app layer** |
| structured result | ✗ → `OperationResult` |
| no auto-publish | ✓ nothing publishes today |

The two gaps are **policy**, not domain. They belong in the application
service, which satisfies "do not duplicate `approve()`/`reject()` — wrap the
existing domain correctly".

**Conclusion:** `approvals list/show` is feasible in 11A without a major
refactor. `list` = `discover_clients()` × `load()` per slug.

### F-5 — `run-campaign` correctly excluded

`PipelineOrchestrator.run()` executes the full pipeline synchronously and
owns its own outputs/audit. Out of scope per the milestone definition;
belongs with the job contract (D-11.7).

---

## 3. Commands prioritised for the Control Center

Ranked by (Control Center value) ÷ (migration risk):

| Rank | Command | CC module | Risk | In 11A? |
|---:|---|---|---|:--:|
| 1 | `seo-report` | SEO Intelligence | **low** — newest, 25 dedicated tests, already has `--overwrite`/`--dry-run` | ✅ |
| 2 | *(read-only)* snapshot list/show | Analytics | **low** — `snapshot_repo.py` (MKT-10B) already exposes the reads; no CLI equivalent exists to break | ✅ |
| 3 | `approvals list/show/approve/reject` | Approval Queue | **low-med** — new commands, no existing behaviour to preserve | ✅ |
| 4 | `ads-analyze` | Campaigns | med | ❌ 11B |
| 5 | `analyze-metrics` | Analytics | med — hand-rolled audit | ❌ 11B |
| 6 | `run-campaign` | Campaigns | **high** | ❌ later (D-11.7) |

---

## 4. Responsibility map — where each concern lands

| Concern | Today | After 11A |
|---|---|---|
| argparse / flags | `cli/main.py` | `cli/main.py` (unchanged) |
| exit-code mapping | 39 × `return 2` | `cli/main.py`, from `OperationResult.status` |
| stdout payload | 21 × `json.dumps` | `cli/main.py` (unchanged shape) |
| client-root resolution | 23 × `JsonFileMemory(...)` | `OperationContext` |
| output dir + mkdir | 17 × inline | `ArtifactWriter` |
| MD/JSON serialisation | 34 × inline | `ArtifactWriter` |
| overwrite / dry-run | ad-hoc | `ArtifactWriter` policy |
| domain orchestration | inline in `_cmd_*` | application service |
| audit | 19 × `core/` + 3 × CLI | unchanged |
| business rules | `core/<domain>/` | unchanged |

---

## 5. Path-traversal exposure (new protection)

No command currently validates that the resolved output path stays inside
the permitted root. `--outputs-dir ../../etc` is accepted today. The
writer will enforce containment via resolved-path prefix checking. This
is **additive hardening**: no legitimate existing invocation is affected,
because every current path already resolves inside its root.

---

## 6. Deferred (documented, not actioned in 11A)

- **D-11A.1** — Unify flat vs per-client output layout (F-1). Behaviour
  change; needs its own block and a portal-compat review.
- **D-11A.2** — Migrate the 3 CLI-side audit builders (`build-tasks`,
  `analyze-metrics`, `intake`) into their domain services.
- **D-11A.3** — Migrate remaining ~12 flat-writing commands to the writer.
- **D-11A.4** — Robust audit reader (D-11.8): pagination, filters,
  corruption tolerance.
- **D-11A.5** — Job contract for long operations (D-11.7).
