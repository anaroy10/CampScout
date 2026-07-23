[CmdletBinding()]
param(
    [string[]]$PytestArguments = @("-q")
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Python = Join-Path $RepoRoot ".venv\Scripts\python.exe"

try {
    Set-Location $RepoRoot
    if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
        throw ".venv is missing. Run run_campscout.bat once to create the environment."
    }
    & $Python -m pytest @PytestArguments
    if ($LASTEXITCODE -ne 0) { throw "pytest failed with exit code $LASTEXITCODE." }
} catch {
    Write-Host "Test workflow failed: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}

exit 0
