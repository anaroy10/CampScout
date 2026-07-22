# Test plan

## Status

Executable profiling and CSV ETL tests are implemented. Database and application sections remain the verification plan for future phases. Tests use small fixtures and temporary output directories and never modify files under `data/raw/`.

## Test principles

- Add tests in the same change as implementation or business-rule changes.
- Keep unit tests deterministic and independent of network access.
- Use relative repository paths and temporary output locations.
- Never use real credentials in fixtures, logs, or assertions.
- Represent unknown source values explicitly and test them separately from negative values.
- Run the narrow relevant suite during development and the full suite before declaring a completed implementation task.

## Source-contract tests

Future ingestion tests should fail clearly when:

- an expected raw filename is missing;
- a required column is absent or unexpectedly renamed;
- a source file cannot be decoded or parsed as CSV;
- selected identifier columns are coerced to numeric types;
- an identifier gains a `.0` suffix or loses leading zeros;
- the selected candidate key is blank or duplicated;
- coordinate columns are missing, nonnumeric after controlled parsing, or outside valid ranges; or
- a previously assumed one-to-one source mapping is violated.

The current hashes in `DATA_SOURCES.md` may be used to verify that local scaffold work did not alter this snapshot. They should not be used to reject a deliberately obtained new source release without a documented source-update process.

## ETL unit tests

### National parks

- Parse representative northern, southern, eastern, and western coordinate values.
- Ignore scraped CSS and invisible characters in the location field without selecting unrelated numbers.
- Apply only approved park-name cleanup and derive identity from the cleaned name rather than row position.
- Leave ambiguous and out-of-range coordinates out of the distance matrix while recording parse failures.
- Parse visitor counts without presenting them as current-year metrics.

### Campgrounds

- Retain `site_id` values such as `01001` exactly.
- Demonstrate that duplicate `site_id` values do not collide in the canonical key.
- Include and exclude each profiled subtype according to the approved eligibility mapping.
- Distinguish parent facilities from camp-unit children according to documented hierarchy rules.
- Preserve original descriptions and identifiers.

### Amenities

- Map explicit positive, negative, blank, and ambiguous samples for fee, water, and restrooms.
- Assert that blank and unrecognized values become `UNKNOWN`, never `NO`.
- Keep the original water/restroom text next to normalized categories.
- Fail or report newly encountered values according to the mapping policy.

### Recreation Areas and activities

- Deduplicate repeated Recreation Area attributes by `RECAREAID` only after consistency assertions pass.
- Preserve multiple activity IDs that share the same name.
- Build one association for each distinct `(RECAREAID, ACTIVITYID)` pair.
- Exclude rows missing either association key from the bridge while reporting them.
- Never create direct campground-to-activity rows.

### Entity matching

- Accept deterministic campground-to-area links with exact, documented evidence.
- Report conflicts and unresolved records.
- Confirm fuzzy candidates remain unmerged.
- Confirm unlinked campgrounds are not assigned activities.

## Distance tests

- Return approximately zero for identical points.
- Check known coordinate pairs against an independent Haversine reference within a documented tolerance.
- Handle points across the antimeridian.
- Include a result exactly on the radius boundary according to the agreed comparison rule.
- Exclude invalid or missing coordinates rather than inventing coordinates.
- Confirm displayed units and labels say kilometers and approximate straight-line distance.

## Database tests

Use a temporary SQLite database file created under the test framework's temporary directory. Verify:

- database creation from all six processed CSVs succeeds without raw inputs;
- primary, unique, and foreign-key constraints match the documented logical model;
- required check constraints and indexes exist and are exercised;
- every connection enables `PRAGMA foreign_keys = ON`;
- repeated loads are idempotent or fail in the explicitly documented way;
- a load rolls back on failure rather than leaving a partial dataset;
- generated row counts and relationships match the processed inputs;
- unknown states survive round trips;
- Unicode and long source text survive round trips;
- all Python values are bound with SQLite `?` or named placeholders;
- application connections are read-only where practical;
- activity filters join through Recreation Areas;
- no campground-to-park foreign key exists; and
- radius, activity, fee, water, restroom, and type filters compose correctly.

## Application tests

- Park selection is required and populated from the database.
- Radius rejects zero, negative, nonnumeric, and unreasonable values according to the UI contract.
- Empty results produce a clear message rather than an error.
- Filter controls preserve the distinction between no filter and filtering for `UNKNOWN`.
- Result cards show only available, source-backed values.
- Details include distance, directions, activities, and an official URL when available.
- Unsupported ratings, reviews, hookups, vehicle advice, booking, and ML recommendations are absent.
- Database and configuration errors do not expose local system details or raw stack traces.

## Documentation and static checks

- Verify all documented commands and paths on Windows PowerShell when their components exist.
- Verify the default database path is `data/campscout.db`, the optional `CAMPSCOUT_DB_PATH` override works when implemented, and no environment variable is required.
- Verify raw CSVs and generated SQLite database/sidecar files are ignored while all six processed CSVs remain trackable.
- Search for hard-coded credentials and unsafe SQL interpolation.
- Update the specification, architecture, dictionary, decisions, and tests when schemas or business rules change.

## Execution levels

```powershell
# Fast unit tests for a component
pytest tests/<component>

# Full local suite
pytest
```

The first command should name a concrete test module, for example `pytest tests/test_clean_parks.py`.

## Release gate

A future release is acceptable only when the full suite passes in the supported Windows environment, data-quality reports contain no unexplained critical violations, the SQLite database builds and validates from a clean clone's six processed CSVs, and the documented end-to-end user flow has been manually smoke-tested.
