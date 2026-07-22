import csv
import json
from pathlib import Path

import pytest

from etl.clean_campgrounds import (
    CAMPGROUND_COLUMNS,
    REQUIRED_SOURCE_COLUMNS,
    CampgroundCleaningError,
    choose_display_name,
    convert_fee,
    extract_recid,
    find_duplicate_candidates,
    normalize_restroom,
    normalize_site_subtype,
    normalize_water,
    parse_total_capacity,
    run_cleaning,
    validate_coordinates,
)


def source_row(**values):
    defaults = {
        "globalid": "{00000000-0000-0000-0000-000000000001}",
        "site_cn": "00001",
        "site_id": "01001",
        "site_name": "Source Camp",
        "site_subtype": "CAMPGROUND",
        "fee_charged": "N",
        "total_capacity": "20",
        "latitude": "40.0",
        "longitude": "-105.0",
    }
    defaults.update(values)
    return {column: defaults.get(column, "") for column in REQUIRED_SOURCE_COLUMNS}


def write_source(path: Path, rows) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=REQUIRED_SOURCE_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def write_recreation_areas(path: Path, ids=("00123",)) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=("RECAREAID", "RECAREANAME"))
        writer.writeheader()
        for recarea_id in ids:
            writer.writerow({"RECAREAID": recarea_id, "RECAREANAME": "Area"})


def read_csv(path: Path):
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def run_fixture(tmp_path: Path, rows, area_ids=("00123",)):
    source = tmp_path / "raw" / "sites.csv"
    recreation_areas = tmp_path / "processed-input" / "recreation_areas.csv"
    processed = tmp_path / "processed"
    reports = tmp_path / "reports"
    write_source(source, rows)
    write_recreation_areas(recreation_areas, area_ids)
    summary = run_cleaning(source, recreation_areas, processed, reports)
    return summary, processed, reports


def test_subtype_normalization_and_filtering_are_exact(tmp_path):
    assert normalize_site_subtype("  group   campground ") == "GROUP CAMPGROUND"
    summary, processed, reports = run_fixture(
        tmp_path,
        [
            source_row(site_subtype=" campground "),
            source_row(
                globalid="{00000000-0000-0000-0000-000000000002}",
                site_subtype="CAMPING AREA",
            ),
        ],
    )
    rows = read_csv(processed / "campgrounds.csv")
    dropped = read_csv(reports / "dropped_campground_rows.csv")
    assert len(rows) == 1
    assert rows[0]["site_subtype"] == "CAMPGROUND"
    assert dropped[0]["drop_category"] == "UNSUPPORTED_SITE_SUBTYPE"
    assert summary["dropped_row_count"] == 1


def test_display_name_uses_required_priority_and_ignores_blank_values():
    assert choose_display_name(" Public ", "Site", "Area") == "Public"
    assert choose_display_name(" \t", " Site ", "Area") == "Site"
    assert choose_display_name("", "", " Area ") == "Area"
    assert choose_display_name("", "", "") == ""


def test_identifier_text_is_preserved_without_float_coercion(tmp_path):
    summary, processed, _ = run_fixture(
        tmp_path,
        [source_row(site_cn="00001", site_id="01001")],
    )
    row = read_csv(processed / "campgrounds.csv")[0]
    assert row["site_cn"] == "00001"
    assert row["site_id"] == "01001"
    assert not row["campground_id"].endswith(".0")
    assert summary["unique_identifier_count"] == 1


def test_duplicate_or_float_suffixed_primary_identifiers_fail(tmp_path):
    duplicate_rows = [
        source_row(),
        source_row(site_cn="00002", site_id="01002"),
    ]
    with pytest.raises(CampgroundCleaningError, match="not unique"):
        run_fixture(tmp_path / "duplicate", duplicate_rows)

    with pytest.raises(CampgroundCleaningError, match=r"\.0 suffix"):
        run_fixture(
            tmp_path / "suffix",
            [source_row(globalid="123.0")],
        )


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Yes, drinking water is available", "AVAILABLE"),
        ("No potable water available", "NOT_AVAILABLE"),
        ("Water can be treated or filtered from a nearby creek", "NEARBY"),
        ("Untreated creek water", "NATURAL_SOURCE"),
        ("Available at a nearby campground", "NEARBY"),
        ("Water is currently unavailable", "NOT_AVAILABLE"),
        ("Yes.", "AVAILABLE"),
        ("Non-potable available for livestock", "OTHER"),
        ("A seasonal situation may apply", "UNKNOWN"),
        ("", "UNKNOWN"),
        (None, "UNKNOWN"),
    ],
)
def test_water_normalization(raw, expected):
    assert normalize_water(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Flush toilet(s)", "FLUSH"),
        ("Vault toilet(s)", "VAULT"),
        ("Composting toilet", "COMPOSTING"),
        ("Portable toilet(s)", "PORTABLE"),
        ("Flush and vault toilets", "MULTIPLE"),
        ("No restroom available", "NONE"),
        ("Restrooms available nearby", "OTHER"),
        ("", "UNKNOWN"),
        (None, "UNKNOWN"),
    ],
)
def test_restroom_normalization(raw, expected):
    assert normalize_restroom(raw) == expected


def test_recid_extraction_uses_only_query_parameter_and_preserves_zeroes():
    assert extract_recid("https://www.fs.usda.gov/x?recid=00123&actid=29") == "00123"
    assert extract_recid("www.fs.usda.gov/x?RECID=00456") == "00456"
    assert extract_recid("https://www.fs.usda.gov/recid/00123") == ""
    assert extract_recid("") == ""


def test_recreation_area_validation_retains_unmatched_campgrounds(tmp_path):
    summary, processed, reports = run_fixture(
        tmp_path,
        [
            source_row(usda_portal_url="https://fs.usda.gov/x?recid=00123"),
            source_row(
                globalid="{00000000-0000-0000-0000-000000000002}",
                site_cn="00002",
                usda_portal_url="https://fs.usda.gov/x?recid=99999",
            ),
            source_row(
                globalid="{00000000-0000-0000-0000-000000000003}",
                site_cn="00003",
                usda_portal_url="",
            ),
        ],
    )
    rows = read_csv(processed / "campgrounds.csv")
    unmatched = read_csv(reports / "unmatched_campgrounds.csv")
    assert [row["recarea_id"] for row in rows] == ["00123", "", ""]
    assert len(rows) == 3
    assert len(unmatched) == 2
    assert summary["validated_recarea_link_count"] == 1
    assert summary["unmatched_recarea_link_count"] == 2


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("Y", "YES"), (" n ", "NO"), ("", "UNKNOWN"), ("maybe", "UNKNOWN")],
)
def test_fee_conversion_is_unambiguous(raw, expected):
    assert convert_fee(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("42", "42"), ("42.50", "42.5"), ("0", "0"), ("about 20", ""), ("1e3", "")],
)
def test_capacity_parsing_accepts_only_plain_nonnegative_numbers(raw, expected):
    assert parse_total_capacity(raw) == expected


def test_coordinate_validation_and_invalid_row_audit(tmp_path):
    assert validate_coordinates("-90", "180") == (-90.0, 180.0)
    with pytest.raises(CampgroundCleaningError, match="Invalid coordinates"):
        validate_coordinates("91", "0")

    summary, processed, reports = run_fixture(
        tmp_path,
        [source_row(latitude="91")],
    )
    assert read_csv(processed / "campgrounds.csv") == []
    dropped = read_csv(reports / "dropped_campground_rows.csv")
    assert dropped[0]["drop_category"] == "INVALID_REQUIRED_DATA"
    assert dropped[0]["drop_reason"] == "INVALID_LATITUDE"
    assert summary["final_campground_row_count"] == 0


def test_duplicate_candidates_require_normalized_name_and_proximity():
    rows = [
        {
            "campground_id": "1",
            "name": "Pine-Camp",
            "latitude": "40.0000",
            "longitude": "-105.0000",
        },
        {
            "campground_id": "2",
            "name": "pine camp",
            "latitude": "40.0005",
            "longitude": "-105.0005",
        },
        {
            "campground_id": "3",
            "name": "Pine Camp",
            "latitude": "42.0",
            "longitude": "-105.0",
        },
    ]
    candidates = find_duplicate_candidates(rows)
    assert len(candidates) == 1
    assert candidates[0]["campground_id_1"] == "1"
    assert candidates[0]["campground_id_2"] == "2"
    assert float(candidates[0]["distance_km"]) < 1


def test_generated_schema_and_subset_statistics_use_final_denominator(tmp_path):
    summary, processed, reports = run_fixture(
        tmp_path,
        [
            source_row(
                water_availability="",
                restroom_availability="Vault toilet",
                directions="",
                usda_portal_url="https://fs.usda.gov/x?recid=00123",
            ),
            source_row(
                globalid="{00000000-0000-0000-0000-000000000002}",
                site_cn="00002",
                water_availability="Potable water available",
                restroom_availability="",
                directions="Go north",
            ),
            source_row(
                globalid="{00000000-0000-0000-0000-000000000003}",
                site_subtype="TRAILHEAD",
            ),
        ],
    )
    rows = read_csv(processed / "campgrounds.csv")
    assert list(rows[0]) == list(CAMPGROUND_COLUMNS)
    assert summary["final_campground_row_count"] == 2
    assert summary["campground_subset_missingness"]["water_availability"] == {
        "missing_count": 1,
        "missing_percentage": 50.0,
    }
    assert summary["campground_subset_missingness"]["directions"]["missing_percentage"] == 50.0
    assert summary["water_category_counts"]["UNKNOWN"] == 1
    assert summary["restroom_category_counts"]["UNKNOWN"] == 1
    written = json.loads(
        (reports / "campground_cleaning_summary.json").read_text(encoding="utf-8")
    )
    assert written == summary
