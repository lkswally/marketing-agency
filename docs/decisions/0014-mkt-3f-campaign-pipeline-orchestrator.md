# ADR 0014 — MKT-3F: Campaign Pipeline Orchestrator

- **Status:** Accepted
- **Date:** 2026-05-31
- **Block:** MKT-3F
- **Supersedes:** —
- **Contract:** `pipeline-run.v1` (new, Pydantic, in `core/pipeline/models.py`).

## Context

After MKT-3A → MKT-3E, the agency operating system had five working
layers (intake, strategy, claim audit + approval, creative pack,
visual direction pack) but no single entry point. Each had to be
invoked manually with its own CLI subcommand and its own outputs
directory. The human ran the chain by hand and reconciled artifacts
across `outputs/<slug>/`.

MKT-3F adds the **last mile of the operator UX**: one command —
`mkt run-campaign --intake <path>` — that walks every layer in order,
persists every intermediate artifact to memory, writes every Markdown
and JSON deliverable to `outputs/<client_slug>/`, and records an
append-only audit trail with a hash chain for the whole run.

The orchestrator is a pure coordinator. It does **not** generate any
content, call any LLM, hit any API, mint any image, send any email
or publish anything. It only chains the layers that already exist.

## Decision

### D-14.1 — Single entry point per campaign run

`PipelineOrchestrator.run_from_file(intake_path, *, strict,
require_approval, stop_on_blocked) -> CampaignRunSummary` is the only
public method. The CLI subcommand `mkt run-campaign` is a thin wrapper
around it.

### D-14.2 — Six fixed stages, in order

```
intake → strategy → approval → creative → visual → summary
```

The order is encoded in `StageId` (StrEnum) and enforced in the
orchestrator body. Stages do not run in parallel and they do not
reorder. A stage may produce one of four outcomes (`StageOutcome`):

| Outcome      | When                                                   |
|--------------|--------------------------------------------------------|
| `succeeded`  | Stage finished without issues.                         |
| `blocked`    | Approval stage when `blocks_publish=True`.             |
| `skipped`    | Downstream stage that did not run because of a flag.   |
| `failed`     | Stage raised, missing file, etc. — pipeline halts.     |

Every stage emits an `audit-trail.v1` event with payload
`{"campaign_pipeline": {"stage": ..., "action": ...}}`. The orchestrator
also emits two non-stage events: `action=started` (after intake, once
the slug is known) and `action=finished` (always last). The hash chain
remains valid end-to-end.

### D-14.3 — Three orthogonal flags

| Flag                  | Behavior                                                                                                  | CLI exit |
|-----------------------|-----------------------------------------------------------------------------------------------------------|----------|
| `--strict`            | If intake has CRITICAL issues → raise `PipelineStrictFailure`. Summary is **not** written (no slug yet).  | 4        |
| `--require-approval`  | If Approval Pack blocks publish → raise `PipelineBlockedByApproval`. Summary **is** written with SKIPPED. | 3        |
| `--stop-on-blocked`   | If Approval Pack blocks publish → clean exit. Creative + visual marked SKIPPED in summary, memory, audit. | 0        |

`--require-approval` and `--stop-on-blocked` cover two different
operational stances on a blocked Approval Pack: hard fail (the
operator wants a non-zero exit, e.g. in CI) vs soft halt (the
operator wants the summary on disk for review). They are evaluated in
that order — `--require-approval` wins if both are set.

### D-14.4 — `CampaignRunSummary` is a meta-artifact, not a duplication

The summary stores only references to the underlying packs
(`report_id`, `approval_pack_id`, `creative_pack_id`, `visual_pack_id`,
plus `brief_path`). It does **not** copy strategy bullets, claims,
asset bodies or prompts. A consumer that wants the full content reads
the referenced packs from memory or disk.

### D-14.5 — Overall state derivation

`overall_state` is computed from the Approval Pack, mirroring the
derivation used by the creative/visual factories:

| Approval state        | `overall_state`         |
|-----------------------|-------------------------|
| `blocks_publish=True` | `BLOCKED`               |
| `APPROVED`            | `READY_FOR_PUBLISH`     |
| `NEEDS_REVIEW`        | `DRAFT`                 |
| `DRAFT` / `REJECTED`  | `DRAFT`                 |
| (no approval pack)    | `NEEDS_REVIEW`          |

The state `PUBLISHED` deliberately does **not** exist — this system
does not publish.

### D-14.6 — Outputs layout

Every run writes to `outputs/<client_slug>/` (created on demand):

```
intake.json
intake-summary.md
brief.json
campaign-strategy.md
approval-pack.md
approval-pack.json
creative-pack.md
creative-pack.json
visual-direction-pack.md
visual-direction-pack.json
campaign-final-summary.md
campaign-final-summary.json
```

Re-running the pipeline overwrites these files. The audit trail in
memory is **append-only** — a re-run produces a new `run_id` plus new
audit events; old events are preserved.

### D-14.7 — Determinism and isolation

- Same intake + same flags → same persisted artifact content (modulo
  fresh `run_id`s, fresh timestamps, fresh entity ids).
- Two different clients running through the same orchestrator instance
  never see each other's data: the memory layer is keyed by
  `client_slug` and the outputs root is sharded by `client_slug` too.
- The orchestrator is single-threaded by design. The summary stage is
  written last so a crash mid-run leaves the intermediate packs
  untouched and the final summary absent — a clean signal to retry.

### D-14.8 — Renderer is pure

`render_markdown_summary(summary)` is a pure function over the
summary. Two calls with the same summary produce byte-identical
Markdown. The renderer makes no I/O and no external lookups.

### D-14.9 — Failure modes

| Failure                                | Behavior                                                                                                              |
|----------------------------------------|-----------------------------------------------------------------------------------------------------------------------|
| Intake file missing / invalid          | Intake stage `FAILED`. No slug yet, so no summary persisted. CLI exit 2 (file missing) or graceful return with FAILED. |
| Intake critical issues + `--strict`    | Raise `PipelineStrictFailure`. CLI exit 4.                                                                            |
| Intake normalization error             | Intake stage `FAILED`, downstream stages never run.                                                                   |
| Strategy pipeline error                | Strategy stage `FAILED`, downstream stages never run.                                                                 |
| Approval blocks + `--require-approval` | Raise `PipelineBlockedByApproval`. Summary persisted with SKIPPED creative + visual. CLI exit 3.                       |
| Approval blocks + `--stop-on-blocked`  | Clean exit. Summary persisted with SKIPPED creative + visual. CLI exit 0.                                              |

## Consequences

### Positive

- One command operates the whole agency. No more manual chaining.
- The audit trail captures the entire run end to end with a single
  hash chain per client.
- The summary is a stable contract that downstream consumers
  (dashboards, reports, future MCP tools) can read.
- Operators have two distinct strategies for blocked claims:
  hard fail (CI) and soft halt (review).

### Negative / accepted trade-offs

- The orchestrator does no parallelism. All five layers run
  sequentially. For the volumes this system targets
  (one campaign per intake, deterministic templates) the cost is
  irrelevant. If parallelism is ever needed, the natural cut is
  creative + visual after approval.
- The summary is overwritten on re-runs. Historical runs are only
  visible through the audit trail. If a per-run archive is needed
  later, a `--archive` flag can add it without breaking the contract.
- `CampaignRunSummary` does not embed the underlying packs. Consumers
  that want everything in one payload must follow the references.

## Out of scope (explicit)

The following are explicitly **not** done in MKT-3F:

- No landing page, no dashboard.
- No Vercel, no Netlify, no deployment.
- No n8n, no webhooks.
- No MCP server (real or mock beyond the existing roadmap).
- No GA4, no Google Ads.
- No image generation. No file upload to any CDN.
- No email sending.
- No `ClaudeCodeBackend` wiring (still mock-only via `MockAgentBackend`).
- No multi-tenant locking. The memory layer is per-slug and the user
  is responsible for not running two campaigns for the same slug
  concurrently.

## Validation

- 52 new tests under `tests/pipeline/` and
  `tests/cli/test_cli_run_campaign.py`.
- Full test suite: **783 passed**.
- Ruff: **clean**.
- ATLAS core (sibling repo): untouched.

## Related

- Supersedes nothing. Adds `pipeline-run.v1`.
- Depends on every prior MKT-3 block (3A → 3E) and on MKT-1D for the
  audit trail hash chain.
- Future work tracked under `P-3F.*` in `PENDING.md`.
