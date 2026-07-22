# CampScout project specification

## Purpose

CampScout will help a user discover United States Forest Service campgrounds near a selected United States national park. It is a location-based discovery tool, not a reservation system or a recommendation engine.

## Target user flow

1. Select a United States national park.
2. Select a search radius in kilometers.
3. Calculate which eligible Forest Service campgrounds fall within that radius.
4. Optionally filter results by activities available in the campground's Recreation Area.
5. Optionally filter by fee status, water availability, restroom type, and campground type.
6. Review approximate straight-line distance and campground information.

## Result information

Each result should expose available source-backed values for:

- campground name and type;
- approximate straight-line distance in kilometers;
- fee status or description;
- water availability;
- restroom type or description;
- directions;
- activities belonging to the associated Recreation Area; and
- an official Forest Service or other official source URL.

Missing fields must be displayed as unknown or unavailable. They must not be silently converted to a negative answer.

## Functional requirements

### Park and radius

- Present the supported national parks from the processed park dataset.
- Require a valid park and a positive radius.
- Use parsed and validated park coordinates.
- Label distance as approximate straight-line distance, not road or travel distance.

### Campground discovery

- Include only source records that meet a documented campground eligibility rule.
- Calculate proximity from park and campground coordinates.
- Do not store a national-park foreign key on a campground.
- Apply all user-provided values through parameterized SQL.

### Filters

- Activity filters operate through the campground's Recreation Area and the Recreation Area-to-Activity relationship.
- Amenity filters preserve a three-way distinction when supported: positive, negative, and `UNKNOWN`.
- Campground type values derive from profiled source categories; unsupported categories must not be invented.
- A missing filter value means no restriction, not a request for missing records.

### Result quality

- Preserve source identifiers as text during ingestion.
- Preserve source descriptions alongside normalized filter fields when practical.
- Do not automatically resolve fuzzy duplicate candidates.
- Prefer deterministic, auditable links between campgrounds and Recreation Areas.

## Non-functional requirements

- Target Windows, VS Code, Python, SQLite, and Streamlit.
- Keep raw inputs immutable and transformations reproducible.
- Default the database to the repository-relative path `data/campscout.db`, with an optional future `CAMPSCOUT_DB_PATH` override.
- Require no database credentials or server configuration.
- Use only relative repository paths.
- Enable SQLite foreign-key enforcement on every connection and preserve database constraints rather than relying only on application validation.
- Use SQLite parameter placeholders for all values passed from Python, and prefer read-only application connections where practical.
- Document schema and business-rule changes in the same change that introduces them.
- Add and run tests appropriate to each implemented component.

## Explicitly unsupported features

CampScout does not provide or infer:

- user ratings;
- reviews;
- electrical hookups;
- sewer hookups;
- vehicle-length recommendations;
- booking functionality; or
- machine-learning recommendations.

Source columns related to unsupported features may be retained in immutable raw files, but they are not application features and should not be promoted into the product without a specification change.

## Acceptance criteria for a future first release

- A user can select a park and positive kilometer radius.
- Every returned campground has validated coordinates within the requested straight-line radius.
- Every displayed activity is reached through a Recreation Area relationship.
- Fee, water, and restroom filters retain `UNKNOWN` rather than treating it as `NO`.
- Result details include distance, available directions, activities, and an official URL.
- No unsupported feature appears in the interface or schema solely because a raw or legacy column exists.
- ETL, database access, and user-flow tests pass in the documented Windows setup.

## Current phase

Raw profiling, the complete deterministic CSV ETL, the SQLite schema, builder, connection factory and validator, and the read-only data-access queries are implemented. The Streamlit interface remains a future phase.
