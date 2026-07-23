[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Python = Join-Path $RepoRoot ".venv\Scripts\python.exe"

try {
    Set-Location $RepoRoot
    if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
        throw ".venv is missing. Run run_campscout.bat once to create the environment."
    }

    Write-Host "=== Verify raw ETL inputs ==="
    & $Python scripts\check_environment.py --require-raw
    if ($LASTEXITCODE -ne 0) { throw "Raw-input validation failed." }

    Write-Host "=== Profile immutable raw data ==="
    & $Python -m etl.profile_raw_data
    if ($LASTEXITCODE -ne 0) { throw "Raw-data profiling failed." }

    Write-Host "=== Run full ETL pipeline ==="
    & $Python -m etl.run_pipeline
    if ($LASTEXITCODE -ne 0) { throw "ETL pipeline failed." }

    Write-Host "=== Verify regenerated processed CSVs ==="
    & $Python scripts\check_environment.py
    if ($LASTEXITCODE -ne 0) { throw "Regenerated processed-data validation failed." }
} catch {
    Write-Host "ETL failed: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}

Write-Host "ETL completed successfully. Raw files were read but not modified."
exit 0
