# Windows Test Baseline (MKT-10Y)

Stable procedure for running the pytest suite on Windows without false-positive
errors caused by Windows file-locking semantics.

---

## Quick start

```powershell
# From the repo root (one-time setup already done if .venv exists):
.\scripts\test.ps1
```

To run a subset:

```powershell
.\scripts\test.ps1 tests/intelligence/
.\scripts\test.ps1 -v -k "utm"
.\scripts\test.ps1 tests/approval/ tests/memory/
```

Or invoke pytest directly — `--basetemp=.pytest_tmp` is set in `pyproject.toml`:

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m pytest tests/intelligence/ -v
```

---

## Root cause

### WinError 32 — Sharing Violation

When `JsonFileMemory.append_audit_event` writes an audit event, it:

1. Opens the JSONL file with `mode="a"` (O_APPEND).
2. Writes the event line.
3. Calls `os.fsync(f.fileno())` — flushes to disk.
4. The `with` block closes the file handle.

On Windows, `os.fsync` calls `FlushFileBuffers`. After this call, the NTFS
driver and/or Windows Defender may hold an internal reference to the file for
a brief period (milliseconds to ~1 second).

If pytest's `tmp_path` teardown runs `shutil.rmtree` on the test directory
during this window, it fails with:

```
PermissionError: [WinError 32] The process cannot access the file because
it is being used by another process
```

pytest's own `on_rm_rf_error` handler handles read-only errors (chmod +
retry) but **does not handle WinError 32** — it propagates the error,
which surfaces as a test ERROR even though the test itself passed.

### WinError 5 — Access Denied (system temp)

On some Windows setups, the default pytest basetemp
(`C:\Users\<user>\AppData\Local\Temp\pytest-of-<user>`) has restrictive
permissions from previous runs. Using a local `.pytest_tmp/` avoids this.

### WinError 183 — File Exists (.pytest_cache)

If a pytest run is interrupted, `.pytest_cache/v/cache` can be left as a
plain file instead of a directory. Subsequent runs fail to recreate it.
`scripts/test.ps1` detects and removes this before running.

---

## Fix implementation (MKT-10Y)

Three layers of defense:

### Layer 1 — `conftest.py` (root)

**`gc.collect()` autouse fixture**: drains CPython's garbage collector after
every test. This closes any file objects kept alive by reference cycles before
pytest's teardown runs.

**`_pytest.pathlib.rm_rf` retry patch** (Windows only): replaces pytest's
internal cleanup function with a version that retries on WinError 32 with
exponential back-off (up to ~1.85 seconds total). The original function is
stored as `_ppl._orig_rm_rf`; subsequent conftest imports are no-ops.

### Layer 2 — `pyproject.toml`

```toml
[tool.pytest.ini_options]
addopts = "-ra --strict-markers --basetemp=.pytest_tmp"
tmp_path_retention_policy = "all"
```

- `--basetemp=.pytest_tmp`: always use a local directory (avoids WinError 5).
- `tmp_path_retention_policy = "all"`: pytest does NOT clean up test dirs
  during the run. The conftest.py retry patch handles any cleanup that
  happens at the start of the next session.
- `cache_dir = ".pytest_tmp/.cache"`: moves the pytest cache inside
  `.pytest_tmp/` (gitignored, pre-cleaned by the script). Avoids WinError 183
  from a corrupt `.pytest_cache/v/cache` file that can appear after an
  interrupted run.

### Layer 3 — `scripts/test.ps1`

Pre-cleans `.pytest_tmp/` and any corrupt `.pytest_cache/v/cache` file with
retry + GC before invoking pytest. By removing old dirs **before** pytest
starts (no Python process holds them), Windows file locking is not an issue.

---

## What NOT to do

| Don't | Why |
|-------|-----|
| `--ignore` or `@pytest.mark.skip` affected tests | Hides real failures |
| `--no-header` to suppress WinError warnings | Masks the symptom |
| Remove `os.fsync()` from production code | Reduces audit durability |
| Use `tmp_path_retention_policy = "none"` | Deletes dirs during the run (more opportunities for WinError 32) |

---

## Verifying the baseline

After setup, the full suite should produce:

```
N passed, 0 warnings, 0 errors
```

No WinError 32 ERRORs. Any genuine test FAILURE is a real failure in test
logic, not a teardown artifact.

If you see a WinError 32 despite the fix, run:

```powershell
.\scripts\test.ps1     # pre-clean + gc patch active
```

If it persists, Windows Defender real-time protection may be unusually slow.
Add the repo directory to Defender's exclusion list as a development
exception.

---

## Files changed in MKT-10Y

| File | Change |
|------|--------|
| `conftest.py` | New — gc + rm_rf retry patch |
| `pyproject.toml` | `addopts` + `tmp_path_retention_policy` |
| `.gitignore` | Added `.pytest_tmp/` |
| `scripts/test.ps1` | New — pre-clean + run script |
| `docs/runtime/windows-test-baseline.md` | This file |
