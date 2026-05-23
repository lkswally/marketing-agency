# Claim Audit — Contract `claim-audit.v1`

> Version: **v1** (MKT-1C).
> Implementation: `core/contracts/claim_audit.py`.
> Breaking changes bump to `claim-audit.v2`.

Compliance is a first-class subsystem of MKT (see `ARCHITECTURE.md` D4). The
Claim Audit contract is the **block embedded in a Return Envelope** when the
agent's output carries factual assertions. Without it, an envelope cannot
ship claims past `claim_strict` gates.

This contract specifies the **shape** of an audit and the **emission policy**
(ship vs. block). It does NOT validate claims against evidence — that is the
claim-validator subsystem (MKT-3A).

---

## 1. When is a claim audit required?

| Carrying envelope's situation | `claims_audit` required? |
|-------------------------------|---------------------------|
| Output contains no factual assertions (e.g. structured config). | No (omit field). |
| Output carries copy, marketing claims, comparisons, percentages, attributions. | **Yes**, even if empty (`claims=[]` + `notes="no claims present"`). |
| Output is from a validator agent (e.g. claim-validator itself). | **Yes**, with verdicts. |

The dispatcher decides via the gate `claims_audit_present` (see
`phase-gates.md`).

---

## 2. Schema

```jsonc
{
  "contract_version": "claim-audit.v1",
  "claims": [
    {
      "claim_id": "c1",
      "text": "Customers ship 3x faster after switching.",
      "severity": "safe|caveat|risky|unsafe",
      "verdict":  "verified|partial|unverified|contradicted",
      "evidence_refs": [
        {
          "evidence_id": "e1",
          "location": "https://demo.co/case-studies/founder-x",
          "trust_level": 0.8
        }
      ],
      "rationale": "Supported by one internal case study."
    }
  ],
  "overall_severity": "caveat",
  "overall_verdict":  "partial",
  "notes": "Single-source claim; broader sample needed."
}
```

### 2.1 Field rules

| Field | Required | Rule |
|-------|----------|------|
| `contract_version` | Yes | Must equal `"claim-audit.v1"`. |
| `claims` | No | List of `ClaimAuditItem`. Default `[]`. |
| `claims[*].text` | Yes | 1..2000 chars. |
| `claims[*].severity` | Yes | Enum from `core.domain.ClaimSeverity`. |
| `claims[*].verdict` | Yes | Enum from `core.domain.ClaimVerdict`. |
| `claims[*].evidence_refs` | No | List of `EvidenceRef`. |
| `evidence_refs[*].trust_level` | No | 0..1 if present. |
| `overall_severity` | No (default `safe`) | MUST be ≥ max(item severities) when `claims` is non-empty. |
| `overall_verdict` | No (default `unverified`) | Aggregate verdict. Not numerically constrained. |
| Extra fields | — | Rejected. |

Severity rank order (low → high): `safe < caveat < risky < unsafe`. The
helper `core.contracts.severity_rank` exposes this rank.

---

## 3. Emission policy

The model exposes a computed property `blocks_emission: bool`:

| `overall_severity` | `overall_verdict` | `blocks_emission` |
|--------------------|-------------------|-------------------|
| `safe` | any | `False` |
| `caveat` | any | `False` |
| `risky` | `verified` | `False` |
| `risky` | `partial` | `False` |
| `risky` | `unverified` | **`True`** |
| `risky` | `contradicted` | **`True`** |
| `unsafe` | any | **`True`** |

When `blocks_emission == True`, the dispatcher MUST NOT ship the carrying
envelope. The phase gate `no_unsafe_claims` (see `phase-gates.md`) implements
this rule.

A human override can be added in a later block as a separate envelope field
(out of scope for `v1`).

---

## 4. Mapping to `core.domain`

`ClaimAudit` is a **denormalized, transport-friendly** shape derived from
`Claim` and `Evidence` entities in `core.domain`. The mapping is 1-to-1:

| Audit field | Source in `core.domain` |
|-------------|--------------------------|
| `claims[*].claim_id` | `Claim.id` |
| `claims[*].text` | `Claim.text` |
| `claims[*].severity` | `Claim.severity` |
| `claims[*].verdict` | `Claim.verdict` |
| `claims[*].evidence_refs[*].evidence_id` | `Evidence.id` |
| `claims[*].evidence_refs[*].location` | `Evidence.location` (optional in ref) |
| `claims[*].evidence_refs[*].trust_level` | `Evidence.trust_level` (optional in ref) |

The repository layer (MKT-1D+) decides whether to dereference the audit's
ids against stored entities. The contract does NOT enforce existence.

---

## 5. Validators

| Function | Returns / Raises |
|----------|------------------|
| `validate_claim_audit(payload)` | `(bool, list[ContractErrorPayload])` |
| `validate_claim_audit_strict(payload)` | `ClaimAudit` or `ContractError` |

---

## 6. Examples

### 6.1 No claims declared (valid)

```json
{
  "contract_version": "claim-audit.v1",
  "claims": [],
  "overall_severity": "safe",
  "overall_verdict": "verified",
  "notes": "No factual claims present in output."
}
```

### 6.2 Risky + unverified (blocks emission)

```json
{
  "contract_version": "claim-audit.v1",
  "claims": [
    {
      "claim_id": "c1",
      "text": "Used by Fortune 500 brands",
      "severity": "risky",
      "verdict": "unverified",
      "evidence_refs": [],
      "rationale": "No public source identified yet."
    }
  ],
  "overall_severity": "risky",
  "overall_verdict": "unverified"
}
```
→ `blocks_emission == True`.

### 6.3 Incoherent (rejected)

```json
{
  "contract_version": "claim-audit.v1",
  "claims": [
    {"claim_id": "c1", "text": "x", "severity": "unsafe", "verdict": "contradicted"}
  ],
  "overall_severity": "safe",
  "overall_verdict": "unverified"
}
```
→ `ContractError(code=invariant_violation, message="overall_severity=safe is below the maximum item severity=unsafe")`.

---

## 7. Versioning

- Additive change (new optional field, new enum member in domain): still `v1`.
- Change in `blocks_emission` policy table: breaking → `claim-audit.v2`.
- Removal of a field or stricter type: breaking → `v2`.
