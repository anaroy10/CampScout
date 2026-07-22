# Planned architecture

## Status

This is a design target, not an implemented system. Table names, column names, and entry points remain proposals until ETL profiling and schema work are completed.

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

No executable ETL, loader, SQL query, or Streamlit page is present yet.

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

A park has a surrogate key, cleaned display name, source attributes, and validated latitude/longitude parsed from the raw location field. It has no campground foreign key.

### Campground

The final campground primary key will be selected after profiling. site_id will not be used as the global primary key because it is duplicated. A unique source identifier such as site_cn or globalid, or a surrogate key, will be selected based on profiling evidence.

The exact eligible `site_subtype` set is deliberately unresolved. Values such as `CAMPGROUND`, `GROUP CAMPGROUND`, `CAMPING AREA`, `HORSE CAMP`, and unit-level types occur in the source, and substring matching alone would mix facilities with child units. A documented eligibility rule must precede ETL implementation.

### Recreation Area

A Recreation Area is keyed from the activity source's preserved `RECAREAID` and carries its name, URL, coordinates, forest name, and status where available. The current activity snapshot is internally consistent at this key: each observed ID maps to one name, URL, and coordinate pair.

### Activity

An Activity preserves `ACTIVITYID`, name, and optional parent activity. Activity identifiers remain text at ingestion. The source currently contains two names associated with multiple IDs, so names are not keys.

### Recreation Area Activity

This associative entity records which activities belong to a Recreation Area. Its proposed key is `(recreation_area_id, activity_id)`. Activities are never attached directly to campgrounds.

### Campground Recreation Area relationship

Campgrounds need a deterministic link to a Recreation Area before activity filtering is valid. The site source provides names and URLs but not an immediately documented `RECAREAID` field. Future profiling may derive an exact ID from an authoritative URL or another stable source attribute, then validate it against the activity dataset.

Name-only or fuzzy matches may be emitted as review candidates, but they must not be merged automatically. Unresolved campgrounds remain unlinked and must not be assigned invented activities. The final cardinality and physical representation (nullable foreign key versus an audited bridge) remain an open schema decision.

## Geographic relationship

National parks and campgrounds relate only through calculated geographic distance:

```text
park(latitude, longitude) -- Haversine calculation --> campground(latitude, longitude)
```

The first implementation should use a documented Earth radius and return kilometers. It may calculate Haversine distance in a parameterized MySQL query or in a tested application service. A latitude/longitude bounding box can reduce candidates, but the final inclusion decision must use the distance formula. The UI must describe the result as approximate straight-line distance.

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
