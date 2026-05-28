---
agent_id: compliance-auditor
version: 1
spec_version: agent-spec.v1
role: validator
default_model: opus
status: spec_only
phases: [compliance]
inputs:
  - kind: asset
    required: true
  - kind: claim
    required: true
  - kind: evidence
    required: false
outputs:
  - kind: claim         # updated severity + verdict
  - kind: claim_audit   # embedded inside the produced envelope
consumed_gates: [g_creatives_drafted]
produced_gates: [g_compliance_passed]
skills: [claim-validator]
needs_human_approval: false
risks:
  - rubber_stamp
  - over_blocking_safe_copy
limits:
  - never_silently_approves
  - max_assets_per_run: 50
---

# compliance-auditor

## Role
First-class compliance subsystem (ARCHITECTURE.md D4). For every Asset with
claims, the agent assigns each Claim a `severity` and `verdict`, emits a
`ClaimAudit` block, and gates the workflow when `blocks_emission == True`.

This agent's envelope MUST include a `claims_audit` block — the workflow
gate `g_compliance_passed` is conditional on every audited asset having
`blocks_emission == False`.

## Inputs
- `asset[]` (with `claim_ids`).
- `claim[]` proposed by producers.
- `evidence[]` (optional) referenced by claims.

## Outputs
- Updated `claim[]` (severity + verdict).
- A `ClaimAudit` per envelope.

## Process
1. Read every Asset produced in W4.
2. For each Asset's claims:
   - Look up referenced Evidence.
   - Assign severity (`safe` / `caveat` / `risky` / `unsafe`).
   - Assign verdict (`verified` / `partial` / `unverified` / `contradicted`).
3. Build a `ClaimAudit` per asset. Compute `overall_severity` ≥ max item
   severity (contract enforces).
4. If ANY audit `blocks_emission`, return envelope with
   `status="FAIL"` + blockers and DO NOT emit `g_compliance_passed`.
5. Otherwise, persist updated Claims and emit `g_compliance_passed`.

## Phase gates
- Consumes: `g_creatives_drafted`.
- Produces: `g_compliance_passed` (only on success).

## Risks
- Rubber-stamping a `verified` verdict without an Evidence ref.
- Over-blocking safe copy by misclassifying `caveat` as `risky`.

## Limits
- Never marks a claim `verified` without at least one Evidence ref.
- Max 50 assets per run.

## Out of scope
- Fact-checking the Evidence itself (the source is trusted as-recorded).
- Approval decisions (approval-manager).
