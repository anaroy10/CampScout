# Data sources and observed structure

## Inspection scope

The repository's three raw CSVs were inspected read-only on 2026-07-22 with CSV-aware parsing. Counts and hashes below describe the current local snapshot, not a guarantee about future source deliveries.

| Relative path | Rows | Columns | SHA-256 |
|---|---:|---:|---|
| `data/raw/Recreation_Sites_INFRA.csv` | 32,114 | 138 | `CDBDC4117D854D97FD0A2D2BD9FEF8BBF0C99F8CFE5BB752A6F32DCBD8D5FA0D` |
| `data/raw/Recreation_Area_Activities.csv` | 52,482 | 25 | `128F3444AD8340CA19D73EFF7CF8829126AC7CD870AC0832BEEFC500F754E0F6` |
| `data/raw/national_parks_raw.csv` | 63 | 8 | `0B10B926B514A193DBB1FD3DB5836D319F032ADB9DDBF3C036E6ED1676364077` |

These files are immutable inputs. Future pipelines must write derived data elsewhere and must not rewrite, reformat, rename, or repair them in place.

## `Recreation_Sites_INFRA.csv`

### Apparent grain

One row represents an infrastructure recreation-site record. The file is broader than campgrounds and includes trailheads, boating sites, picnic sites, individual camp units, and other facility types. It therefore cannot be loaded wholesale as a campground table.

### Fields relevant to CampScout

- Identity: `site_cn`, `root_cn`, `parent_cn`, `site_id`, `globalid`
- Naming and classification: `site_name`, `public_site_name`, `site_subtype`, `development_status`
- Recreation Area context: `recarea_name`, `parent_recarea`
- Location: `latitude`, `longitude`, address and town fields
- Filters: `fee_charged`, `fee_type`, `water_availability`, `restroom_availability`
- Display: `fee_description`, `directions`, `site_directions`, `closest_towns`
- URLs: `usda_portal_url`, `rec1stop_url`

### Observed profiling facts

- `site_cn`: 32,114 nonblank values and 32,114 distinct values.
- `globalid`: 32,114 nonblank values and 32,114 distinct values.
- `site_id`: 32,114 nonblank values but only 29,972 distinct values, producing 2,142 duplicate rows by this field. Values include leading zeros, so it must be read as text.
- Coordinates are nonblank in all rows, although their ranges and validity still require testing.
- `fee_charged` has 245 blanks; observed nonblank values are `Y` and `N`.
- `water_availability` has 20,414 blanks and 440 distinct nonblank free-text values.
- `restroom_availability` has 20,345 blanks and 550 distinct nonblank free-text values.
- `electricity_hookup` is blank in every row, `max_vehicle_length` is blank in every row, and `sewer_hookup` is blank in all but one row. These fields are outside the supported product scope regardless.

The largest `site_subtype` groups are `CAMPING AREA` (10,960), `TRAILHEAD` (7,360), `CAMPGROUND` (4,198), `BOATING SITE` (1,375), and `PICNIC SITE` (1,212). There are also `GROUP CAMPGROUND`, `CAMP UNIT`, `HORSE CAMP`, `CAMP UNIT - TENT`, and `CAMP UNIT - TRAILER/RV` records. Campground eligibility must be defined from source semantics and hierarchy, not by checking whether the subtype contains the word `CAMP`.

## `Recreation_Area_Activities.csv`

### Apparent grain

Rows with an activity identifier represent a Recreation Area-to-Activity association. Recreation Area descriptive fields repeat for each associated activity. There are 769 rows without `ACTIVITYID` or `ACTIVITYNAME`; they may still describe Recreation Areas but cannot form activity associations.

### Fields relevant to CampScout

- Recreation Area: `RECAREAID`, `RECAREANAME`, `RECAREAURL`, `FORESTNAME`
- Location/status: `LATITUDE`, `LONGITUDE`, `OPENSTATUS`
- Activity: `ACTIVITYID`, `ACTIVITYNAME`, `PARENTACTIVITYID`, `PARENTACTIVITYNAME`
- Source record: `OBJECTID`

### Observed profiling facts

- `OBJECTID`: 52,482 nonblank, distinct values.
- `RECAREAID`: 14,469 distinct nonblank values.
- Within this snapshot each `RECAREAID` maps to one observed name, URL, and coordinate pair.
- There are 79 distinct nonblank activity IDs and 77 distinct nonblank activity names.
- Each activity ID maps to one name, but `Picnicking` maps to IDs `69` and `70`, and `Scenic Driving` maps to IDs `75` and `105`. Activity name is therefore not a key.
- No duplicate `(RECAREAID, ACTIVITYID)` pairs were observed among rows with both values.
- `OPENSTATUS` includes `open`, `none`, `closed`, `temporarily closed`, `unreachable`, `not cleared`, and `unknown`.

This source supports the rule that activities belong to Recreation Areas. A separate, validated relationship is required to expose those activities for a campground.

## `national_parks_raw.csv`

### Apparent grain

One row represents a national park. All 63 names and the unnamed leading index values are distinct in this snapshot.

### Fields

- unnamed leading source index
- `Name`
- `Image`
- `Location`
- `Date established as park[7][12]`
- `Area (2021)[13]`
- `Recreation visitors (2021)[11]`
- `Description`

### Observed profiling facts

- `Image` is blank in all 63 rows.
- Several names contain source annotation characters such as `*`; cleanup rules must be explicit and retain the original name.
- `Location` combines state or territory text, coordinate text, and—in at least the first row—a scraped CSS fragment. It also contains degree symbols and invisible byte-order-mark characters around the coordinate alternatives.
- Establishment date, area, visitor count, and description are populated in every row in this snapshot.
- Coordinates are not provided as dedicated columns. Future ETL must parse, validate, and test latitude/longitude rather than trusting arbitrary numeric substrings.
- Visitor figures are labeled as 2021 data and must not be presented as current counts.

## Legacy SQL reference

The requested path `legacy/partner_schema.sql` is absent from this repository. The only SQL file found during inspection was `legacy/schema.sql`, and it was reviewed as non-authoritative reference material.

That legacy schema conflicts with current rules by using `site_id` as a primary key, linking campsites directly to parks and activities, and including unsupported rating, hookup, and vehicle fields. No current design decision is based on those structures. The legacy file was not modified.

## Provenance still required

The repository does not currently document download URLs, publishers, licenses, retrieval dates, or source versions for these snapshots. Before redistribution or production use, those provenance details must be recorded from authoritative source metadata rather than inferred from filenames or column contents.
