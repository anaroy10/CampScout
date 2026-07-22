import csv
import json
from pathlib import Path

import pytest

from etl.profile_raw_data import (
    ACTIVITY_AREA_ATTRIBUTES,
    PARK_EXAMPLE_COLUMNS,
    SITE_KEY_COLUMNS,
    SITE_MISSINGNESS_COLUMNS,
    ProfilingError,
    profile_dataset,
    run_profiling,
)


def write_csv(path: Path, header, rows) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)


def test_profile_dataset_preserves_identifiers_and_exact_statistics(tmp_path):
    path = tmp_path / "sample.csv"
    write_csv(
        path,
        ["site_id", "quantity", "note"],
        [
            ["01001", "1", "alpha"],
            ["01001", "1", "alpha"],
            ["2", "2", " "],
            ["3", "", "beta"],
        ],
    )

    result = profile_dataset(path)
    columns = {row["column_name"]: row for row in result.column_profiles}

    assert result.summary["row_count"] == 4
    assert result.summary["column_count"] == 3
    assert result.summary["exact_duplicate_row_count"] == 1
    assert result.summary["exact_duplicate_group_count"] == 1
    assert columns["site_id"]["inferred_data_type"] == "string"
    assert columns["site_id"]["sample_non_null_values"].startswith('["01001"')
    assert columns["quantity"]["missing_count"] == 1
    assert columns["note"]["missing_count"] == 1
    assert columns["note"]["distinct_count"] == 2
    assert columns["note"]["maximum_text_length"] == 5


def test_profile_dataset_reports_unreadable_utf8(tmp_path):
    path = tmp_path / "bad.csv"
    path.write_bytes(b"name\ninvalid-\xff\n")

    with pytest.raises(ProfilingError, match="Cannot decode .* as UTF-8"):
        profile_dataset(path)


def test_profile_dataset_reports_missing_file(tmp_path):
    with pytest.raises(ProfilingError, match="Required raw CSV file is missing"):
        profile_dataset(tmp_path / "missing.csv")


def test_run_profiling_generates_all_reports_from_fixture_data(tmp_path):
    raw_dir = tmp_path / "raw"
    report_dir = tmp_path / "reports"

    site_header = list(
        dict.fromkeys(
            list(SITE_KEY_COLUMNS)
            + list(SITE_MISSINGNESS_COLUMNS)
            + ["site_subtype", "site_name"]
        )
    )

    def site_row(**values):
        return [values.get(name, "") for name in site_header]

    write_csv(
        raw_dir / "Recreation_Sites_INFRA.csv",
        site_header,
        [
            site_row(
                site_cn="1",
                globalid="g1",
                objectid="o1",
                site_id="010",
                site_subtype="CAMPGROUND",
                site_name="One",
                latitude="1.0",
                longitude="2.0",
                water_availability="Potable",
            ),
            site_row(
                site_cn="2",
                globalid="g2",
                objectid="o2",
                site_id="010",
                site_subtype="GROUP CAMPGROUND",
                site_name="Two",
                latitude="1.1",
                longitude="2.1",
                restroom_availability="Vault",
            ),
            site_row(
                site_cn="3",
                globalid="g3",
                objectid="o3",
                site_id="011",
                site_subtype="HORSE CAMP",
                site_name="Three",
                latitude="1.2",
                longitude="2.2",
            ),
        ],
    )

    activity_header = list(
        dict.fromkeys(
            ["RECAREAID", "ACTIVITYID", "ACTIVITYNAME"]
            + list(ACTIVITY_AREA_ATTRIBUTES)
        )
    )

    def activity_row(**values):
        return [values.get(name, "") for name in activity_header]

    write_csv(
        raw_dir / "Recreation_Area_Activities.csv",
        activity_header,
        [
            activity_row(
                RECAREAID="100",
                ACTIVITYID="01",
                ACTIVITYNAME="Hiking",
                RECAREANAME="Area A",
            ),
            activity_row(
                RECAREAID="100",
                ACTIVITYID="02",
                ACTIVITYNAME="Hiking",
                RECAREANAME="Area A changed",
            ),
            activity_row(RECAREAID="101", RECAREANAME="Area B"),
        ],
    )

    park_header = ["", "Name", "Image"] + list(PARK_EXAMPLE_COLUMNS)

    def park_row(**values):
        return [values.get(name, "") for name in park_header]

    write_csv(
        raw_dir / "national_parks_raw.csv",
        park_header,
        [
            park_row(
                **{
                    "": "0",
                    "Name": "Example*",
                    "Location": "State 1°N 2°W",
                    "Area (2021)[13]": "10 acres",
                    "Date established as park[7][12]": "January 1, 2000",
                    "Recreation visitors (2021)[11]": "1000",
                }
            )
        ],
    )

    summary = run_profiling(raw_dir, report_dir)

    assert summary["datasets"]["Recreation_Sites_INFRA.csv"]["special_analysis"][
        "selected_subtype_combined_count"
    ] == 3
    activity = summary["datasets"]["Recreation_Area_Activities.csv"]["special_analysis"]
    assert activity["rows_missing_either_identifier"] == 1
    assert activity["activity_name_to_multiple_ids_count"] == 1
    assert activity["recreation_area_attribute_conflicts"]["RECAREANAME"][
        "conflicting_recarea_count"
    ] == 1
    parks = summary["datasets"]["national_parks_raw.csv"]["special_analysis"]
    assert parks["empty_columns"] == ["Image"]
    assert parks["names_with_stars_count"] == 1

    expected_reports = {
        "profile_summary.json",
        "column_profiles.csv",
        "key_analysis.csv",
        "value_examples.json",
        "data_quality_findings.md",
    }
    assert {path.name for path in report_dir.iterdir()} == expected_reports
    parsed = json.loads((report_dir / "profile_summary.json").read_text(encoding="utf-8"))
    assert parsed["datasets"]["national_parks_raw.csv"]["row_count"] == 1


def test_run_profiling_fails_before_writing_when_an_input_is_missing(tmp_path):
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    report_dir = tmp_path / "reports"

    with pytest.raises(ProfilingError, match="Recreation_Sites_INFRA.csv"):
        run_profiling(raw_dir, report_dir)

    assert not report_dir.exists()
