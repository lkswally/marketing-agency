# ADR 0032 — MKT-9A: Portal MVP (read-only)

- **Status:** Accepted
- **Date:** 2026-06-04
- **Block:** MKT-9A
- **Supersedes:** —
- **Contracts shipped:** none (the portal is a UI shell; it reads
  existing persisted contracts).

## Context

After MKT-8A the system had a complete operator playbook + CLI
inventory but every artifact was a Markdown / JSON file the
operator had to find by hand. Reviewing a pilot meant opening
each file in an editor and cross-referencing them mentally. The
user asked for a minimal read-only portal that:

1. Lists all clients the system knows about.
2. For a chosen client, shows the status of every pack in the
   pipeline order.
3. Renders the per-pack Markdown + raw JSON without leaving the
   browser.
4. Computes a pre-flight checklist that says whether the campaign
   is publish-ready / ATLAS-handoff-ready.
5. Never writes to disk, never calls any API, never publishes.

## Decision

### D-32.1 — Stack: Streamlit, optional extra

Streamlit (>= 1.32 < 2.0) wins on:

- One command to run (`streamlit run portal/app.py`).
- Zero JS / build / Vercel.
- Native Python — fits the rest of the codebase.
- Sufficient widgets for the read-only display we need
  (`st.markdown`, `st.json`, `st.expander`, `st.metric`,
  `st.tabs`, `st.sidebar.selectbox`).

Rejected:
- **Flask / FastAPI + Jinja** — more files (templates/, static/),
  manual routing, more surface to lock down.
- **Bare `http.server`** — sub-par UX for what the operator needs.
- **Next.js** — explicitly out of scope per the spec; introduces
  node, build, deploy.

Streamlit ships as an **optional extra** (`pip install -e
".[portal]"`). The base install of MARKETING-AGENCY-OS does NOT
pull it in, so CI stays lean.

### D-32.2 — `portal/` package layout

```
portal/
├── __init__.py            # re-exports — no streamlit
├── app.py                 # Streamlit entry — the ONLY streamlit-importing module
├── pack_registry.py       # declarative table of the 14 packs
├── pack_loader.py         # safe load: returns OK / BLOCKED / MISSING / ERROR
├── client_discovery.py    # union of data/ and outputs/
├── checklist.py           # aggregate per-pack results into pre-flight
└── README.md
```

`__init__.py` re-exports only the streamlit-free symbols so unit
tests can `from portal import ...` without the extra installed.
Pinned by `test_portal_init_does_not_import_streamlit` and
`test_only_app_py_imports_streamlit`.

### D-32.3 — Declarative pack registry (14 entries)

`portal/pack_registry.py` defines `PORTAL_PACK_REGISTRY` as a
frozen tuple of `PortalPackSpec`. Each entry carries:

- `order` — position in the UI (1..14).
- `kind` + `singleton_id` — JsonFileMemory discriminator.
- `title` — human label.
- `markdown_filenames` — tuple of candidate filenames under
  `outputs/<slug>/`.
- `blocks_publish_field` — `None` when the pack cannot block;
  `"blocks_publish"` for the five blockable packs (approval,
  creative, visual, image jobs, image provider plan, ATLAS).
- `optional` — `False` for the four required packs (strategy,
  approval, creative, visual); `True` otherwise.
- `description` — caption surfaced in the expander.

Rejected: hard-coding the 14 packs in `app.py`. The declarative
registry lets the renderer iterate generically and makes it
trivial to add a 15th pack later (just add a tuple entry).

### D-32.4 — Safe loader — every status is a value, never an exception

`pack_loader.load_pack(...)` catches both `EntityNotFound`
(→ `MISSING`) and any other deserialisation exception
(→ `ERROR` with `error_message`). The portal therefore never
crashes on a partial dataset.

Pinned by:

- `test_load_pack_returns_missing_when_absent`
- `test_load_pack_returns_error_when_json_corrupt`
- `test_load_pack_for_every_registry_spec_does_not_crash`

### D-32.5 — Checklist aggregates four counters and two gates

`checklist.PreflightChecklist` carries `ok` / `missing` /
`blocked` / `error` plus three lists (`required_missing`,
`blocked_titles`, `error_titles`) and two computed properties:

- `is_atlas_handoff_ready` — required-missing is empty and
  blocked count is 0.
- `is_publish_ready` — additionally requires zero errors.

This separation reflects the operator workflow: ATLAS handoff
can ship even if the analytics / iteration packs are absent,
but publishing requires everything to be clean.

### D-32.6 — Streamlit widgets are display-only

Pinned by `test_no_destructive_streamlit_widgets_in_app` — the
app source is grep-asserted not to contain `st.button(`,
`st.form(`, `st.form_submit_button(`, `st.file_uploader(`,
`st.data_editor(`, `st.download_button(`,
`st.experimental_data_editor`.

The expectations are also positive: the app MUST use
`st.markdown`, `st.json`, `st.expander`, `st.caption`. Pinned by
`test_app_py_only_uses_display_streamlit_calls`.

### D-32.7 — No disk write, ever, anywhere in `portal/`

Pinned by `test_no_write_mode_open_in_portal_modules` and
`test_no_path_write_methods_in_portal`. We grep for:

- `open(..., 'w'/'a'/'wb')`
- `.write_text(` / `.write_bytes(`
- `shutil.copy/move/rmtree`
- `os.remove/unlink/rmdir/makedirs`
- `Path.mkdir` (string form — the loader uses Path BUT never
  mkdir; the renderer uses no Path writes either)
- `json.dump(` (only `json.dumps` for the copy-as-text widget)

### D-32.8 — No subprocess inside `portal/`; wrapper lives in CLI

The Streamlit app must not spawn subprocesses. The CLI wrapper
`mkt portal` is the only place that calls `subprocess.call(
["streamlit", "run", ...])` — that lives in `cli/main.py` so
the portal package itself stays subprocess-free. Pinned by
`test_no_subprocess_in_portal_modules`.

### D-32.9 — No HTTP, no credential read, no integration reach-in

Same grep-pin posture as MKT-7B / MKT-8A:

- No `requests` / `httpx` / `urllib.request` / `aiohttp`.
- No `os.environ` / `os.getenv`.
- No reach into `core.notion_sync` / `core.n8n_sync` /
  `core.atlas_bridge.factory` (the portal reads the persisted
  ATLAS handoff brief from `JsonFileMemory` like any other
  pack — it does NOT call the factory).
- No image SDK / PIL.

### D-32.10 — CLI wrapper `mkt portal`

`cli.main._cmd_portal`:

1. Probes Streamlit via `importlib.util.find_spec("streamlit")`.
2. If missing → print install hint, exit 2. Pinned by
   `test_portal_prints_install_hint_when_streamlit_missing` and
   `test_portal_does_not_spawn_when_streamlit_missing`.
3. If present → compose
   `[sys.executable, "-m", "streamlit", "run",
   "portal/app.py", "--", "--root", ..., "--outputs-dir", ...]`
   and `subprocess.call(...)`. The forward `--` separator
   delegates the wrapper args to the app's own argparse.
4. Forward Streamlit's exit code.

### D-32.11 — `pyproject.toml` extra + wheel includes `portal`

`[project.optional-dependencies].portal = ["streamlit>=1.32,<2.0"]`.
`[tool.hatch.build.targets.wheel].packages` adds `"portal"` so
installs ship the package alongside `core` and `cli`.

### D-32.12 — Tests run without Streamlit

CI doesn't have Streamlit. The pure-Python modules are testable
in isolation (`pack_registry`, `pack_loader`, `client_discovery`,
`checklist`). `app.py` is NOT imported by any test. The CLI
wrapper tests monkey-patch `importlib.util.find_spec` and
`subprocess.call`.

## Consequences

### Positive

- The operator now has a local UI for browsing every pack in
  pipeline order without the CLI.
- The pre-flight checklist makes the publish / handoff
  decision explicit instead of asking the operator to count
  pack files by hand.
- The portal tolerates missing packs gracefully — required for
  Alpha Pilot where the analytics loop may not run until a real
  cycle ends.
- Hard read-only guarantee — grep-pinned against every write,
  every external call, every credential read.
- Tests stay lean — CI doesn't install Streamlit.

### Negative / accepted trade-offs

- Single-user, single-machine. Auth + multi-user is P-9A.1.
- No live disk-change watch — operator refreshes the browser
  to re-read. Auto-refresh is P-9A.2.
- The JSON viewer is `st.json` (good for small packs; large
  packs may be slow to render). The "copy as raw text"
  expander is a fallback.
- Pack-level error rendering is text-only — operator opens the
  file in their editor to inspect.

## Out of scope (explicit)

- Editing any pack.
- Login / auth.
- New database.
- Any API call.
- Deploy to Vercel.
- Publishing anything.
- Image generation.
- Notion / n8n write.
- ATLAS reach-in (the portal reads the persisted brief; it does
  NOT call the bridge factory or anything else).

## Validation

- 51 new tests:
  - 8 `test_pack_registry.py`
  - 6 `test_client_discovery.py`
  - 13 `test_pack_loader.py`
  - 9 `test_checklist.py`
  - 11 `test_safety.py`
  - 4 `test_cli_portal.py`
- Full suite: green.
- Ruff: clean.
- ATLAS core: untouched.

## Related

- Depends on `JsonFileMemory` (MKT-1D) and every pack contract
  from MKT-1 through MKT-8A.
- Sets up no future blocks directly — the portal is a leaf
  feature that supports the Alpha Pilot.
- Future work tracked as `P-9A.*` in `PENDING.md`.
- Runtime doc: `docs/runtime/portal-mvp.md`.
