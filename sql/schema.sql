CREATE TABLE national_parks (
    park_id TEXT PRIMARY KEY NOT NULL,
    name TEXT NOT NULL,
    state_or_territory TEXT NOT NULL,
    latitude REAL NOT NULL CHECK (latitude BETWEEN -90.0 AND 90.0),
    longitude REAL NOT NULL CHECK (longitude BETWEEN -180.0 AND 180.0),
    established_date TEXT NOT NULL,
    area_acres REAL NOT NULL CHECK (area_acres >= 0.0),
    recreation_visitors_2021 INTEGER NOT NULL
        CHECK (recreation_visitors_2021 >= 0),
    description TEXT NOT NULL
) STRICT;

CREATE TABLE recreation_areas (
    recarea_id TEXT PRIMARY KEY NOT NULL,
    longitude REAL CHECK (longitude IS NULL OR longitude BETWEEN -180.0 AND 180.0),
    latitude REAL CHECK (latitude IS NULL OR latitude BETWEEN -90.0 AND 90.0),
    name TEXT NOT NULL,
    source_longitude TEXT NOT NULL,
    source_latitude TEXT NOT NULL,
    official_url TEXT NOT NULL,
    open_season_start TEXT,
    open_season_end TEXT,
    forest_name TEXT NOT NULL,
    marker_type TEXT,
    marker_activity TEXT,
    marker_activity_group TEXT,
    description TEXT,
    spotlight_display INTEGER NOT NULL CHECK (spotlight_display IN (0, 1)),
    attraction_display INTEGER NOT NULL CHECK (attraction_display IN (0, 1)),
    accessibility TEXT,
    open_status TEXT NOT NULL,
    shape TEXT
) STRICT;

CREATE TABLE activities (
    activity_id TEXT PRIMARY KEY NOT NULL,
    name TEXT NOT NULL,
    parent_activity_id TEXT NOT NULL,
    parent_activity_name TEXT
) STRICT;

CREATE TABLE campgrounds (
    campground_id TEXT PRIMARY KEY NOT NULL,
    globalid TEXT NOT NULL UNIQUE,
    site_cn TEXT NOT NULL,
    site_id TEXT NOT NULL,
    objectid TEXT NOT NULL,
    root_cn TEXT NOT NULL,
    parent_cn TEXT,
    name TEXT NOT NULL,
    public_site_name TEXT,
    site_name TEXT NOT NULL,
    recarea_name TEXT NOT NULL,
    campground_type TEXT NOT NULL
        CHECK (campground_type IN ('CAMPGROUND', 'GROUP CAMPGROUND', 'HORSE CAMP')),
    campground_type_raw TEXT NOT NULL,
    recarea_id TEXT REFERENCES recreation_areas (recarea_id),
    recid_extracted TEXT,
    fee_charged TEXT NOT NULL
        CHECK (fee_charged IN ('YES', 'NO', 'UNKNOWN')),
    fee_charged_raw TEXT NOT NULL,
    fee_type TEXT,
    fee_description TEXT,
    total_capacity REAL NOT NULL CHECK (total_capacity >= 0.0),
    total_capacity_raw TEXT NOT NULL,
    water_category TEXT NOT NULL
        CHECK (water_category IN (
            'AVAILABLE', 'NOT_AVAILABLE', 'NATURAL_SOURCE',
            'NEARBY', 'OTHER', 'UNKNOWN'
        )),
    water_availability_raw TEXT,
    restroom_category TEXT NOT NULL
        CHECK (restroom_category IN (
            'FLUSH', 'VAULT', 'COMPOSTING', 'PORTABLE',
            'MULTIPLE', 'NONE', 'OTHER', 'UNKNOWN'
        )),
    restroom_availability_raw TEXT,
    directions TEXT,
    site_directions TEXT,
    closest_towns TEXT,
    operational_hours TEXT,
    official_url TEXT,
    usda_portal_url TEXT,
    rec1stop_url TEXT,
    latitude REAL NOT NULL CHECK (latitude BETWEEN -90.0 AND 90.0),
    longitude REAL NOT NULL CHECK (longitude BETWEEN -180.0 AND 180.0),
    last_update TEXT NOT NULL,
    CHECK (campground_id = globalid)
) STRICT;

CREATE TABLE recreation_area_activities (
    recarea_id TEXT NOT NULL REFERENCES recreation_areas (recarea_id),
    activity_id TEXT NOT NULL REFERENCES activities (activity_id),
    PRIMARY KEY (recarea_id, activity_id)
) STRICT;

CREATE TABLE park_campground_distances (
    park_id TEXT NOT NULL REFERENCES national_parks (park_id),
    campground_id TEXT NOT NULL REFERENCES campgrounds (campground_id),
    distance_km REAL NOT NULL CHECK (distance_km >= 0.0),
    PRIMARY KEY (park_id, campground_id)
) STRICT;
