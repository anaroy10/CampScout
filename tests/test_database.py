import csv
import sqlite3
from pathlib import Path

import pytest

from db import connection
from db.build_database import (
    TABLE_SPECS,
    DatabaseBuildError,
    build_database,
    create_schema,
    null_if_missing,
)
from db.apply_indexes import apply_indexes
from db.validate_database import validate_database


PROCESSED_DIR = Path(__file__).resolve().parents[1] / "data" / "processed"
EXPECTED_TABLES = {spec.table_name for spec in TABLE_SPECS}


@pytest.fixture
def schema_connection(tmp_path):
    database_path = tmp_path / "schema.db"
    database = connection.connect_database(database_path)
    database.execute("BEGIN")
    create_schema(database)
    database.commit()
    try:
        yield database
    finally:
        database.close()


@pytest.fixture(scope="module")
def built_database(tmp_path_factory):
    database_path = tmp_path_factory.mktemp("database") / "campscout-test.db"
    row_counts = build_database(database_path, processed_dir=PROCESSED_DIR)
    apply_indexes(database_path)
    return database_path, row_counts


def _park_values(park_id="park-1", latitude=10.0):
    return (
        park_id,
        "Test Park",
        "Test State",
        latitude,
        20.0,
        "2000-01-01",
        100.0,
        1000,
        "A sufficiently long Unicode description: יער",
    )


PARK_INSERT = """
    INSERT INTO national_parks (
        park_id, name, state_or_territory, latitude, longitude,
        established_date, area_acres, recreation_visitors_2021, description
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
"""


def test_default_database_path_is_repository_relative(monkeypatch, tmp_path):
    monkeypatch.delenv("CAMPSCOUT_DB_PATH", raising=False)
    monkeypatch.chdir(tmp_path)

    assert connection.resolve_database_path() == connection.DEFAULT_DATABASE_PATH.resolve()


def test_environment_database_path_override(monkeypatch, tmp_path):
    override = tmp_path / "override.db"
    monkeypatch.setenv("CAMPSCOUT_DB_PATH", str(override))

    assert connection.resolve_database_path() == override.resolve()


def test_every_connection_enables_foreign_keys_and_rows(schema_connection):
    assert schema_connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    schema_connection.execute(PARK_INSERT, _park_values())
    row = schema_connection.execute(
        "SELECT park_id, name FROM national_parks WHERE park_id = ?", ("park-1",)
    ).fetchone()
    assert row["park_id"] == "park-1"
    assert row["name"] == "Test Park"


def test_read_only_connection_rejects_writes(tmp_path):
    database_path = tmp_path / "readonly.db"
    writable = connection.connect_database(database_path)
    writable.execute("CREATE TABLE example (value TEXT) STRICT")
    writable.close()

    readonly = connection.connect_database(database_path, read_only=True)
    try:
        assert readonly.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            readonly.execute("INSERT INTO example (value) VALUES (?)", ("blocked",))
    finally:
        readonly.close()


def test_schema_creates_all_six_strict_tables_without_forbidden_relationships(
    schema_connection,
):
    tables = {
        row[0]
        for row in schema_connection.execute(
            "SELECT name FROM sqlite_schema WHERE type = ? AND name NOT LIKE ?",
            ("table", "sqlite_%"),
        )
    }
    strict = {
        row[1]: row[5]
        for row in schema_connection.execute("PRAGMA table_list")
        if row[1] in EXPECTED_TABLES
    }
    campground_columns = {
        row[1] for row in schema_connection.execute("PRAGMA table_info(campgrounds)")
    }
    bridge_columns = {
        row[1]
        for row in schema_connection.execute(
            "PRAGMA table_info(recreation_area_activities)"
        )
    }

    assert tables == EXPECTED_TABLES
    assert strict == {table_name: 1 for table_name in EXPECTED_TABLES}
    assert "park_id" not in campground_columns
    assert "campground_id" not in bridge_columns


def test_strict_table_rejects_incompatible_storage_class(schema_connection):
    values = list(_park_values())
    values[7] = b"not an integer"
    with pytest.raises(sqlite3.IntegrityError):
        schema_connection.execute(PARK_INSERT, values)


def test_primary_key_rejection(schema_connection):
    schema_connection.execute(PARK_INSERT, _park_values())
    with pytest.raises(sqlite3.IntegrityError):
        schema_connection.execute(PARK_INSERT, _park_values())


def test_foreign_key_rejection(schema_connection):
    with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
        schema_connection.execute(
            "INSERT INTO recreation_area_activities (recarea_id, activity_id) "
            "VALUES (?, ?)",
            ("missing-area", "missing-activity"),
        )


def test_check_constraint_rejection(schema_connection):
    with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
        schema_connection.execute(PARK_INSERT, _park_values(latitude=91.0))


def test_empty_and_nan_values_become_sql_null():
    assert null_if_missing("") is None
    assert null_if_missing(float("nan")) is None
    assert null_if_missing("UNKNOWN") == "UNKNOWN"
    assert null_if_missing("NO") == "NO"


def _write_tiny_processed_files(directory, *, invalid_distance_foreign_key):
    directory.mkdir()
    rows = {
        "national_parks": {
            "park_id": "park-1",
            "name": "Park",
            "state_or_territory": "State",
            "latitude": "10",
            "longitude": "20",
            "established_date": "2000-01-01",
            "area_acres": "100",
            "recreation_visitors_2021": "50",
            "description": "Description",
        },
        "recreation_areas": {
            "RECAREAID": "area-1",
            "X": "20",
            "Y": "10",
            "RECAREANAME": "Area",
            "LONGITUDE": "20",
            "LATITUDE": "10",
            "RECAREAURL": "https://example.test/area",
            "OPEN_SEASON_START": "",
            "OPEN_SEASON_END": "",
            "FORESTNAME": "Forest",
            "MARKERTYPE": "",
            "MARKERACTIVITY": "",
            "MARKERACTIVITYGROUP": "",
            "RECAREADESCRIPTION": "Description",
            "SPOTLIGHTDISPLAY": "N",
            "ATTRACTIONDISPLAY": "N",
            "ACCESSIBILITY": "",
            "OPENSTATUS": "open",
            "SHAPE": "",
        },
        "activities": {
            "ACTIVITYID": "activity-1",
            "ACTIVITYNAME": "Hiking",
            "PARENTACTIVITYID": "parent-1",
            "PARENTACTIVITYNAME": "Outdoors",
        },
        "campgrounds": {
            "campground_id": "camp-1",
            "globalid": "camp-1",
            "site_cn": "01001",
            "site_id": "01001",
            "objectid": "object-1",
            "root_cn": "root-1",
            "parent_cn": "",
            "name": "Camp",
            "public_site_name": "Camp",
            "site_name": "Camp",
            "recarea_name": "Area",
            "site_subtype": "CAMPGROUND",
            "site_subtype_raw": "CAMPGROUND",
            "recarea_id": "area-1",
            "recid_extracted": "area-1",
            "fee_charged": "NO",
            "fee_charged_raw": "N",
            "fee_type": "",
            "fee_description": "",
            "total_capacity": "2",
            "total_capacity_raw": "2",
            "water_availability": "UNKNOWN",
            "water_availability_raw": "",
            "restroom_availability": "NONE",
            "restroom_availability_raw": "No restroom",
            "directions": "",
            "site_directions": "",
            "closest_towns": "",
            "operational_hours": "",
            "official_url": "https://example.test/camp",
            "usda_portal_url": "https://example.test/camp",
            "rec1stop_url": "",
            "latitude": "10",
            "longitude": "20",
            "last_update": "2026-01-01",
        },
        "recreation_area_activities": {
            "RECAREAID": "area-1",
            "ACTIVITYID": "activity-1",
        },
        "park_campground_distances": {
            "park_id": "park-1",
            "campground_id": "missing-camp"
            if invalid_distance_foreign_key
            else "camp-1",
            "distance_km": "1.5",
        },
    }
    for spec in TABLE_SPECS:
        with (directory / spec.csv_filename).open(
            "w", encoding="utf-8", newline=""
        ) as handle:
            writer = csv.DictWriter(handle, fieldnames=spec.csv_fields)
            writer.writeheader()
            writer.writerow(rows[spec.table_name])


def test_failed_load_rolls_back_and_removes_partial_database(tmp_path):
    processed_dir = tmp_path / "processed"
    database_path = tmp_path / "rollback.db"
    _write_tiny_processed_files(processed_dir, invalid_distance_foreign_key=True)

    with pytest.raises(DatabaseBuildError, match="FOREIGN KEY"):
        build_database(database_path, processed_dir=processed_dir)

    assert not database_path.exists()


def test_reset_refuses_environment_override_and_preserves_file(monkeypatch, tmp_path):
    protected_path = tmp_path / "not-the-default.db"
    protected_path.write_bytes(b"must remain")
    monkeypatch.setenv("CAMPSCOUT_DB_PATH", str(protected_path))

    with pytest.raises(DatabaseBuildError, match="restricted"):
        build_database(reset=True)

    assert protected_path.read_bytes() == b"must remain"


def test_all_six_processed_tables_load_with_csv_row_counts(built_database):
    database_path, row_counts = built_database
    expected_counts = {}
    for spec in TABLE_SPECS:
        with (PROCESSED_DIR / spec.csv_filename).open(
            "r", encoding="utf-8-sig", newline=""
        ) as handle:
            expected_counts[spec.table_name] = sum(1 for _ in csv.DictReader(handle))

    assert database_path.is_file()
    assert row_counts == expected_counts
    assert set(row_counts) == EXPECTED_TABLES


def test_validation_queries_pass_for_complete_database(built_database):
    database_path, row_counts = built_database

    result = validate_database(database_path, processed_dir=PROCESSED_DIR)

    assert result.row_counts == row_counts
    assert result.check_count >= 30
