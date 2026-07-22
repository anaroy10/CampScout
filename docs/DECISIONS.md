# Decision log

This log captures durable project decisions. Proposed details that still need evidence are listed as open questions rather than silently treated as decisions.

## D-001 — Raw inputs are immutable

**Status:** Accepted

All files under `data/raw/` are read-only inputs. Cleaning and normalization write new artifacts to processed or reporting paths. This preserves provenance and makes transformation behavior reproducible.

## D-002 — Preserve identifiers as text

**Status:** Accepted

Raw identifiers are ingested as strings. This prevents leading-zero loss, float coercion, scientific notation, and accidental `.0` suffixes. The current site file contains values such as `01001` and dotted control numbers.

## D-003 — Select the campground primary key after profiling

**Status:** Provisional pending formal profiling

The final campground primary key will be selected after profiling. site_id will not be used as the global primary key because it is duplicated. A unique source identifier such as site_cn or globalid, or a surrogate key, will be selected based on profiling evidence.

## D-004 — Model activities at Recreation Area level

**Status:** Accepted

The activity source is organized by `RECAREAID` and `ACTIVITYID`. Activities belong to Recreation Areas, and the application reaches them through a validated campground-to-Recreation Area relationship. There is no direct campground-to-activity association.

## D-005 — Calculate park proximity

**Status:** Accepted

National parks and campgrounds are related by a great-circle distance calculation over validated coordinates. A campground does not store a park foreign key. The interface will label this value as approximate straight-line distance in kilometers.

## D-006 — Preserve unknown amenity states

**Status:** Accepted

Missing or ambiguous amenity data maps to `UNKNOWN`, not `NO`. Raw water and restroom descriptions are preserved next to any normalized filter category. This is necessary because both source fields are mostly missing and contain hundreds of distinct descriptions.

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

## Open questions requiring evidence

1. Which recreation-site records are actual campground entities rather than areas, units, or other facilities?
2. Is `site_cn` or `globalid` stable and unique across multiple source snapshots, or only within the current file?
3. Can `RECAREAID` be extracted deterministically from an authoritative campground URL, and how should conflicts be handled?
4. Should the campground-to-Recreation Area relationship be one-to-one, optional many-to-one, or represented by an audited bridge?
5. Which exact free-text values map to each supported water and restroom category?
6. Which source field has precedence for campground name, directions, and official URL?
7. Should distance be calculated in MySQL or in a Python service after a database bounding-box query?

Each answer must be based on profiling or an authoritative source definition, recorded here, reflected in the data dictionary, and covered by tests before implementation is declared complete.
