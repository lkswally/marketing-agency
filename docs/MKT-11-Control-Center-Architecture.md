# MKT-11 — Marketing Control Center: Architecture Proposal

> **Status:** PROPOSAL — awaiting approval. No implementation has started.
> **Scope:** design only. This document defines the stack, the folder
> structure, the component model, the routing/navigation model, and the
> reuse map. Implementation begins only after this design is approved.

---

## 0. Executive summary

The Control Center is **not** a new application. It is a second
presentation surface over the services the CLI already drives.

To satisfy "consume the existing services / do not duplicate CLI logic",
one architectural piece is currently **missing**: an application-service
layer. Today `cli/main.py` (2,785 lines, 28 subcommands) mixes four
concerns — argument parsing, service orchestration, output-file writing,
and exit-code shaping. The output-writing block alone is duplicated **35
times**. A UI that called `core/` directly would duplicate that block a
36th time.

The central proposal is therefore:

1. Extract a **UI-agnostic application-service layer** (`core/services/`)
   that both the CLI and the Control Center call.
2. Refactor the CLI to consume it — behaviour-identical, no command
   removed, no flag renamed.
3. Build the Control Center strictly on top of that layer.

Three findings materially shape the design and need an explicit decision
from you (see §7 — Open decisions):

- The existing `portal/` has a **hard read-only contract** pinned by 12
  safety tests. A Control Center that *operates* the system cannot live
  inside it.
- **Approval Queue has no CLI equivalent.** `approve()`/`reject()` exist
  in Python but were never exposed as commands (P-3B.5). Building the
  queue in the UI first would make the UI more capable than the CLI —
  inverting the stated "CLI is the internal API" principle.
- `read_audit_events()` loads **every** JSONL file into memory and raises
  on the first corrupt line. Acceptable for a CLI dump, not for a UI.

---

## 1. Current architecture (as analysed)

### 1.1 Layers that exist today

```
┌──────────────────────────────────────────────────────────┐
│  cli/main.py  (2,785 LOC, 28 subcommands)                │
│  argparse + orchestration + output writing + exit codes  │
└────────────────────────┬─────────────────────────────────┘
                         │  direct calls
┌────────────────────────▼─────────────────────────────────┐
│  core/<module>/   — domain services (24 modules)         │
│  builder / analyzer / factory + models + renderer        │
└────────────────────────┬─────────────────────────────────┘
                         │
┌────────────────────────▼─────────────────────────────────┐
│  core/memory/  JsonFileMemory  (entities + audit trail)  │
└──────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────┐
│  portal/  (819 LOC, MKT-9A)  — READ-ONLY Streamlit app   │
│  reads memory directly; never writes; 12 safety pins     │
└──────────────────────────────────────────────────────────┘
```

### 1.2 What is genuinely reusable

The `portal/` package already contains the exact primitives the Control
Center needs, and they are **pure Python with zero Streamlit coupling**
(pinned by `test_only_app_py_imports_streamlit`):

| Asset | What it gives us | Verdict |
|---|---|---|
| `pack_registry.PortalPackSpec` | Declarative table: kind → title, singleton ids, markdown filenames, `blocks_publish` field, optional/required | **Reuse + extend** |
| `pack_loader.load_pack()` | Never-raises loader returning `OK / BLOCKED / MISSING / ERROR` | **Reuse as-is** |
| `checklist.build_preflight_checklist()` | Publish-gate + ATLAS-handoff-gate aggregation | **Reuse as-is** |
| `client_discovery.discover_clients()` | Multi-tenant client enumeration from memory ∪ outputs | **Reuse as-is** |

This is a significant head start: the registry pattern is precisely the
"reusable component" abstraction the Control Center needs, and it already
covers 14 pack kinds.

### 1.3 The consistent service shape

Every domain module follows the same contract, which makes a generic
service layer feasible:

```python
Service(memory=...).build(client_slug, **params) -> Pack   # pure, no I/O
Service(memory=...).persist(pack)                          # memory + audit
render_markdown_<x>(pack) -> str                           # pure
```

`SEOIntelligenceReportBuilder`, `GoogleAdsAnalyzer`, `AnalyticsImporter`,
`AdsFeedbackBridge`, `CreativeFactory`, `VisualPromptFactory` all conform.

### 1.4 The duplication seam

Repeated verbatim across ~15 CLI commands:

```python
outputs_dir = Path(args.outputs_dir)
outputs_dir.mkdir(parents=True, exist_ok=True)
md_path = outputs_dir / "<name>.md"
md_path.write_text(render_markdown_x(pack), encoding="utf-8")
json_path = outputs_dir / "<name>.json"
json_path.write_text(pack.to_json(indent=2), encoding="utf-8")
```

This is the logic the UI must **not** re-implement. It belongs in the
service layer.

---

## 2. Proposed stack

### 2.1 Recommendation: Streamlit multipage, behind a UI-agnostic service layer

**Rationale — coherence with the project as it actually is:**

- The repo is **100% Python**. No `package.json`, no node toolchain, no
  bundler, no JS test runner. The entire quality story is 1,818 pytest
  tests + ruff.
- Streamlit is **already an accepted optional dependency**
  (`[portal]` extra, MKT-9A) and the team already ships a Streamlit app.
- Streamlit ≥1.36 supports real multipage apps (`st.Page` / `st.navigation`),
  which covers the required per-client workspace with lateral navigation.
- Delivers the 9-module MVP without introducing a second language, a
  build step, CORS, session/auth infrastructure, or a parallel CI lane.

**The critical caveat:** Streamlit is chosen for the *MVP presentation
layer only*. The design below places **zero business logic** in it. The
service layer is deliberately framework-agnostic so that a later
FastAPI + React front end (a plausible MKT-12/13) can be added by writing
a new presentation layer against the *same* services — without touching
`core/`, without touching the CLI, and without a rewrite.

### 2.2 Alternative considered: FastAPI + React

| | Streamlit multipage | FastAPI + React |
|---|---|---|
| New languages / toolchains | none | Node, TS, bundler, JS tests |
| Time to 9-module MVP | short | long |
| Component reuse | moderate (Python functions) | strong (real components) |
| Responsive control | limited, framework-driven | full |
| Complex nav / deep-linking | workable, some friction | native |
| Auth / multi-user | not solved | designed for it |
| Fits current CI | yes (pytest only) | needs a second lane |

**Honest assessment:** FastAPI + React is the better *destination* if the
Control Center is meant to become a multi-user, externally-hosted product.
It is the wrong *starting point* for an MVP in a single-language repo with
no auth story — it would roughly triple the surface before delivering the
first module.

**Recommendation:** Streamlit now, with the service layer as the
insurance policy that makes the migration cheap later. If your intent is
that the Control Center becomes customer-facing and multi-user within the
next 2–3 blocks, say so — that changes the recommendation to FastAPI +
React now, and I would re-scope MKT-11 accordingly.

### 2.3 Explicitly out of scope for MKT-11

No auth, no multi-user sessions, no external hosting, no WebSockets, no
real-time push. The Control Center remains a **local, single-operator**
tool, exactly like the current portal.

---

## 3. Target architecture

```
┌───────────────────────────────────────────────────────────────┐
│  PRESENTATION                                                 │
│                                                               │
│   control_center/          (new — operational UI)             │
│   portal/                  (frozen — read-only, MKT-9A)       │
│   cli/                     (unchanged commands)               │
└───────────────────────────┬───────────────────────────────────┘
                            │  the ONLY allowed downward call
┌───────────────────────────▼───────────────────────────────────┐
│  APPLICATION SERVICES        core/services/          (new)    │
│                                                               │
│  • use-case functions (build+persist+render+write outputs)    │
│  • tenant scoping guard                                       │
│  • ServiceResult contract (ok / error, never raises to UI)    │
│  • output-path policy (single source of truth)                │
│  • read models / view specs for UI consumption                │
└───────────────────────────┬───────────────────────────────────┘
                            │
┌───────────────────────────▼───────────────────────────────────┐
│  DOMAIN            core/<module>/  (unchanged)                │
│  builders · analyzers · factories · models · renderers        │
└───────────────────────────┬───────────────────────────────────┘
                            │
┌───────────────────────────▼───────────────────────────────────┐
│  PERSISTENCE       core/memory/  JsonFileMemory (unchanged)   │
└───────────────────────────────────────────────────────────────┘
```

**Dependency rule (enforced by test):** `control_center/` may import
`core.services` and `portal.*` pure helpers. It may **not** import
`core.<domain>` builders directly, and may **not** import
`core.memory` directly. This is what mechanically guarantees "no business
logic in the UI".

---

## 4. Folder structure

```
core/services/                      # NEW — application layer
  __init__.py                       # public façade; the UI imports only this
  result.py                         # ServiceResult, ServiceError, ErrorCode
  context.py                        # ServiceContext (root, outputs_dir, tenant)
  outputs.py                        # write_pack_outputs() — the 35× dedup
  registry.py                       # extends PortalPackSpec → ArtifactSpec
  clients.py                        # list_clients, client_overview
  analytics.py                      # import_metrics, analyze, list_snapshots
  seo.py                            # build_seo_report, list_seo_reports
  campaigns.py                      # run_campaign, run_strategy, build_*
  approvals.py                      # list_pending, approve, reject
  memory_view.py                    # structured knowledge read models
  audit.py                          # paginated, corruption-tolerant reader

control_center/                     # NEW — operational UI
  __init__.py                       # streamlit-free (pinned, like portal)
  main.py                           # ONLY module importing streamlit
  nav.py                            # route table + navigation model
  state.py                          # session state keys, tenant selection
  formatters.py                     # value → display string (pure)
  components/                       # reusable, streamlit-free where possible
    __init__.py
    status_badge.py                 # OK / BLOCKED / MISSING / ERROR chip
    pack_card.py                    # artifact summary card
    kv_table.py                     # structured key/value renderer
    finding_list.py                 # SEOFinding / insight list w/ nature+confidence
    timeline.py                     # audit event timeline
    empty_state.py                  # "no data yet + how to produce it"
    confirm_action.py               # two-step guard for every write
  pages/
    home.py
    clients.py
    analytics.py
    seo.py
    campaigns.py
    memory.py
    audit.py
    approvals.py
    settings.py

tests/services/                     # NEW — service layer tests
tests/control_center/               # NEW — UI logic + safety pins
docs/decisions/0034-mkt-11-control-center.md   # ADR (follows 0033)
```

`portal/` is **not** modified. Its 12 safety pins stay green.

---

## 5. Core abstractions

### 5.1 `ServiceResult` — the UI never sees an exception

```python
@dataclass(frozen=True)
class ServiceResult[T]:
    ok: bool
    data: T | None
    error: ServiceError | None      # code + human message + remediation hint
    artifacts: list[Path]           # files written, if any
    audit_event_id: str | None      # provenance for the Audit module
```

Mirrors the CLI's exit-code semantics (`0` → ok, `2` → error) so both
surfaces behave identically. The UI renders `error.message` and
`error.remediation`; it never formats a traceback.

### 5.2 `ServiceContext` — tenant scoping guard

```python
@dataclass(frozen=True)
class ServiceContext:
    root: Path              # memory root (default data/clients)
    outputs_dir: Path
    client_slug: str        # validated via validate_slug()
```

Every write service takes a `ServiceContext`. The context is constructed
**once** per request from the selected tenant and is the only path to a
client slug — a UI bug cannot write into the wrong tenant's namespace,
because no service accepts a free-form slug argument alongside a context.

### 5.3 `ArtifactSpec` — registry extension, not replacement

Extends the proven `PortalPackSpec` with the fields the Control Center
needs, keeping the existing 14 entries intact:

```python
@dataclass(frozen=True)
class ArtifactSpec(PortalPackSpec):        # inherits order/kind/title/...
    module: str                            # which Control Center page owns it
    produced_by: str                       # CLI command that creates it
    view_fields: tuple[ViewField, ...]     # structured render (Memory module)
    period_scoped: bool = False            # MKT-10B/10C period entities
```

`view_fields` is what turns the Memory module from a JSON dump into
structured knowledge — a declarative projection per kind, not bespoke
rendering code per pack.

### 5.4 `write_pack_outputs()` — the 35× deduplication

```python
def write_pack_outputs(
    pack, *, ctx: ServiceContext, spec: ArtifactSpec, renderer, overwrite: bool
) -> list[Path]
```

Single source of truth for output-file naming and writing. Both the CLI
and the Control Center call it. This is the concrete answer to "do not
duplicate CLI logic".

---

## 6. Routing and navigation model

### 6.1 Two-level model

```
Level 1 — global (no tenant selected)
  /                     Home            cross-tenant overview
  /clients              Clients         tenant list + create/select
  /settings             Settings        roots, paths, environment posture

Level 2 — client workspace (tenant selected; lateral nav)
  /c/<slug>                     Overview
  /c/<slug>/analytics           Analytics
  /c/<slug>/seo                 SEO Intelligence
  /c/<slug>/campaigns           Campaigns
  /c/<slug>/memory              Memory
  /c/<slug>/audit               Audit
  /c/<slug>/approvals           Approval Queue
```

Implemented with `st.navigation` + `st.Page`; the selected tenant lives in
session state and is reflected in the URL via `st.query_params` so a
workspace view is linkable and survives refresh.

### 6.2 Navigation rules

- Selecting a tenant enters the workspace; the lateral nav appears.
- The tenant selector is **always visible** in the workspace header — the
  single most important guard against acting on the wrong client.
- Every page states its evidence posture: `OK / BLOCKED / MISSING / ERROR`
  reusing `PackStatus` — one vocabulary across CLI, portal and UI.
- Empty states are first-class: every module that can be empty renders
  *the exact command that would produce the missing artifact*, keeping
  the CLI discoverable rather than hidden.

### 6.3 Module → service → existing capability map

| Module | Reads | Service | Writes? |
|---|---|---|---|
| Home | all tenants: packs, audit tails, approvals | `clients.overview` | no |
| Clients | `discover_clients` + `_meta.json` | `clients.list` | no (MVP) |
| Analytics | `MetricsSnapshot` (+ MKT-10B periods) | `analytics.*` | import-metrics |
| SEO | `seo_intelligence_report_pack` | `seo.*` | build report |
| Campaigns | strategy / creative / visual / tasks | `campaigns.*` | run pipeline |
| Memory | all kinds via `ArtifactSpec.view_fields` | `memory_view.*` | no |
| Audit | audit JSONL, paginated | `audit.read_page` | no |
| Approvals | `approval_pack` where `blocks_publish` | `approvals.*` | approve/reject |
| Settings | resolved paths, SDK availability | `context` | no |

---

## 7. Open decisions requiring your approval

These four change what gets built. I have a recommendation for each but
will not proceed on assumption.

### D-11.1 — Where does the operational UI live?

`portal/` is pinned read-only by 12 tests, including an explicit ban on
`st.button`, `st.form`, `st.download_button` and all write calls. The
Control Center must operate the system.

- **Recommended:** new `control_center/` package. `portal/` stays frozen
  and keeps every guarantee MKT-9A shipped. The new package gets its own
  explicit safety contract (below).
- Alternative: extend `portal/` and delete the widget/write pins —
  loses a shipped safety guarantee.

### D-11.2 — Safety contract for a *writing* UI

Proposed pins for `control_center/`, mirroring `portal/` minus the
widget ban:

- No direct `core.memory` import — writes only via `core.services`.
- No direct `core.<domain>` builder import.
- No `requests` / `httpx` / `urllib` / `aiohttp`.
- No `os.environ` / `os.getenv` outside `settings.py`.
- No `subprocess` / `os.system`.
- No `notion_client`, no `core.n8n_sync`, no `core.notion_sync`, no ATLAS
  reach-in — external writes remain CLI-only, `--confirm`-gated.
- Every write path routes through `confirm_action` (two-step).

### D-11.3 — Approval Queue vs the CLI-is-the-API principle

`ApprovalPackBuilder.approve()/reject()` exist; there is **no** `mkt
approve` / `mkt reject` command (P-3B.5, deferred since MKT-3B).

- **Recommended:** add `mkt approve` / `mkt reject` **first**, as part of
  MKT-11 phase 1. Resolves P-3B.5, and the UI then calls the same service
  the CLI does — the stated principle holds.
- Alternative: build it UI-only — the UI becomes more capable than the
  CLI, contradicting "the CLI is the internal API".

### D-11.4 — Long-running operations

`run-campaign` runs the full pipeline synchronously. In Streamlit this
blocks the session.

- **Recommended for MVP:** synchronous execution behind a `JobRunner`
  interface (`InlineJobRunner` now), with a spinner and an explicit
  duration warning. The interface means a future background/queue runner
  is a swap, not a refactor.
- Alternative: build the job queue now — meaningful extra scope.

---

## 8. Phasing

Each phase is independently shippable and leaves the suite green.

| Phase | Deliverable | Touches |
|---|---|---|
| **11A** | `core/services/` + `ServiceResult` + `write_pack_outputs` + CLI refactored onto it (behaviour-identical) + `mkt approve`/`mkt reject` | `core/services/`, `cli/main.py` |
| **11B** | `control_center/` skeleton: nav, routing, tenant scoping, components, Home, Clients, Settings | `control_center/` |
| **11C** | Read modules: Analytics, SEO, Memory, Audit | `control_center/pages/` |
| **11D** | Operational modules: Campaigns, Approval Queue (write paths, confirm guard) | `control_center/pages/`, services |

Phase 11A is the one that carries risk: it refactors a 2,785-line file
that 1,818 tests depend on. It is deliberately first, deliberately
behaviour-preserving, and deliberately verified by the existing CLI test
suite before any UI code is written.

---

## 9. Constraints honoured

- **ATLAS untouched** — no file under `atlas/` is read or written; the
  UI cannot even import the ATLAS bridge factory (pinned).
- **CLI preserved** — no command removed, no flag renamed. The CLI stops
  *containing* orchestration and starts *calling* it.
- **No duplicated logic** — the service layer is the single
  implementation; the 35× output-writing block collapses to one function.
- **No business logic in the UI** — enforced by an import-boundary test,
  not by convention.
- **Multi-tenant** — `ServiceContext` is the only path to a client slug.
- **Backward compatible** — `portal/` frozen; all existing entities,
  contracts and audit shapes unchanged.
- **Ready for Learning / Decision Engine / Market Intelligence** — these
  arrive as new services + a new page each, with no change to the shell.

---

## 10. What I need from you

1. Approve or amend **D-11.1 … D-11.4** (§7).
2. Confirm the **stack decision** (§2) — in particular, tell me if the
   Control Center is intended to become multi-user / hosted soon, because
   that flips the recommendation to FastAPI + React now.
3. Confirm the **phasing** (§8), especially that phase 11A (CLI refactor
   onto the service layer) may proceed — it is the prerequisite for
   everything else and the only phase that touches existing code.

No code will be written until these are settled.
