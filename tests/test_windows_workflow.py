from __future__ import annotations

import csv
from pathlib import Path

import pytest

from db.build_database import TABLE_SPECS
from scripts import check_environment


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_NAMES = (
    "run_campscout.ps1",
    "run_etl.ps1",
    "build_database.ps1",
    "run_tests.ps1",
    "run_app.ps1",
    "full_validation.ps1",
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_environment_checker_verifies_all_committed_processed_csvs():
    counts = check_environment.check_processed_files(REPOSITORY_ROOT)

    assert set(counts) == {spec.csv_filename for spec in TABLE_SPECS}
    assert all(count > 0 for count in counts.values())


def test_environment_checker_rejects_missing_and_changed_processed_contracts(tmp_path):
    processed = tmp_path / "data" / "processed"
    processed.mkdir(parents=True)

    with pytest.raises(check_environment.EnvironmentCheckError, match="missing"):
        check_environment.check_processed_files(tmp_path)

    for spec in TABLE_SPECS:
        with (processed / spec.csv_filename).open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(spec.csv_fields)
    first = TABLE_SPECS[0]
    (processed / first.csv_filename).write_text("wrong_header\n", encoding="utf-8")

    with pytest.raises(check_environment.EnvironmentCheckError, match="Unexpected headers"):
        check_environment.check_processed_files(tmp_path)


def test_batch_launcher_uses_its_own_path_and_keeps_failures_visible():
    launcher = _read(REPOSITORY_ROOT / "run_campscout.bat").lower()

    assert "%~dp0" in launcher
    assert "scripts\\run_campscout.ps1" in launcher
    assert "-executionpolicy bypass" in launcher
    assert "%*" in launcher
    assert "pause" in launcher


def test_quick_start_bootstraps_python_venv_requirements_and_default_database():
    script = _read(REPOSITORY_ROOT / "scripts" / "run_campscout.ps1")

    assert "Get-Command py" in script
    assert "Get-Command python" in script
    assert '"-m", "venv"' not in script  # venv creation uses the detected launcher directly
    assert "-m venv" in script
    assert "requirements.txt" in script
    assert ".campscout-requirements.sha256" in script
    assert "data\\campscout.db" in script
    assert "-RebuildDatabase" not in script  # PowerShell parameters omit the dash in declarations
    assert "[switch]$RebuildDatabase" in script
    assert "db.validate_database" in script
    assert 'Join-Path $PSScriptRoot "run_app.ps1"' in script


def test_application_script_uses_only_official_root_streamlit_command():
    script = _read(REPOSITORY_ROOT / "scripts" / "run_app.ps1")

    assert "-m streamlit run streamlit_app.py" in script
    assert "db.validate_database" in script


def test_full_validation_contains_every_required_stage_and_optional_etl():
    script = _read(REPOSITORY_ROOT / "scripts" / "full_validation.ps1")

    for required in (
        "[switch]$RunEtl",
        "check_environment.py",
        "run_etl.ps1",
        "build_database.ps1",
        "db.validate_database",
        "db.apply_indexes",
        "run_tests.ps1",
        "--check-database",
        "--check-app-import",
        "FULL VALIDATION PASSED",
    ):
        assert required in script


def test_all_powershell_workflows_are_root_relative_and_stop_on_errors():
    for name in SCRIPT_NAMES:
        script = _read(REPOSITORY_ROOT / "scripts" / name)
        lowered = script.lower()
        assert "$PSScriptRoot" in script
        assert '$ErrorActionPreference = "Stop"' in script
        assert "git " not in lowered
        assert "set-executionpolicy" not in lowered
        assert "remove-item" not in lowered or "env:campscout_db_path" in lowered


def test_readme_and_runbook_document_quick_start_and_full_etl_paths():
    readme = _read(REPOSITORY_ROOT / "README.md")
    runbook = _read(REPOSITORY_ROOT / "docs" / "RUNBOOK.md")

    assert "## Quick start" in readme
    assert "Double-click `run_campscout.bat`" in readme
    assert "## Full ETL reproduction" in readme
    assert "scripts\\full_validation.ps1 -RunEtl" in readme
    assert "python -m streamlit run streamlit_app.py" in runbook
    assert "Raw files are read only" in runbook
