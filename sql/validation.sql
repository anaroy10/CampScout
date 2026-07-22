-- Every statement returns zero rows when its validation passes.
SELECT 'invalid_national_park_coordinate' AS issue, park_id AS record_key
FROM national_parks
WHERE latitude NOT BETWEEN -90.0 AND 90.0
   OR longitude NOT BETWEEN -180.0 AND 180.0;

SELECT 'invalid_recreation_area_coordinate' AS issue, recarea_id AS record_key
FROM recreation_areas
WHERE (latitude IS NOT NULL AND latitude NOT BETWEEN -90.0 AND 90.0)
   OR (longitude IS NOT NULL AND longitude NOT BETWEEN -180.0 AND 180.0);

SELECT 'invalid_campground_coordinate' AS issue, campground_id AS record_key
FROM campgrounds
WHERE latitude NOT BETWEEN -90.0 AND 90.0
   OR longitude NOT BETWEEN -180.0 AND 180.0;

SELECT 'negative_distance' AS issue,
       park_id || ':' || campground_id AS record_key
FROM park_campground_distances
WHERE distance_km < 0.0;

SELECT 'invalid_campground_type' AS issue, campground_id AS record_key
FROM campgrounds
WHERE campground_type NOT IN ('CAMPGROUND', 'GROUP CAMPGROUND', 'HORSE CAMP');

SELECT 'invalid_water_category' AS issue, campground_id AS record_key
FROM campgrounds
WHERE water_category NOT IN (
    'AVAILABLE', 'NOT_AVAILABLE', 'NATURAL_SOURCE', 'NEARBY', 'OTHER', 'UNKNOWN'
);

SELECT 'invalid_restroom_category' AS issue, campground_id AS record_key
FROM campgrounds
WHERE restroom_category NOT IN (
    'FLUSH', 'VAULT', 'COMPOSTING', 'PORTABLE',
    'MULTIPLE', 'NONE', 'OTHER', 'UNKNOWN'
);

SELECT 'duplicate_recreation_area_activity' AS issue,
       recarea_id || ':' || activity_id AS record_key
FROM recreation_area_activities
GROUP BY recarea_id, activity_id
HAVING COUNT(*) > 1;

SELECT 'duplicate_park_campground_distance' AS issue,
       park_id || ':' || campground_id AS record_key
FROM park_campground_distances
GROUP BY park_id, campground_id
HAVING COUNT(*) > 1;

SELECT 'incomplete_distance_matrix' AS issue,
       CAST((SELECT COUNT(*) FROM park_campground_distances) AS TEXT) AS record_key
WHERE (SELECT COUNT(*) FROM park_campground_distances)
      != (SELECT COUNT(*) FROM national_parks) * (SELECT COUNT(*) FROM campgrounds);

SELECT 'no_linked_campgrounds' AS issue, '' AS record_key
WHERE NOT EXISTS (SELECT 1 FROM campgrounds WHERE recarea_id IS NOT NULL);

SELECT 'no_unlinked_campgrounds' AS issue, '' AS record_key
WHERE NOT EXISTS (SELECT 1 FROM campgrounds WHERE recarea_id IS NULL);

SELECT 'water_unknown_or_negative_missing' AS issue, '' AS record_key
WHERE NOT EXISTS (SELECT 1 FROM campgrounds WHERE water_category = 'UNKNOWN')
   OR NOT EXISTS (SELECT 1 FROM campgrounds WHERE water_category = 'NOT_AVAILABLE');

SELECT 'restroom_unknown_or_negative_missing' AS issue, '' AS record_key
WHERE NOT EXISTS (SELECT 1 FROM campgrounds WHERE restroom_category = 'UNKNOWN')
   OR NOT EXISTS (SELECT 1 FROM campgrounds WHERE restroom_category = 'NONE');
