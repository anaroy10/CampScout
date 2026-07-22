-- Representative planner evidence captured with SQLite 3.50.4 against a freshly
-- built database containing the current six processed CSVs.
-- Bound example: Yosemite park_id, radius 100 km, LIMIT 25.
--
-- BEFORE sql/indexes.sql:
-- SEARCH d USING INDEX sqlite_autoindex_park_campground_distances_1 (park_id=?)
-- SEARCH c USING INDEX sqlite_autoindex_campgrounds_1 (campground_id=?)
-- USE TEMP B-TREE FOR ORDER BY
--
-- AFTER sql/indexes.sql:
-- SEARCH d USING COVERING INDEX idx_park_distance_campground
--     (park_id=? AND distance_km<?)
-- SEARCH c USING INDEX sqlite_autoindex_campgrounds_1 (campground_id=?)
-- No temporary ORDER BY B-tree was reported.
--
-- Adding campground type, fee, water, and restroom predicates retained the same
-- distance-first plan. SQLite fetched each candidate campground by its primary-key
-- index, so standalone category indexes were not selected and were not added.

EXPLAIN QUERY PLAN
SELECT d.park_id, d.distance_km, c.campground_id, c.name,
       c.campground_type, c.fee_charged, c.water_category,
       c.restroom_category
FROM park_campground_distances AS d
JOIN campgrounds AS c ON c.campground_id = d.campground_id
WHERE d.park_id = ?
  AND d.distance_km <= ?
ORDER BY d.distance_km, d.campground_id
LIMIT ?;

-- With representative optional campground filters, the selected indexes remained
-- idx_park_distance_campground for d and the campground primary key for c.
EXPLAIN QUERY PLAN
SELECT d.park_id, d.distance_km, c.campground_id, c.name
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

-- ALL-activity plan after indexes:
-- SEARCH raa USING COVERING INDEX idx_activity_recarea (activity_id=?)
-- USE TEMP B-TREE FOR GROUP BY
-- SEARCH d USING COVERING INDEX idx_park_distance_campground
--     (park_id=? AND distance_km<?)
-- SEARCH c USING INDEX sqlite_autoindex_campgrounds_1 (campground_id=?)
-- SEARCH matched USING AUTOMATIC COVERING INDEX (recarea_id=?)
EXPLAIN QUERY PLAN
WITH matched_recreation_areas AS (
    SELECT raa.recarea_id
    FROM recreation_area_activities AS raa
    WHERE raa.activity_id IN (?, ?)
    GROUP BY raa.recarea_id
    HAVING COUNT(DISTINCT raa.activity_id) = ?
)
SELECT d.park_id, d.distance_km, c.campground_id, c.name
FROM park_campground_distances AS d
JOIN campgrounds AS c ON c.campground_id = d.campground_id
JOIN matched_recreation_areas AS matched ON matched.recarea_id = c.recarea_id
WHERE d.park_id = ?
  AND d.distance_km <= ?
ORDER BY d.distance_km, d.campground_id
LIMIT ?;
