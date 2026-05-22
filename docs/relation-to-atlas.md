# Relation to ATLAS

MARKETING-AGENCY-OS (MKT) and ATLAS are **independent systems**. This document defines the boundary.

---

## Rule of independence

1. **MKT does not import ATLAS code.** Ever. No `from atlas import ...`, no symlinks, no shared Python paths.
2. **ATLAS does not depend on MKT.** ATLAS must run identically whether MKT exists on disk or not.
3. **MKT runs standalone.** With zero ATLAS components installed, MKT-1A through MKT-5C must function fully.

The two repos live as siblings:

```
D:\ProyectosIA\
├─ ProyectosClaude\        # ATLAS (and other Claude work)
└─ MARKETING-AGENCY-OS\    # MKT (this repo)
```

---

## What MKT inherits from ATLAS

**Philosophy only.** Patterns proven by ATLAS that MKT adopts independently:

| Pattern | How MKT applies it |
|---------|--------------------|
| Return Envelope | `docs/contracts/envelope.md` (MKT-1C). MKT's envelope is distinct: includes `claims_audit`, drops `pre_return_audit` (which is code-focused in ATLAS). |
| Phase Gates | `docs/contracts/phase-gates.md` (MKT-1C). Predicates over workflow state. |
| Audit Trail (append-only) | `docs/contracts/audit-trail.md` (MKT-1C). JSONL per client per day. |
| Engram as persistent memory | Optional backend in MKT. Default is local JSON. |
| Fail-open external integrations | All adapters in `integrations/` swallow failures, log, and return degraded results. |
| Enforcement opt-in | Hard rejection of malformed envelopes is opt-in via env var until contracts stabilize. |
| Separation of concerns | Agents (role specs) vs Skills (capabilities) vs Workflows (DAGs) vs Outputs (artifacts). |

---

## What MKT does NOT inherit

| Item | Why not |
|------|---------|
| ATLAS dispatcher code | MKT writes its own (MKT-2A). Smaller surface, different domain. |
| ATLAS helpers (16 in `tools/atlas_dispatcher.py`) | Not reusable — they're tied to ATLAS's pipeline, phase definitions, and engram namespace. |
| ATLAS pre-return audit | Targets code artifacts (debugger, .only, secrets). MKT's audit targets **claims, sources, fabricated data** — different ruleset, separate subsystem. |
| Playwright / visual QA | Not relevant until MKT has a landing page (future). |
| ATLAS hook system | MKT's hooks (if needed) will live under its own `.github/hooks/` or similar, never `~/.claude/hooks/`. |
| ATLAS Engram topic key conventions | MKT uses its own namespace and its own conventions. |

---

## Engram namespace

| System | Namespace prefix |
|--------|------------------|
| ATLAS | `atlas/*` |
| MKT | `marketing-agency-os/*` |
| MKT cross-client | `marketing-agency-os/_shared/*` |

These two prefixes are **disjoint**. A misconfigured agent that tries to write `atlas/something` from MKT (or vice versa) must be caught by the Memory adapter (MKT-1D) and rejected.

---

## The bridge (future, MKT-6C)

A single module `bridge/atlas_adapter.py` will expose a small, versioned surface for ATLAS to invoke MKT operations.

### Contract shape (sketch — to be finalized in MKT-6C)

```python
# bridge.v1 — DO NOT IMPLEMENT YET (MKT-6C)
def run_workflow(workflow_name: str, client_slug: str, brief: dict) -> Envelope: ...
def validate_claims(client_slug: str, text: str) -> ClaimsAudit: ...
def get_brand_voice(client_slug: str) -> BrandVoice: ...
```

### Activation

- **Off by default.** Adapter is not imported unless `MKT_BRIDGE_ATLAS=1` is set in the environment.
- **Kill-switch:** `MKT_BRIDGE_ATLAS=0` (or unset) disables instantly. No restart required for downstream consumers.

### Direction

- ATLAS → MKT only. MKT never reaches into ATLAS.
- If MKT ever needs to ask ATLAS something, it does so via a separate `atlas_client.py` (also opt-in), not the bridge.

### Versioning

- `bridge.v1` is the initial contract. Breaking changes bump to `bridge.v2`. Both versions may coexist during transition.

---

## Operational implications

- **No shared CI.** Each repo has its own GitHub Actions.
- **No shared dependencies.** MKT pins its own versions in `pyproject.toml`.
- **No shared `.env`.** Secrets live in MKT's repo or in MKT's per-client dirs.
- **No shared CLAUDE.md.** MKT can have its own `CLAUDE.md` if/when needed (likely MKT-2A).

---

## Verification

This boundary is verifiable at any time by:

```bash
# 1. ATLAS must show no awareness of MKT
cd D:\ProyectosIA\ProyectosClaude
grep -r "MARKETING-AGENCY-OS\|marketing-agency-os" --include="*.py" --include="*.md" --include="*.json"
# Expected: zero matches.

# 2. MKT must not import from ATLAS
cd D:\ProyectosIA\MARKETING-AGENCY-OS
grep -r "from atlas\|import atlas\|ProyectosClaude" --include="*.py"
# Expected: zero matches.
```

If either check produces matches, the independence rule is broken and must be repaired before the next block.
