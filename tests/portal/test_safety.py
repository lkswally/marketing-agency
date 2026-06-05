"""Safety pins for the portal — read-only contract (MKT-9A)."""

from __future__ import annotations

from pathlib import Path

PORTAL_DIR = Path(__file__).resolve().parents[2] / "portal"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_no_write_mode_open_in_portal_modules() -> None:
    """No `open(..., 'w'...)` / `open(..., 'a'...)` anywhere."""
    forbidden = (
        'open("', "open('",  # we whitelist below
    )
    write_modes = ('"w"', "'w'", '"a"', "'a'", '"wb"', "'wb'")
    for py in PORTAL_DIR.glob("*.py"):
        text = _read(py)
        for mode in write_modes:
            assert "open(" not in text or mode not in text, (
                f"{py.name} contains a write-mode open with {mode!r}"
            )
    _ = forbidden


def test_no_path_write_methods_in_portal() -> None:
    forbidden = (
        ".write_text(", ".write_bytes(",
        "shutil.copy", "shutil.move", "shutil.rmtree",
        "os.remove", "os.unlink", "os.rmdir", "os.makedirs",
        "Path.mkdir", "json.dump(",
    )
    for py in PORTAL_DIR.glob("*.py"):
        text = _read(py)
        for needle in forbidden:
            assert needle not in text, (
                f"{py.name} contains write-style call {needle!r}"
            )


def test_no_http_lib_in_portal_modules() -> None:
    forbidden = (
        "import requests", "from requests",
        "import httpx", "from httpx",
        "import urllib.request", "from urllib.request",
        "import aiohttp", "from aiohttp",
    )
    for py in PORTAL_DIR.glob("*.py"):
        text = _read(py)
        for needle in forbidden:
            assert needle not in text, f"{py.name} contains {needle!r}"


def test_no_credential_read_in_portal_source() -> None:
    forbidden = ("os.environ", "os.getenv")
    for py in PORTAL_DIR.glob("*.py"):
        text = _read(py)
        for needle in forbidden:
            assert needle not in text, f"{py.name} contains {needle!r}"


def test_no_subprocess_in_portal_modules() -> None:
    """The portal app itself must not spawn subprocesses. The CLI
    wrapper `mkt portal` does — that lives in cli/main.py."""
    forbidden = (
        "import subprocess", "from subprocess",
        "os.system", "os.popen",
    )
    for py in PORTAL_DIR.glob("*.py"):
        text = _read(py)
        for needle in forbidden:
            assert needle not in text, f"{py.name} contains {needle!r}"


def test_no_destructive_streamlit_widgets_in_app() -> None:
    """The Streamlit app must not host buttons / forms / file
    uploaders that could trigger destructive behaviour."""
    app = _read(PORTAL_DIR / "app.py")
    forbidden = (
        "st.button(",
        "st.download_button(",
        "st.form(",
        "st.form_submit_button(",
        "st.file_uploader(",
        "st.experimental_data_editor",
        "st.data_editor(",
    )
    for needle in forbidden:
        assert needle not in app, f"app.py contains {needle!r}"


def test_no_notion_n8n_atlas_reach_in_portal() -> None:
    """The portal must not import or call any external integration
    module that could write to Notion / n8n / ATLAS."""
    forbidden_tokens = (
        "notion_client", "notion-client", "notion.Client",
        "n8n_executor", "n8n.executor",
        "from core.atlas_bridge.factory import",  # bridge factory writes audit
        "atlas_core", "atlas-core", "ATLAS_API_URL",
        "from core.n8n_sync",  # any writer module
        "from core.notion_sync",
    )
    for py in PORTAL_DIR.glob("*.py"):
        text = _read(py)
        for needle in forbidden_tokens:
            assert needle not in text, f"{py.name} contains {needle!r}"


def test_no_image_sdk_imported_in_portal() -> None:
    forbidden = (
        "import openai", "from openai",
        "import replicate", "from replicate",
        "stability_sdk",
        "from PIL", "import PIL",
        "Image.open(", "Image.save(",
    )
    for py in PORTAL_DIR.glob("*.py"):
        text = _read(py)
        for needle in forbidden:
            assert needle not in text, f"{py.name} contains {needle!r}"


def test_app_py_only_uses_display_streamlit_calls() -> None:
    """Sanity: app.py should only use Streamlit display widgets.
    We can't fully enumerate Streamlit's API; instead we assert the
    expected display widgets ARE present (so a future refactor
    cannot silently drop them all)."""
    app = _read(PORTAL_DIR / "app.py")
    expected_display = ("st.markdown", "st.json", "st.expander", "st.caption")
    for w in expected_display:
        assert w in app, f"app.py is missing {w!r}"


def test_portal_init_does_not_import_streamlit() -> None:
    """portal/__init__.py must stay streamlit-free so the tests
    can import the pure-Python modules without the extra installed.
    We check for the actual `import` lines — docstring mentions
    of Streamlit are allowed."""
    init = _read(PORTAL_DIR / "__init__.py")
    for needle in ("import streamlit", "from streamlit"):
        assert needle not in init, f"__init__.py contains {needle!r}"


def test_only_app_py_imports_streamlit() -> None:
    """Pin: app.py is the ONLY module under portal/ that imports
    streamlit. Everything else stays pure Python so CI tests run
    without the extra installed."""
    for py in PORTAL_DIR.glob("*.py"):
        if py.name == "app.py":
            continue
        text = _read(py)
        assert "import streamlit" not in text, (
            f"{py.name} unexpectedly imports streamlit"
        )
        assert "from streamlit" not in text, (
            f"{py.name} unexpectedly imports from streamlit"
        )
