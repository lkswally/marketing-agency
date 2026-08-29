# scripts/test.ps1 — Windows-stable pytest runner (MKT-10Y)
#
# Usage:
#   .\scripts\test.ps1                         # full suite
#   .\scripts\test.ps1 tests/intelligence/     # single module
#   .\scripts\test.ps1 -v -k "utm"             # pytest flags pass-through
#
# What this script does:
#   1. Pre-cleans .pytest_tmp/ and .pytest_cache/ with retry (avoids
#      WinError 32 "sharing violation" from previous run's stale files).
#   2. Activates the venv if not already active.
#   3. Runs pytest — --basetemp=.pytest_tmp is set in pyproject.toml.
#
# Requirements: run from the repo root; .venv/ must exist.

param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$PytestArgs
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# ── helpers ────────────────────────────────────────────────────────────────

function Remove-WithRetry {
    param(
        [string]$Path,
        [int]$MaxAttempts = 8,
        [int]$BaseDelayMs = 200
    )
    if (-not (Test-Path $Path)) { return }
    Write-Host "  Cleaning $Path ..." -ForegroundColor DarkGray
    for ($i = 0; $i -lt $MaxAttempts; $i++) {
        try {
            Remove-Item -Recurse -Force $Path -ErrorAction Stop
            return
        }
        catch {
            if ($i -lt $MaxAttempts - 1) {
                [System.GC]::Collect()
                [System.GC]::WaitForPendingFinalizers()
                $delay = $BaseDelayMs * [Math]::Pow(2, $i)
                Start-Sleep -Milliseconds $delay
            }
            else {
                Write-Warning "Could not remove $Path after $MaxAttempts attempts: $_"
            }
        }
    }
}

# ── pre-clean ──────────────────────────────────────────────────────────────

Write-Host "==> Pre-cleaning stale pytest artifacts..." -ForegroundColor Cyan
Remove-WithRetry ".pytest_tmp"
# .pytest_cache/v/cache can become a FILE instead of a dir on interrupted runs
if (Test-Path ".pytest_cache\v\cache") {
    $item = Get-Item ".pytest_cache\v\cache"
    if (-not $item.PSIsContainer) {
        Write-Host "  Removing corrupt .pytest_cache/v/cache file..." -ForegroundColor Yellow
        Remove-WithRetry ".pytest_cache\v\cache"
    }
}

# ── activate venv if needed ────────────────────────────────────────────────

$python = ".\.venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    Write-Error "Virtual environment not found at .venv/. Run: py -m venv .venv && pip install -e '.[dev,portal,claude,notion]'"
    exit 1
}

# ── run pytest ─────────────────────────────────────────────────────────────

Write-Host "==> Running pytest..." -ForegroundColor Cyan
if ($PytestArgs.Count -gt 0) {
    & $python -m pytest @PytestArgs
}
else {
    & $python -m pytest
}
exit $LASTEXITCODE
