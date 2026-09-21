# RND-MKT-SKILLS-01 — External Capability Analysis

> **Status:** RESEARCH / NON-RUNTIME — informational analysis only, no code
> in this repo depends on it, nothing here is implemented.
> **Method:** direct review of each repository's README/structure, cross-referenced
> against MAOS's actual current state as established in
> `docs/MAOS-AUTONOMOUS-AGENCY-MASTER-PLAN.md` (readiness matrix, §2–§5) and the
> MKT-11A–11D inventories. Where a comparison depends on a MAOS capability, the
> exact module/LOC/state is cited, not assumed.

---

## 0. Classification legend

| Label | Meaning |
|---|---|
| **ADOPT** | Use it directly — as a dependency or near-verbatim, with a short adapter |
| **ADAPT** | Reimplement the *idea* inside MAOS's own contracts (audit, evidence, multi-tenant, `OperationResult`) — don't import the code/format as-is |
| **INSPIRE** | Useful reference for scope/structure/naming — write MAOS's own version from scratch, informed by it |
| **DEFER** | Real value, wrong time — revisit once a named prerequisite milestone lands |
| **REJECT** | Wrong architecture, wrong risk posture, or duplicates something MAOS already does better |

---

## 1. `coreyhaines31/marketingskills`

**What it is:** 70+ Markdown `SKILL.md` files (CRO, content/copy, SEO, paid ads,
measurement, growth, strategy, sales/RevOps), following the generic "Agent
Skills" spec, consumable by Claude Code / Codex / Cursor / Windsurf. Pure
prompt/knowledge content — no scripts, no execution, no state, no audit.

**Against MAOS:** MAOS already has 24 skill specs (`skills/*.md`,
`SkillSpec` contract) plus 16 agent specs — **all `status: spec_only`,
zero implementations** (confirmed in the master plan audit). This repo is
the same *category* of artifact (skill knowledge) MAOS already has a typed,
versioned contract for. The content itself carries none of MAOS's
guarantees: no `FACT`/`HYPOTHESIS`/`MISSING` discipline, no audit trail, no
evidence source, no multi-tenant isolation, no determinism (it's an LLM
prompt, re-run it and the output changes).

| Sub-capability | Classification | Why |
|---|---|---|
| Skill *topics* MAOS doesn't cover yet (AI-search optimization, programmatic SEO, schema markup, referral-program design) | **INSPIRE** | Good scope checklist for new `SEOFinding` categories / new templated generators — write MAOS's own deterministic or evidence-gated version |
| The Markdown skill *format itself* | **REJECT** | MAOS already has a stricter, typed `SkillSpec`/`AgentSpec` contract (MKT-1E/2B) — adopting a second, looser format would fragment the spec system MAOS already invested in |
| "Hierarchical skill dependencies" / cross-skill references pattern | **INSPIRE** | Same idea as MAOS's own agent-spec `depends_on` fields — nothing to import, already the direction MAOS is going |
| Wholesale content (copy the 70 skill files in) | **REJECT** | Would populate MAOS's agent runtime with unaudited, non-deterministic, non-evidence-gated prompt content — directly contradicts the master plan's "no opaque scores / evidence tiers" principle (§20) and the "exactly two LLM-backed roles" recommendation (§8) |

---

## 2. `ericosiu/ai-marketing-skills`

**What it is:** ~25 Python-scripted workflows ("growth-engine",
"sales-pipeline", "seo-ops", "revenue-intelligence", etc.) with real
statistical methods (bootstrap confidence intervals, Mann-Whitney U tests),
an "expert panel" multi-persona scoring system, a PII sanitizer, and
opt-in telemetry. Designed to run **autonomously** against live systems
(CRM, ad platforms, GSC).

**Against MAOS:** this is the closest external match to MAOS's declared,
still-unbuilt **Evidence Engine** (master plan §20: sample size, duration,
consistency, causality-vs-correlation) and **Optimization Engine** (§23).
MAOS has zero statistical testing anywhere today — every "analysis" module
(`core/ads_analysis/`, `core/analytics/analyzer.py`) is fixed-threshold
rule matching, not inferential statistics. But the repo's *execution
posture* — autonomous, live-API, no approval gate described in the
overview — is exactly what the master plan's Human-in-the-Loop matrix
(§25) and Autonomy Levels (§24) exist to prevent MAOS from doing
prematurely.

| Sub-capability | Classification | Why |
|---|---|---|
| Statistical test methodology (bootstrap CI, Mann-Whitney U) for experiment significance | **ADAPT** | Exactly the rigor MAOS's Evidence Engine needs — reimplement as a MAOS `core/evidence/` module returning a typed, audited tier (`data\|signal\|hypothesis\|learning\|reusable_knowledge`), not imported code |
| "Expert panel" multi-persona explainable scoring | **INSPIRE** | Matches the master plan's explicit "no opaque score" requirement (§15) — informs the *shape* of MAOS's own Opportunity Scoring (§15/§20), not the personas themselves |
| PII sanitizer / pre-commit security hooks | **ADAPT** | MAOS already fingerprints identifiers before persisting (`core/analytics/connectors/service.py::fingerprint_identifier`) — a general PII-scan utility is a reasonable, small addition once external data ingestion (Website Intelligence, MKT-13A) lands; not urgent now since MAOS has no HTTP/scraping capability yet |
| Autonomous execution against live CRM/ad platforms without a described approval gate | **REJECT (as-is)** | Contradicts MAOS's supervised-autonomy principle and current read-only posture on every external connector (GA4/GSC/Ads are read-only *by code*, not just by convention) |
| Cold email / lead pipeline automation scripts | **DEFER** | Real capability, but MAOS has no write-capable CRM/email connector at all yet — revisit only after a `DataProvider` write port exists (master plan §12, not scheduled) |
| Opt-in telemetry pattern | **INSPIRE** | MAOS's Observability gap (master plan §27, currently "NONE") could reuse the opt-in framing — build MAOS's own on top of the job system, don't import |

---

## 3. `pymc-labs/pymc-marketing`

**What it is:** a mature, Apache-2.0, PyPI-published Bayesian statistics
library — Marketing Mix Modeling (MMM), Customer Lifetime Value (CLV),
Bass diffusion, discrete choice models, and an alpha-stage incrementality
module (PIE). Built on PyMC/ArviZ with NUTS samplers (BlackJax, NumPyro).
Real peer-adjacent statistical software, not a prompt collection.

**Against MAOS:** this is the strongest single match in the set. The
master plan explicitly named MMM-adjacent capability as missing (§18
Attribution: "nothing connects a UTM value back to the campaign... that
produced it"; §23 Optimization Engine detection rules are all
threshold-based, no causal modeling) and explicitly rejected opaque
scoring (§15, §20) — a Bayesian model with posterior credible intervals is
the *opposite* of opaque, it is maximally explainable. But it is a
**heavy dependency** (PyMC + ArviZ + a NUTS sampler backend) for a
project whose entire current dependency list is `pydantic` + `pyyaml`
(master plan §2.1) — adopting it is not a small decision.

| Sub-capability | Classification | Why |
|---|---|---|
| MMM (media-spend attribution across channels) | **ADAPT (later)** | Real, valuable, matches MAOS's own future Attribution/Optimization design exactly — but only once MKT-15A (Attribution Foundation, decodable UTM→outcome join) exists to feed it real data. Wrap as a MAOS `DataProvider`-style adapter behind MAOS's own contracts (`OperationContext`/`OperationResult`, audited), never call it raw from a handler |
| CLV models (contractual/non-contractual) | **DEFER** | No customer-level revenue/retention data model exists in MAOS today (`core/domain/` has no subscription/renewal entity) — needs its own domain-modeling pass before this is even usable |
| Bass diffusion (new-product-adoption forecasting) | **DEFER** | Niche, no current MAOS use case (no product-launch-tracking capability yet) |
| PIE / incrementality (alpha) | **DEFER** | The repo itself marks this alpha-stage; do not build on an unstable upstream API |
| MaxDiff / Bayesian BLP / discrete choice | **REJECT (for now)** | No MAOS capability produces the kind of stated-preference survey data these models need — solving a problem MAOS doesn't have yet |
| Wholesale adoption as MAOS's own stats engine | **REJECT (direct copy)** | Correct to *depend on* via pip when the time comes, wrong to vendor/fork — Apache 2.0 permits either, but forking loses upstream maintenance for zero benefit |

**Sequencing note:** this is explicitly a **post-MKT-15A** decision per
the master plan's own dependency ordering (§30: "Attribution before
learning"). Raising it now is correctly timed as a *scouting* exercise,
not a signal to add the dependency today.

---

## 4. `mautic/mautic`

**What it is:** a full, mature, PHP/Symfony marketing-automation
**platform** (10.4k stars, 40k+ commits) — real email sending, contact
segmentation, campaign trigger workflows, forms, landing pages, plugin
architecture, REST API. A product in the same market category MAOS is
aimed at, not a library or skill set.

**Against MAOS:** this is architecturally incompatible for direct reuse —
different language (PHP vs Python), different framework (Symfony vs
MAOS's own `core.application`/`core.jobs` stack), its own database/ORM
where MAOS uses `JsonFileMemory` + an audit-chained event log, and its own
UI where MAOS's Control Center is explicitly planned as FastAPI + Next.js
(master plan §9). The master plan's own "What NOT to Build Yet" section
(§32) already rules out "a new monolith" and "microservices" — Mautic
*is* the monolith MAOS deliberately isn't building.

| Sub-capability | Classification | Why |
|---|---|---|
| Whole platform / codebase | **REJECT** | Wrong language, wrong architecture, wrong risk model (MAOS has zero write-capable execution surfaces by design; Mautic's entire value is being a write-capable execution surface) |
| Campaign trigger/workflow model (event → condition → action) | **INSPIRE** | Directly comparable to MAOS's own planned Execution Layer (master plan §17: `CampaignPlan → Tasks → Jobs → ApprovalRequest → Adapter write`) — useful to see how a mature product models triggers, but MAOS's job/approval/audit substrate is already more rigorous (hash-chained audit, structured `OperationResult`, explicit risk classes) than what a general trigger engine typically has |
| Segmentation query model (contact filtering rules) | **INSPIRE** | Relevant scope reference for a future MAOS audience/segment entity — no code to take, MAOS's domain model (`core/domain/audience.py`) is a different shape already |
| Plugin/integration architecture | **INSPIRE** | Same *concept* as MAOS's `DataProvider` port design (master plan §12) — independently arrived at, nothing to borrow structurally since the languages differ |
| Self-hosted deployment / Docker patterns | **DEFER** | Only relevant once MAOS has something worth self-hosting for a third party (post Control Center, post-auth) — not now |

---

## 5. Cross-cutting findings

1. **None of the four sources solve MAOS's actual top blockers.** Per the
   master plan's readiness matrix, MAOS's real gaps are: no HTTP layer, no
   job-driven web surface (now partially closed by MKT-11C/11D), no agent
   runtime, no auth. None of these four repos address any of them — three
   are content/analysis capability sources (relevant to *later* phases:
   Learning/Evidence/Optimization/Attribution), one is a rejected
   architecture reference.
2. **The two "skills" repos both compete with MAOS's own spec_only agent/skill
   system**, not with implemented MAOS code. The honest comparison isn't
   "MAOS vs these repos" — it's "these repos vs MAOS's own 16+24 unimplemented
   specs." Neither collection changes the master plan's §8 recommendation
   (two LLM-backed roles, not eleven agents): both external repos *lean into*
   heavy agentification, which the master plan already argued against with
   evidence from MAOS's own codebase (the one existing LLM path needed a
   templated fallback to be trustworthy).
3. **`pymc-marketing` is the one genuine, high-value future dependency** in
   this set — but its correct entry point is MKT-15A/15B (Attribution,
   Evidence Engine), not now. Filing it here as a scouted, pre-approved
   direction avoids re-litigating "should MAOS ever use Bayesian MMM" when
   that milestone actually comes up.
4. **`ericosiu/ai-marketing-skills`'s statistical rigor is worth mining even
   before pymc-marketing** — bootstrap/Mann-Whitney is lightweight (no new
   heavy dependency, `scipy`/`numpy`-level, arguably justifiable earlier
   than a full PyMC stack) and could seed MAOS's Evidence Engine (§20)
   ahead of MKT-15B if a future milestone wants a cheaper first cut.

---

## 6. Summary table

| Source | Overall verdict | Primary reusable idea | Timing |
|---|---|---|---|
| `coreyhaines31/marketingskills` | **INSPIRE** (topics only) | Skill-topic checklist for gaps MAOS's own specs don't cover yet | Anytime, no dependency |
| `ericosiu/ai-marketing-skills` | **ADAPT** (methodology) | Statistical significance testing for MAOS's future Evidence Engine | Before or at MKT-15B |
| `pymc-labs/pymc-marketing` | **ADAPT** (as a dependency, later) | Bayesian MMM for real attribution | At MKT-15A/15B, not before |
| `mautic/mautic` | **REJECT** (as code) / **INSPIRE** (as reference) | Trigger/workflow and segmentation *concepts* only | Reference only, no adoption planned |

No code was written or modified to produce this analysis. No dependency
was added. ATLAS was not touched.
