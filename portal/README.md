# `portal/` — Read-only Streamlit portal (MKT-9A)

The portal lets the operator pick a client and browse every pack
MARKETING-AGENCY-OS persists — strategy, creative, visual,
approval, execution, analytics, ads, image, ATLAS — without
touching the CLI for every command.

**Read-only contract:** no widget mutates disk, no API call, no
credential read. Pinned by `tests/portal/test_safety.py`.

## Install

```bash
pip install -e ".[portal]"
```

The `portal` extra adds Streamlit. The default install of
MARKETING-AGENCY-OS does NOT pull Streamlit in.

## Run

```bash
# Recommended (CLI wrapper):
mkt portal

# With custom paths:
mkt portal --root data --outputs-dir outputs

# Direct:
python -m streamlit run portal/app.py -- --root data --outputs-dir outputs
```

Open the URL Streamlit prints (typically `http://localhost:8501`).

If Streamlit is not installed, `mkt portal` prints the install
command and exits 2.

## What the portal shows

Per client, all 14 packs in pipeline order:

1. Campaign final summary
2. Campaign strategy
3. Approval pack (may block publish)
4. Creative pack (may block publish)
5. Visual direction pack (may block publish)
6. Campaign execution tasks
7. Notion sync plan (dry preview)
8. n8n execution plan (dry preview)
9. Image generation jobs (NOT generated)
10. Image provider plan (dry-run only)
11. Analytics recommendations (optional)
12. Campaign feedback pack (optional)
13. Next campaign iteration plan (optional)
14. ATLAS bridge briefs (landing / branding / page_design)

Each pack expander shows status (OK / MISSING / BLOCKED / ERROR),
rendered Markdown, raw JSON (collapsible + copy-as-text), and the
on-disk file paths.

The portal also computes a pre-flight checklist showing whether
the campaign is "ATLAS handoff ready" and "Publish gate
satisfied".

## What the portal does NOT do

- No edit. No save. No "publish" button.
- No external API call.
- No subprocess outside the Streamlit launch.
- No new database. No write to disk anywhere.
- No login / auth — single-user local tool.

## Tests

Functional logic lives in plain Python modules
(`pack_registry.py`, `pack_loader.py`, `client_discovery.py`,
`checklist.py`). Streamlit is not imported by the tests — only
the renderer (`app.py`) imports `streamlit`. CI runs without
Streamlit installed.
