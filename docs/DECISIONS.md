# Decision log

This log captures durable project decisions. Proposed details that still need evidence are listed as open questions rather than silently treated as decisions.

## D-001 — Raw inputs are immutable

**Status:** Accepted

All files under `data/raw/` are read-only inputs. Cleaning and normalization write new artifacts to processed or reporting paths. This preserves provenance and makes transformation behavior reproducible.

## D-002 — Preserve identifiers as text

**Status:** Accepted

Raw identifiers are ingested as strings. This prevents leading-zero loss, float coercion, scientific notation, and accidental `.0` suffixes. The current site file contains values such as `01001` and dotted control numbers.

## D-003 — Select the campground primary key after profiling

**Status:** Profiled snapshot; final selection remains provisional

The formal profiler found that `site_cn`, `globalid`, and `objectid` are each complete and unique across all 32,114 current recreation-site rows. `site_id` is complete but has only 29,972 distinct values: 1,865 values are duplicated, producing 2,142 duplicate excess rows. It will not be used as the global primary key. The remaining choice among a source identifier and a surrogate key stays provisional because one-snapshot uniqueness does not prove cross-release stability.

## D-004 — Model activities at Recreation Area level

**Status:** Accepted

The activity source is organized by `RECAREAID` and `ACTIVITYID`. Activities belong to Recreation Areas, and the application reaches them through a validated campground-to-Recreation Area relationship. There is no direct campground-to-activity association.

The implemented area-activity bridge contains 51,713 unique `(RECAREAID, ACTIVITYID)` pairs. The source has 14,469 non-missing Recreation Area IDs, 79 non-missing activity IDs, no duplicate non-missing pairs in this snapshot, and 769 rows missing either association identifier. Missing-key rows do not form bridge records and are retained in a generated audit report.

## D-005 — Calculate park proximity

**Status:** Accepted

National parks and campgrounds are related by a great-circle distance calculation over validated coordinates. A campground does not store a park foreign key. The interface will label this value as approximate straight-line distance in kilometers.

## D-006 — Preserve unknown amenity states

**Status:** Accepted

Missing or ambiguous amenity data maps to `UNKNOWN`, not `NO`. Raw water and restroom descriptions are preserved next to any normalized filter category. This is necessary because both source fields are mostly missing and contain hundreds of distinct descriptions.

The current profile reports 20,414 missing `water_availability` values (63.567292%) and 20,345 missing `restroom_availability` values (63.352432%) among 32,114 site rows. Common non-missing values include multiple differently worded positive and negative descriptions, so this profiling phase does not define a normalization mapping.

## D-007 — Do not auto-merge fuzzy matches

**Status:** Accepted

Fuzzy matching may identify candidates for human review or reporting. It must not create entity links or merge records automatically. Deterministic matches require explainable source evidence and validation.

## D-008 — Treat legacy SQL as reference only

**Status:** Accepted

Legacy SQL is not a source of truth. The available `legacy/schema.sql` conflicts with current rules by using `site_id` as a primary key, relating campsites directly to parks and activities, and modeling unsupported features. It will not be migrated as-is.

The requested `legacy/partner_schema.sql` file was not present during scaffold creation.

## D-009 — Keep product scope narrow

**Status:** Accepted

The application supports park/radius discovery, Recreation Area activities, fee/water/restroom/type filters, and source-backed details. Ratings, reviews, electrical hookups, sewer hookups, vehicle-length recommendations, booking, and machine-learning recommendations are excluded even if a raw or legacy field suggests them.

## D-010 — Separate concerns by package

**Status:** Accepted

Future ETL belongs in `etl/`, MySQL access and loading in `db/` and `sql/`, UI code in `app/`, developer entry points in `scripts/`, and verification in `tests/`. Generated data and reports remain outside source packages.

## D-011 — Use environment configuration and parameterized SQL

**Status:** Accepted

Database configuration is supplied through the documented environment variables. Credentials are never hard-coded. All query values use MySQL connector parameters; any dynamic identifier must come from a fixed allow-list.

## D-012 — Target the documented Windows stack

**Status:** Accepted

The supported development environment is Windows, VS Code, Python, MySQL, and Streamlit. Documentation and future automation should provide PowerShell-compatible commands and use relative repository paths.

## D-013 — Canonicalize repeated Recreation Area and Activity values deterministically

**Status:** Accepted and implemented for the activity source

The activity cleaning phase preserves identifiers as text and uses literal source column names in its processed CSVs. For every attribute repeated under one `RECAREAID` or `ACTIVITYID`, blank values are ignored and the most frequent normalized non-blank value is selected. Ties are resolved by case-insensitive lexical order and then literal lexical order. All distinct non-blank disagreements, their frequencies, and the selected value are written to `reports/generated/activity_conflicts.csv`.

Whitespace and HTML entities are normalized. HTML markup is removed from Recreation Area descriptions and accessibility text while meaningful text boundaries are retained. Opening-season values remain free text. The cleaner validates that every bridge key exists in the corresponding entity output before writing its artifacts.

The current generated snapshot has no Recreation Area conflicts and 13 Activity conflicts, all in `PARENTACTIVITYID`. These values are preserved and reported as source facts; the cleaner does not infer or repair a hierarchy.

## Open questions requiring evidence

1. Which recreation-site records are actual campground entities rather than areas, units, or other facilities?
2. Is `site_cn` or `globalid` stable and unique across multiple source snapshots, or only within the current file?
3. Can `RECAREAID` be extracted deterministically from an authoritative campground URL, and how should conflicts be handled?
4. Should the campground-to-Recreation Area relationship be one-to-one, optional many-to-one, or represented by an audited bridge?
5. Which exact free-text values map to each supported water and restroom category?
6. Which source field has precedence for campground name, directions, and official URL?
7. Should distance be calculated in MySQL or in a Python service after a database bounding-box query?

Each answer must be based on profiling or an authoritative source definition, recorded here, reflected in the data dictionary, and covered by tests before implementation is declared complete.

Current profiling narrows but does not close questions 1, 2, and 5: exact counts exist for `CAMPGROUND` (4,198), `GROUP CAMPGROUND` (431), and `HORSE CAMP` (181); three source columns are unique in this snapshot; and raw water/restroom frequencies are recorded. Category eligibility, cross-release identifier stability, and reviewed amenity mappings remain unresolved.
