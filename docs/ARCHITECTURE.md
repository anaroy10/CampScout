# Architecture

## Status

The profiling and CSV ETL layers are implemented. MySQL and Streamlit remain design targets; their table names, queries, and application entry points are proposals until those phases are completed.

## Component boundaries

```text
data/raw/*.csv (immutable)
        |
        v
etl/  profile -> validate -> normalize -> publish
        |
        v
data/processed/  reproducible artifacts and quality reports
        |
        v
db/ + sql/  MySQL schema, loader, and parameterized read queries
        |
        v
app/  Streamlit controls, result list, and campground details

tests/ verifies transformation rules, database behavior, and user flows
reports/ stores profiling and generated report outputs
scripts/ contains future developer entry points
report/ contains future project-report source material
```

Executable profiling and ETL modules are present under `etl/`. No MySQL loader, application SQL query layer, or Streamlit page is present yet.

## Planned data flow

1. Read all raw identifiers as strings so values such as `01001` and dotted identifiers are preserved exactly.
2. Profile source grain, missingness, categorical values, coordinates, duplicates, and possible relationships.
3. Validate required fields and quarantine or report invalid records without changing raw files.
4. Normalize only with explicit, tested mappings. Keep raw descriptive values when normalization could lose information.
5. Write deterministic processed artifacts under `data/processed/` and profiling output under `reports/profiling/`.
6. Load the normalized entities into MySQL using transactions and parameterized statements.
7. Query MySQL through a small data-access layer; the Streamlit layer should not construct SQL from string interpolation.

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

Campgrounds link to a Recreation Area only when a `recid` extracted from the USDA portal URL exactly matches a processed `RECAREAID`. Name-only or fuzzy matches are never used to create links. Unresolved campgrounds remain unlinked and cannot receive invented activities. The future MySQL representation remains an open schema decision.

## Geographic relationship

National parks and campgrounds relate only through calculated geographic distance:

```text
park(latitude, longitude) -- Haversine calculation --> campground(latitude, longitude)
```

The implemented CSV phase calculates the complete valid cross product with the Haversine formula and the 6,371.0088 km IUGG mean Earth radius. It sorts deterministically, retains full calculation precision, rounds only the exported value to six decimals, and validates cardinality. The result is approximate straight-line distance from the park's representative coordinate, not road or entrance distance. A future MySQL query may use a bounding box for performance, but final inclusion must still use an equivalent distance formula.

## Missing-value model

Raw blanks remain missing. Normalized filter fields should support `YES`, `NO`, and `UNKNOWN` where a binary-looking source attribute is required. Free-text water and restroom descriptions should be preserved alongside any controlled category. A blank or ambiguous phrase must never become `NO` merely to simplify filtering.

## Configuration and security

- Load `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, and `DB_PASSWORD` from the environment.
- Keep local secrets in `.env`, which is excluded from Git.
- Validate configuration at startup without logging passwords.
- Use parameter placeholders supported by `mysql-connector-python` for values.
- Allow-list identifiers such as sort columns; identifiers cannot be protected by value placeholders.

## Failure handling and observability

Future ETL should fail clearly on schema drift, invalid required coordinates, duplicate selected keys, or broken relationship assumptions. Expected data-quality exceptions should be counted and written to profiling reports. Database loads should be transactional and idempotent by design. User-facing failures should be actionable without exposing credentials or raw stack traces.
