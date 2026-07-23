[CmdletBinding()]
param(
    [switch]$Rebuild
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Python = Join-Path $RepoRoot ".venv\Scripts\python.exe"
$DatabasePath = Join-Path $RepoRoot "data\campscout.db"
$ExistingOverride = $env:CAMPSCOUT_DB_PATH
$HadOverride = Test-Path Env:CAMPSCOUT_DB_PATH

try {
    Set-Location $RepoRoot
    if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
        throw ".venv is missing. Run run_campscout.bat once to create the environment."
    }
    & $Python scripts\check_environment.py
    if ($LASTEXITCODE -ne 0) { throw "Environment or processed-data validation failed." }

    Remove-Item Env:CAMPSCOUT_DB_PATH -ErrorAction SilentlyContinue
    if ($Rebuild) {
        Write-Host "Rebuilding only data\campscout.db..."
        & $Python -m db.build_database --reset
    } elseif (-not (Test-Path -LiteralPath $DatabasePath -PathType Leaf)) {
        Write-Host "Building data\campscout.db from committed processed CSVs..."
        & $Python -m db.build_database
    } else {
        Write-Host "data\campscout.db already exists; it will not be rebuilt."
    }
    if ($LASTEXITCODE -ne 0) { throw "Database build failed." }

    & $Python -m db.apply_indexes
    if ($LASTEXITCODE -ne 0) { throw "Index application failed." }
    & $Python -m db.validate_database
    if ($LASTEXITCODE -ne 0) { throw "Database validation failed." }
} catch {
    Write-Host "Database workflow failed: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
} finally {
    if ($HadOverride) {
        $env:CAMPSCOUT_DB_PATH = $ExistingOverride
    }
}

Write-Host "SQLite database is ready."
exit 0
