# Claim Audit + Approval Pack (MKT-3B)

> Status: **implemented** (MKT-3B).
> Module: `core.approval`.
> Backend: rules-based, deterministic (no LLM, no API, no MCP).
> Contract: `approval-pack.v1`.
> CLI entries:
> - `mkt audit-strategy --client <slug>`
> - `mkt run-strategy --brief <path> --audit` (chained)

The approval pack is the gate between "we generated a strategy" and "we
can ship it". It runs a deterministic claim auditor over the
`CampaignStrategyReport` produced by MKT-3A, surfaces every risky span,
classifies it by severity, and bundles the results into an
`ApprovalPack` that a human reviewer can sign off on.

It runs without LLMs, without external APIs, without MCP servers.

---

## 1. What it produces

For every claim detected, the pack records:

- `category` — what kind of risk (`guaranteed_outcome`, `medical_or_sensitive`,
  `superlative`, `competitor_comparison`, `artificial_urgency`,
  `unsourced_statistic`, etc.).
- `severity` — `safe` / `caveat` / `risky` / `unsafe` (reuses the
  vocabulary from `claim-audit.v1`).
- `text_span` — the exact substring that matched.
- `located_in` — JSON-pointer-ish path inside the report
  (`email_sequence.emails[2].body`, `value_proposition.headline`, ...).
- `rule_id` + `rule_description` — auditable provenance.
- `suggested_mitigation` — actionable remediation hint.

Plus, at pack level:

- `overall_severity` — at least as high as the max detection severity.
- `blocks_publish` — policy flag a future publisher MUST honor.
- `checklist` — human-facing items grouped as `blocker` / `must` / `should`.
- `state` — pack lifecycle (`draft` → `needs_review` → `approved` |
  `rejected`).

---

## 2. Architecture

```
CampaignStrategyReport (MKT-3A)
        │
        ▼
ClaimAuditor.audit(report)
        │
        │ for every high-risk field, against every rule
        │
        ▼
list[ClaimDetection]
        │
        ▼
ApprovalPackBuilder.build_from_report(report)
        │
        ▼
ApprovalPack  (state=draft, blocks_publish derived)
        │
        ▼
ApprovalPackBuilder.persist(pack)
        │
        │ writes:
        │   data/clients/<slug>/approval_pack/current.json
        │ emits audit event:
        │   approval_pack created
        │
        ▼
(human reviews)
        │
        ▼
submit_for_review / approve / reject
        │ emits audit event per transition
        ▼
Terminal state
```

### 2.1 Module map (`core/approval/`)

| File | Purpose |
|------|---------|
| `models.py` | Pydantic models — `ApprovalPack`, `ClaimDetection`, `ClaimRule`, `ApprovalChecklistItem`, `ApprovalDecision`, `ApprovalState`, `ClaimCategory`. |
| `claim_auditor.py` | `ClaimAuditor` class + `DEFAULT_RULES` (22 rules). Compiles patterns lazily; broken regexes surface at construction time. |
| `approval_pack.py` | `ApprovalPackBuilder` — build / persist / transition. `audit_and_persist` convenience helper. |
| `renderer.py` | Pure Markdown renderer over `ApprovalPack`. |

### 2.2 Memory kind

- `approval_pack` — singleton id `"current"` per client (consistent with
  the strategy report convention from MKT-3A).

### 2.3 Audit events

Recorded via the existing `audit-trail.v1`:

| Action (payload key `approval_pack.action`) | Triggered by |
|---------------------------------------------|--------------|
| `created` | `ApprovalPackBuilder.persist(...)` on a new pack. |
| `updated` | `persist(...)` when the pack already existed. |
| `submitted` | `submit_for_review(...)`. |
| `approved` | `approve(reviewer, notes)`. |
| `rejected` | `reject(reviewer, notes)`. |

All events are wrapped in `event_type=note` with payload key
`approval_pack` so they coexist with the broader audit trail. A future
block may promote these to first-class `event_type` values (additive to
`audit-trail.v1`).

---

## 3. The default rule set

22 rules (`default-rules.v1`) covering the 12 risk categories the user
asked for:

| Category | Default severity | Example trigger |
|----------|------------------|-----------------|
| `guaranteed_outcome` | unsafe | "te aseguramos", "garantizado" |
| `risk_free_claim` | unsafe / risky | "sin riesgo", "garantizado o tu dinero" |
| `financial_promise` | unsafe / risky | "ROI garantizado", "ahorrá dinero" |
| `legal_or_tax` | unsafe | "deducible", "tax-free" |
| `medical_or_sensitive` | unsafe | "cura", "previene", "diagnóstico" |
| `superlative` | risky | "somos los mejores", "líder absoluto" |
| `competitor_comparison` | risky | "mejor que <Competitor>" |
| `exaggerated_benefit` | caveat | "increíble", "vas a flipar" |
| `artificial_urgency` | caveat | "solo hoy", "últimas 5 unidades" |
| `unsourced_statistic` | risky | numeric `%`, `3x más` |
| `absolute_claim` | caveat | "siempre funciona", "nunca falla" |
| `generic_promise` | caveat | "aumentá tus ventas" |

### 3.1 Custom rule sets

```python
from core.approval import ClaimAuditor, ClaimRule, ClaimCategory
from core.domain.enums import ClaimSeverity

custom = [
    ClaimRule(
        rule_id="acme.banned_phrase",
        category=ClaimCategory.SUPERLATIVE,
        default_severity=ClaimSeverity.UNSAFE,
        description="Frase específica vetada por el cliente.",
        pattern=r"\bnumber one experience\b",
        suggested_mitigation="Reescribir.",
    ),
]

auditor = ClaimAuditor(rules=custom, rule_set_id="acme.v1")
```

The `rule_set_id` is persisted on the pack so audits are traceable to
their source ruleset.

---

## 4. High-risk fields scanned

The auditor only walks fields likely to carry persuasion-driven copy:

- `executive_summary.headline` + `one_liner`
- `value_proposition.headline` + `differentiators[*]` + `proof_points[*]`
- `email_sequence.emails[*]` — subject, preview_text, body, CTA
- `social_post_drafts[*]` — hook, body, CTA
- `reels_script_pack.scripts[*]` — hook, voiceover_lines[*], on_screen_text[*], CTA
- `creative_brief_pack.briefs[*]` — copy_overlay[*], CTA
- `suggested_pieces[*].purpose`

Non-textual fields (schedules, checklists, metric ids) are skipped on
purpose: they would produce noise and no signal.

---

## 5. State machine

```
DRAFT ──submit_for_review──▶ NEEDS_REVIEW ──approve──▶ APPROVED
  │                              │
  │                              └─reject──▶ REJECTED
  │
  └─ (cannot skip review without going through it)
```

Disallowed transitions raise `ApprovalStateError`:

- `submit_for_review` from anything that isn't `DRAFT`.
- `approve` an already-`APPROVED` or `REJECTED` pack.
- `reject` an already-`APPROVED` or `REJECTED` pack.

### 5.1 Mapping to the formal Approval Center states

The Approval Center spec (`docs/approval-center.md`) defines five states:
`PROPOSED → IN_REVIEW → APPROVED | REJECTED | NEEDS_REVISION`. The
MKT-3B pack uses a subset:

| MKT-3B `ApprovalState` | Approval Center equivalent |
|------------------------|---------------------------|
| `DRAFT` | (pre-PROPOSED — the pack is not yet submitted) |
| `NEEDS_REVIEW` | `IN_REVIEW` |
| `APPROVED` | `APPROVED` |
| `REJECTED` | `REJECTED` |

There is no direct equivalent of `NEEDS_REVISION` in MKT-3B; when the
Approval Center implementation block lands, the mapping will translate
`NEEDS_REVISION` back into a fresh `DRAFT` pack with the reviewer's
notes attached.

---

## 6. `blocks_publish` policy

| Pack state | overall severity | `blocks_publish` |
|-----------|------------------|------------------|
| Any non-terminal | `safe` / `caveat` | `False` |
| Any non-terminal | `risky` / `unsafe` | **`True`** |
| `APPROVED` | any | `False` |
| `REJECTED` | any | **`True`** |

The flag is policy-only in MKT-3B — no publisher exists yet. Future
publishers (MKT-MCP-8 via n8n, future email send adapter) MUST consult
the flag and refuse to act when it is `True`.

---

## 7. CLI usage

### 7.1 Chained — strategy + audit in one command

```bash
mkt run-strategy \
  --brief examples/clients/demo-saas/brief.json \
  --root data/clients \
  --outputs-dir outputs \
  --audit
```

Output is the same JSON as `mkt run-strategy`, plus an `approval_pack`
key with a small summary. Two Markdown files are written:

- `outputs/campaign-strategy.md`
- `outputs/approval-pack.md`

### 7.2 Standalone — audit a previously persisted report

```bash
mkt audit-strategy --client demo-saas --root data/clients --outputs-dir outputs
```

Loads the persisted `CampaignStrategyReport` for the client, audits it,
writes `outputs/approval-pack.md`, persists the pack to memory.

Exit codes:
- `0` — pack produced (regardless of severity).
- `1` — auditor failure (reserved; nothing today triggers it).
- `2` — no persisted report for the client.

---

## 8. Programmatic API

```python
from pathlib import Path

from core.memory import JsonFileMemory
from core.strategy import StrategyPipeline
from core.approval import ApprovalPackBuilder, ClaimAuditor, render_markdown_pack

mem = JsonFileMemory(Path("data/clients"))

# 1. Get a strategy report.
report = StrategyPipeline(memory=mem).run_from_path(
    "examples/clients/demo-saas/brief.json"
).report

# 2. Build + persist a draft pack.
builder = ApprovalPackBuilder(memory=mem, auditor=ClaimAuditor())
pack = builder.build_from_report(report)
builder.persist(pack)

# 3. (Human reviews via Markdown render)
print(render_markdown_pack(pack))

# 4. Transitions
builder.submit_for_review(report.client_slug)
final = builder.approve(report.client_slug, reviewer="lucas", notes="Aprobado")

assert final.blocks_publish is False
```

---

## 9. Limitations (and the block that opens them)

| Concern | Block |
|---------|-------|
| LLM-backed claim detection (catches paraphrases the regex misses) | dedicated block, post-Claude Code safety |
| Source-aware evidence linking (`Claim` ↔ `Evidence` from MKT-1B) | MKT-3B+ continuation |
| Approval Center real entity + UI | dedicated Approval Center implementation block |
| Custom rules per client | post-MKT-3B (just plumbing) |
| Workflow-level halt-and-wait at `g_approval_packaged` | MKT-3B continuation |
| External publisher honoring `blocks_publish` | MKT-MCP-8 (via n8n) |
| Image-content audit (not just text) | post-image-gen block |

---

## 10. Audit trail invariants

Even after MKT-3B's transitions, the audit chain remains valid:

```python
from core.contracts import verify_chain
events = mem.read_audit_events(client_slug)
assert verify_chain(events) == []
```

The pack actions are recorded as `event_type=note` with a `payload.approval_pack`
sub-dict. A future block may promote them to first-class types in
`audit-trail.v2`.
