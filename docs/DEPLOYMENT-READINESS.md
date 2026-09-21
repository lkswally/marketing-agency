# Deployment Readiness — MARKETING-AGENCY-OS

> Minimal, practical reference for the next thread that configures the VPS.
> Not a full audit — see `docs/VPS-READINESS-AUDIT.md` (if/when created) for that.
> Verified against real commands on this commit (`HEAD` = MKT-11E + this
> closure commit). `NOT VERIFIED` marks anything not actually tested.

## Python

- **Minimum required:** `>=3.11` (`pyproject.toml`).
- **CI-tested version:** 3.11, on `ubuntu-latest` (`.github/workflows/ci.yml`).
- **Local dev venv observed:** 3.14.5 (Windows) — works, but is *ahead* of
  what CI actually exercises. **Recommendation: target Python 3.11 on the
  VPS**, matching CI, not the newer local dev interpreter.

## Install

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Optional extras, install only what the VPS will actually use:

```bash
pip install -e ".[claude]"   # Anthropic SDK — only if ANTHROPIC_API_KEY will be set
pip install -e ".[notion]"   # notion-client — only if real Notion sync will be used
pip install -e ".[portal]"   # Streamlit — only if the portal will be exposed
```

Core runtime dependencies are minimal and always required: `pydantic`, `pyyaml`.

## Running the CLI

```bash
mkt --help
mkt list-workflows
mkt validate-specs
mkt run-campaign --intake <path> --root data/clients --outputs-dir outputs
```

`mkt` is a console-script entry point (`mkt = "cli.main:main"`) installed by
`pip install -e .` — confirm it's on `$PATH` inside whatever venv/service
user runs it on the VPS.

## Running the portal

```bash
pip install -e ".[portal]"
mkt portal --root data/clients --outputs-dir outputs
```

- Streamlit dependency is **correctly optional** (`[portal]` extra) — do not
  move it to core runtime dependencies unless the VPS is meant to always run
  the portal as a service.
- Verified in this session: `mkt portal` launches cleanly (real Streamlit
  server start, no traceback) when the extra is installed; exits 2 with a
  clear install hint when it is not.
- On a VPS, the portal would need its own reverse-proxy/port exposure
  decision — **NOT VERIFIED**, out of scope until the VPS phase.

## `data/` and `outputs/`

- `data/clients/<slug>/` — per-client persisted state (JSON files + audit
  JSONL). This is the **only stateful, must-persist** directory. Gitignored
  except the `data/clients/.gitkeep` placeholder.
- `outputs/<slug>/` — generated deliverables (Markdown/JSON artifacts).
  Regenerable from `data/` + a re-run in most cases, but treat as
  operationally valuable (reports already delivered to a client). Gitignored
  except `outputs/.gitkeep`.
- `assets/clients/<slug>/` — per-client binary assets. Gitignored except
  `assets/clients/.gitkeep`.

**What must persist across deploys/restarts on the VPS:** `data/clients/`,
`outputs/`, `assets/clients/` (whatever exists under them for real clients).

**What must stay OUT of the repo / version control:** everything already
excluded by `.gitignore` — `.env`, `data/*` (except the gitkeep), `outputs/*`
(except the gitkeep), `.venv/`, `__pycache__/`, `.pytest_tmp*/`, `.ruff_cache/`.

## Environment variables (see `.env.example` for the authoritative list)

All are optional; every integration degrades gracefully without them (no
crash, no fabricated data — falls back to templated/dry-run/skip with a
clear message).

| Variable | Used by |
|---|---|
| `MKT_MEMORY_BACKEND`, `MKT_LOG_LEVEL`, `MKT_BRIDGE_ATLAS` | Core runtime — **NOT VERIFIED which are actually read today** vs reserved for later; grep `core/` before relying on them. |
| `ANTHROPIC_API_KEY` | `--backend claude` on `run-strategy`/`run-campaign`. Read once from env, never logged/persisted (enforced by `core/strategy/backends/invokers/anthropic_sdk.py`). |
| `NOTION_TOKEN`, `NOTION_TASKS_DATABASE_ID`, `NOTION_PARENT_PAGE_ID` | `notion-sync --write --confirm`. |
| `GOOGLE_APPLICATION_CREDENTIALS` | GA4 / Search Console read-only connectors. |
| `GOOGLE_ADS_CUSTOMER_ID`, `GOOGLE_ADS_DEVELOPER_TOKEN`, `GOOGLE_ADS_LOGIN_CUSTOMER_ID` | Google Ads read-only connector (also needs `GOOGLE_ADS_CLIENT_ID`/`_SECRET`/`_REFRESH_TOKEN` per the connector's own docstring — not listed in `.env.example` today, a gap worth closing before relying on this connector in production). |

No secret is ever written into `JobRecord`, approval records, or audit
events — enforced by `core.jobs.repository.sanitize_params` at the job
persistence choke point, and confirmed by direct code read in this session.

## Docker

**No Dockerfile or docker-compose file exists in this repository as of this
commit.** Confirmed by exhaustive search. This is genuine outstanding work
for the VPS phase, not a documentation gap.

## Linux compatibility

- **Reviewed, not fully verified.** CI (`.github/workflows/ci.yml`) runs
  `ruff check .` and `pytest -m "not integration"` on `ubuntu-latest` for
  every push/PR to `main` — so the full test suite (2100+ tests) is exercised
  on Linux on every commit already merged to `origin/main`.
- Everything audited in this session (CLI, jobs, approvals, pipeline) is pure
  Python + `pydantic`/`pyyaml` — no OS-specific code paths were found in
  `core/` or `cli/`.
- One Windows-specific issue was found and fixed in this closure commit: a
  Unicode arrow character in a CLI help string crashed under the Windows
  default console codepage (cp1252). Fixed by replacing it with ASCII
  (`->`). Linux consoles default to UTF-8, so this class of bug is
  **unlikely but NOT VERIFIED** to be fully absent elsewhere in help/error
  strings — worth a targeted grep for non-ASCII characters in user-facing
  strings before going live.
- File path handling: the codebase uses `pathlib.Path` throughout in the
  audited modules — no hardcoded Windows-style paths (`C:\...`) found in
  `core/`/`cli/`. **Not exhaustively verified across the entire tree.**

## ARM64

**NOT VERIFIED.** No native ARM64 test has been run — this dev environment
is x86_64 Windows, and CI runs on `ubuntu-latest` (x86_64 GitHub-hosted
runners). If the target Oracle Cloud VPS is an Ampere/ARM64 shape:
- Core dependencies (`pydantic`, `pyyaml`) ship ARM64 wheels for recent
  CPython — likely fine, but not confirmed on this exact stack.
- Optional extras (`anthropic`, `notion-client`, `streamlit`, and
  transitively any Google SDKs for `[claude]`/`[portal]`/analytics
  connectors) have not been checked for ARM64 wheel availability.
- **Action for the VPS thread:** `pip install -e ".[dev]"` on the actual
  ARM64 instance and run the full test suite there before trusting it.

## Checklist for the VPS thread

- [ ] Confirm target architecture (x86_64 vs ARM64/Ampere) before anything else.
- [ ] Install Python 3.11 (match CI, not necessarily the newest available).
- [ ] Create venv, `pip install -e ".[dev]"`, run full test suite + `ruff check .` natively on the VPS.
- [ ] Decide which optional extras are actually needed in production (`claude`/`notion`/`portal`) and install only those.
- [ ] Write and validate a `Dockerfile` (none exists yet) — base image should match the Python version above.
- [ ] Decide process-management strategy for `mkt jobs run` (this system has no background worker/scheduler yet — jobs are synchronous, operator-triggered).
- [ ] Decide `data/clients/`, `outputs/`, `assets/clients/` persistence strategy (volume mount / backup policy) — this is the only stateful data.
- [ ] Provision `.env` from `.env.example` with only the credentials actually needed; never commit it.
- [ ] If exposing the portal, decide reverse-proxy / auth in front of it (the portal itself has no auth — it's designed as a local operator tool).
- [ ] Re-run the Unicode/console-encoding check on the actual VPS shell/locale.
- [ ] No Docker image, no systemd unit, no reverse proxy config exists yet — all of this is net-new work for that thread.

## Steps that remain before any real deploy

1. Architecture confirmation (x86_64 vs ARM64) and native test run there.
2. Dockerfile creation + build verification.
3. Decision on process supervision (systemd, Docker Compose, etc. — none chosen yet).
4. Decision on whether/how the portal is exposed externally (auth, reverse proxy).
5. Credential provisioning for whichever integrations are actually going live first (`docs/HANDOFF` roadmap suggests Search Console first).
6. Backup/persistence strategy for `data/clients/`.

This document intentionally does not go further — the VPS configuration
itself is out of scope until explicitly authorized in its own thread.
