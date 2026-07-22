# Proposed data dictionary

## Status and conventions

This dictionary describes the implemented Recreation Area/activity processed CSVs and the intended model for later phases. It is not a deployed MySQL schema. Types and nullability for MySQL must be finalized before DDL is written.

The current snapshot was formally profiled with `python -m etl.profile_raw_data`. Generated column types, missingness, distinct counts, maximum text lengths, samples, and key checks are recorded under `reports/profiling/`; the facts below do not replace those generated reports.

Conventions:

- All raw identifiers enter the pipeline as strings and remain available without formatting changes.
- Key strategy is selected from profiling evidence; a surrogate key may be generated where source uniqueness or stability is unproven.
- `UNKNOWN` means the source is blank, missing, or too ambiguous to classify. It is distinct from `NO`.
- Columns ending in `_raw` preserve unnormalized source text.
- Latitude and longitude require range validation before a row participates in distance search.
- Activity-phase processed CSVs retain the literal uppercase source column names. Proposed future database field names may use snake case.

## `national_park`

The profiled file has 63 rows and 8 literal source columns. `Image` is empty in all 63 rows. Six `Name` values contain `*`; one of those names (`Wrangell–St. Elias *`) also contains unusual whitespace. No park name contains a bracketed citation in this snapshot. These are source observations only; no name cleanup has been implemented.

| Proposed field | Meaning | Source / rule |
|---|---|---|
| `park_id` | Internal surrogate primary key | Generated; never sourced from row position |
| `source_row_id` | Preserved unnamed source index | Unnamed first column; ingest as text |
| `name_raw` | Original park name including annotations | `Name` |
| `display_name` | User-facing park name | Deterministic cleanup with explicit tests |
| `state_or_territory` | Source-backed location label | Parsed cautiously from `Location` |
| `latitude` | Validated park latitude | Parsed from the coordinate portion of `Location` |
| `longitude` | Validated park longitude | Parsed from the coordinate portion of `Location` |
| `established_date` | Park establishment date | `Date established as park[7][12]` after strict parsing |
| `area_raw` | Original area text | `Area (2021)[13]` |
| `recreation_visitors_2021` | Visitor count labeled for 2021 | `Recreation visitors (2021)[11]` |
| `description` | Source description | `Description`; citation markers may require documented cleanup |

There is intentionally no campground foreign key on this entity.

## `campground`

The final campground primary key remains unselected. In the current 32,114-row snapshot, `site_cn`, `globalid`, and `objectid` are each complete and unique. `site_id` is complete but has 29,972 distinct values, 1,865 distinct duplicated values, and 2,142 duplicate excess rows; examples include the leading-zero value `01001`. Snapshot uniqueness does not establish stability across future source releases, so this profiler evidence does not by itself select the production key.

Literal `site_subtype` counts include 4,198 `CAMPGROUND`, 431 `GROUP CAMPGROUND`, and 181 `HORSE CAMP` records (4,810 combined). These counts do not define the campground eligibility rule.

| Proposed field | Meaning | Source / rule |
|---|---|---|
| `campground_id` | Optional internal surrogate key | Generated only if profiling selects the surrogate-key strategy |
| `site_cn_raw` | Preserved site control number | `site_cn`; string even when numeric-looking or dotted |
| `site_id_raw` | Preserved site ID | `site_id`; not a primary key in the inspected snapshot |
| `globalid_raw` | Preserved source global ID | `globalid` |
| `root_cn_raw` | Preserved hierarchy root | `root_cn` |
| `parent_cn_raw` | Preserved hierarchy parent | `parent_cn` |
| `name` | Selected campground display name | Deterministic preference among profiled name fields |
| `name_raw` | Original `site_name` | `site_name` |
| `public_name_raw` | Original public name | `public_site_name` |
| `campground_type` | Controlled filter/display type | Derived only from an approved `site_subtype` mapping |
| `site_subtype_raw` | Original subtype | `site_subtype` |
| `recreation_area_id` | Deterministically linked Recreation Area, when resolved | Exact validated link; never a fuzzy auto-match |
| `recreation_area_name_raw` | Source Recreation Area label | `recarea_name` and/or `parent_recarea`, kept for audit |
| `latitude` | Validated campground latitude | `latitude` |
| `longitude` | Validated campground longitude | `longitude` |
| `fee_status` | `YES`, `NO`, or `UNKNOWN` | Map explicit `Y`/`N`; blank or unexpected value is `UNKNOWN` |
| `fee_type_raw` | Original fee classification | `fee_type` |
| `fee_description` | Source fee details | `fee_description` |
| `water_status` | Controlled water category including `UNKNOWN` | Explicit, reviewed mapping from free text |
| `water_details_raw` | Original water description | `water_availability` |
| `restroom_type` | Controlled restroom category including `UNKNOWN` | Explicit, reviewed mapping from free text |
| `restroom_details_raw` | Original restroom description | `restroom_availability` |
| `directions` | User-facing source directions | Documented preference between `directions` and `site_directions` |
| `closest_towns_raw` | Original nearby-town text | `closest_towns` |
| `official_url` | Selected official informational URL | Deterministic allow-listed preference from source URL fields |
| `usda_portal_url_raw` | Original USDA URL | `usda_portal_url` |
| `recreation_gov_url_raw` | Original Recreation.gov URL | `rec1stop_url` |

There is intentionally no `park_id` column. Unsupported hookup, rating, booking, and vehicle-recommendation fields are not part of this product model.

Selected raw missingness in the current snapshot is: 0 of 32,114 for both `latitude` and `longitude`; 245 for `fee_charged`; 20,414 for `water_availability`; 20,345 for `restroom_availability`; 20,970 for `directions`; 21,765 for `usda_portal_url`; and 7 for `total_capacity`. Missing amenity values remain unknown, and no normalization mapping has been applied.

## `recreation_area`

Implemented artifact: `data/processed/recreation_areas.csv`. It contains one row per non-blank `RECAREAID`, sorted by the preserved text identifier. `OBJECTID` is excluded because it identifies source rows rather than Recreation Areas. Repeated non-blank values are resolved by frequency, with a case-insensitive lexical tie-break followed by the literal value; every disagreement is written to `reports/generated/activity_conflicts.csv`.

| Processed field | Meaning | Source / rule |
|---|---|---|
| `RECAREAID` | Preserved source identifier and CSV key | Ingested as text; blank IDs do not create entity rows |
| `X`, `Y` | Source map coordinates | Whitespace-normalized source text; no numeric coercion in this phase |
| `RECAREANAME` | Recreation Area name | Whitespace and HTML entities normalized |
| `LONGITUDE`, `LATITUDE` | Source Recreation Area coordinates | Preserved as normalized text; range validation remains required before distance use |
| `RECAREAURL` | Source Recreation Area URL | Whitespace and HTML entities normalized |
| `OPEN_SEASON_START`, `OPEN_SEASON_END` | Source opening-season descriptions | Preserved as free text; not coerced to dates |
| `FORESTNAME` | Managing forest label | Whitespace and HTML entities normalized |
| `MARKERTYPE`, `MARKERACTIVITY`, `MARKERACTIVITYGROUP` | Source marker metadata | Preserved as normalized text |
| `RECAREADESCRIPTION` | Recreation Area description | HTML removed, entities decoded, whitespace normalized |
| `SPOTLIGHTDISPLAY`, `ATTRACTIONDISPLAY` | Source display flags | Preserved source values; no boolean inference in this phase |
| `ACCESSIBILITY` | Source accessibility description | HTML removed, entities decoded, whitespace normalized |
| `OPENSTATUS` | Original operational status | Preserved normalized text; `unknown` or `none` is not converted to `closed` |
| `SHAPE` | Source shape value | Preserved when present; blank remains blank |

The generated snapshot has 14,469 Recreation Area rows and no Recreation Area attribute conflicts after normalization.

## `activity`

Implemented artifact: `data/processed/activities.csv`. It contains one row per non-blank `ACTIVITYID`, sorted by the preserved text identifier. The same deterministic frequency rule used for Recreation Areas resolves repeated attributes.

| Processed field | Meaning | Source / rule |
|---|---|---|
| `ACTIVITYID` | Preserved source activity ID and CSV key | Ingested as text; blank IDs do not create entity rows |
| `ACTIVITYNAME` | Activity name | Normalized text; not a unique identifier |
| `PARENTACTIVITYID` | Preserved parent ID | Ingested as text; blank values are ignored during canonical selection |
| `PARENTACTIVITYNAME` | Preserved parent name | Normalized text; blank values are ignored during canonical selection |

The generated snapshot contains 79 activity rows. It retains separate IDs for non-unique names: `Picnicking` maps to IDs `69` and `70`, while `Scenic Driving` maps to IDs `75` and `105`. Code must join by ID, not name. Thirteen source conflicts in non-blank parent IDs are reported rather than hidden.

## `recreation_area_activity`

Implemented artifact: `data/processed/recreation_area_activities.csv`.

| Processed field | Meaning | Source / rule |
|---|---|---|
| `RECAREAID` | Associated Recreation Area | Foreign key to `recreation_areas.csv.RECAREAID` |
| `ACTIVITYID` | Associated activity | Foreign key to `activities.csv.ACTIVITYID` |

The composite CSV key is `(RECAREAID, ACTIVITYID)`. Duplicate source pairs are removed. The generated snapshot contains 51,713 relationships and no duplicate source pairs. Its 769 rows missing either required identifier are excluded from the relationship and preserved in `reports/generated/dropped_activity_rows.csv`. Foreign-key consistency is validated before any artifact is published. No campground identifier belongs in this table.

## Derived query value: `distance_km`

`distance_km` is not a foreign key or source attribute. It is the approximate great-circle distance calculated from the selected park coordinates and each campground's coordinates. The formula, Earth-radius constant, precision, and boundary behavior must be documented and unit tested. Results at or below the requested radius are eligible.

## Filter semantics

| Filter | Required behavior |
|---|---|
| Activity | Join campground to its resolved Recreation Area, then to `recreation_area_activity` and `activity` |
| Fee | Filter on `YES`, `NO`, or `UNKNOWN`; never map missing fee data to `NO` |
| Water | Use a reviewed category plus the raw description; missing is `UNKNOWN` |
| Restroom | Use a reviewed type plus the raw description; missing is `UNKNOWN` |
| Campground type | Use only approved categories derived from `site_subtype` profiling |
| Radius | Compare a calculated `distance_km` to the positive user-supplied radius |

## Unresolved dictionary items

- The authoritative campground eligibility rule and source hierarchy behavior.
- The stable campground key across future source snapshots.
- The exact deterministic link from a campground to `RECAREAID`.
- Controlled category mappings for water, restrooms, and campground type.
- Name, directions, and official-URL preference rules.
- Final SQL types, maximum lengths, indexes, and nullability.

These are profiling or design tasks, not gaps to fill by assumption.
