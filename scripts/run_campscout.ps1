[CmdletBinding()]
param(
    [switch]$RebuildDatabase
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$VenvDirectory = Join-Path $RepoRoot ".venv"
$VenvPython = Join-Path $VenvDirectory "Scripts\python.exe"
$RequirementsPath = Join-Path $RepoRoot "requirements.txt"
$RequirementsStamp = Join-Path $VenvDirectory ".campscout-requirements.sha256"
$DatabasePath = Join-Path $RepoRoot "data\campscout.db"
$ProcessedFiles = @(
    "national_parks.csv",
    "recreation_areas.csv",
    "activities.csv",
    "campgrounds.csv",
    "recreation_area_activities.csv",
    "park_campground_distances.csv"
)

function Invoke-CheckedPython {
    param([string[]]$PythonArguments)
    & $VenvPython @PythonArguments
    if ($LASTEXITCODE -ne 0) {
        throw "Python command failed with exit code ${LASTEXITCODE}: $($PythonArguments -join ' ')"
    }
}

try {
    Set-Location $RepoRoot
    Write-Host "[CampScout] Repository: $RepoRoot"

    foreach ($FileName in $ProcessedFiles) {
        $Path = Join-Path $RepoRoot "data\processed\$FileName"
        if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
            throw "Required processed CSV is missing: data\processed\$FileName"
        }
    }
    Write-Host "[CampScout] All six processed CSV files are present."

    if (-not (Test-Path -LiteralPath $VenvPython -PathType Leaf)) {
        $Launcher = Get-Command py -ErrorAction SilentlyContinue
        $LauncherArguments = @("-3")
        if ($null -eq $Launcher) {
            $Launcher = Get-Command python -ErrorAction SilentlyContinue
            $LauncherArguments = @()
        }
        if ($null -eq $Launcher) {
            throw "Python 3 was not found. Install Python from python.org, then run this launcher again."
        }

        Write-Host "[CampScout] Creating .venv with $($Launcher.Source)..."
        & $Launcher.Source @LauncherArguments -m venv $VenvDirectory
        if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $VenvPython)) {
            throw "Python was found, but creation of .venv failed."
        }
    }

    & $VenvPython -m pip --version *> $null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[CampScout] pip is missing from .venv; restoring the bundled pip."
        Invoke-CheckedPython -PythonArguments @("-m", "ensurepip", "--upgrade")
    }

    $RequirementsHash = (Get-FileHash -LiteralPath $RequirementsPath -Algorithm SHA256).Hash
    $InstalledHash = if (Test-Path -LiteralPath $RequirementsStamp) {
        (Get-Content -LiteralPath $RequirementsStamp -Raw).Trim()
    } else {
        ""
    }
    $NeedsInstall = $RequirementsHash -ne $InstalledHash
    if ($NeedsInstall) {
        Write-Host "[CampScout] Installing requirements for first setup or a changed requirements file..."
        Invoke-CheckedPython -PythonArguments @("-m", "pip", "install", "-r", $RequirementsPath)
        Set-Content -LiteralPath $RequirementsStamp -Value $RequirementsHash -Encoding ASCII
    }

    & $VenvPython scripts\check_environment.py
    if ($LASTEXITCODE -ne 0 -and -not $NeedsInstall) {
        Write-Host "[CampScout] Environment imports are incomplete; repairing installed requirements..."
        Invoke-CheckedPython -PythonArguments @("-m", "pip", "install", "-r", $RequirementsPath)
        Set-Content -LiteralPath $RequirementsStamp -Value $RequirementsHash -Encoding ASCII
        Invoke-CheckedPython -PythonArguments @("scripts\check_environment.py")
    } elseif ($LASTEXITCODE -ne 0) {
        throw "CampScout environment validation failed after installing requirements."
    }

    $ExistingOverride = $env:CAMPSCOUT_DB_PATH
    $HadOverride = Test-Path Env:CAMPSCOUT_DB_PATH
    Remove-Item Env:CAMPSCOUT_DB_PATH -ErrorAction SilentlyContinue
    try {
        if ($RebuildDatabase) {
            Write-Host "[CampScout] Rebuilding the repository database by explicit request..."
            & (Join-Path $PSScriptRoot "build_database.ps1") -Rebuild
            if ($LASTEXITCODE -ne 0) { throw "Database rebuild failed." }
        } elseif (-not (Test-Path -LiteralPath $DatabasePath -PathType Leaf)) {
            Write-Host "[CampScout] Database is missing; building it from committed processed CSVs..."
            & (Join-Path $PSScriptRoot "build_database.ps1")
            if ($LASTEXITCODE -ne 0) { throw "Database build failed." }
        } else {
            Write-Host "[CampScout] Validating the existing database (no rebuild)..."
            Invoke-CheckedPython -PythonArguments @("-m", "db.validate_database")
        }

        Write-Host "[CampScout] Starting Streamlit. Press Ctrl+C to stop."
        & (Join-Path $PSScriptRoot "run_app.ps1") -SkipValidation
        if ($LASTEXITCODE -ne 0) { throw "Streamlit exited with an error." }
    } finally {
        if ($HadOverride) {
            $env:CAMPSCOUT_DB_PATH = $ExistingOverride
        }
    }
} catch {
    Write-Host ""
    Write-Host "[CampScout] ERROR: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host "[CampScout] Setup stopped. No raw or processed data was deleted."
    exit 1
}

exit 0
