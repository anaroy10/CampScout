import csv
import json
from pathlib import Path

import pytest

from etl.calculate_distances import EARTH_RADIUS_KM, haversine_km, run_calculation


def write_coordinates(path: Path, identifier_column: str, rows) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=(identifier_column, "latitude", "longitude")
        )
        writer.writeheader()
        writer.writerows(rows)


def read_csv(path: Path):
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def test_haversine_known_examples_and_antimeridian():
    assert EARTH_RADIUS_KM == 6371.0088
    assert haversine_km(36.12, -86.67, 33.94, -118.40) == pytest.approx(
        2886.44843, abs=0.001
    )
    assert haversine_km(0, 0, 0, 0) == pytest.approx(0)
    assert haversine_km(0, 179, 0, -179) == pytest.approx(222.39016, abs=0.001)


def test_output_cardinality_uses_every_valid_pair_and_is_sorted(tmp_path):
    parks = tmp_path / "input" / "parks.csv"
    campgrounds = tmp_path / "input" / "campgrounds.csv"
    processed = tmp_path / "processed"
    reports = tmp_path / "reports"
    write_coordinates(
        parks,
        "park_id",
        [
            {"park_id": "park-b", "latitude": "10", "longitude": "20"},
            {"park_id": "park-a", "latitude": "0", "longitude": "0"},
            {"park_id": "park-invalid", "latitude": "", "longitude": "0"},
        ],
    )
    write_coordinates(
        campgrounds,
        "campground_id",
        [
            {"campground_id": "camp-3", "latitude": "1", "longitude": "1"},
            {"campground_id": "camp-1", "latitude": "2", "longitude": "2"},
            {"campground_id": "camp-2", "latitude": "3", "longitude": "3"},
            {"campground_id": "camp-invalid", "latitude": "91", "longitude": "0"},
        ],
    )

    summary = run_calculation(parks, campgrounds, processed, reports)
    rows = read_csv(processed / "park_campground_distances.csv")
    with (reports / "distance_summary.json").open(encoding="utf-8") as handle:
        persisted_summary = json.load(handle)

    assert len(rows) == 2 * 3 == 6
    assert [(row["park_id"], row["campground_id"]) for row in rows] == [
        ("park-a", "camp-1"),
        ("park-a", "camp-2"),
        ("park-a", "camp-3"),
        ("park-b", "camp-1"),
        ("park-b", "camp-2"),
        ("park-b", "camp-3"),
    ]
    assert all(float(row["distance_km"]) >= 0 for row in rows)
    assert all(len(row["distance_km"].split(".")[1]) == 6 for row in rows)
    assert summary == persisted_summary
    assert summary["expected_pair_count"] == 6
    assert summary["distance_row_count"] == 6
    assert summary["invalid_park_coordinate_count"] == 1
    assert summary["invalid_campground_coordinate_count"] == 1
    assert summary["later_phases"] == {
        "sqlite_database": "implemented separately",
        "query_layer": "implemented separately",
        "streamlit": "not implemented",
    }
