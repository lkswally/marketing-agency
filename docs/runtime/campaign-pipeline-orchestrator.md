# Runtime — Campaign Pipeline Orchestrator (MKT-3F)

The orchestrator chains every layer of the agency pipeline into one
command: `mkt run-campaign --intake <path>`. It does no content
generation of its own — it only walks the existing layers in order,
persists their artifacts to memory and to disk, and records an
append-only audit trail with a hash chain.

- **Module:** `core/pipeline/`
- **Contract:** `pipeline-run.v1` (`core/pipeline/models.py`)
- **CLI subcommand:** `mkt run-campaign`
- **Entry point:** `PipelineOrchestrator.run_from_file(...)`

## Stages

```
intake → strategy → approval → creative → visual → summary
```

| Stage      | Module             | Memory kinds written                       | Output files                                          |
|------------|--------------------|--------------------------------------------|-------------------------------------------------------|
| intake     | `core.intake`      | `client_intake`, `intake_validation`       | `intake.json`, `intake-summary.md`, `brief.json`      |
| strategy   | `core.strategy`    | `campaign_strategy_report`                 | `campaign-strategy.md`                                |
| approval   | `core.approval`    | `approval_pack`                            | `approval-pack.md`, `approval-pack.json`              |
| creative   | `core.creative`    | `creative_asset_pack`                      | `creative-pack.md`, `creative-pack.json`              |
| visual     | `core.visual`      | `visual_direction_pack`                    | `visual-direction-pack.md`, `visual-direction-pack.json` |
| summary    | `core.pipeline`    | `campaign_run_summary`                     | `campaign-final-summary.md`, `campaign-final-summary.json` |

Every stage emits an `audit-trail.v1` event under `actor=pipeline_orchestrator`
with payload `{"campaign_pipeline": {"stage": ..., "action": <outcome>}}`. The
orchestrator also emits two non-stage events at the boundaries:
`action=started` (after intake) and `action=finished` (always last).

## Usage

### Basic — clean intake

```bash
mkt run-campaign --intake examples/intake/demo-business.json
```

Default `--root` is `data/clients/` and default `--outputs-dir` is
`outputs/`. On a successful run you get:

```
outputs/<client_slug>/
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

and stdout prints a JSON summary:

```json
{
  "run_id": "...",
  "client_slug": "acme-bootstrapped",
  "contract_version": "pipeline-run.v1",
  "overall_state": "draft",
  "blocks_publish": false,
  "is_complete": true,
  "duration_seconds": 0.41,
  "intake_critical": 0,
  "intake_warning": 0,
  "intake_info": 0,
  "report_id": "...",
  "approval_pack_id": "...",
  "creative_pack_id": "...",
  "visual_pack_id": "...",
  "stage_counts": {"succeeded": 6, "skipped": 0, "blocked": 0, "failed": 0},
  "outputs_dir": "outputs/acme-bootstrapped"
}
```

### Flags

| Flag                  | Effect                                                                                                  | Exit |
|-----------------------|---------------------------------------------------------------------------------------------------------|------|
| `--strict`            | Halt after intake when there are CRITICAL validation issues.                                            | 4    |
| `--require-approval`  | Halt with non-zero exit when the Approval Pack blocks publish. Summary is still written.                | 3    |
| `--stop-on-blocked`   | Halt cleanly when the Approval Pack blocks publish. Creative + visual are recorded as `skipped`.        | 0    |

Both `--require-approval` and `--stop-on-blocked` write the final
summary with `blocks_publish=True` and creative/visual marked
`skipped`; the difference is the exit code and whether a typed
exception is raised. `--require-approval` wins if both are set.

### Programmatic

```python
from pathlib import Path
from core.memory import JsonFileMemory
from core.pipeline import PipelineOrchestrator

memory = JsonFileMemory(Path("data/clients"))
orch = PipelineOrchestrator(memory=memory, outputs_root=Path("outputs"))

summary = orch.run_from_file(
    Path("examples/intake/demo-business.json"),
    strict=False,
    require_approval=False,
    stop_on_blocked=False,
)

print(summary.client_slug, summary.overall_state, summary.blocks_publish)
print(summary.count_by_outcome())
```

Typed sentinels:

- `PipelineStrictFailure` — raised when `strict=True` and the intake
  has critical issues. CLI exit 4.
- `PipelineBlockedByApproval` — raised when `require_approval=True`
  and the Approval Pack blocks publish. CLI exit 3.

## Exit codes (CLI)

| Code | Meaning                                                            |
|------|--------------------------------------------------------------------|
| 0    | Pipeline completed (with or without warnings; or clean stop-on-blocked). |
| 2    | Intake file missing.                                               |
| 3    | `--require-approval` and the Approval Pack blocks publish.         |
| 4    | `--strict` and the intake has critical issues.                     |

## What gets persisted to memory

For client `acme-bootstrapped`, `data/clients/acme-bootstrapped/`:

```
client_intake/current.json
intake_validation/current.json
campaign_strategy_report/current.json
approval_pack/current.json
creative_asset_pack/current.json
visual_direction_pack/current.json
campaign_run_summary/current.json
audit/YYYY-MM-DD.jsonl     ← append-only, hash-chained
```

`campaign_run_summary` is overwritten on each run, but the audit trail
JSONL grows monotonically. To replay history, walk
`mem.read_audit_events(client_slug)` and filter for
`payload.campaign_pipeline.action`.

## Determinism

- Same intake + same flags → same persisted artifact content (modulo
  fresh `run_id`s, fresh timestamps, fresh entity ids).
- Pipeline is single-threaded by design. The summary stage is written
  last so a crash mid-run leaves intermediate packs intact and the
  final summary absent — a clean signal to retry.
- The Markdown renderer (`render_markdown_summary`) is a pure
  function: same `CampaignRunSummary` → byte-identical Markdown.

## Constraints

- No LLM. No external API. No MCP. No n8n. No GA4. No Google Ads.
- No image generation. No publishing. No email sending.
- `ClaudeCodeBackend` is still mock-only (`MockAgentBackend`); the
  orchestrator does not invoke it.
- The state `published` does not exist in this system — the highest
  state any artifact reaches is `READY_FOR_PUBLISH`.

## Validation

- 52 tests under `tests/pipeline/` + `tests/cli/test_cli_run_campaign.py`.
- Full test suite green (783 tests).
- `ruff check .` clean.

## Tracked follow-ups

See `PENDING.md` → section `From MKT-3F`.
