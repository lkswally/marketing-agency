# Alpha Pilot Playbook (MKT-8A)

The playbook the operator follows when running the first
controlled real-business pilot of MARKETING-AGENCY-OS.

This guide tells the operator **exactly** what to do — no
guessing about which commands run when. It assumes:

- A single tenant client (one `--client <slug>`).
- No real provider integrations (no Google Ads write, no n8n,
  no real Notion, no real image generation).
- Every artifact stays local — Markdown + JSON files plus a
  per-client JsonFileMemory directory.

If anything in this guide conflicts with the per-block ADRs,
the ADRs win.

---

## 0. Pre-flight (one-time per pilot)

1. Pick a client slug (lowercase, dash-separated). Example:
   `acme-coffee`.
2. Copy the intake template:
   `examples/intake/alpha-pilot-template.json` → fill in.
3. Run the full Definition of Ready checklist (see
   `alpha-pilot-definition-of-ready.md`).
4. Confirm `data/` is writable and the operator has a fresh
   `outputs/<slug>/` directory.

## 1. Strategy + creative pipeline

```bash
mkt run-campaign --intake path/to/intake-<slug>.json
```

Produces the strategy report, creative pack, visual direction
pack and approval pack — all under
`data/<slug>/<kind>/current.json`.

Outputs land in `outputs/<slug>/`.

## 2. Operational layer

```bash
mkt build-tasks --client <slug>
mkt notion-plan --client <slug>          # dry preview of Notion shape
mkt n8n-plan    --client <slug>          # dry preview of n8n shape
```

`notion-plan` / `n8n-plan` are dry previews — they NEVER write
to Notion / n8n.

## 3. Analytics + iteration loop (after a real campaign cycle)

```bash
mkt import-metrics  --client <slug> --source ga4            --file ga4.csv
mkt import-metrics  --client <slug> --source search_console --file sc.csv
mkt import-metrics  --client <slug> --source social         --file social.csv
mkt import-metrics  --client <slug> --source email          --file email.csv
mkt import-metrics  --client <slug> --source google_ads     --file ads.csv

mkt analyze-metrics --client <slug>
mkt feedback-plan   --client <slug>
mkt apply-feedback  --client <slug>
```

Optional Google integrations (read-only — skipped on missing
creds):

```bash
mkt analytics-fetch --client <slug> --source ga4
mkt analytics-fetch --client <slug> --source search_console
mkt analytics-fetch --client <slug> --source google_ads
```

## 4. Google Ads analyzer + bridge

```bash
mkt ads-analyze  --client <slug>
mkt ads-feedback --client <slug>
```

Optional opt-in promotion of ads insights into the canonical packs:

```bash
mkt feedback-plan  --client <slug> --include-ads-bridge
mkt build-tasks    --client <slug> --include-ads-bridge
mkt apply-feedback --client <slug> --include-ads-bridge
```

Idempotent — re-runs skip duplicates.

## 5. Image jobs + provider plan (preview only)

```bash
mkt image-jobs           --client <slug>   # MKT-7A — no generation
mkt image-provider-plan  --client <slug>   # MKT-7B — no provider call
```

Both blocks are review-only. No images are generated.

## 6. ATLAS handoff

When the campaign needs a landing page, a branding system, or a
generic page, emit the handoff brief and copy it into the
ATLAS workflow manually:

```bash
mkt atlas-brief --client <slug> --kind landing
mkt atlas-brief --client <slug> --kind branding
mkt atlas-brief --client <slug> --kind page_design --page-name pricing
```

MARKETING-AGENCY-OS does NOT reach into ATLAS. The operator
copies the Markdown / JSON into the ATLAS workflow.

## 7. Post-pilot

1. Run the Definition of Done checklist
   (`alpha-pilot-definition-of-done.md`).
2. Archive the `data/<slug>/` directory and the `outputs/<slug>/`
   directory together with the pilot retrospective notes.
3. Capture surprises in `PENDING.md` as new `P-*` entries.

---

## Hard guarantees during the pilot

- No real external write of any kind.
- No real image generation.
- No real Notion / n8n write.
- No real Google Ads / GA4 / Search Console write.
- No real ATLAS reach-in.
- Every action records an audit event in
  `data/<slug>/audit/*.jsonl`.

If any of these would be violated, the operator stops the
pilot and files a `PENDING` entry instead.
