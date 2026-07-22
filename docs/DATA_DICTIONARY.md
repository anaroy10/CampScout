# Data dictionary

## Status and conventions

This dictionary describes the implemented Recreation Area/activity, campground, national-park, and park-distance processed CSVs. It is not a deployed MySQL schema. Types and nullability for MySQL must be finalized before DDL is written.

The current snapshot was formally profiled with `python -m etl.profile_raw_data`. Generated column types, missingness, distinct counts, maximum text lengths, samples, and key checks are recorded under `reports/profiling/`; the facts below do not replace those generated reports.

Conventions:

- All raw identifiers enter the pipeline as strings and remain available without formatting changes.
- Key strategy is selected from profiling evidence; a surrogate key may be generated where source uniqueness or stability is unproven.
- `UNKNOWN` means the source is blank, missing, or too ambiguous to classify. It is distinct from `NO`.
- Columns ending in `_raw` preserve unnormalized source text.
- Latitude and longitude require range validation before a row participates in distance search.
- Activity-phase processed CSVs retain the literal uppercase source column names. Proposed future database field names may use snake case.

## `national_park`

Implemented artifact: `data/processed/national_parks.csv`. The current output contains 63 records, one for every source row. The unnamed source index is removed rather than used for identity, and the fully empty `Image` column is excluded. Parse failures are left blank in the processed field and written to `reports/generated/park_parse_failures.csv`; the current snapshot has none.

| Processed field | Meaning | Source / rule |
|---|---|---|
| `park_id` | Stable processed key | UUIDv5 in the URL namespace over `https://campscout.local/national-park/` plus the case-folded, whitespace-normalized cleaned name; independent of source order and unnamed index |
| `name` | User-facing park name | HTML entities and whitespace normalized; trailing marker stars removed |
| `state_or_territory` | Cleaned source location label | Text preceding coordinates in `Location`, with CSS, scripts, HTML tags, BOMs, and unrelated markup removed; multi-state labels remain source-backed text |
| `latitude` | Validated decimal latitude | Decimal coordinate pair in `Location`, falling back to degrees/minutes/seconds; `N` is positive and `S` is negative; range `-90..90` |
| `longitude` | Validated decimal longitude | Parsed with latitude; `E` is positive and `W` is negative; range `-180..180` |
| `established_date` | ISO park establishment date | Numeric citations removed from `Date established as park[7][12]`, then strict full-month parsing to `YYYY-MM-DD` |
| `area_acres` | Numeric acreage | First non-negative numeric acres value from `Area (2021)[13]`; grouping commas removed without converting square-kilometer text |
| `recreation_visitors_2021` | Integer visitor count labeled for 2021 | `Recreation visitors (2021)[11]`; optional grouping commas removed; decimals and prose are not coerced |
| `description` | Cleaned source description | Whitespace and entities normalized and numeric citation markers such as `[14]` removed |

There is intentionally no campground foreign key on this entity. A park with invalid coordinates remains auditable in this artifact but does not participate in the distance matrix.

## `campground`

Implemented artifact: `data/processed/campgrounds.csv`. The cleaner normalizes `site_subtype` by trimming, collapsing whitespace, and uppercasing, then retains only exact `CAMPGROUND`, `GROUP CAMPGROUND`, and `HORSE CAMP` values. The current output contains 4,810 records: 4,198, 431, and 181 respectively. These categories represent explicit campground entities with useful structured information; they do not imply ratings, reviews, or quality.

`globalid` is the selected `campground_id`. Profiling found it non-null and unique in all 32,114 source rows, and validation confirms 4,810 distinct non-null values in the campground subset. `site_cn` was also complete and unique, but `globalid` is a source-issued UUID-like identifier and is used directly. `site_id` remains an audit attribute because only 29,972 of its 32,114 values are distinct. All identifiers are ingested and written as text, without numeric conversion.

| Processed field | Meaning | Source / rule |
|---|---|---|
| `campground_id` | Campground CSV key | Exact preserved `globalid` |
| `globalid` | Preserved selected source identifier | Exact preserved `globalid` |
| `site_cn`, `site_id`, `objectid` | Preserved source identifiers | Trim surrounding whitespace only; retain leading zeroes and punctuation |
| `root_cn`, `parent_cn` | Preserved source hierarchy identifiers | Trim surrounding whitespace only |
| `name` | Campground display name | First non-blank of `public_site_name`, `site_name`, `recarea_name` |
| `public_site_name`, `site_name`, `recarea_name` | Auditable source names | Whitespace normalized; blanks remain blank |
| `site_subtype` | Supported normalized campground subtype | Trim/collapse whitespace, uppercase, then exact allow-list match |
| `site_subtype_raw` | Original subtype text | Unmodified source field |
| `recarea_id` | Optional validated Recreation Area link | Extract `recid` only from `usda_portal_url`; populate only when it exists in `recreation_areas.csv.RECAREAID` |
| `recid_extracted` | URL-extracted candidate identifier | First non-blank case-insensitive `recid` query parameter, preserved as text |
| `fee_charged` | Normalized fee state | Exact `Y` -> `YES`, exact `N` -> `NO`, otherwise `UNKNOWN` |
| `fee_charged_raw` | Original fee flag | Unmodified `fee_charged` source field |
| `fee_type`, `fee_description` | Source fee details | Whitespace normalized; no fee amounts inferred |
| `total_capacity` | Safely parsed numeric capacity | Plain non-negative integer or decimal only; prose, signs, grouping separators, and scientific notation remain unparsed |
| `total_capacity_raw` | Original capacity text | Unmodified source field |
| `water_availability` | Normalized water category | One of `AVAILABLE`, `NOT_AVAILABLE`, `NATURAL_SOURCE`, `NEARBY`, `OTHER`, `UNKNOWN` |
| `water_availability_raw` | Original water description | Unmodified source field |
| `restroom_availability` | Normalized restroom category | One of `FLUSH`, `VAULT`, `COMPOSTING`, `PORTABLE`, `MULTIPLE`, `NONE`, `OTHER`, `UNKNOWN` |
| `restroom_availability_raw` | Original restroom description | Unmodified source field |
| `directions`, `site_directions` | Source direction fields | Kept separately; `directions` is the display field and is not backfilled from another source |
| `closest_towns`, `operational_hours` | Source visitor information | Whitespace normalized; blanks remain blank |
| `official_url` | Official campground information URL | Exact normalized `usda_portal_url`; no URL is invented or substituted |
| `usda_portal_url`, `rec1stop_url` | Auditable source URLs | Preserved separately after whitespace normalization |
| `latitude`, `longitude` | Campground coordinates | Source numeric text retained after finite range validation (`-90..90`, `-180..180`) |
| `last_update` | Source update value | Preserved as normalized text; no unsupported date inference |

Water normalization checks explicit alternative-source evidence and negative phrases before positive phrases. Nearby/adjacent water maps to `NEARBY`; water described as requiring treatment or filtering, or explicitly as an untreated creek, river, spring, stream, lake, or natural source, maps to `NATURAL_SOURCE`; explicit `no`, `none`, `not available`, `not provided`, offline, closed-system, or discontinued-pump wording maps to `NOT_AVAILABLE`; explicit potable/drinking/available, pump, faucet, hydrant, spigot, pressurized, gravity, or well wording maps to `AVAILABLE`; explicit non-potable, boil-only, or livestock/stock/trough text maps to `OTHER`; unclassified or unrelated text maps to `UNKNOWN`. Thus `No potable water available` cannot become `AVAILABLE`.

Restroom normalization checks negative wording first. Explicit absence maps to `NONE`; recognized flush, vault/pit/outhouse, composting, and portable wording maps to its corresponding category; text containing more than one recognized type maps to `MULTIPLE`; generic text that clearly mentions a restroom, toilet, facility, or shower but not a supported type maps to `OTHER`; and blank, explicitly unknown, unrelated, or ambiguous text maps to `UNKNOWN`. Missing values never become `NONE`.

Campgrounds with no validated link remain in this artifact with blank `recarea_id` and are written to `reports/generated/unmatched_campgrounds.csv` with one of three reasons: missing USDA URL, no `recid` query parameter, or extracted ID absent from the processed Recreation Areas. No fuzzy match is applied. Possible duplicates are exact normalized display-name pairs no more than 1 km apart; `reports/generated/duplicate_candidates.csv` provides both identifiers, names, coordinates, and Haversine distance for human review. No candidate is merged automatically.

There is intentionally no `park_id` column. Unsupported hookup, rating, booking, and vehicle-recommendation fields are not part of this product model.

The current campground-subset missingness is recorded in `reports/generated/campground_cleaning_summary.json` using 4,810—not the full 32,114 source rows—as the denominator. The summary also contains subtype, identifier, link, normalized category, drop, unmatched, and duplicate-pair counts.

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

## `park_campground_distance`

Implemented artifact: `data/processed/park_campground_distances.csv`. It is a deterministic complete cross product of parks and campgrounds with valid coordinates, sorted by `park_id` and then `campground_id`. The current snapshot contains 303,030 rows: 63 valid parks multiplied by 4,810 valid campgrounds.

| Processed field | Meaning | Source / rule |
|---|---|---|
| `park_id` | Park identifier | Validated reference to `national_parks.csv.park_id` |
| `campground_id` | Campground identifier | Validated reference to `campgrounds.csv.campground_id` |
| `distance_km` | Approximate straight-line kilometers | Haversine great-circle distance using the 6,371.0088 km IUGG mean Earth radius; full precision is retained during calculation and only the CSV value is rounded to six decimal places |

The distance starts at the park's representative source coordinate. It is not road distance and not distance from a park entrance. Negative or non-finite results are rejected, and publication requires the output cardinality to equal valid park count multiplied by valid campground count. Results at or below a requested radius are eligible.

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

- Whether `globalid` remains stable and unique across future source snapshots; the current phase validates every run and fails rather than silently replacing it.
- Whether unsupported recreation-site subtypes should be included in a future product scope change.
- Whether reviewed duplicate candidates represent distinct facilities or source duplicates.
- Final SQL types, maximum lengths, indexes, and nullability.

These are profiling or design tasks, not gaps to fill by assumption.
