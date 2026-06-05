# Definition of Ready — Alpha Pilot (MKT-8A)

Before starting a real-business pilot, every item below must
be true. If any item is `❌`, the pilot does NOT start —
resolve first.

## Client

- [ ] Client slug chosen and confirmed unique.
- [ ] Intake JSON exists at a known path and validates with
      `mkt intake --file <path>` (exit 0).
- [ ] Account lead and approval reviewer named.
- [ ] Pilot scope documented: which channels, which assets,
      which markets.
- [ ] Pilot end-date set (recommended ≤ 4 weeks).

## Local environment

- [ ] Python 3.11+ active.
- [ ] `pip install -e .` succeeded.
- [ ] `python -m pytest -q` exits 0 on the operator's machine.
- [ ] `ruff check .` exits 0.
- [ ] Free disk space ≥ 1 GB under `data/`.

## Data

- [ ] No prior `data/<slug>/` directory exists (or operator
      consciously chose to continue a previous run).
- [ ] Fresh `outputs/<slug>/` directory created.

## Source data (when applicable)

- [ ] CSV exports from GA4 / Search Console / social / email /
      Google Ads are available OR the operator has decided to
      defer the analytics loop to a later cycle.
- [ ] All CSVs are <5 MB and use UTF-8.

## Credentials (NOT required for the pilot)

- The pilot intentionally does NOT require any provider
  credential. `analytics-fetch` degrades to `skipped` when env
  vars are absent.
- If the operator chooses to provide credentials, they MUST be
  set as environment variables — never committed.

## Stakeholders

- [ ] Account lead briefed on the dry-run nature of the
      pilot.
- [ ] Reviewer briefed that they must look at every
      `current.json` + `*.md` before approving.
- [ ] Client expectations set: deliverables = MD + JSON. No
      live publication, no images generated.

## ATLAS handoff readiness

- [ ] Operator knows which ATLAS workflow they'll feed.
- [ ] Operator understands MARKETING-AGENCY-OS does NOT reach
      into ATLAS — they will copy the brief manually.

## Safety / posture

- [ ] No `--no-verify` / `--force` flag in any operator
      runbook.
- [ ] Approval pack reviewer empowered to set
      `blocks_publish=True` and pause the pilot.
- [ ] Audit JSONL files monitored daily during the pilot.

When all boxes are checked, run the Alpha Pilot Playbook
(`alpha-pilot-playbook.md`).
