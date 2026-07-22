-- Application indexes are installed explicitly with python -m db.apply_indexes.
-- Remove indexes from the database-layer phase that are redundant or superseded.
DROP INDEX IF EXISTS idx_park_campground_distances_campground_id;
DROP INDEX IF EXISTS idx_park_campground_distances_park_distance;
DROP INDEX IF EXISTS idx_recreation_area_activities_activity_id;

-- Covers the park/radius range, required distance order, and joined campground key.
CREATE INDEX IF NOT EXISTS idx_park_distance_campground
    ON park_campground_distances (park_id, distance_km, campground_id);

-- Reverses the bridge primary-key order for selected-activity lookup.
CREATE INDEX IF NOT EXISTS idx_activity_recarea
    ON recreation_area_activities (activity_id, recarea_id);

-- Supports campground lookup from Recreation Area relationships and views.
-- Standalone campground category indexes are intentionally absent: evaluated core
-- plans drive from bounded park-distance candidates and fetch campgrounds by PK.
CREATE INDEX IF NOT EXISTS idx_campgrounds_recarea_id
    ON campgrounds (recarea_id);
