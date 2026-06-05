"""Streamlit entry point for the portal (MKT-9A).

Run with:

    mkt portal
    # or
    python -m streamlit run portal/app.py -- --root <data> --outputs-dir <out>

This module is the ONLY place that imports ``streamlit``. Every
other module in :mod:`portal` is plain Python and unit-testable
without a Streamlit session running.

Read-only contract:

- No ``st.button`` / ``st.form`` / ``st.file_uploader`` triggers
  any disk write.
- No file is opened in write mode.
- No HTTP call, no SDK import, no credential read.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import streamlit as st  # type: ignore[import-not-found]

from portal.checklist import (
    PreflightChecklist,
    build_preflight_checklist,
)
from portal.client_discovery import discover_clients
from portal.pack_loader import (
    PackLoadResult,
    PackStatus,
    load_pack,
    load_pack_markdown,
)
from portal.pack_registry import iter_pack_specs

_DEFAULT_ROOT = Path("data")
_DEFAULT_OUTPUTS = Path("outputs")

_STATUS_ICON = {
    PackStatus.OK: "✅",
    PackStatus.BLOCKED: "🚫",
    PackStatus.MISSING: "⚪",
    PackStatus.ERROR: "❌",
}

_STATUS_LABEL = {
    PackStatus.OK: "OK",
    PackStatus.BLOCKED: "BLOCKED",
    PackStatus.MISSING: "MISSING",
    PackStatus.ERROR: "ERROR",
}


def _parse_cli_args() -> argparse.Namespace:
    """Parse ``streamlit run ... -- --root X --outputs-dir Y``."""
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--root", default=str(_DEFAULT_ROOT))
    parser.add_argument("--outputs-dir", default=str(_DEFAULT_OUTPUTS))
    # Streamlit may inject its own flags; ignore the unknown ones.
    args, _ = parser.parse_known_args(sys.argv[1:])
    return args


def main() -> None:
    args = _parse_cli_args()
    root = Path(args.root)
    outputs_dir = Path(args.outputs_dir)

    st.set_page_config(
        page_title="MARKETING-AGENCY-OS — Portal",
        layout="wide",
    )
    st.title("MARKETING-AGENCY-OS — Portal (MKT-9A)")
    st.caption("Read-only browser over persisted packs. No writes, no APIs.")

    _render_paths_banner(root=root, outputs_dir=outputs_dir)

    clients = discover_clients(root=root, outputs_dir=outputs_dir)
    if not clients:
        st.warning(
            f"No clients found under `{root}` / `{outputs_dir}`. "
            "Run `mkt run-campaign --intake <path>` first."
        )
        return

    selected = st.sidebar.selectbox(
        "Client",
        options=clients,
        index=0,
        help="Pick a client to browse its persisted packs.",
    )
    st.sidebar.markdown("---")
    st.sidebar.caption(
        "Portal is read-only. No widget on this page mutates disk."
    )

    if not selected:
        return

    st.header(f"Client: `{selected}`")
    results = [
        load_pack(
            root=root, outputs_dir=outputs_dir,
            client_slug=selected, spec=spec,
        )
        for spec in iter_pack_specs()
    ]
    checklist = build_preflight_checklist(results)
    _render_preflight(checklist)
    st.markdown("---")
    _render_pack_sections(results)


def _render_paths_banner(*, root: Path, outputs_dir: Path) -> None:
    cols = st.columns(2)
    with cols[0]:
        st.metric("Data root", str(root))
        if not root.exists():
            st.caption(":warning: data root does not exist yet")
    with cols[1]:
        st.metric("Outputs dir", str(outputs_dir))
        if not outputs_dir.exists():
            st.caption(":warning: outputs dir does not exist yet")


def _render_preflight(checklist: PreflightChecklist) -> None:
    st.subheader("Pre-flight checklist")
    cols = st.columns(5)
    cols[0].metric("Total packs", checklist.total)
    cols[1].metric("OK", checklist.ok)
    cols[2].metric("Missing", checklist.missing)
    cols[3].metric("Blocked", checklist.blocked)
    cols[4].metric("Errors", checklist.error)

    if checklist.required_missing:
        st.error(
            "Required packs missing — pre-flight not satisfied: "
            + ", ".join(checklist.required_missing)
        )
    if checklist.blocked_titles:
        st.warning(
            "Posture blocks publish in: "
            + ", ".join(checklist.blocked_titles)
        )
    if checklist.error_titles:
        st.error(
            "Errors loading: " + ", ".join(checklist.error_titles)
        )

    badge_cols = st.columns(2)
    with badge_cols[0]:
        if checklist.is_atlas_handoff_ready:
            st.success("ATLAS handoff ready")
        else:
            st.warning("ATLAS handoff NOT ready")
    with badge_cols[1]:
        if checklist.is_publish_ready:
            st.success("Publish gate satisfied")
        else:
            st.warning("Publish gate NOT satisfied")


def _render_pack_sections(results: list[PackLoadResult]) -> None:
    st.subheader("Packs")
    for r in results:
        icon = _STATUS_ICON[r.status]
        label = _STATUS_LABEL[r.status]
        optional_tag = " (optional)" if r.spec.optional else " (required)"
        header = f"{icon} {label} — {r.spec.title}{optional_tag}"
        with st.expander(header, expanded=False):
            st.caption(r.spec.description)
            _render_pack_body(r)


def _render_pack_body(r: PackLoadResult) -> None:
    if r.error_message:
        st.error(f"Load error: {r.error_message}")
    if r.file_path:
        st.caption(f"JSON file path: `{r.file_path}`")
    if r.markdown_path:
        st.caption(f"Markdown path: `{r.markdown_path}`")

    if r.status is PackStatus.MISSING:
        st.info("Pack not present yet.")
        return

    md = (
        load_pack_markdown(r.markdown_path) if r.markdown_path else ""
    )
    tabs = st.tabs(["Markdown", "JSON (raw)"])
    with tabs[0]:
        if md:
            st.markdown(md)
        else:
            st.caption(
                "No rendered Markdown found under `outputs/<slug>/` — "
                "run the corresponding CLI to produce one."
            )
    with tabs[1]:
        if r.data is None:
            st.caption("No JSON available.")
        else:
            st.json(r.data)
            # Provide a copy-ready code block as fallback for the
            # JSON-collapsed view.
            try:
                serialised = json.dumps(r.data, indent=2, default=str)
            except Exception:  # noqa: BLE001 — never crash the portal
                serialised = str(r.data)
            with st.expander("Copy as raw JSON text", expanded=False):
                st.code(serialised, language="json")


if __name__ == "__main__":
    main()
