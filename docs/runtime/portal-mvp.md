# Portal MVP (MKT-9A)

Runtime guide for the read-only Streamlit portal that lets the
operator browse every persisted pack of a client without using
the CLI for each command.

**Read-only contract:** no widget mutates disk, no API call, no
credential read. Pinned by `tests/portal/test_safety.py`.

## Install

```bash
pip install -e ".[portal]"
```

The `portal` extra adds Streamlit (>= 1.32 < 2.0). The base
install of MARKETING-AGENCY-OS does NOT pull Streamlit in.

## Launch

```bash
# Recommended — CLI wrapper.
mkt portal

# Custom paths.
mkt portal --root data --outputs-dir outputs

# Direct (skip the wrapper).
python -m streamlit run portal/app.py -- --root data --outputs-dir outputs
```

Open the URL Streamlit prints (typically `http://localhost:8501`).

If Streamlit is not installed, `mkt portal` prints:

```
Streamlit is not installed. Install the optional `portal` extra:
    pip install -e ".[portal]"
```

and exits 2. The wrapper does NOT spawn a subprocess in this case.

## What the portal shows

A sidebar `selectbox` lists every client found under `data/` or
`outputs/` (union, sorted, `_shared` excluded). Pick a client to
see:

1. **Two header metrics**: data root + outputs dir (with warning
   if either does not exist yet).
2. **Pre-flight checklist** with 5 metric tiles
   (total / OK / missing / blocked / errors), plus two badges:
   - `ATLAS handoff ready` — all required packs present + nothing
     blocked.
   - `Publish gate satisfied` — same + zero errors.
3. **14 expanders, in pipeline order**, one per pack registered
   in `portal/pack_registry.py`:

| # | Pack | Required? | May block? |
|---|------|:--------:|:----------:|
| 1 | Campaign final summary | optional | no |
| 2 | Campaign strategy | **required** | no |
| 3 | Approval pack | **required** | **yes** |
| 4 | Creative pack | **required** | **yes** |
| 5 | Visual direction pack | **required** | **yes** |
| 6 | Campaign execution tasks | optional | no |
| 7 | Notion sync plan (preview only) | optional | no |
| 8 | n8n execution plan (preview only) | optional | no |
| 9 | Image generation jobs (NOT generated) | optional | **yes** |
| 10 | Image provider plan (dry-run only) | optional | **yes** |
| 11 | Analytics recommendations | optional | no |
| 12 | Campaign feedback pack | optional | no |
| 13 | Next campaign iteration plan | optional | no |
| 14 | ATLAS bridge briefs | optional | **yes** |

## Per-pack expander layout

| Element | What it shows |
|---|---|
| Header | Status icon + status label + title + `(required/optional)` |
| Caption | One-line description from the registry |
| Error block | When `status == ERROR`, the exception text |
| JSON file path | Where the pack lives on disk |
| Markdown path | The rendered MD file under `outputs/<slug>/` |
| Tab `Markdown` | Rendered MD content (or hint to run CLI) |
| Tab `JSON (raw)` | `st.json` collapsible viewer + nested expander with the same JSON as plain text for easy copy |

## Status pills

| Icon | Status | Meaning |
|------|---|---|
| ✅ | OK | Pack exists, deserialised cleanly, posture is fine. |
| 🚫 | BLOCKED | Pack exists but its `blocks_publish` flag is `true`. |
| ⚪ | MISSING | Pack file not on disk. Informational for optional packs, blocker for required. |
| ❌ | ERROR | Pack file exists but failed to deserialise; operator must inspect. |

## Tolerance to missing packs

The portal NEVER crashes on a missing pack. The loader
(`portal/pack_loader.py`) catches `EntityNotFound` and any other
exception, returning `PackStatus.MISSING` / `PackStatus.ERROR`
with a captured message instead of raising.

Same applies when the user picks a client whose `data/` or
`outputs/` directory does not exist — the page shows a graceful
warning and an empty checklist (`is_publish_ready=True` /
`is_atlas_handoff_ready=True` because zero rows trivially
satisfy the gates; the empty state is otherwise visible).

## Empty-state handling

When no client exists under either root, the portal shows:

> No clients found under `<data>` / `<outputs>`. Run
> `mkt run-campaign --intake <path>` first.

No exception is raised.

## Cardinal guarantees (test-pinned)

| Guarantee | Test |
|---|---|
| No `open(..., 'w'/'a'/'wb')` anywhere | `test_no_write_mode_open_in_portal_modules` |
| No `Path.write_*` / `shutil.copy/move/rmtree` / `os.remove/unlink/rmdir/makedirs` / `json.dump(` | `test_no_path_write_methods_in_portal` |
| No `requests` / `httpx` / `urllib.request` / `aiohttp` | `test_no_http_lib_in_portal_modules` |
| No `os.environ` / `os.getenv` | `test_no_credential_read_in_portal_source` |
| No `subprocess` / `os.system` / `os.popen` inside `portal/` | `test_no_subprocess_in_portal_modules` |
| No `st.button` / `st.form` / `st.file_uploader` / `st.data_editor` | `test_no_destructive_streamlit_widgets_in_app` |
| No reach into Notion / n8n / ATLAS writers | `test_no_notion_n8n_atlas_reach_in_portal` |
| No image SDK / PIL | `test_no_image_sdk_imported_in_portal` |
| `app.py` is the only Streamlit-importing module | `test_only_app_py_imports_streamlit` |
| `portal/__init__.py` does not import Streamlit | `test_portal_init_does_not_import_streamlit` |
| Loader tolerates missing packs for every registry entry | `test_load_pack_for_every_registry_spec_does_not_crash` |

## CLI wrapper — exit codes

| Code | Meaning |
|---|---|
| `0` | Streamlit exited cleanly (`q` in terminal or browser close + ctrl-c). |
| Streamlit's own | Whatever `streamlit run` returned (we forward it). |
| `2` | Streamlit not installed; install hint printed. |

## NOT in scope (deferred — see `PENDING.md`)

- **P-9A.1** — Auth / multi-user (today single-user local).
- **P-9A.2** — Auto-refresh on disk-change detection.
- **P-9A.3** — Export of the consolidated checklist to PDF.
- **P-9A.4** — Cycle-vs-cycle comparison view.
- **P-9A.5** — Full-text search across all rendered Markdown.
- **P-9A.6** — Editing opt-in (explicitly out of scope in MKT-9A).

## Related docs

- [Alpha Pilot Playbook](../alpha-pilot-playbook.md)
- [Alpha Pilot Checklist](../alpha-pilot-checklist.md)
- [Definition of Ready](../alpha-pilot-definition-of-ready.md)
- [Definition of Done](../alpha-pilot-definition-of-done.md)
- [Real-Business Intake Template](../real-business-intake-template.md)
- [ADR 0032 — Portal MVP](../decisions/0032-mkt-9a-portal-mvp.md)
