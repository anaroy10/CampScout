# CampScout

CampScout is a planned Python, MySQL, and Streamlit application for finding Forest Service campgrounds near United States national parks. A user will choose a national park and a radius in kilometers, then narrow nearby results using activities available in each campground's Recreation Area, fee status, water availability, restroom type, and campground type.

The result view is planned to show approximate straight-line distance, campground details, directions, Recreation Area activities, and an official URL. Ratings, reviews, hookups, vehicle-length recommendations, booking, and machine-learning recommendations are outside the project scope.

## Planned architecture

The intended data flow is:

```text
immutable raw CSV files
        -> reproducible Python ETL and validation
        -> processed data artifacts
        -> normalized MySQL database
        -> parameterized data-access layer
        -> Streamlit user interface
```

Activities will be modeled on Recreation Areas, not campgrounds. National parks and campgrounds will not have a direct relationship; proximity will be calculated from their coordinates. See `docs/ARCHITECTURE.md` for the proposed boundaries and data model.

## Expected raw files

Place these exact, unmodified filenames in `data/raw/`:

- `Recreation_Sites_INFRA.csv`
- `Recreation_Area_Activities.csv`
- `national_parks_raw.csv`

Raw CSVs are local inputs, intentionally excluded from Git, and must never be edited in place.

## Windows setup

Prerequisites:

- Windows with PowerShell
- VS Code
- Python 3
- MySQL Server

From the repository root in PowerShell:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

If PowerShell blocks activation, allow scripts only for the current process and activate again:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

Edit `.env` locally with the MySQL connection values. The `.env` file is ignored by Git; credentials must never be placed in source code or documentation.

## Current implementation status

Raw-data profiling and the Recreation Area/activity cleaning phase are implemented. The activity phase reads only `data/raw/Recreation_Area_Activities.csv` and writes three processed CSVs plus summary, conflict, and dropped-row audit reports.

Run the standalone phase from the repository root:

```powershell
python -m etl.clean_activities
```

The current pipeline entry point invokes that phase and explicitly reports the unimplemented later phases:

```powershell
python -m etl.run_pipeline
```

The cleaner keeps identifiers as text, normalizes whitespace and HTML entities, removes HTML from descriptive output, creates one canonical row per source identifier, and deduplicates `(RECAREAID, ACTIVITYID)` pairs. Missing-key source rows and conflicting repeated attributes remain available in generated audit reports. Processed CSVs use the literal source column names documented in `docs/DATA_DICTIONARY.md`.

Run all tests with:

```powershell
pytest
```

Campground cleaning, national-park cleaning, the MySQL loader and queries, and the Streamlit application are not implemented yet.

## Future commands — not implemented yet

The following later-stage commands do **not** work yet because their entry points do not exist:

```powershell
# NOT IMPLEMENTED: create/load the MySQL schema
python -m db.load

# NOT IMPLEMENTED: launch the Streamlit interface
streamlit run app/main.py

```

Do not infer implementation details from these placeholder command names. They may change when the relevant component is designed.

## Documentation

- `docs/PROJECT_SPEC.md` — product scope and acceptance criteria
- `docs/ARCHITECTURE.md` — planned components and logical model
- `docs/DATA_SOURCES.md` — source inventory and observed profiling facts
- `docs/DATA_DICTIONARY.md` — proposed canonical fields and semantics
- `docs/DECISIONS.md` — durable design decisions and open questions
- `docs/TEST_PLAN.md` — future verification strategy
