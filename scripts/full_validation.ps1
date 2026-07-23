[CmdletBinding()]
param(
    [switch]$RunEtl
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Python = Join-Path $RepoRoot ".venv\Scripts\python.exe"
$ExistingOverride = $env:CAMPSCOUT_DB_PATH
$HadOverride = Test-Path Env:CAMPSCOUT_DB_PATH

function Invoke-Stage {
    param([string]$Name, [scriptblock]$Action)
    Write-Host ""
    Write-Host "=== $Name ===" -ForegroundColor Cyan
    & $Action
}

try {
    Set-Location $RepoRoot
    if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
        throw ".venv is missing. Run run_campscout.bat once to create the environment."
    }
    Remove-Item Env:CAMPSCOUT_DB_PATH -ErrorAction SilentlyContinue

    Invoke-Stage "1. Python, SQLite, packages, and processed CSVs" {
        & $Python scripts\check_environment.py
        if ($LASTEXITCODE -ne 0) { throw "Environment validation failed." }
    }

    if ($RunEtl) {
        Invoke-Stage "2. Optional raw profiling and full ETL" {
            & (Join-Path $PSScriptRoot "run_etl.ps1")
            if ($LASTEXITCODE -ne 0) { throw "Optional ETL workflow failed." }
        }
    } else {
        Write-Host ""
        Write-Host "=== 2. Optional raw profiling and ETL: skipped (use -RunEtl) ===" -ForegroundColor Yellow
    }

    Invoke-Stage "3. Fresh SQLite database rebuild" {
        & (Join-Path $PSScriptRoot "build_database.ps1") -Rebuild
        if ($LASTEXITCODE -ne 0) { throw "Fresh database build failed." }
    }

    Invoke-Stage "4. Database validation" {
        & $Python -m db.validate_database
        if ($LASTEXITCODE -ne 0) { throw "Database validation failed." }
    }

    Invoke-Stage "5. Index installation and verification" {
        & $Python -m db.apply_indexes
        if ($LASTEXITCODE -ne 0) { throw "Index verification failed." }
    }

    Invoke-Stage "6. Full pytest suite" {
        & (Join-Path $PSScriptRoot "run_tests.ps1")
        if ($LASTEXITCODE -ne 0) { throw "Test suite failed." }
    }

    Invoke-Stage "7. Core read-only application queries" {
        & $Python scripts\check_environment.py --check-database
        if ($LASTEXITCODE -ne 0) { throw "Core application query checks failed." }
    }

    Invoke-Stage "8. Streamlit application imports" {
        & $Python scripts\check_environment.py --check-app-import
        if ($LASTEXITCODE -ne 0) { throw "Streamlit import check failed." }
    }
} catch {
    Write-Host ""
    Write-Host "FULL VALIDATION FAILED: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
} finally {
    if ($HadOverride) {
        $env:CAMPSCOUT_DB_PATH = $ExistingOverride
    }
}

Write-Host ""
Write-Host "FULL VALIDATION PASSED" -ForegroundColor Green
exit 0
