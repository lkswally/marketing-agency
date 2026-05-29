# Data Permissions Policy

> Status: **policy** (MKT-2C). Applies from the first external-source
> integration (post MKT-MCP-3). Today no external source is connected, so
> the policy is dormant; the moment one is wired in, every rule below is
> binding.

This is the single source of truth for "what can each external source do,
at what phase, with what approval". Roadmap docs reference this file; the
adapter code (when it lands) enforces it.

---

## 1. Default deny

Any operation not explicitly listed as allowed → **forbidden**.
There is no "general write" or "general read" mode. Every tool name
the MCP exposes is either in the allowlist, the explicit forbidden list,
or treated as forbidden by default.

---

## 2. `DataPermissionPolicy` shape

```yaml
contract_version: data-permission-policy.v0   # promoted with first adapter
source_id: "gads-acme"                        # references an ExternalDataSource

# READS
allowed_reads:
  - tool: { mcp_name: "gads", tool_name: "campaign.report" }
    scope: { entity_kinds: ["campaign", "ad_group", "keyword"], read_fields: ["*"] }
    rate_limit: { calls_per_minute: 30 }
    audit: required
  - tool: { mcp_name: "gads", tool_name: "search_term.report" }
    scope: { entity_kinds: ["search_term"], read_fields: ["*"] }
    rate_limit: { calls_per_minute: 30 }
    audit: required

# WRITES — always empty until R4 opens for this source
allowed_writes: []
approval_required_for: []   # populated only when R4 opens

# FORBIDDEN — explicit, never resolves through wildcards
forbidden_tools:
  - "mutate*"
  - "create*"
  - "update*"
  - "delete*"
  - "pause*"
  - "resume*"
  - "addKeywords*"
  - "removeKeywords*"
  - "setBudget*"

# FAIL POLICY
on_read_failure: "fail_open_log_warn"     # workflow continues with empty data
on_write_failure: "fail_closed_audit"     # only meaningful when allowed_writes is non-empty
on_unknown_tool: "fail_closed_audit"      # any tool not in allowlist/forbidden → reject
```

The adapter MUST evaluate the policy at every call, not at construction
time. A tool name resolved at call time that does not match any allowed
read AND matches no allowed write is rejected with a structured error
(`external_action_rejected` audit event).

---

## 3. Per-source matrix (default policies)

A starting point for each prioritized source. Adapters MAY narrow these
further; they MUST NOT widen them.

### 3.1 Google Analytics 4

| Phase | allowed_reads | allowed_writes |
|-------|---------------|----------------|
| R3 (post MKT-MCP-3) | `runReport`, `runRealtimeReport`, `runPivotReport`, `batchRunReports`, `getMetadata` | `[]` |
| R4 | not planned (`ga4` is treated as analysis-only) | `[]` |

### 3.2 Google Search Console

| Phase | allowed_reads | allowed_writes |
|-------|---------------|----------------|
| R3 (post MKT-MCP-5) | `searchanalytics.query`, `sitemaps.list`, `sitemaps.get`, `sites.list`, `urlInspection.index.inspect` | `[]` |
| R4 | not planned | `[]` |

### 3.3 Google Ads

| Phase | allowed_reads | allowed_writes |
|-------|---------------|----------------|
| R3 (post MKT-MCP-4) | `customer.list`, `campaign.search`, `adGroup.search`, `ad.search`, `keyword.search`, `searchTerm.search`, `*.report` | `[]` |
| R4 (FUTURE, **only after** double-approval rule below) | `campaign.mutate{PAUSE}`, `campaign.mutate{ENABLE}`, `campaignBudget.mutate`, `keyword.mutate{ADD,REMOVE}` | listed left ← |
| R4 forbidden forever (would require its own ADR) | `customer.mutate`, `account.delete`, anything touching billing or conversion settings | |

**Double-approval rule (Ads R4)**: every approved `ProposedAction`
against Google Ads requires sign-off by BOTH the account lead AND the
client side. Either party's `REJECT` cancels.

### 3.4 Google Drive / Sheets

| Phase | allowed_reads | allowed_writes |
|-------|---------------|----------------|
| R3 (post MKT-MCP-3 parallel) | `files.list`, `files.get`, `files.export`, `spreadsheets.values.get`, `spreadsheets.get` | `[]` |
| R4 per-folder (FUTURE) | `spreadsheets.values.update` SCOPED to folders the client explicitly delegated; `files.create` in same folders | listed left ← |

### 3.5 Gmail / email drafts

| Phase | allowed_reads | allowed_writes |
|-------|---------------|----------------|
| R3 (post MKT-MCP-7) | `users.messages.list`, `users.messages.get`, `users.drafts.list`, `users.drafts.get`, `users.labels.list` | `[]` |
| R4 draft-only (FUTURE) | `users.drafts.create`, `users.drafts.update` | listed left ← |
| Forbidden forever in current design | `users.messages.send`, `users.drafts.send`, anything that releases mail without a human click | |

### 3.6 YouTube / social analytics

| Phase | allowed_reads | allowed_writes |
|-------|---------------|----------------|
| R3 (post MKT-MCP-5 follow-on) | YouTube Analytics API read-only endpoints; other social platforms: only stable read-only MCPs | `[]` |
| R4 | not planned | `[]` |

### 3.7 n8n

n8n is an execution layer, not a data source. Its policy lives in
[`n8n-execution-roadmap.md`](n8n-execution-roadmap.md). Summary: a
single allowed write — `trigger_workflow` with a signed payload — and
only against workflows pre-registered in `n8n-registry`. Everything else
forbidden.

---

## 4. Approval coupling

A `ProposedAction` is the only path to any write. The bridge between a
`MarketingRecommendation` and an external mutation looks like:

```
optimizer-agent → MarketingRecommendation
                     │
                     ▼
              ProposedAction (state=PROPOSED)
                     │   approval-manager packages it
                     ▼
              Approval Center entry (state=PROPOSED)
                     │   human review
                     ▼
            APPROVED ──► adapter executes via DataPermissionPolicy
                     │
                     ▼
             execution result + audit event
```

Rules:

1. The Approval Center entry references the `ProposedAction.id` AND
   carries a snapshot of its parameters at the moment of approval. If
   the proposed parameters change before execution, a new approval is
   required.
2. Execution only happens after the approval reaches state `APPROVED`.
   `NEEDS_REVISION` returns to `optimizer-agent` with notes; `REJECTED`
   cancels.
3. The adapter that executes MUST re-evaluate the
   `DataPermissionPolicy` AND verify the action's tool is in
   `allowed_writes`. Even with approval, an out-of-policy action is
   rejected.

---

## 5. Promotion checklists

### 5.1 R2 (manual) → R3 (read-only programmatic)

Per source. Already documented in `mcp-roadmap.md` §6. Adds, for this
policy doc:

- [ ] `DataPermissionPolicy.allowed_reads` for the source is enumerated.
- [ ] `DataPermissionPolicy.forbidden_tools` is enumerated and includes
      every write-like pattern the source's MCP exposes.
- [ ] `on_unknown_tool: fail_closed_audit` is the configured default.

### 5.2 R3 (read-only) → R4 (write with approval)

Per source AND per allowed-write tool. The block opening R4:

- [ ] Has its own ADR.
- [ ] Lists every `allowed_writes` entry with full scope.
- [ ] Specifies whether double-approval applies (mandatory for Google
      Ads; optional but recommended for others).
- [ ] Adds the new audit event types (`proposed_action_*`) to
      `audit-trail.v1`.
- [ ] Documents the rollback path for `EXECUTION_FAILED`.

---

## 6. Audit events introduced by external sources

Additive to `audit-trail.v1` when adapters land. Defined here for
forward reference:

| Event type | When | Required fields |
|------------|------|-----------------|
| `external_fetch` | An adapter completes a read call. | `source_id`, `tool`, `byte_count`, `metric_ids` (the ids that were just created/updated) |
| `external_fetch_failed` | An adapter's read fails. | `source_id`, `tool`, `error_class`, `message` |
| `proposed_action_created` | A `ProposedAction` is persisted (state=PROPOSED). | `proposed_action_id`, `source_id`, `tool`, `target` |
| `proposed_action_approved` | Approval Center marks the linked approval as APPROVED. | `proposed_action_id`, `approval_id`, `reviewer` |
| `proposed_action_executed` | The adapter executes the approved action. | `proposed_action_id`, `result` |
| `proposed_action_failed` | Execution failed. | `proposed_action_id`, `error_class`, `message` |
| `external_action_rejected` | The adapter rejected an action attempt (policy violation, unknown tool, missing approval). | `source_id`, `tool`, `reason` |

---

## 7. Out of scope for MKT-2C

- Any adapter code.
- Any credential handling.
- Any actual approval flow implementation.
- Any audit event emission.
- Any `ProposedAction` entity in `core.domain`.
