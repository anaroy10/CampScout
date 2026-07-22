import csv
import json
from decimal import Decimal
from pathlib import Path

import pytest

from etl.clean_parks import (
    AREA_COLUMN,
    DATE_COLUMN,
    REQUIRED_SOURCE_COLUMNS,
    VISITORS_COLUMN,
    ParkCleaningError,
    clean_park_name,
    make_park_id,
    parse_acreage,
    parse_coordinates,
    parse_date,
    parse_location,
    parse_visitors,
    remove_citation_markers,
    run_cleaning,
)


def source_row(**values):
    defaults = {
        "Name": "Example Park *",
        "Image": "",
        "Location": "Example State44°21′N 68°13′W / 44.35°N 68.21°W",
        DATE_COLUMN: "February 26, 1919",
        AREA_COLUMN: "49,071.40 acres (198.6 km2)",
        VISITORS_COLUMN: "4,069,098",
        "Description": "Useful text.[14] More text.[15]",
    }
    defaults.update(values)
    return {column: defaults.get(column, "") for column in REQUIRED_SOURCE_COLUMNS}


def write_source(path: Path, rows) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=("",) + REQUIRED_SOURCE_COLUMNS)
        writer.writeheader()
        for index, row in enumerate(rows):
            writer.writerow({"": str(index), **row})


def read_csv(path: Path):
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def test_coordinate_parsing_uses_decimal_pair_and_removes_css_from_location():
    raw = (
        "Maine.mw-parser-output .geo-default{display:inline}"
        "44°21′N 68°13′W / 44.35°N 68.21°W"
    )
    assert parse_coordinates(raw) == pytest.approx((44.35, -68.21))
    label, latitude, longitude = parse_location(raw)
    assert label == "Maine"
    assert (latitude, longitude) == pytest.approx((44.35, -68.21))


def test_location_returns_clean_label_and_dms_coordinates_when_decimal_is_absent():
    label, latitude, longitude = parse_location(
        "<b>South Pacific</b> 14°15′S 170°41′E"
    )
    assert label == "South Pacific"
    assert latitude == pytest.approx(-14.25)
    assert longitude == pytest.approx(170 + 41 / 60)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("10.5°N 20.25°E", (10.5, 20.25)),
        ("10.5°N 20.25°W", (10.5, -20.25)),
        ("10.5°S 20.25°E", (-10.5, 20.25)),
        ("10.5°S 20.25°W", (-10.5, -20.25)),
    ],
)
def test_coordinate_directions_apply_all_latitude_and_longitude_signs(raw, expected):
    assert parse_coordinates(raw) == pytest.approx(expected)


def test_date_acreage_and_visitors_parsing():
    assert parse_date("December 20, 2019[112]") == "2019-12-20"
    assert parse_date("not a date") is None
    assert parse_acreage("49,071.40 acres (198.6 km2)") == Decimal("49071.40")
    assert parse_acreage("unknown") is None
    assert parse_visitors("4,069,098") == 4069098
    assert parse_visitors("12.5") is None


def test_name_and_description_cleanup_are_narrow_and_identifier_is_stable():
    assert clean_park_name(" Wrangell–St.\xa0Elias * ") == "Wrangell–St. Elias"
    assert remove_citation_markers("First.[14] Second [15].") == "First. Second ."
    assert make_park_id(" Example   Park ") == make_park_id("example park")


def test_run_cleaning_publishes_clean_rows_summary_and_failure_report(tmp_path):
    source = tmp_path / "raw" / "parks.csv"
    processed = tmp_path / "processed"
    reports = tmp_path / "reports"
    write_source(
        source,
        [
            source_row(),
            source_row(
                Name="Broken Coordinates",
                Location="Somewhere without coordinates",
                **{DATE_COLUMN: "bad", AREA_COLUMN: "bad", VISITORS_COLUMN: "bad"},
            ),
        ],
    )

    summary = run_cleaning(source, processed, reports)
    parks = read_csv(processed / "national_parks.csv")
    failures = read_csv(reports / "park_parse_failures.csv")
    with (reports / "park_cleaning_summary.json").open(encoding="utf-8") as handle:
        persisted_summary = json.load(handle)

    assert [row["name"] for row in parks] == ["Broken Coordinates", "Example Park"]
    assert "" not in parks[0]
    assert "Image" not in parks[0]
    assert parks[1]["state_or_territory"] == "Example State"
    assert parks[1]["established_date"] == "1919-02-26"
    assert parks[1]["area_acres"] == "49071.40"
    assert parks[1]["recreation_visitors_2021"] == "4069098"
    assert "[14]" not in parks[1]["description"]
    assert len(failures) == 4
    assert summary == persisted_summary
    assert summary["source_row_count"] == 2
    assert summary["valid_coordinate_park_count"] == 1
    assert summary["removed_unnamed_columns"] == [""]
    assert summary["excluded_fully_empty_columns"] == ["Image"]
    assert summary["later_phases"] == {
        "sqlite_database": "implemented separately",
        "query_layer": "implemented separately",
        "streamlit": "not implemented",
    }


def test_nonempty_image_column_requires_schema_review(tmp_path):
    source = tmp_path / "parks.csv"
    write_source(source, [source_row(Image="unexpected.jpg")])
    with pytest.raises(ParkCleaningError, match="no longer fully empty"):
        run_cleaning(source, tmp_path / "processed", tmp_path / "reports")
