# MKT-11D — Campaign Job Migration: Inventory

> **Status:** analysis complete — implementation NOT started, awaiting approval.
> **Method:** direct read of `cli/main.py::_cmd_run_campaign`, its argparse
> subparser, `core/pipeline/orchestrator.py` (full `PipelineOrchestrator`),
> `core/pipeline/models.py`, `core/strategy/backends/invokers/anthropic_sdk.py`,
> and every test in `tests/cli/test_cli_run_campaign.py`. Every claim below is
> traceable to a line number or a test.

---

## 1. Real CLI arguments (verbatim from the subparser, `cli/main.py:3259-3310`)

| Flag | Required | Default | Notes |
|---|:--:|---|---|
| `--intake` | ✅ | — | path to the intake JSON |
| `--root` | | `data/clients` | memory root |
| `--outputs-dir` | | `outputs` | per-client outputs root |
| `--strict` | | `False` | exit 4 on critical intake issues |
| `--require-approval` | | `False` | exit 3 when approval blocks publish |
| `--stop-on-blocked` | | `False` | exit 0, skip creative/visual, when blocked |
| `--backend` | | `"templated"` | `templated` \| `claude` |
| `--claude-model` | | `None` | overrides `ANTHROPIC_MODEL` env var |

**No `--client` flag** — `client_slug` comes from the intake file's
`client_name` (via `IntakeValidator`), never from a CLI argument.
**No `--dry-run`, no `--overwrite`, no `--correlation-id`** — none exist
today. The spec's mention of these was conceptual; they are **not
implemented in MKT-11D** per "no inventar parámetros."

---

## 2. Backend selection (`cli/main.py:2268-2309`)

Resolved entirely in the CLI, before the orchestrator is ever called:

```
--backend templated (default)        → strategy_backend = None
--backend claude, ANTHROPIC_API_KEY set, SDK installed
                                      → AnthropicSDKInvoker (real calls)
--backend claude, ANTHROPIC_API_KEY missing
                                      → RefusingClaudeInvoker + WARNING to stderr
--backend claude, SDK not installed  → NoCredentialsError caught →
                                        RefusingClaudeInvoker + WARNING to stderr
```

`RefusingClaudeInvoker` makes every one of the 6 creative methods fall back
to templated — the pipeline **always completes**, never raises for a
backend problem. `ANTHROPIC_MODEL` env var is the model fallback when
`--claude-model` is absent.

**Credential handling:** `os.environ.get("ANTHROPIC_API_KEY")` is read once,
passed into `AnthropicSDKInvoker(api_key=..., model=...)`. The key is never
put into `CampaignRunSummary`, `ClaudeInvocationRecord` (fields: model id,
request id, token counts, duration, `ok` flag — verified in
`core/pipeline/models.py:121-126`), audit payloads, or stdout.

---

## 3. `PipelineOrchestrator.run()` control flow (`orchestrator.py:123-318`)

Six stages, always in order: `INTAKE → STRATEGY → APPROVAL → CREATIVE →
VISUAL → SUMMARY`. Three distinct exit paths, **verified by reading the
code, not assumed**:

### 3a. Intake stage fails (`orchestrator.py:144-161`)
`PipelineStrictFailure` is raised **only if `strict=True` AND the intake
*parsed* AND `validation.missing_critical_count > 0`**. Any other intake
failure (malformed JSON, schema mismatch, normalization error) returns a
**normal summary with exit 0** — this is existing graceful-degradation
behaviour, not a bug MKT-11D should fix. `client_slug="invalid"` in that
case; the summary is **not persisted** (`orchestrator.py:783-785`).

### 3b. Approval blocks publish (`orchestrator.py:189-272`) — three distinct sub-paths depending on flags
| Flags | Behaviour |
|---|---|
| `--require-approval` | Persists the summary (creative/visual **skipped**), then raises `PipelineBlockedByApproval` → CLI catches → exit 3 |
| `--stop-on-blocked` | Persists the summary (creative/visual **skipped**), returns normally → CLI exit 0 |
| neither (default) | Same skip behaviour, audit event `approval.blocked`, returns normally → CLI exit 0 |

**Critical finding:** only the `--require-approval` path raises an
exception. The other two return an ordinary `CampaignRunSummary` with
`blocks_publish=True` and `overall_state="blocked"`. All three are the
*same underlying pipeline event* (approval blocks publish) — they differ
only in what the **legacy CLI** does with it. This directly shapes §7 of
the proposal below: the job-outcome mapping must key off
`summary.blocks_publish`, not off which CLI flag was passed, since a job
submission has no flag-driven exception contract to preserve.

### 3c. Success (`orchestrator.py:274-318`)
Creative + visual stages run, summary built and persisted, `campaign_run_summary`
(kind, singleton `"current"` — **same singleton pattern as the approval
pack**, `orchestrator.py:89-90,312-317`) written, exit 0.

---

## 4. Persistence (verified per-kind)

| Kind | Singleton? | Written by |
|---|:--:|---|
| `client_intake` | `"current"` | intake stage |
| `intake_validation` | `"current"` | intake stage |
| `campaign_strategy_report` | `"current"` | strategy stage (via `StrategyPipeline`) |
| `approval_pack` | `"current"` | approval stage |
| `creative_asset_pack` | `"current"` | creative stage |
| `visual_direction_pack` | `"current"` | visual stage |
| `campaign_run_summary` | **`"current"`** | orchestrator, end of run |

**`campaign_run_summary` is a singleton, same limitation class as
`approval_pack`** (documented in the MKT-11B inventory and the master
plan). Each `run-campaign` invocation overwrites the previous run's
summary. This is pre-existing and **out of scope to fix** in MKT-11D — the
job wrapper must reference it as-is, not change its persistence shape.

**Output files** (verified against `test_run_campaign_writes_expected_files`):
`intake.json`, `intake-summary.md`, `brief.json`, `campaign-strategy.md`,
`approval-pack.{md,json}`, `creative-pack.{md,json}`,
`visual-direction-pack.{md,json}`, `campaign-final-summary.{md,json}` — all
under `<outputs-dir>/<client_slug>/` (PER_CLIENT layout, per the MKT-11A
inventory's F-1 finding — `run-campaign` already uses PER_CLIENT, unlike
`seo-report`'s FLAT).

---

## 5. Audit trail

Two `campaign_pipeline` events guaranteed by the pinned test
`test_audit_trail_records_pipeline_run`: `action="started"` (right after
intake succeeds) and `action="finished"` (end of every non-exception path).
An `action="approval.blocked"` event fires on the default (no-flag) blocked
path. Every stage additionally emits its own `action=<stage_outcome>` event
(e.g. `action="succeeded"` for intake). All wrapped in `event_type=NOTE`,
`actor="pipeline_orchestrator"`, `payload.campaign_pipeline.*` — the same
shape every other block in this codebase uses (not yet promoted to
`audit-trail.v2`, per the long-standing backlog item).

---

## 6. Exceptions — complete list

| Exception | Raised when | CLI exit |
|---|---|---|
| `PipelineStrictFailure` | `--strict` AND intake *parsed* AND has critical issues | 4 |
| `PipelineBlockedByApproval` | `--require-approval` AND `blocks_publish=True` | 3 |
| *(no exception)* — file not found | `--intake` path does not exist | 2 (checked in the CLI **before** the orchestrator is ever constructed) |
| *(no exception)* — malformed intake | bad JSON / schema mismatch | 0 (graceful degradation, §3a) |
| *(no exception)* — blocked without `--require-approval` | `--stop-on-blocked` or default | 0 |

**No other exception type is caught or expected.** An orchestrator crash
from a genuinely unexpected error (e.g. a domain bug) propagates as an
unhandled exception today — the CLI has no `except Exception` wrapper.
This is the gap `ErrorCode.INTERNAL` in the job wrapper closes.

---

## 7. stdout / stderr contract (verified)

- **stdout:** exactly one `json.dumps(payload, indent=2, default=str)` call,
  on success (0) — 18 fields (`run_id`, `client_slug`, `contract_version`,
  `overall_state`, `blocks_publish`, `is_complete`, `duration_seconds`,
  `intake_critical/warning/info`, `report_id`, `approval_pack_id`,
  `creative_pack_id`, `visual_pack_id`, `stage_counts`, `outputs_dir`,
  `backend_requested/effective/fallback_count/fallback_notes`). On error
  paths (2/3/4) a plain `print(f"error: {e}", file=out)` line — **not**
  JSON. This is `out`, which in tests is captured separately from real
  stdout — but in production `out` **is** stdout.
- **stderr:** two possible `WARNING:` lines — no API key /  no SDK
  (backend selection), and partial Claude fallback (`backend_fallback_count > 0`).
  Always `sys.stderr` directly, never routed through `out`.

---

## 8. `ErrorCode` / `ExitCode` vocabulary already available (MKT-11A/B/C)

```
ErrorCode: NOT_FOUND, INVALID_INPUT, INVALID_STATE_TRANSITION, ALREADY_EXISTS,
           PATH_NOT_ALLOWED, PERMISSION_DENIED, PERSISTENCE_ERROR,
           UNKNOWN_OPERATION, INTERNAL
ExitCode:  OK=0, INVALID_INPUT=2, NOT_FOUND=3, INVALID_STATE_TRANSITION=4,
           PERMISSION_DENIED=5, PERSISTENCE_ERROR=6, JOB_FAILED=7, UNEXPECTED=70
```

No `ErrorCode` for "strict failure" or "blocked by approval" exists yet.
Both map naturally to existing codes without inventing new ones:
`PipelineStrictFailure` → `ErrorCode.INVALID_INPUT` (the intake, i.e. the
input, is what's critically wrong); an unexpected orchestrator crash →
`ErrorCode.INTERNAL`. "Blocked by approval" is **not an error** in the job
model — it is `JobOutcomeStatus.WAITING_APPROVAL`, which carries no
`ErrorCode` at all (confirmed: `JobOutcome.waiting_approval()` takes no
error parameter, `core/jobs/models.py:127-131`).

---

## 9. `OperationSpec` fields that do not exist yet (MKT-11C, `core/jobs/registry.py`)

Current fields: `operation`, `params_model`, `handler`, `risk_class`,
`description`, `sensitive_param_fields`, `dev_only`. The MKT-11D brief asks
for `cancel_support`, `long_running`, `produces_artifacts`,
`may_wait_for_approval` — **none exist today**. Adding them is an additive,
backward-compatible dataclass change (new fields with defaults); the three
existing `demo.*` registrations need no changes to keep working.

`JobOutcome.waiting_approval()` (`core/jobs/models.py:127-131`) currently
accepts only `reason` — no `data` / `result_ref`. The brief's §7 requires
"result data parcial, artifacts disponibles" on the WAITING_APPROVAL
outcome. This needs a small, additive signature extension (optional
`data`/`result_ref` kwargs) — the only other MKT-11C file this milestone
touches besides adding a new operations module.

---

## 10. Test inventory to preserve verbatim

`tests/cli/test_cli_run_campaign.py` — 7 tests, all currently passing,
all must keep passing **unmodified**:

1. `test_run_campaign_demo_succeeds` — exit 0, full payload shape
2. `test_run_campaign_writes_expected_files` — 12 named output files
3. `test_run_campaign_missing_intake_fails` — exit 2
4. `test_run_campaign_strict_blocks_on_critical` — exit 4
5. `test_run_campaign_require_approval_blocks_when_risky` — exit 3
6. `test_run_campaign_stop_on_blocked_exits_zero` — exit 0, 2 skipped stages
7. `test_audit_trail_records_pipeline_run` — `started`/`finished` events, valid hash chain

---

## 11. What this inventory rules out

- **No `--client` param exists** for `campaign.run`'s params model to
  mirror — the params model takes an intake path/reference, not a slug.
- **No secret ever needs to enter `JobRecord.params`** — the CLI already
  resolves `ANTHROPIC_API_KEY` from the environment at call time and passes
  a constructed invoker object, never the key itself, into the orchestrator.
  The job params model should carry `backend` + `claude_model` (both
  non-secret) and let the service resolve the key from the environment at
  **execution** time, exactly mirroring today's CLI behaviour — not a new
  pattern.
- **Cancellation cannot be supported** — `run()` is one long synchronous
  call into `PipelineOrchestrator`; there is no checkpoint. Confirms the
  brief's `cancel_support=False` requirement is not just conservative, it's
  the only honest option, identical in kind to MKT-11C's `InlineJobRunner`
  RUNNING-cancel limitation.
