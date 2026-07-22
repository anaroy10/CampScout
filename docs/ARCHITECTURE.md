# Architecture

## Status

The profiling and CSV ETL layers are implemented. SQLite and Streamlit remain design targets; their table names, queries, and application entry points are proposals until those phases are completed. No database schema, database builder, query layer, or Streamlit page has been implemented.

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
db/ + sql/  future SQLite schema, builder, and validation
        |
        v
data/campscout.db  generated SQLite database (not committed)
        |
        v
db/  future parameterized, read-only-where-practical query layer
        |
        v
app/  Streamlit controls, result list, and campground details

tests/ verifies transformation rules, database behavior, and user flows
reports/ stores profiling and generated report outputs
scripts/ contains future developer entry points
report/ contains future project-report source material
```

Executable profiling and ETL modules are present under `etl/`. No SQLite schema, database builder, application SQL query layer, or Streamlit page is present yet.

## Planned data flow

1. Read all raw identifiers as strings so values such as `01001` and dotted identifiers are preserved exactly.
2. Profile source grain, missingness, categorical values, coordinates, duplicates, and possible relationships.
3. Validate required fields and quarantine or report invalid records without changing raw files.
4. Normalize only with explicit, tested mappings. Keep raw descriptive values when normalization could lose information.
5. Write deterministic processed artifacts under `data/processed/` and profiling output under `reports/profiling/`.
6. Build `data/campscout.db` from all six processed CSVs using transactions, database constraints, and parameterized statements.
7. Validate database row counts, keys, foreign keys, integrity constraints, and required indexes before accepting the generated database.
8. Query SQLite through a small data-access layer; the Streamlit layer should not construct SQL from string interpolation.

The six processed CSVs are committed so a clean clone can reproduce the future database-build workflow without possessing the raw source files. Raw CSVs remain excluded from Git, and running the complete ETL still requires obtaining the original sources. Processed CSVs are published only by the ETL pipeline.

## Proposed logical model

### National Park

A processed park has a deterministic UUIDv5 key, cleaned name, source-backed state/location label, parsed source attributes, and validated latitude/longitude from the raw location field. It has no campground foreign key. Parse failures are audited rather than filled with invented values.

### Campground

The processed campground key is the complete and unique source `globalid`; duplicated `site_id` remains an audit attribute. Eligibility is an exact normalized match on `CAMPGROUND`, `GROUP CAMPGROUND`, or `HORSE CAMP`. The cleaner validates the key, categories, required coordinates, and output count on every run.

### Recreation Area

A Recreation Area is keyed from the activity source's preserved `RECAREAID` and carries its name, URL, coordinates, forest name, and status where available. The current activity snapshot is internally consistent at this key: each observed ID maps to one name, URL, and coordinate pair.

### Activity

An Activity preserves `ACTIVITYID`, name, and optional parent activity. Activity identifiers remain text at ingestion. The source currently contains two names associated with multiple IDs, so names are not keys.

### Recreation Area Activity

This associative entity records which activities belong to a Recreation Area. Its proposed key is `(recreation_area_id, activity_id)`. Activities are never attached directly to campgrounds.

### Campground Recreation Area relationship

Campgrounds link to a Recreation Area only when a `recid` extracted from the USDA portal URL exactly matches a processed `RECAREAID`. Name-only or fuzzy matches are never used to create links. Unresolved campgrounds remain unlinked and cannot receive invented activities. The future SQLite representation remains an open schema decision.

## Geographic relationship

National parks and campgrounds relate only through calculated geographic distance:

```text
park(latitude, longitude) -- Haversine calculation --> campground(latitude, longitude)
```

The implemented CSV phase calculates the complete valid cross product with the Haversine formula and the 6,371.0088 km IUGG mean Earth radius. It sorts deterministically, retains full calculation precision, rounds only the exported value to six decimals, and validates cardinality. The result is approximate straight-line distance from the park's representative coordinate, not road or entrance distance. A future SQLite query may use indexed coordinates or precomputed distances for performance, but final inclusion must retain the documented distance semantics.

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

Future ETL should fail clearly on schema drift, invalid required coordinates, duplicate selected keys, or broken relationship assumptions. Expected data-quality exceptions should be counted and written to profiling reports. The future SQLite database build should be transactional, deterministic, and idempotent by design. User-facing failures should be actionable without exposing local system details or raw stack traces.
