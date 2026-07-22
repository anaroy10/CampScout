import sqlite3

import pytest

from app import queries
from db.apply_indexes import EXPECTED_INDEXES, apply_indexes
from db.build_database import create_schema, create_views
from db.connection import connect_database


PARK_INSERT = """
INSERT INTO national_parks (
    park_id, name, state_or_territory, latitude, longitude,
    established_date, area_acres, recreation_visitors_2021, description
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
"""

AREA_INSERT = """
INSERT INTO recreation_areas (
    recarea_id, longitude, latitude, name, source_longitude, source_latitude,
    official_url, forest_name, spotlight_display, attraction_display, open_status
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""

ACTIVITY_INSERT = """
INSERT INTO activities (
    activity_id, name, parent_activity_id, parent_activity_name
) VALUES (?, ?, ?, ?)
"""

CAMP_INSERT = """
INSERT INTO campgrounds (
    campground_id, globalid, site_cn, site_id, objectid, root_cn,
    name, site_name, recarea_name, campground_type, campground_type_raw,
    recarea_id, fee_charged, fee_charged_raw, total_capacity,
    total_capacity_raw, water_category, restroom_category,
    latitude, longitude, last_update
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""


def _camp_values(
    campground_id,
    name,
    recarea_id,
    campground_type,
    fee_charged,
    water_category,
    restroom_category,
):
    return (
        campground_id,
        campground_id,
        f"cn-{campground_id}",
        f"site-{campground_id}",
        f"object-{campground_id}",
        f"root-{campground_id}",
        name,
        name,
        "Source Area",
        campground_type,
        campground_type,
        recarea_id,
        fee_charged,
        "N" if fee_charged == "NO" else "Y",
        10.0,
        "10",
        water_category,
        restroom_category,
        10.0,
        20.0,
        "2026-01-01",
    )


@pytest.fixture
def query_database(tmp_path):
    database_path = tmp_path / "queries.db"
    database = connect_database(database_path)
    database.execute("BEGIN")
    create_schema(database)
    database.executemany(
        PARK_INSERT,
        (
            ("park-1", "Alpha Park", "State", 10.0, 20.0, "2000-01-01", 1.0, 1, "A"),
            ("park-2", "Zulu Park", "State", 11.0, 21.0, "2001-01-01", 2.0, 2, "B"),
        ),
    )
    database.executemany(
        AREA_INSERT,
        (
            ("area-1", 20.0, 10.0, "Area One", "20", "10", "https://area/1", "Forest", 0, 0, "open"),
            ("area-2", 21.0, 11.0, "Area Two", "21", "11", "https://area/2", "Forest", 0, 0, "open"),
            ("area-3", 22.0, 12.0, "Unused Area", "22", "12", "https://area/3", "Forest", 0, 0, "open"),
        ),
    )
    database.executemany(
        ACTIVITY_INSERT,
        (
            ("activity-a", "Archery", "parent", "Outdoor"),
            ("activity-b", "Biking", "parent", "Outdoor"),
            ("activity-c", "Climbing", "parent", "Outdoor"),
        ),
    )
    database.executemany(
        CAMP_INSERT,
        (
            _camp_values("camp-null", "No Link", None, "HORSE CAMP", "NO", "AVAILABLE", "VAULT"),
            _camp_values("camp-both", "Both Activities", "area-1", "CAMPGROUND", "NO", "AVAILABLE", "FLUSH"),
            _camp_values("camp-one", "One Activity", "area-2", "GROUP CAMPGROUND", "YES", "UNKNOWN", "NONE"),
        ),
    )
    database.executemany(
        "INSERT INTO recreation_area_activities (recarea_id, activity_id) VALUES (?, ?)",
        (
            ("area-1", "activity-a"),
            ("area-1", "activity-b"),
            ("area-2", "activity-a"),
            ("area-3", "activity-c"),
        ),
    )
    database.executemany(
        "INSERT INTO park_campground_distances (park_id, campground_id, distance_km) VALUES (?, ?, ?)",
        (
            ("park-1", "camp-null", 5.0),
            ("park-1", "camp-both", 10.0),
            ("park-1", "camp-one", 20.0),
        ),
    )
    database.execute(
        "CREATE INDEX idx_park_campground_distances_park_distance "
        "ON park_campground_distances (park_id, distance_km)"
    )
    database.execute(
        "CREATE INDEX idx_park_campground_distances_campground_id "
        "ON park_campground_distances (campground_id)"
    )
    database.execute(
        "CREATE INDEX idx_recreation_area_activities_activity_id "
        "ON recreation_area_activities (activity_id)"
    )
    create_views(database)
    database.commit()
    database.close()
    apply_indexes(database_path)
    return database_path


def test_index_installation_is_idempotent_and_nonredundant(query_database):
    assert apply_indexes(query_database) == EXPECTED_INDEXES
    database = connect_database(query_database, read_only=True)
    try:
        explicit_indexes = {
            row[0]
            for row in database.execute(
                "SELECT name FROM sqlite_schema WHERE type = ? AND sql IS NOT NULL",
                ("index",),
            )
        }
    finally:
        database.close()

    assert explicit_indexes == set(EXPECTED_INDEXES)
    assert "idx_park_campground_distances_campground_id" not in explicit_indexes
    assert "idx_park_campground_distances_park_distance" not in explicit_indexes


def test_list_queries_use_display_order_and_only_reachable_activities(query_database):
    parks = queries.list_national_parks(query_database)
    activities = queries.list_available_activities(query_database)

    assert [row["park_id"] for row in parks] == ["park-1", "park-2"]
    assert [row["activity_id"] for row in activities] == ["activity-a", "activity-b"]


def test_search_orders_by_distance_and_keeps_unlinked_without_activity_filter(
    query_database,
):
    results = queries.find_campgrounds("park-1", 100, database_path=query_database)

    assert [row["campground_id"] for row in results] == [
        "camp-null",
        "camp-both",
        "camp-one",
    ]
    assert results[0]["recarea_id"] is None
    assert results[0]["recreation_area_name"] is None
    assert results[0]["has_activity_information"] == 0
    assert results[1]["recreation_area_name"] == "Area One"
    assert results[1]["has_activity_information"] == 1


def test_search_requires_all_distinct_selected_activities(query_database):
    one_activity = queries.find_campgrounds(
        "park-1", 100, activity_ids=["activity-a"], database_path=query_database
    )
    all_activities = queries.find_campgrounds(
        "park-1",
        100,
        activity_ids=["activity-a", "activity-b", "activity-a"],
        database_path=query_database,
    )

    assert [row["campground_id"] for row in one_activity] == ["camp-both", "camp-one"]
    assert [row["campground_id"] for row in all_activities] == ["camp-both"]
    assert all(row["recarea_id"] is not None for row in one_activity)


def test_search_composes_supported_filters_and_bound_limit(query_database):
    results = queries.find_campgrounds(
        "park-1",
        100,
        campground_type="campground",
        fee_status="free",
        water_category="available",
        restroom_category="flush",
        limit=1,
        database_path=query_database,
    )

    assert [row["campground_id"] for row in results] == ["camp-both"]
    with pytest.raises(ValueError, match="limit"):
        queries.find_campgrounds("park-1", 100, limit=501, database_path=query_database)
    with pytest.raises(ValueError, match="radius_km"):
        queries.find_campgrounds("park-1", 0, database_path=query_database)


def test_user_values_are_bound_and_cannot_change_sql_structure(query_database):
    malicious = "park-1' OR 1=1 --"
    sql, parameters = queries.build_search_query(
        park_id=malicious, radius_km=100, activity_ids=["activity-a') OR 1=1 --"]
    )

    assert malicious not in sql
    assert "activity-a') OR 1=1 --" not in sql
    assert malicious in parameters
    assert queries.find_campgrounds(
        malicious, 100, database_path=query_database
    ) == []


def test_details_and_activity_view_follow_recreation_area_relationship(query_database):
    details = queries.get_campground_details("camp-both", query_database)
    activities = queries.list_campground_activities("camp-both", query_database)

    assert details["linked_recreation_area_name"] == "Area One"
    assert [row["activity_id"] for row in activities] == ["activity-a", "activity-b"]
    assert queries.list_campground_activities("camp-null", query_database) == []


def test_aggregate_window_free_and_completeness_queries(query_database):
    counts = queries.count_nearby_campgrounds_per_park(15, query_database)
    nearest = queries.nearest_campgrounds_per_park(2, query_database)
    free_known = queries.list_free_campgrounds_with_known_amenities(
        limit=10, database_path=query_database
    )
    completeness = queries.get_data_completeness_report(query_database)

    assert {row["park_id"]: row["nearby_campground_count"] for row in counts} == {
        "park-1": 2,
        "park-2": 0,
    }
    assert [row["campground_id"] for row in nearest] == ["camp-null", "camp-both"]
    assert {row["campground_id"] for row in free_known} == {"camp-null", "camp-both"}
    assert completeness["campground_count"] == 3
    assert completeness["missing_recreation_area_link_count"] == 1


def test_core_plan_uses_covering_park_distance_index(query_database):
    sql, parameters = queries.build_search_query(
        park_id="park-1", radius_km=100, limit=10
    )
    database = connect_database(query_database, read_only=True)
    try:
        details = [
            row[3]
            for row in database.execute(
                "EXPLAIN QUERY PLAN " + sql, parameters
            ).fetchall()
        ]
    finally:
        database.close()

    assert any("idx_park_distance_campground" in detail for detail in details)
    assert not any("TEMP B-TREE FOR ORDER BY" in detail for detail in details)


def test_application_query_connection_is_short_lived_and_read_only(
    query_database, monkeypatch
):
    captured = []
    original_connect = queries.connect_database

    def recording_connect(database_path, *, read_only):
        captured.append((original_connect(database_path, read_only=read_only), read_only))
        return captured[-1][0]

    monkeypatch.setattr(queries, "connect_database", recording_connect)
    queries.list_national_parks(query_database)

    assert captured[0][1] is True
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        captured[0][0].execute("SELECT 1")
