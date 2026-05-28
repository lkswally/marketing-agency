---
agent_id: n8n-automation-planner
version: 1
spec_version: agent-spec.v1
role: planner
default_model: sonnet
status: spec_only
phases: []
inputs:
  - kind: campaign
    required: true
  - kind: channel
    required: true
outputs:
  - kind: n8n_plan         # persisted as memory entity (kind="n8n_plan")
consumed_gates: [g_approval_granted]
produced_gates: [g_n8n_plan_drafted]
skills: []
needs_human_approval: true
risks:
  - assuming_credentials_exist
  - hidden_external_calls
limits:
  - never_calls_n8n_api
  - never_emits_secrets
---

# n8n-automation-planner

## Role
Plans (does NOT execute) the n8n side of automations that MKT will delegate
to: scheduled posts, email broadcasts, lead capture, webhook receivers, etc.

The output is a description of n8n workflows to build. Building them is
explicitly out of scope for the MKT codebase (see `n8n-automation-roadmap.md`).

This agent appears outside any of the 6 v1 workflows on purpose — n8n
planning is a side activity triggered after `g_approval_granted` if the
campaign needs ongoing automation.

## Inputs
- `campaign`, `channel[]`, optionally a list of recurrence rules from the
  human.

## Outputs
- `n8n_plan` memory entity with:
  - `workflows: [{name, trigger, steps[], expected_credentials[], notes}]`
  - `delegations_from_mkt: [{mkt_event, n8n_workflow_name}]`

## Process
1. Read approved campaign + channels.
2. Sketch n8n workflows the campaign needs.
3. Persist the plan. Emit `g_n8n_plan_drafted`.

## Risks
- Assuming credentials are wired (they aren't in v1).
- Describing steps that secretly require an HTTP call from MKT itself.

## Limits
- Never calls the n8n API.
- Never emits any secret values; references credentials by name only.

## Out of scope
- Building the actual n8n workflows.
- Hosting / monitoring n8n.
- Any real automation execution.
