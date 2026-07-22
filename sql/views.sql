DROP VIEW IF EXISTS campground_activity_details;

CREATE VIEW campground_activity_details AS
SELECT
    c.campground_id,
    c.name AS campground_name,
    c.campground_type,
    c.recarea_id,
    ra.name AS recreation_area_name,
    a.activity_id,
    a.name AS activity_name,
    a.parent_activity_id,
    a.parent_activity_name
FROM campgrounds AS c
JOIN recreation_areas AS ra
    ON ra.recarea_id = c.recarea_id
JOIN recreation_area_activities AS raa
    ON raa.recarea_id = c.recarea_id
JOIN activities AS a
    ON a.activity_id = raa.activity_id;

DROP VIEW IF EXISTS campground_data_completeness;

CREATE VIEW campground_data_completeness AS
SELECT
    c.campground_id,
    c.name AS campground_name,
    c.recarea_id,
    CASE WHEN c.recarea_id IS NOT NULL THEN 1 ELSE 0 END AS has_recreation_area_link,
    CASE WHEN c.official_url IS NOT NULL THEN 1 ELSE 0 END AS has_official_url,
    CASE WHEN c.directions IS NOT NULL THEN 1 ELSE 0 END AS has_directions,
    CASE WHEN c.fee_charged <> 'UNKNOWN' THEN 1 ELSE 0 END AS has_known_fee_status,
    CASE WHEN c.water_category <> 'UNKNOWN' THEN 1 ELSE 0 END AS has_known_water,
    CASE WHEN c.restroom_category <> 'UNKNOWN' THEN 1 ELSE 0 END AS has_known_restroom,
    (
        CASE WHEN c.recarea_id IS NOT NULL THEN 1 ELSE 0 END
        + CASE WHEN c.official_url IS NOT NULL THEN 1 ELSE 0 END
        + CASE WHEN c.directions IS NOT NULL THEN 1 ELSE 0 END
        + CASE WHEN c.fee_charged <> 'UNKNOWN' THEN 1 ELSE 0 END
        + CASE WHEN c.water_category <> 'UNKNOWN' THEN 1 ELSE 0 END
        + CASE WHEN c.restroom_category <> 'UNKNOWN' THEN 1 ELSE 0 END
    ) AS completeness_fields_present,
    6 AS completeness_fields_total
FROM campgrounds AS c;
