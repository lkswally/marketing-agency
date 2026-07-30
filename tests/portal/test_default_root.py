"""Portal and CLI must agree on the canonical memory root (MKT-10A)."""

from __future__ import annotations

from pathlib import Path


def test_portal_default_root_matches_cli_default() -> None:
    """`portal/app.py`'s `_DEFAULT_ROOT` must match `cli.main.DEFAULT_DATA_ROOT`.

    `mkt portal` always forwards its own `--root` (which defaults to
    `data/clients`) to the Streamlit subprocess, so this only matters when
    an operator runs `streamlit run portal/app.py` directly without
    `--root`. Before MKT-10A this default was `data`, silently pointing at
    the wrong directory (client data lives under `data/clients/<slug>/`).
    """
    from cli.main import DEFAULT_DATA_ROOT
    from portal.app import _DEFAULT_ROOT

    assert _DEFAULT_ROOT == DEFAULT_DATA_ROOT == Path("data/clients")
