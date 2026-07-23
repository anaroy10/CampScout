[CmdletBinding()]
param(
    [switch]$SkipValidation,
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$StreamlitArguments
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Python = Join-Path $RepoRoot ".venv\Scripts\python.exe"

try {
    Set-Location $RepoRoot
    if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
        throw ".venv is missing. Run run_campscout.bat once to create the environment."
    }
    if (-not $SkipValidation) {
        & $Python -m db.validate_database
        if ($LASTEXITCODE -ne 0) { throw "Database validation failed." }
    }

    & $Python -m streamlit run streamlit_app.py @StreamlitArguments
    if ($LASTEXITCODE -ne 0) { throw "Streamlit exited with code $LASTEXITCODE." }
} catch {
    Write-Host "Application launch failed: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}

exit 0
