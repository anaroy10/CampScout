-- 1. National parks in display order.
SELECT park_id, name, state_or_territory, latitude, longitude
FROM national_parks
ORDER BY name COLLATE NOCASE, park_id;

-- 2. Activities that are reachable from at least one campground.
SELECT DISTINCT a.activity_id, a.name, a.parent_activity_id, a.parent_activity_name
FROM activities AS a
JOIN recreation_area_activities AS raa ON raa.activity_id = a.activity_id
JOIN campgrounds AS c ON c.recarea_id = raa.recarea_id
ORDER BY a.name COLLATE NOCASE, a.activity_id;

-- 3-9. Core radius search. Optional predicates are appended from a fixed allow-list
-- in app/queries.py; every value, including LIMIT, remains a bound parameter.
SELECT
    d.park_id,
    d.distance_km,
    c.campground_id,
    c.name,
    c.campground_type,
    c.recarea_id,
    c.fee_charged,
    c.water_category,
    c.restroom_category,
    c.latitude,
    c.longitude,
    c.official_url
FROM park_campground_distances AS d
JOIN campgrounds AS c ON c.campground_id = d.campground_id
WHERE d.park_id = ?
  AND d.distance_km <= ?
  AND c.campground_type = ?
  AND c.fee_charged = ?
  AND c.water_category = ?
  AND c.restroom_category = ?
ORDER BY d.distance_km, d.campground_id
LIMIT ?;

-- 10-11. Representative two-activity ALL-match search. The Python layer creates
-- exactly one ? per selected activity and binds the distinct selected count.
WITH matched_recreation_areas AS (
    SELECT raa.recarea_id
    FROM recreation_area_activities AS raa
    WHERE raa.activity_id IN (?, ?)
    GROUP BY raa.recarea_id
    HAVING COUNT(DISTINCT raa.activity_id) = ?
)
SELECT d.park_id, d.distance_km, c.campground_id, c.name, c.recarea_id
FROM park_campground_distances AS d
JOIN campgrounds AS c ON c.campground_id = d.campground_id
JOIN matched_recreation_areas AS matched
    ON matched.recarea_id = c.recarea_id
WHERE d.park_id = ?
  AND d.distance_km <= ?
ORDER BY d.distance_km, d.campground_id
LIMIT ?;

-- 12. Complete campground details.
SELECT c.*, ra.name AS linked_recreation_area_name,
       ra.official_url AS linked_recreation_area_url,
       ra.forest_name AS linked_forest_name,
       ra.open_status AS linked_recreation_area_status
FROM campgrounds AS c
LEFT JOIN recreation_areas AS ra ON ra.recarea_id = c.recarea_id
WHERE c.campground_id = ?;

-- 13. Activities available in one campground's Recreation Area.
SELECT activity_id, activity_name, parent_activity_id, parent_activity_name
FROM campground_activity_details
WHERE campground_id = ?
ORDER BY activity_name COLLATE NOCASE, activity_id;

-- 14. Nearby campground count for every park at one radius.
SELECT p.park_id, p.name, COUNT(d.campground_id) AS nearby_campground_count
FROM national_parks AS p
LEFT JOIN park_campground_distances AS d
    ON d.park_id = p.park_id AND d.distance_km <= ?
GROUP BY p.park_id, p.name
ORDER BY p.name COLLATE NOCASE, p.park_id;

-- 15. Nearest N campgrounds per park using a window function.
WITH ranked AS (
    SELECT
        d.park_id,
        p.name AS park_name,
        d.campground_id,
        c.name AS campground_name,
        d.distance_km,
        ROW_NUMBER() OVER (
            PARTITION BY d.park_id
            ORDER BY d.distance_km, d.campground_id
        ) AS distance_rank
    FROM park_campground_distances AS d
    JOIN national_parks AS p ON p.park_id = d.park_id
    JOIN campgrounds AS c ON c.campground_id = d.campground_id
)
SELECT *
FROM ranked
WHERE distance_rank <= ?
ORDER BY park_name COLLATE NOCASE, park_id, distance_rank;

-- 16. Free campgrounds whose water and restroom categories are known.
SELECT campground_id, name, campground_type, water_category, restroom_category,
       recarea_id, official_url
FROM campgrounds
WHERE fee_charged = 'NO'
  AND water_category <> 'UNKNOWN'
  AND restroom_category <> 'UNKNOWN'
ORDER BY name COLLATE NOCASE, campground_id
LIMIT ?;

-- 17. Completeness and missing Recreation Area links.
SELECT
    COUNT(*) AS campground_count,
    SUM(has_recreation_area_link) AS linked_recreation_area_count,
    SUM(1 - has_recreation_area_link) AS missing_recreation_area_link_count,
    SUM(has_official_url) AS official_url_count,
    SUM(has_directions) AS directions_count,
    SUM(has_known_fee_status) AS known_fee_status_count,
    SUM(has_known_water) AS known_water_count,
    SUM(has_known_restroom) AS known_restroom_count
FROM campground_data_completeness;
