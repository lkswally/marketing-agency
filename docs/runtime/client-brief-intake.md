# Client Brief Intake Pack (MKT-3E)

> Status: **implemented** (MKT-3E).
> Module: `core.intake`.
> Backend: deterministic, LLM-free, no data fabrication.
> Contracts: `client-intake.v1` + `intake-validation.v1`.
> CLI entry: `mkt intake --file <path>`.

The intake layer is the **first mile** of the agency pipeline. Given a
friendly JSON file describing a client, it produces:

1. A persisted `ClientIntake` (exactly what the human sent — auditable).
2. A persisted `IntakeValidationResult` (severity-tagged warnings).
3. A `StrategyInputBrief` (MKT-1B / MKT-3A) ready for
   `mkt run-strategy --brief`.
4. A Markdown summary the reviewer can scan in seconds.

**The cardinal rule: no data is invented.** Missing fields are reported,
not filled.

---

## 1. The intake JSON shape

```json
{
  "schema_version": "client-intake.v1",
  "client_name": "Acme Bootstrapped",
  "industry": "marketing automation",
  "market": "LATAM",
  "product_or_service": "Acme Pro — suite de automatización...",
  "product_type": "subscription",
  "audience_description": "Fundadores de SaaS bootstrapped...",
  "commercial_objective": "150 trials calificados/mes...",
  "brand_tone": ["claro", "directo", "irreverente"],
  "preferred_words": ["equipos", "lanzar"],
  "forbidden_words": ["disruptivo", "sinergia"],
  "claim_style": "Específico, con fuente...",
  "possible_channels": ["newsletter", "linkedin"],
  "known_competitors": [
    {"name": "Big SaaS", "url": "https://...", "notes": "enterprise"}
  ],
  "budget_estimate": 3500,
  "budget_currency": "USD",
  "deadline": "2026-09-30",
  "duration_weeks": 10,
  "primary_kpi": "qualified_trials",
  "locale": "es-AR",
  "constraints": ["No paid ads en el primer mes"],
  "claims_to_avoid": ["Garantizados", "Sin riesgo"],
  "good_examples": ["..."],
  "bad_examples": ["..."],
  "additional_context": "...",
  "client_slug_override": null
}
```

Only `client_name` is hard-required by Pydantic. Everything else is
optional. The validator decides the severity of each missing field.

A complete demo lives at `examples/intake/demo-business.json`.

---

## 2. Validation severity matrix

| Field missing | Severity | Why |
|---------------|----------|-----|
| `client_name` (or underivable slug) | **critical** | No client identity |
| `product_or_service` | **critical** | Brief requires a product |
| `commercial_objective` | **critical** | Brief requires an objective |
| `audience_description` | **critical** | Brief requires at least one audience hint |
| `industry` | warning | Diagnosis loses precision |
| `market` | warning | Audience demographics incomplete |
| `brand_tone` (empty) | warning | Copy will be neutral |
| `known_competitors` (empty) | warning | Benchmark confidence low |
| `budget_estimate` | warning | Strategy avoids paid recommendations |
| `constraints` (empty) | warning | Reviewer can't see "what NOT to do" |
| `duration_weeks` | info | Default 8 applied (see §3) |
| `primary_kpi` | info | Default `qualified_leads` applied |
| `locale` | info | Default `es-AR` applied |
| `deadline` | info | Calendar starts at today |
| `claim_style` | info | Reasonable default |
| `forbidden_words` (empty) | info | Banned words list empty |
| `good_examples` / `bad_examples` (both empty) | info | Useful for tone calibration |
| Unknown `possible_channels[i]` | warning | Channel dropped from brief |

Critical → `can_normalize=False`. Warning / info → still normalizable.

---

## 3. The three operational defaults

The normalizer applies **exactly three defaults** when the corresponding
fields are missing:

| Field | Default | Constant |
|-------|---------|----------|
| `duration_weeks` | `8` | `DEFAULT_DURATION_WEEKS` |
| `primary_kpi` | `"qualified_leads"` | `DEFAULT_PRIMARY_KPI` |
| `locale` | `"es-AR"` | `DEFAULT_LOCALE` |

These are NOT inventions. They are documented operational defaults the
pipeline already uses (declared in `core/strategy/models.py` and
`core/intake/validator.py`). Every applied default is recorded in
`IntakeValidationResult.operational_defaults_applied` and surfaced in the
Markdown summary under section 04.

Every other field that is missing stays empty / `None` in the brief. No
exception.

---

## 4. Slug derivation

The client slug is derived from `client_name` via
`core.intake.derive_slug`:

- Lowercase.
- Non-alphanumeric runs collapsed to a single dash.
- Leading / trailing dashes stripped.
- Clamped to 64 characters (slug field max).
- Rejected if it conflicts with reserved slugs (`_shared`).
- Rejected if it ends up empty (e.g. `"!!!"`).

Override the derivation explicitly with `client_slug_override` if you
need a specific slug.

---

## 5. Architecture

```
intake.json (human)
     │
     ▼
ClientIntake.model_validate(raw)   ← Pydantic (schema check)
     │
     ▼
IntakeValidator.validate(intake)   ← deterministic warnings
     │
     ▼
IntakeValidationResult
     │
     │ if can_normalize:
     ▼
normalize_intake(intake, validation) ─► StrategyInputBrief
     │                                       │
     ▼                                       ▼
data/clients/<slug>/client_intake/     outputs/<slug>/brief.json
                /intake_validation/
                /audit/
outputs/<slug>/intake.json
outputs/<slug>/intake-summary.md
```

### 5.1 Module map (`core/intake/`)

| File | Purpose |
|------|---------|
| `models.py` | `ClientIntake`, `CompetitorIntake`, `IntakeWarning`, `IntakeValidationResult`. |
| `validator.py` | `IntakeValidator` + severity rules + `derive_slug`. |
| `normalizer.py` | `normalize_intake(intake, validation) → StrategyInputBrief`. |
| `renderer.py` | Pure Markdown renderer. |

### 5.2 Memory kinds

- `client_intake` — singleton id `"current"` per client.
- `intake_validation` — singleton id `"current"` per client.

### 5.3 Audit events

`mkt intake` emits one `event_type=note` event per run with
`payload.intake.action == "created"`. Same wrapping pattern as MKT-3B / 3C / 3D.

---

## 6. CLI usage

```bash
# Validate + normalize a brand-new client intake:
mkt intake --file examples/intake/demo-business.json

# Continue the pipeline with the produced brief:
mkt run-strategy --brief outputs/acme-bootstrapped/brief.json --audit
mkt build-creatives --client acme-bootstrapped
mkt build-visuals   --client acme-bootstrapped
```

Exit codes:

- `0` — intake processed (even with warnings).
- `2` — intake file missing, malformed JSON, or Pydantic validation
  failure.
- `4` — `--strict` was set AND the validator found critical issues.

Output to stdout is a JSON summary with paths, counts, and the resolved
slug. Disk side effects:

- `outputs/<slug>/intake.json` — what the human sent, normalized JSON.
- `outputs/<slug>/intake-summary.md` — readable summary with warnings.
- `outputs/<slug>/brief.json` — written only when `can_normalize=True`.
- `data/clients/<slug>/client_intake/current.json` (persisted).
- `data/clients/<slug>/intake_validation/current.json` (persisted).
- An audit event recording the action.

The `--strict` flag is intended for CI: it returns exit 4 when critical
issues are present, so a pipeline can fail-fast.

---

## 7. Programmatic API

```python
import json
from pathlib import Path

from core.intake import (
    ClientIntake,
    IntakeValidator,
    normalize_intake,
    render_intake_summary,
)

data = json.loads(Path("examples/intake/demo-business.json").read_text(encoding="utf-8"))
intake = ClientIntake.model_validate(data)

validation = IntakeValidator().validate(intake)
if validation.can_normalize:
    brief = normalize_intake(intake, validation)
    # brief is a StrategyInputBrief ready for `mkt run-strategy --brief`.

print(render_intake_summary(intake, validation))
```

---

## 8. Pipeline position

```
INTAKE (MKT-3E)
   │ feeds
   ▼
StrategyInputBrief
   │ consumed by
   ▼
StrategyPipeline (MKT-3A) ─► CampaignStrategyReport
   │ feeds
   ▼
ApprovalPack (MKT-3B)
   │ feeds
   ▼
CreativeAssetPack (MKT-3C)
   │ feeds
   ▼
VisualDirectionPack (MKT-3D)
```

The intake is the **only** layer that talks to humans in v1. Everything
downstream consumes typed Pydantic models.

---

## 9. The "no fabrication" guarantee

The validator and normalizer were designed and tested to never
manufacture data. Three invariants:

1. **The intake is never mutated** — the validator's `validate(intake)`
   is a pure function of its input (test:
   `test_validator_never_mutates_intake`).
2. **Empty / `None` fields stay empty / `None`** in the produced brief
   (tests: `test_industry_preserved_as_none_when_missing`,
   `test_budget_preserved_as_none_when_missing`, etc.).
3. **Only three documented defaults** are applied (`duration_weeks`,
   `primary_kpi`, `locale`), each declared in the warnings and in
   `operational_defaults_applied`.

Adding a new default to the normalizer requires adding it to the
documentation, to the validator's `_collect_info_and_defaults`, and to
the operational-defaults dict so it is auditable.

---

## 10. Limitations (and where they open)

| Concern | Block |
|---------|-------|
| Web form for intake (no JSON typing) | dedicated landing/portal block |
| LLM-assisted intake completion | post-Claude Code safety |
| Multi-language intake (currently Spanish/English mixed) | continuation block |
| Import from Notion / Google Forms / Typeform | per-source adapter blocks |
| Versioned intake (history / diff) | as needed |
| Interactive `mkt intake --wizard` | as operational case demands |
| Intake-side image attachments (logo, references) | post image-gen block |

---

## 11. Audit trail invariants

After a complete intake + strategy + audit + creative + visual cycle,
the chain contains `intake`, `workflow_started`/`envelope_received`/...,
`approval_pack`, `creative_pack` and `visual_pack` events. The chain
remains valid:

```python
from core.contracts import verify_chain
events = mem.read_audit_events(client_slug)
assert verify_chain(events) == []
```
