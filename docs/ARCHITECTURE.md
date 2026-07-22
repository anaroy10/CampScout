# Architecture

## Status

The profiling, CSV ETL, and SQLite database layers are implemented. The application query layer and Streamlit page remain future phases.

## Component boundaries

```text
data/raw/*.csv (immutable)
        |
        v
etl/  profile -> validate -> normalize -> publish
        |
        v
data/processed/  six committed, reproducible CSV artifacts
        |
        v
db/ + sql/  implemented SQLite schema, builder, connection, and validation
        |
        v
data/campscout.db  generated SQLite database (not committed)
        |
        v
db/  future parameterized application query layer
        |
        v
app/  Streamlit controls, result list, and campground details

tests/ verifies transformation rules, database behavior, and user flows
reports/ stores profiling and generated report outputs
scripts/ contains future developer entry points
report/ contains future project-report source material
```

Executable profiling and ETL modules are present under `etl/`. The SQLite schema and commands are present under `sql/` and `db/`. No application SQL query layer or Streamlit page is present yet.

## Data flow

1. Read all raw identifiers as strings so values such as `01001` and dotted identifiers are preserved exactly.
2. Profile source grain, missingness, categorical values, coordinates, duplicates, and possible relationships.
3. Validate required fields and quarantine or report invalid records without changing raw files.
4. Normalize only with explicit, tested mappings. Keep raw descriptive values when normalization could lose information.
5. Write deterministic processed artifacts under `data/processed/` and profiling output under `reports/profiling/`.
6. Build `data/campscout.db` from all six processed CSVs using one explicit transaction, database constraints, and parameterized statements.
7. Validate database row counts, keys, foreign keys, controlled vocabularies, matrix cardinality, integrity constraints, and required indexes before accepting the generated database.
8. Query SQLite through a small data-access layer; the Streamlit layer should not construct SQL from string interpolation.

The six processed CSVs are committed so a clean clone can reproduce the future database-build workflow without possessing the raw source files. Raw CSVs remain excluded from Git, and running the complete ETL still requires obtaining the original sources. Processed CSVs are published only by the ETL pipeline.

## Implemented logical model

### National Park

A processed park has a deterministic UUIDv5 primary key, cleaned name, source-backed state/location label, parsed source attributes, and checked REAL latitude/longitude values. It has no campground foreign key. Parse failures are audited rather than filled with invented values.

### Campground

The processed campground key is the complete and unique source `globalid`; duplicated `site_id` remains an unconstrained audit attribute. The database uses `campground_id` as the primary key, preserves `globalid` with a supported unique constraint, checks the approved campground and amenity categories, and enforces the nullable Recreation Area foreign key.

### Recreation Area

A Recreation Area is keyed from the activity source's preserved `RECAREAID`. Processed `X`/`Y` are loaded as nullable REAL longitude/latitude with geographic range checks. The unvalidated source `LONGITUDE`/`LATITUDE` fields are retained separately as TEXT because the current source contains swapped and projected values; the database does not invent corrections.

### Activity

An Activity preserves `ACTIVITYID`, name, and optional parent activity. Activity identifiers remain text at ingestion. The source currently contains two names associated with multiple IDs, so names are not keys.

### Recreation Area Activity

This associative entity records which activities belong to a Recreation Area. Its proposed key is `(recreation_area_id, activity_id)`. Activities are never attached directly to campgrounds.

### Campground Recreation Area relationship

Campgrounds link to a Recreation Area only when a `recid` extracted from the USDA portal URL exactly matches a processed `RECAREAID`. Name-only or fuzzy matches are never used to create links. The SQLite representation is the nullable `campgrounds.recarea_id` foreign key. Unresolved campgrounds remain present with SQL NULL and cannot receive invented activities.

## Geographic relationship

National parks and campgrounds relate only through calculated geographic distance:

```text
park(latitude, longitude) -- Haversine calculation --> campground(latitude, longitude)
```

The implemented CSV phase calculates the complete valid cross product with the Haversine formula and the 6,371.0088 km IUGG mean Earth radius. It sorts deterministically, retains full calculation precision, rounds only the exported value to six decimals, and validates cardinality. The result is approximate straight-line distance from the park's representative coordinate, not road or entrance distance. The database loads this matrix into `park_campground_distances`, keyed by `(park_id, campground_id)`, with both foreign keys, a non-negative distance check, and a future park/radius index.

## Missing-value model

Raw blanks remain missing. Normalized filter fields should support `YES`, `NO`, and `UNKNOWN` where a binary-looking source attribute is required. Free-text water and restroom descriptions should be preserved alongside any controlled category. A blank or ambiguous phrase must never become `NO` merely to simplify filtering.

## SQLite configuration and connection policy

- Default to the repository-relative path `data/campscout.db`.
- Allow a future optional `CAMPSCOUT_DB_PATH` environment variable to override the default; the project must work without it.
- Require no database server, database account, password, host, or port.
- Enable foreign-key enforcement on every connection with `PRAGMA foreign_keys = ON` before database work.
- Use SQLite `?` or named placeholders for values supplied from Python. Allow-list identifiers such as sort columns because identifiers cannot be protected by value placeholders.
- Open application connections read-only where practical. Database creation, migration, and loading connections are necessarily writable.
- Define primary keys, foreign keys, uniqueness, checks, and other integrity rules in the database; application validation complements rather than replaces them.
- Keep `data/campscout.db` and SQLite journal, WAL, and shared-memory sidecar files out of Git.

## Failure handling and observability

ETL fails clearly on schema drift, invalid required coordinates, duplicate selected keys, or broken relationship assumptions. The database builder similarly rejects header drift, duplicates, broken foreign keys, check violations, and row-count mismatches. It rolls back and removes a newly created partial database on failure. Rebuilding an existing default database requires the narrowly guarded `--reset` option.
