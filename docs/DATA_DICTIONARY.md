# Proposed data dictionary

## Status and conventions

This dictionary describes the intended canonical model. It is not a deployed MySQL schema. Types and nullability must be finalized through ETL profiling before DDL is written.

Conventions:

- All raw identifiers enter the pipeline as strings and remain available without formatting changes.
- Key strategy is selected from profiling evidence; a surrogate key may be generated where source uniqueness or stability is unproven.
- `UNKNOWN` means the source is blank, missing, or too ambiguous to classify. It is distinct from `NO`.
- Columns ending in `_raw` preserve unnormalized source text.
- Latitude and longitude require range validation before a row participates in distance search.

## `national_park`

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

The final campground primary key will be selected after profiling. site_id will not be used as the global primary key because it is duplicated. A unique source identifier such as site_cn or globalid, or a surrogate key, will be selected based on profiling evidence.

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

## `recreation_area`

| Proposed field | Meaning | Source / rule |
|---|---|---|
| `recreation_area_id` | Preserved source identifier and candidate primary key | `RECAREAID`, ingested as text |
| `name` | Recreation Area name | `RECAREANAME` |
| `forest_name` | Managing forest label | `FORESTNAME` |
| `official_url` | Source Recreation Area URL | `RECAREAURL` |
| `latitude` | Recreation Area latitude | `LATITUDE`, range validated |
| `longitude` | Recreation Area longitude | `LONGITUDE`, range validated |
| `open_status_raw` | Original operational status | `OPENSTATUS`; do not collapse `unknown` or `none` into `closed` |

The activity source repeats these values. Future ETL must assert that every ID still maps consistently before deduplicating it into this entity.

## `activity`

| Proposed field | Meaning | Source / rule |
|---|---|---|
| `activity_id` | Preserved source activity ID | `ACTIVITYID`, ingested as text |
| `name` | Activity name | `ACTIVITYNAME`; not unique in the current source |
| `parent_activity_id_raw` | Preserved parent ID | `PARENTACTIVITYID` |
| `parent_activity_name_raw` | Preserved parent name | `PARENTACTIVITYNAME` |

The current snapshot shows that one activity ID maps to one name, but some names map to multiple IDs. Code must join by ID, not name.

## `recreation_area_activity`

| Proposed field | Meaning | Source / rule |
|---|---|---|
| `recreation_area_id` | Associated Recreation Area | `RECAREAID`; foreign key to `recreation_area` |
| `activity_id` | Associated activity | `ACTIVITYID`; foreign key to `activity` |

The proposed composite primary key is `(recreation_area_id, activity_id)`. Rows lacking either member cannot populate this association. No `campground_id` belongs in this table.

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
