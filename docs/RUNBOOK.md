# CampScout Windows runbook

This runbook describes the supported local Windows workflow for the SQLite version of CampScout. Every command is run from repository-relative paths. No MySQL server, Workbench installation, SQLite CLI, database account, credential, or `.env` file is used.

## Quick start from a clean clone

Prerequisite: install Python 3.10 or newer and enable either the Windows `py` launcher or the `python` command.

1. Clone or download the repository.
2. Confirm the six committed files remain under `data/processed/`.
3. Double-click `run_campscout.bat`.

The batch file resolves its own directory and launches `scripts/run_campscout.ps1` with a process-scoped execution-policy bypass. The PowerShell script then:

1. checks the six committed processed CSV paths;
2. detects `py` first and `python` second;
3. creates `.venv` if `.venv\Scripts\python.exe` is absent;
4. restores bundled pip only if pip is unavailable;
5. installs `requirements.txt` on first setup or after that file changes;
6. checks Python, SQLite, required imports, CSV headers, and CSV row readability;
7. builds `data/campscout.db` only when it is missing;
8. applies the justified SQLite indexes and validates the database;
9. starts `python -m streamlit run streamlit_app.py` from the repository root.

An existing database that passes validation is not rebuilt. An existing invalid database causes startup to stop; use the explicit rebuild option after reviewing the validation error:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\run_campscout.ps1 -RebuildDatabase
```

The rebuild path can recreate only `data/campscout.db`. It does not delete raw data, processed data, or any environment-overridden database. The quick-start workflow deliberately uses the default repository database for reproducibility and restores any inherited `CAMPSCOUT_DB_PATH` value when it exits. Direct application commands continue to support that documented override.

If setup fails, the batch launcher prints an error and waits for a keypress so the terminal does not disappear. Correct the reported issue and run it again.

## Individual Windows commands

Run these commands from the repository root:

```powershell
# Check Python, bundled SQLite, imports, and all processed CSVs
.\.venv\Scripts\python.exe scripts\check_environment.py

# Build only when missing; always apply indexes and validate
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\build_database.ps1

# Explicitly rebuild only data/campscout.db
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\build_database.ps1 -Rebuild

# Run pytest
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\run_tests.ps1

# Validate and start Streamlit
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\run_app.ps1
```

`-ExecutionPolicy Bypass` applies only to the launched PowerShell process. None of these scripts changes the user or machine execution policy.

## Development validation without raw files

The normal development gate uses the committed processed files and does not require raw inputs:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\full_validation.ps1
```

It stops immediately on a failed stage and returns a non-zero exit code. Its stages are:

1. Python, SQLite, package-import, and processed-CSV checks;
2. optional ETL, skipped unless requested;
3. a fresh rebuild of the default SQLite database;
4. database validation;
5. idempotent index application and exact index verification;
6. the full pytest suite;
7. live park, activity, radius search, detail, completeness, and ALL-selected-activities queries through short-lived read-only connections;
8. imports of `app.app` and `streamlit_app`.

## Full ETL reproduction

Obtain these original files and place the unmodified copies under `data/raw/`:

- `Recreation_Sites_INFRA.csv`
- `Recreation_Area_Activities.csv`
- `national_parks_raw.csv`

Then run either the ETL alone:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\run_etl.ps1
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\build_database.ps1 -Rebuild
```

or the complete validation gate with optional ETL enabled:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\full_validation.ps1 -RunEtl
```

The ETL mode verifies the exact raw filenames, profiles raw inputs, regenerates the six processed outputs in dependency order, checks their headers and readability, rebuilds SQLite, and compares database row counts with the regenerated CSV counts. Raw files are read only. If any raw file is absent, optional ETL stops with a list of missing filenames; quick start and normal validation remain available from committed processed data.

## Validation coverage

`python -m db.validate_database` and `sql/validation.sql` verify table and CSV row counts, STRICT tables, views and indexes, non-null and unique primary keys, coordinates, controlled vocabularies, valid Recreation Area links, complete distance cardinality, non-negative distances, duplicate bridge and distance pairs, foreign-key orphans, `PRAGMA foreign_key_check`, `PRAGMA integrity_check`, and distinct UNKNOWN versus negative amenity states.

The pytest suite additionally verifies database rebuild from committed processed files, constraint rejection and rollback, reset safety, parameter binding, ALL-selected-activities semantics, and short-lived read-only application connections. `scripts/check_environment.py --check-database` repeats representative application queries against the finished local database and attempts a prohibited write through the read-only connection.

## Troubleshooting

- **Python is missing:** install a current 64-bit Python from python.org and enable `py` or add `python` to PATH.
- **Package installation fails:** check internet access and proxy settings, then rerun the launcher. No credentials belong in the repository.
- **A processed CSV is missing or has unexpected headers:** restore the committed file. Quick start never regenerates it from raw data.
- **Database validation fails:** run the explicit `-RebuildDatabase` option. If rebuilding also fails, the processed data or local Python/SQLite runtime does not satisfy the documented contract.
- **Port 8501 is occupied:** stop the other process or run `scripts/run_app.ps1 --server.port 8502`.
- **Streamlit stops:** return to the terminal for the error. Press Ctrl+C for a normal shutdown.

## Remaining manual release checks

Automation verifies startup imports and the Streamlit health endpoint in pytest. Before a release, manually open the browser, run a representative park/radius search, combine at least two activities, reset all filters, open campground details, inspect the map markers, and stop Streamlit with Ctrl+C. Double-click behavior should also be checked on a clean Windows user profile because Explorer and local security policy are outside pytest's control.
