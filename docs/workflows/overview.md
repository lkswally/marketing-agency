# Workflows — Overview

> Status: **specs only** (MKT-1E). No runtime executes these yet.
> Spec format version: `workflow-spec.v1` (not yet a Pydantic contract — see ADR 0005).

A workflow is a declarative description of how a marketing motion runs: which
phases, which agents, which gates, which outputs, where humans approve. The
dispatcher (MKT-2A+) will load these YAML files; nothing executes them today.

---

## 1. The 6 workflows in v1

| ID | Workflow | Purpose |
|----|----------|---------|
| **W1** | `intake_to_strategy` | New client onboarding through positioning. |
| **W2** | `keyword_and_competitor_research` | Keyword universe + competitor baseline. |
| **W3** | `campaign_builder` | Brief + strategy → planned Campaign with channels & offers. |
| **W4** | `creative_factory_draft` | Asset drafts: copy, social posts, reels scripts, emails, landing copy. |
| **W5** | `claim_audit_and_approval` | Compliance pass + Approval Center handoff. |
| **W6** | `report_summary` | Period report from existing metrics (no live data in MVP). |

Dependency hint (informational; not enforced by the format):

```
W1 ──┬──> W2 ──┬──> W3 ──> W4 ──> W5 ──> (ship)
     │         │                   │
     └────────→┴───────────────────┴──> W6 (any time after baseline data exists)
```

---

## 2. YAML schema (informal)

```yaml
workflow_id: string                  # required, unique. Format: W{N}_<snake_name>
version: int                         # required, integer. Bumped on breaking change.
spec_version: "workflow-spec.v1"     # required, pinned literal
description: |
  Multi-line description.

phases:                              # required, non-empty list
  - id: string                       # required, unique within the workflow
    agents: [string]                 # required, non-empty list of agent_id
    gates_required_before: [string]  # optional, default []
    gates_produced: [string]         # optional, default []
    outputs: [string]                # informational; entity kinds produced
    description: string              # optional

approval:                            # optional
  state_machine: "standard"          # see approval-center.md
  human_required_at: [string]        # phase ids that require human approval

notes: [string]                      # optional, free-form
```

### 2.1 Field rules

| Field | Rule |
|-------|------|
| `workflow_id` | Matches `^W[0-9]+_[a-z0-9_]+$`. |
| `version` | Integer ≥ 1. Increments on breaking change to phase order, gates, or outputs. |
| `phases[].id` | Lowercase snake_case, unique within the workflow. |
| `phases[].agents` | Every entry must exist as a file under `agents/<agent_id>.md`. |
| `phases[].gates_required_before` | Every entry must be produced by an earlier phase in this workflow OR by another workflow whose completion is a precondition. |
| `phases[].gates_produced` | Follows the gate naming convention in §3. |
| `approval.human_required_at` | Each entry must be a phase id present in this workflow. |

These rules are documented for downstream validators (MKT-2A) and for reviewers
reading the YAML. They are NOT enforced by code in MKT-1E.

---

## 3. Phase gate naming convention

Gates follow `g_<noun>_<verb_past>`:

| Gate | Produced by | Meaning |
|------|-------------|---------|
| `g_brief_captured` | W1.intake | A non-empty `MarketingBrief` has been persisted. |
| `g_audience_research_complete` | W1.research | At least one `Audience` (and any `Persona`) persisted. |
| `g_competitor_baseline` | W2.competitor | At least one `Competitor` with sources captured. |
| `g_keywords_drafted` | W2.keywords | A keyword universe (clusters + negatives) persisted to memory. |
| `g_positioning_drafted` | W1.strategy | A `Positioning` persisted. |
| `g_brand_voice_captured` | W1.strategy | A `Brand.voice` persisted. |
| `g_channels_proposed` | W3.channel_mix | At least one `Channel` proposed for the campaign. |
| `g_offer_drafted` | W3.offer | At least one `Offer` referenced by the campaign. |
| `g_campaign_drafted` | W3.assemble | A `Campaign` persisted with `status: planned`. |
| `g_creatives_drafted` | W4.* | At least one `Asset` per requested channel. |
| `g_compliance_passed` | W5.compliance | All creative assets carry a `ClaimAudit` with `blocks_emission == False`. |
| `g_approval_granted` | W5.approval | Approval Center status is `APPROVED`. |
| `g_report_drafted` | W6 | A `Report` persisted. |

Adding a new gate is additive in `workflow-spec.v1`. Removing/renaming an
existing one is breaking and requires updating every workflow that references
it.

---

## 4. Approval coupling

Workflows opt into the Approval Center via `approval.human_required_at`. The
state machine is fixed and documented in [`../approval-center.md`](../approval-center.md).
Conservative defaults in v1:

- W1 → human required at `strategy`.
- W3 → human required at `assemble`.
- W4 → no human gate (drafts).
- W5 → human required at `approval`.
- W6 → no human gate.
- W2 → no human gate (research).

---

## 5. What workflows do NOT carry

- Concrete prompts for agents (those live in `agents/<id>.md`).
- Skill implementations (those are `skills/<id>.md` specs only).
- Cron / scheduling info (out of scope; the dispatcher decides cadence).
- External API credentials (never in YAML).

---

## 6. Lifecycle of a workflow spec

1. **`spec_only`** (MKT-1E). YAML exists, no executor. The dispatcher MUST
   refuse to run it.
2. **`implemented`** (MKT-2A+). Dispatcher loads the YAML, validates against
   the (future) `workflow-spec.v1` Pydantic contract, and runs phases.
3. **`deprecated`**. Superseded by a higher-version YAML; kept for audit
   reconstruction.

The current status of each workflow is **NOT** tracked in the YAML for v1;
status is implicit from the absence of dispatcher support.
