"""Read-only, parameterized SQLite queries for the future CampScout UI."""

from __future__ import annotations

import math
import sqlite3
from typing import Any, Iterable, Optional, Sequence

from db.connection import PathLike, connect_database


MAX_SEARCH_RESULTS = 500
MAX_NEAREST_PER_PARK = 100
CAMPGROUND_TYPES = frozenset({"CAMPGROUND", "GROUP CAMPGROUND", "HORSE CAMP"})
FEE_STATUS_TO_DATABASE = {"FREE": "NO", "PAID": "YES"}
WATER_CATEGORIES = frozenset(
    {"AVAILABLE", "NOT_AVAILABLE", "NATURAL_SOURCE", "NEARBY", "OTHER", "UNKNOWN"}
)
RESTROOM_CATEGORIES = frozenset(
    {"FLUSH", "VAULT", "COMPOSTING", "PORTABLE", "MULTIPLE", "NONE", "OTHER", "UNKNOWN"}
)


PARKS_SQL = """
SELECT park_id, name, state_or_territory, latitude, longitude
FROM national_parks
ORDER BY name COLLATE NOCASE, park_id
"""

AVAILABLE_ACTIVITIES_SQL = """
SELECT DISTINCT a.activity_id, a.name, a.parent_activity_id, a.parent_activity_name
FROM activities AS a
JOIN recreation_area_activities AS raa ON raa.activity_id = a.activity_id
JOIN campgrounds AS c ON c.recarea_id = raa.recarea_id
ORDER BY a.name COLLATE NOCASE, a.activity_id
"""

SEARCH_SELECT_SQL = """
SELECT
    d.park_id,
    d.distance_km,
    c.campground_id,
    c.name,
    c.campground_type,
    c.recarea_id,
    ra.name AS recreation_area_name,
    CASE WHEN EXISTS (
        SELECT 1
        FROM recreation_area_activities AS activity_info
        WHERE activity_info.recarea_id = c.recarea_id
    ) THEN 1 ELSE 0 END AS has_activity_information,
    c.fee_charged,
    c.fee_type,
    c.fee_description,
    c.water_category,
    c.water_availability_raw,
    c.restroom_category,
    c.restroom_availability_raw,
    c.directions,
    c.closest_towns,
    c.operational_hours,
    c.latitude,
    c.longitude,
    c.official_url
FROM park_campground_distances AS d
JOIN campgrounds AS c ON c.campground_id = d.campground_id
LEFT JOIN recreation_areas AS ra ON ra.recarea_id = c.recarea_id
"""

CAMPGROUND_DETAILS_SQL = """
SELECT
    c.*,
    ra.name AS linked_recreation_area_name,
    ra.official_url AS linked_recreation_area_url,
    ra.forest_name AS linked_forest_name,
    ra.open_status AS linked_recreation_area_status,
    ra.open_season_start AS linked_open_season_start,
    ra.open_season_end AS linked_open_season_end,
    ra.description AS linked_recreation_area_description,
    ra.accessibility AS linked_recreation_area_accessibility
FROM campgrounds AS c
LEFT JOIN recreation_areas AS ra ON ra.recarea_id = c.recarea_id
WHERE c.campground_id = ?
"""

CAMPGROUND_ACTIVITIES_SQL = """
SELECT activity_id, activity_name, parent_activity_id, parent_activity_name
FROM campground_activity_details
WHERE campground_id = ?
ORDER BY activity_name COLLATE NOCASE, activity_id
"""

NEARBY_COUNTS_SQL = """
SELECT p.park_id, p.name, COUNT(d.campground_id) AS nearby_campground_count
FROM national_parks AS p
LEFT JOIN park_campground_distances AS d
    ON d.park_id = p.park_id AND d.distance_km <= ?
GROUP BY p.park_id, p.name
ORDER BY p.name COLLATE NOCASE, p.park_id
"""

NEAREST_PER_PARK_SQL = """
WITH ranked AS (
    SELECT
        d.park_id,
        p.name AS park_name,
        d.campground_id,
        c.name AS campground_name,
        c.campground_type,
        d.distance_km,
        ROW_NUMBER() OVER (
            PARTITION BY d.park_id
            ORDER BY d.distance_km, d.campground_id
        ) AS distance_rank
    FROM park_campground_distances AS d
    JOIN national_parks AS p ON p.park_id = d.park_id
    JOIN campgrounds AS c ON c.campground_id = d.campground_id
)
SELECT park_id, park_name, campground_id, campground_name, campground_type,
       distance_km, distance_rank
FROM ranked
WHERE distance_rank <= ?
ORDER BY park_name COLLATE NOCASE, park_id, distance_rank
"""

FREE_KNOWN_AMENITIES_SQL = """
SELECT campground_id, name, campground_type, water_category, restroom_category,
       recarea_id, official_url
FROM campgrounds
WHERE fee_charged = ?
  AND water_category <> ?
  AND restroom_category <> ?
ORDER BY name COLLATE NOCASE, campground_id
LIMIT ?
"""

COMPLETENESS_SQL = """
SELECT
    COUNT(*) AS campground_count,
    SUM(has_recreation_area_link) AS linked_recreation_area_count,
    SUM(1 - has_recreation_area_link) AS missing_recreation_area_link_count,
    SUM(has_official_url) AS official_url_count,
    SUM(has_directions) AS directions_count,
    SUM(has_known_fee_status) AS known_fee_status_count,
    SUM(has_known_water) AS known_water_count,
    SUM(has_known_restroom) AS known_restroom_count,
    SUM(completeness_fields_present) AS completeness_fields_present,
    SUM(completeness_fields_total) AS completeness_fields_total
FROM campground_data_completeness
"""


def _fetch_all(
    sql: str,
    parameters: Sequence[Any] = (),
    database_path: Optional[PathLike] = None,
) -> list[dict[str, Any]]:
    connection = connect_database(database_path, read_only=True)
    try:
        return [dict(row) for row in connection.execute(sql, tuple(parameters)).fetchall()]
    finally:
        connection.close()


def _fetch_one(
    sql: str,
    parameters: Sequence[Any],
    database_path: Optional[PathLike],
) -> Optional[dict[str, Any]]:
    connection = connect_database(database_path, read_only=True)
    try:
        row = connection.execute(sql, tuple(parameters)).fetchone()
        return None if row is None else dict(row)
    finally:
        connection.close()


def _positive_number(value: Any, name: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a positive finite number")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a positive finite number") from exc
    if not math.isfinite(number) or number <= 0.0:
        raise ValueError(f"{name} must be a positive finite number")
    return number


def _bounded_integer(value: Any, name: str, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= maximum:
        raise ValueError(f"{name} must be an integer from 1 through {maximum}")
    return value


def _optional_category(
    value: Optional[str],
    name: str,
    allowed: frozenset[str],
) -> Optional[str]:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{name} is invalid")
    normalized = value.strip().upper()
    if normalized not in allowed:
        raise ValueError(f"{name} is invalid")
    return normalized


def _distinct_activity_ids(activity_ids: Optional[Sequence[str]]) -> tuple[str, ...]:
    if activity_ids is None:
        return ()
    if isinstance(activity_ids, (str, bytes)):
        raise ValueError("activity_ids must be a sequence of identifiers")
    distinct: list[str] = []
    seen: set[str] = set()
    for activity_id in activity_ids:
        if not isinstance(activity_id, str) or not activity_id:
            raise ValueError("activity_ids must contain non-empty text identifiers")
        if activity_id not in seen:
            seen.add(activity_id)
            distinct.append(activity_id)
    return tuple(distinct)


def list_national_parks(database_path: Optional[PathLike] = None) -> list[dict[str, Any]]:
    """Return all supported parks in stable display order."""

    return _fetch_all(PARKS_SQL, database_path=database_path)


def list_available_activities(
    database_path: Optional[PathLike] = None,
) -> list[dict[str, Any]]:
    """Return activities reachable through at least one linked campground."""

    return _fetch_all(AVAILABLE_ACTIVITIES_SQL, database_path=database_path)


def build_search_query(
    *,
    park_id: str,
    radius_km: Any,
    limit: int = 100,
    campground_type: Optional[str] = None,
    fee_status: Optional[str] = None,
    water_category: Optional[str] = None,
    restroom_category: Optional[str] = None,
    activity_ids: Optional[Sequence[str]] = None,
) -> tuple[str, tuple[Any, ...]]:
    """Build trusted SQL structure and a separate bound-parameter tuple."""

    if not isinstance(park_id, str) or not park_id:
        raise ValueError("park_id must be a non-empty text identifier")
    radius = _positive_number(radius_km, "radius_km")
    safe_limit = _bounded_integer(limit, "limit", MAX_SEARCH_RESULTS)
    campground_type = _optional_category(
        campground_type, "campground_type", CAMPGROUND_TYPES
    )
    water_category = _optional_category(
        water_category, "water_category", WATER_CATEGORIES
    )
    restroom_category = _optional_category(
        restroom_category, "restroom_category", RESTROOM_CATEGORIES
    )
    if fee_status is None:
        fee_value = None
    elif isinstance(fee_status, str):
        fee_value = FEE_STATUS_TO_DATABASE.get(fee_status.strip().upper())
        if fee_value is None:
            raise ValueError("fee_status must be FREE or PAID")
    else:
        raise ValueError("fee_status must be FREE or PAID")

    selected_activity_ids = _distinct_activity_ids(activity_ids)
    parameters: list[Any] = []
    sql_parts: list[str] = []
    if selected_activity_ids:
        placeholders = ", ".join("?" for _ in selected_activity_ids)
        sql_parts.append(
            "WITH matched_recreation_areas AS (\n"
            "    SELECT raa.recarea_id\n"
            "    FROM recreation_area_activities AS raa\n"
            f"    WHERE raa.activity_id IN ({placeholders})\n"
            "    GROUP BY raa.recarea_id\n"
            "    HAVING COUNT(DISTINCT raa.activity_id) = ?\n"
            ")\n"
        )
        parameters.extend(selected_activity_ids)
        parameters.append(len(selected_activity_ids))

    sql_parts.append(SEARCH_SELECT_SQL)
    if selected_activity_ids:
        sql_parts.append(
            "JOIN matched_recreation_areas AS matched "
            "ON matched.recarea_id = c.recarea_id\n"
        )

    predicates = ["d.park_id = ?", "d.distance_km <= ?"]
    parameters.extend((park_id, radius))
    optional_filters = (
        ("c.campground_type = ?", campground_type),
        ("c.fee_charged = ?", fee_value),
        ("c.water_category = ?", water_category),
        ("c.restroom_category = ?", restroom_category),
    )
    for predicate, value in optional_filters:
        if value is not None:
            predicates.append(predicate)
            parameters.append(value)

    sql_parts.append("WHERE " + "\n  AND ".join(predicates) + "\n")
    sql_parts.append("ORDER BY d.distance_km, d.campground_id\nLIMIT ?")
    parameters.append(safe_limit)
    return "".join(sql_parts), tuple(parameters)


def find_campgrounds(
    park_id: str,
    radius_km: Any,
    *,
    limit: int = 100,
    campground_type: Optional[str] = None,
    fee_status: Optional[str] = None,
    water_category: Optional[str] = None,
    restroom_category: Optional[str] = None,
    activity_ids: Optional[Sequence[str]] = None,
    database_path: Optional[PathLike] = None,
) -> list[dict[str, Any]]:
    """Find distance-ordered campgrounds with optional ALL-activity semantics."""

    sql, parameters = build_search_query(
        park_id=park_id,
        radius_km=radius_km,
        limit=limit,
        campground_type=campground_type,
        fee_status=fee_status,
        water_category=water_category,
        restroom_category=restroom_category,
        activity_ids=activity_ids,
    )
    return _fetch_all(sql, parameters, database_path)


def get_campground_details(
    campground_id: str,
    database_path: Optional[PathLike] = None,
) -> Optional[dict[str, Any]]:
    """Return all campground fields plus linked Recreation Area details."""

    if not isinstance(campground_id, str) or not campground_id:
        raise ValueError("campground_id must be a non-empty text identifier")
    return _fetch_one(CAMPGROUND_DETAILS_SQL, (campground_id,), database_path)


def list_campground_activities(
    campground_id: str,
    database_path: Optional[PathLike] = None,
) -> list[dict[str, Any]]:
    """List activities reached through the campground's Recreation Area."""

    if not isinstance(campground_id, str) or not campground_id:
        raise ValueError("campground_id must be a non-empty text identifier")
    return _fetch_all(CAMPGROUND_ACTIVITIES_SQL, (campground_id,), database_path)


def count_nearby_campgrounds_per_park(
    radius_km: Any,
    database_path: Optional[PathLike] = None,
) -> list[dict[str, Any]]:
    """Return every park with its campground count inside the selected radius."""

    radius = _positive_number(radius_km, "radius_km")
    return _fetch_all(NEARBY_COUNTS_SQL, (radius,), database_path)


def nearest_campgrounds_per_park(
    count: int,
    database_path: Optional[PathLike] = None,
) -> list[dict[str, Any]]:
    """Return the nearest N campgrounds for every park using ROW_NUMBER."""

    safe_count = _bounded_integer(count, "count", MAX_NEAREST_PER_PARK)
    return _fetch_all(NEAREST_PER_PARK_SQL, (safe_count,), database_path)


def list_free_campgrounds_with_known_amenities(
    *,
    limit: int = 100,
    database_path: Optional[PathLike] = None,
) -> list[dict[str, Any]]:
    """Return free campgrounds with non-UNKNOWN water and restroom categories."""

    safe_limit = _bounded_integer(limit, "limit", MAX_SEARCH_RESULTS)
    return _fetch_all(
        FREE_KNOWN_AMENITIES_SQL,
        ("NO", "UNKNOWN", "UNKNOWN", safe_limit),
        database_path,
    )


def get_data_completeness_report(
    database_path: Optional[PathLike] = None,
) -> dict[str, Any]:
    """Summarize campground field completeness and missing Recreation Area links."""

    result = _fetch_one(COMPLETENESS_SQL, (), database_path)
    if result is None:
        raise sqlite3.DatabaseError("Campground completeness query returned no row")
    return result
