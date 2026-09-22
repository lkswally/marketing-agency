# Deployment Readiness — MARKETING-AGENCY-OS

> Minimal, practical reference for the next thread that configures the VPS.
> Not a full audit — see `docs/VPS-READINESS-AUDIT.md` (if/when created) for that.
> Verified against real commands on this commit (`HEAD` = MKT-11E + this
> closure commit). `NOT VERIFIED` marks anything not actually tested.

## Python

- **Minimum required:** `>=3.11` (`pyproject.toml`).
- **CI-tested version:** 3.11, on `ubuntu-latest` (`.github/workflows/ci.yml`).
- **Local dev venv observed:** 3.14.5 (Windows) — works, but is *ahead* of
  what CI actually exercises.
- **VPS validation (reported by operator, VPS-02A):** Python **3.12.3** on
  the target ARM64 VPS — `pip install -e ".[dev,portal]"` PASS, full suite
  (2159 tests) PASS, `ruff check .` PASS, portal PASS. This is the first
  confirmation on the actual target architecture/OS, reported from a
  separate session against the real host — not independently re-verified
  from this repo checkout.

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
  `assets/clients/.gitkeep`. **Verified in VPS-02A: this is a convention
  only** — `core/domain/asset.py`'s `Asset.path` is a freeform
  `str | None`, and no runtime code resolves or writes to a literal
  `assets/` root. There is no `--assets-dir` flag anywhere in the CLI.
  Nothing in `core/`/`cli/` currently reads or writes real files under
  `assets/clients/` — it exists today only as a documented taxonomy
  (`ARCHITECTURE.md` D7) and a `.gitignore` rule, not as implemented I/O.

**What must persist across deploys/restarts on the VPS:** `data/clients/`
and `outputs/` — confirmed, real, actively read/written by every command
via `--root`/`--outputs-dir`. `assets/clients/` should be provisioned on
the VPS for forward-compatibility (per the taxonomy) but there is nothing
to migrate today, since nothing writes there yet.

**What must stay OUT of the repo / version control:** everything already
excluded by `.gitignore` — `.env`, `data/*` (except the gitkeep), `outputs/*`
(except the gitkeep), `.venv/`, `__pycache__/`, `.pytest_tmp*/`, `.ruff_cache/`.

## Persistence path contract (proposed, VPS-02A)

Audited: every command that touches client state exposes an explicit
`--root` (35 occurrences across the CLI) and/or `--outputs-dir` (25
occurrences) flag — there is no command that silently writes to a
hardcoded absolute path. Defaults are relative (`data/clients`, `outputs`,
resolved from the process's working directory) purely as a local-dev
convenience; every real invocation is expected to pass explicit paths.

Confirmed chain of default-vs-override, top to bottom:

- `cli/main.py::DEFAULT_DATA_ROOT = Path("data/clients")` — CLI-level
  argparse default, overridden by `--root` on every subcommand that needs it.
- `core/application/context.py::DEFAULT_DATA_ROOT` / `DEFAULT_OUTPUTS_ROOT`
  — `OperationContext` pydantic field defaults, always overridden by the
  CLI/job layer passing `root=Path(args.root)` explicitly.
- `portal/app.py` — its own `--root`/`--outputs-dir` args (passed by the
  `mkt portal` wrapper via `streamlit run ... -- --root X --outputs-dir Y`).
- **`assets/` has no equivalent** — see finding above. Not a blocker (no
  writer exists to relocate), but must be added before any code starts
  actually writing binary assets.

**Proposed contract for the target host layout**
(`/opt/data/marketing-os/{clients,outputs,assets}`):

| Concern | Value | Consumed by |
|---|---|---|
| Client state root | `/opt/data/marketing-os/clients` | `mkt --root /opt/data/marketing-os/clients ...` for every command; `mkt portal --root ...`; a future `campaign.run` job's `ctx.root` |
| Outputs root | `/opt/data/marketing-os/outputs` | `--outputs-dir` on every command that generates artifacts; `mkt portal --outputs-dir ...` |
| Assets root | `/opt/data/marketing-os/assets` | **Not yet consumed by any code.** Reserve the path now; wire a `--assets-dir` flag (or an `OperationContext.assets_root` field, mirroring `root`/`outputs_root`) when a real asset-writing feature lands. |
| How the CLI/jobs receive these | Explicit flags, never env-var-implicit | Already true today — no code change needed for `--root`/`--outputs-dir`. A future systemd unit or Docker Compose service should set them via command args or a wrapper script, not rely on the relative defaults. |
| How the portal receives these | Same flags, forwarded by `mkt portal` to the Streamlit subprocess | Already true today. |
| How Docker Compose should wire it (VPS-02B) | Bind-mount `/opt/data/marketing-os/{clients,outputs,assets}` on the host to fixed paths inside the container (e.g. `/data/clients`, `/data/outputs`, `/data/assets`), then pass `--root /data/clients --outputs-dir /data/outputs` (and, once it exists, `--assets-dir /data/assets`) as the container command's fixed arguments. | Proposed for VPS-02B — not implemented, no symlinks, no data moved. |

This contract requires **zero code changes** for `clients`/`outputs` — the
flags already exist and are already honored end-to-end. It requires **one
new flag** (`--assets-dir` or equivalent) before `assets/` can be part of
the same contract, and that flag has no urgency until a real asset writer
exists.

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

**PASS — validated on the real target VPS (reported by operator, VPS-02A),
not independently re-run from this checkout.** Python 3.12.3,
`pip install -e ".[dev,portal]"`, full suite (2159 tests), `ruff check .`,
and the portal all passed natively on the Oracle Cloud ARM64/Ampere
instance. This supersedes the earlier "not verified" status from the
x86_64-only dev/CI environments.

Still not verified on that VPS run: the `claude` and `notion` extras
(`anthropic`, `notion-client` SDKs) and the Google analytics connector SDKs
— only `[dev,portal]` was installed. Verify those specifically if/when the
corresponding integration is turned on.

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
