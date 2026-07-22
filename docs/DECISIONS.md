# Decision log

This log captures durable project decisions. Proposed details that still need evidence are listed as open questions rather than silently treated as decisions.

## D-001 — Raw inputs are immutable

**Status:** Accepted

All files under `data/raw/` are read-only inputs. Cleaning and normalization write new artifacts to processed or reporting paths. This preserves provenance and makes transformation behavior reproducible.

## D-002 — Preserve identifiers as text

**Status:** Accepted

Raw identifiers are ingested as strings. This prevents leading-zero loss, float coercion, scientific notation, and accidental `.0` suffixes. The current site file contains values such as `01001` and dotted control numbers.

## D-003 — Use `globalid` as the campground CSV key

**Status:** Accepted and implemented for the current source contract

The formal profiler found that `site_cn`, `globalid`, and `objectid` are each complete and unique across all 32,114 current recreation-site rows. `globalid` is selected as `campground_id` because it is a complete, unique, UUID-like source identifier. The campground cleaner revalidates non-nullness and uniqueness on every run and fails clearly if the contract changes. Cross-release stability remains an item to monitor.

`site_id` is complete but has only 29,972 distinct values: 1,865 values are duplicated, producing 2,142 duplicate excess rows. It is preserved as text but is not the primary key. `site_cn`, `site_id`, `objectid`, `root_cn`, and `parent_cn` are never numerically coerced; source formatting such as leading zeroes and dotted control numbers is retained.

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

## D-014 — Define the campground entity subset and display name

**Status:** Accepted and implemented

Campground eligibility is an exact match after trimming, collapsing whitespace, and uppercasing `site_subtype`. Only `CAMPGROUND`, `GROUP CAMPGROUND`, and `HORSE CAMP` are retained. They represent explicit campground entities with useful structured information; they are not described as better rated, better reviewed, or higher quality. Unsupported source rows are audited separately from rows with invalid required campground data.

The display name is the first non-blank value in this fixed order: `public_site_name`, `site_name`, then `recarea_name`. Whitespace-only values count as missing. All three source name fields remain in the processed record for audit.

## D-015 — Normalize campground water, restrooms, fees, and capacity conservatively

**Status:** Accepted and implemented

Raw water and restroom text is retained next to a controlled category. Negative phrases are evaluated before positive phrases. Water categories are `AVAILABLE`, `NOT_AVAILABLE`, `NATURAL_SOURCE`, `NEARBY`, `OTHER`, and `UNKNOWN`. Restroom categories are `FLUSH`, `VAULT`, `COMPOSTING`, `PORTABLE`, `MULTIPLE`, `NONE`, `OTHER`, and `UNKNOWN`. Specific phrase rules are documented in `docs/DATA_DICTIONARY.md` and covered by representative positive, negative, missing, multiple-type, natural-source, nearby, and ambiguous tests. Blank or ambiguous amenity values remain `UNKNOWN`, never an inferred negative.

Only exact `Y` and `N` fee flags become `YES` and `NO`; all other values become `UNKNOWN`. Total capacity is parsed only from a plain non-negative integer or decimal representation. Raw fee and capacity fields remain alongside normalized values.

## D-016 — Link campgrounds only through validated USDA URL `recid` values

**Status:** Accepted and implemented

The campground cleaner extracts the first non-blank case-insensitive `recid` query parameter only from `usda_portal_url`. It assigns `recarea_id` only when that exact text identifier exists in `data/processed/recreation_areas.csv`. A missing URL, URL without `recid`, or extracted identifier absent from the processed Recreation Areas leaves `recarea_id` blank. These campgrounds remain in `data/processed/campgrounds.csv` and are listed with evidence and a reason in `reports/generated/unmatched_campgrounds.csv`. Names are never used to infer or repair a link.

## D-017 — Report possible campground duplicates without merging

**Status:** Accepted and implemented

A possible duplicate pair must have the same normalized display name and coordinates no more than 1 km apart by the Haversine formula with a 6,371.0088 km mean Earth radius. Name normalization uppercases and replaces punctuation/whitespace runs with a single space. Every candidate report row contains both source identifiers, both names, both coordinate pairs, and calculated distance. The threshold is a review heuristic, not evidence sufficient to merge records, so the cleaner never merges candidates.

## Open questions requiring evidence

1. Is `globalid` stable and unique across multiple source snapshots, or only within the current file?
2. Should the optional many-campgrounds-to-one-Recreation-Area link remain a nullable field when the MySQL schema is designed, or be represented by an audited relationship table?
3. Which reported duplicate candidates represent distinct facilities, and which represent source duplicates?
4. Should park-to-campground distance be calculated in MySQL or in a Python service after a database bounding-box query?

Each answer must be based on profiling or an authoritative source definition, recorded here, reflected in the data dictionary, and covered by tests before implementation is declared complete.

The current cleaner resolves campground eligibility, current-snapshot key selection, URL-based Recreation Area validation, amenity mappings, display-name precedence, and the official URL rule. It does not claim cross-release key stability, adjudicate duplicate candidates, design the future database representation, or implement park-distance queries.
