# CampScout

CampScout is a planned Python, MySQL, and Streamlit application for finding Forest Service campgrounds near United States national parks. A user will choose a national park and a radius in kilometers, then narrow nearby results using activities available in each campground's Recreation Area, fee status, water availability, restroom type, and campground type.

The result view is planned to show approximate straight-line distance, campground details, directions, Recreation Area activities, and an official URL. Ratings, reviews, hookups, vehicle-length recommendations, booking, and machine-learning recommendations are outside the project scope.

## Architecture

The intended data flow is:

```text
immutable raw CSV files
        -> reproducible Python ETL and validation
        -> processed data artifacts
        -> normalized MySQL database
        -> parameterized data-access layer
        -> Streamlit user interface
```

Activities are modeled on Recreation Areas, not campgrounds. National parks and campgrounds have no direct foreign-key relationship; the ETL materializes their calculated straight-line distances from validated coordinates. See `docs/ARCHITECTURE.md` for the component boundaries and data model.

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

Raw-data profiling and the complete CSV transformation pipeline are implemented. The pipeline cleans Recreation Areas and activities, cleans campgrounds, cleans national parks, and calculates every valid park-campground distance. The campground phase uses `data/processed/recreation_areas.csv` only to validate Recreation Area identifiers extracted from USDA portal URLs; it does not fuzzy-link unmatched records.

Run an individual phase from the repository root when needed:

```powershell
python -m etl.clean_activities
python -m etl.clean_campgrounds
python -m etl.clean_parks
python -m etl.calculate_distances
```

The supported full command creates missing output directories, runs all four phases in dependency order, logs each phase, and stops with a non-zero exit code if a phase fails validation:

```powershell
python -m etl.run_pipeline
```

The activity cleaner keeps identifiers as text, normalizes whitespace and HTML entities, removes HTML from descriptive output, creates one canonical row per source identifier, and deduplicates `(RECAREAID, ACTIVITYID)` pairs. Missing-key source rows and conflicting repeated attributes remain available in generated audit reports.

The campground cleaner:

- retains exact normalized subtypes `CAMPGROUND`, `GROUP CAMPGROUND`, and `HORSE CAMP`;
- uses complete, unique `globalid` as `campground_id` while preserving `site_cn` and non-unique `site_id` as text;
- chooses the display name from `public_site_name`, then `site_name`, then `recarea_name`;
- preserves raw water/restroom descriptions beside documented normalized categories;
- retains campgrounds whose USDA URL is missing, lacks `recid`, or names an unknown Recreation Area, and audits them in `reports/generated/unmatched_campgrounds.csv`;
- reports exact normalized-name pairs within 1 km as possible duplicates without merging them; and
- validates keys, categories, coordinates, Recreation Area links, identifier formatting, and output count before publishing artifacts.

The park cleaner removes the unnamed source index and fully empty image column, normalizes whitespace and non-breaking spaces, removes trailing name stars and numeric description citations, parses ISO establishment dates, acreage, visitor counts, and signed coordinates, and records any parse failure without inventing a value. Its UUIDv5 `park_id` is derived from the normalized cleaned name rather than source row position.

The distance phase uses the Haversine formula and the 6,371.0088 km IUGG mean Earth radius. It emits one row per valid park-campground pair, preserves full precision during calculation, rounds only exported `distance_km` to six decimal places, sorts by both identifiers, rejects negative or non-finite results, and validates the complete cross-product cardinality. These values are straight-line distances from each park's representative coordinate, not road or entrance distances.

Principal outputs are:

- `data/processed/recreation_areas.csv`, `activities.csv`, and `recreation_area_activities.csv`;
- `data/processed/campgrounds.csv`;
- `data/processed/national_parks.csv`;
- `data/processed/park_campground_distances.csv`; and
- deterministic cleaning, failure, matching, and distance reports under `reports/generated/`.

Run all tests with:

```powershell
pytest -q
```

National-park cleaning and distance generation are implemented. The MySQL loader, application queries, and Streamlit application are not implemented yet.

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
