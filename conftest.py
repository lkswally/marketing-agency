"""Project-wide pytest fixtures and Windows test baseline stability (MKT-10Y).

Windows root cause
------------------
On Windows, NTFS + Windows Defender can hold a JSONL audit file briefly
"in use" (WinError 32 = ERROR_SHARING_VIOLATION) after a Python process
writes, fsync's, and closes it.  pytest's shutil.rmtree teardown then raises
PermissionError — surfaced as a test ERROR even though the test itself passed.

Two-part fix
------------
1. ``_gc_collect_after_test`` — autouse fixture that drains CPython's garbage
   collector after every test.  This closes file objects kept alive by
   reference cycles before pytest attempts tmp_path cleanup.

2. ``_patch_rm_rf_retry`` (Windows only) — replaces ``_pytest.pathlib.rm_rf``
   with a version that retries on WinError 32 with exponential back-off.
   pytest's own ``on_rm_rf_error`` handler handles read-only errors via chmod
   but propagates sharing-violation errors unchanged; we fill that gap here.

Neither fix touches test logic or relaxes any assertions.
"""

from __future__ import annotations

import gc
import sys
import time
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Fix 1 — GC drain (all platforms, cheap)
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _gc_collect_after_test() -> None:  # type: ignore[return]
    """Drain CPython GC after each test to release lingering file handles."""
    yield  # type: ignore[misc]
    gc.collect()


# ---------------------------------------------------------------------------
# Fix 2 — retry rm_rf on WinError 32 (Windows only)
# ---------------------------------------------------------------------------

if sys.platform == "win32":
    _WINERROR_SHARING_VIOLATION = 32
    # Total max wait: 0.05 + 0.1 + 0.2 + 0.5 + 1.0 ≈ 1.85 s — acceptable for
    # a cleanup step that should normally succeed on the first retry.
    _RETRY_DELAYS_S = (0.05, 0.1, 0.2, 0.5, 1.0)

    def _rm_rf_with_retry(path: Path) -> None:
        import _pytest.pathlib as _ppl  # local import — may not exist in all envs

        orig = _ppl._orig_rm_rf  # type: ignore[attr-defined]
        last_exc: PermissionError | None = None
        for delay in _RETRY_DELAYS_S:
            try:
                orig(path)
                return
            except PermissionError as exc:
                if getattr(exc, "winerror", None) == _WINERROR_SHARING_VIOLATION:
                    last_exc = exc
                    gc.collect()
                    time.sleep(delay)
                else:
                    raise
        # Final attempt — propagate if still locked after all retries.
        if last_exc is not None:
            orig(path)

    def _patch_rm_rf() -> None:
        try:
            import _pytest.pathlib as _ppl

            if hasattr(_ppl, "_orig_rm_rf"):
                return  # already patched (e.g., conftest imported twice)
            _ppl._orig_rm_rf = _ppl.rm_rf  # type: ignore[attr-defined]
            _ppl.rm_rf = _rm_rf_with_retry  # type: ignore[attr-defined]
        except (ImportError, AttributeError):
            pass  # pytest internals changed — skip the patch gracefully

    _patch_rm_rf()
