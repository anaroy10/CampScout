import csv
import json
from pathlib import Path

import pytest

from etl.clean_activities import (
    ACTIVITY_COLUMNS,
    RECREATION_AREA_COLUMNS,
    SOURCE_COLUMNS,
    ActivityCleaningError,
    normalize_text,
    run_cleaning,
    validate_foreign_keys,
)


def write_source(path: Path, rows) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=SOURCE_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def read_csv(path: Path):
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def source_row(**values):
    return {column: values.get(column, "") for column in SOURCE_COLUMNS}


def test_normalize_text_decodes_entities_strips_html_and_keeps_boundaries():
    assert normalize_text(" <p>First&nbsp;line</p><p>Second &amp; last</p> ", strip_html=True) == (
        "First line Second & last"
    )


def test_run_cleaning_builds_entities_bridge_and_audit_reports(tmp_path):
    source = tmp_path / "raw" / "Recreation_Area_Activities.csv"
    processed = tmp_path / "processed"
    reports = tmp_path / "reports"
    write_source(
        source,
        [
            source_row(
                RECAREAID="010",
                ACTIVITYID="001",
                RECAREANAME="Zulu Area",
                ACTIVITYNAME="Picnicking",
                PARENTACTIVITYID="069",
                PARENTACTIVITYNAME="Day Use",
                OPEN_SEASON_START=" weather permitting ",
                RECAREADESCRIPTION="<p>A&nbsp;useful area.</p>",
                ACCESSIBILITY="<div>Ramp<br>available</div>",
            ),
            source_row(
                RECAREAID="010",
                ACTIVITYID="001",
                RECAREANAME="Alpha Area",
                ACTIVITYNAME="Picnicking",
                PARENTACTIVITYID="069",
                PARENTACTIVITYNAME="Day Use",
                OPEN_SEASON_START="weather   permitting",
                RECAREADESCRIPTION="A useful area.",
                ACCESSIBILITY="Ramp available",
            ),
            source_row(
                RECAREAID="010",
                ACTIVITYID="002",
                RECAREANAME="Zulu Area",
                ACTIVITYNAME="Picnicking",
                PARENTACTIVITYID="069",
                PARENTACTIVITYNAME="Day Use",
                OPEN_SEASON_START="weather permitting",
                RECAREADESCRIPTION="A useful area.",
                ACCESSIBILITY="Ramp available",
            ),
            source_row(
                RECAREAID="002",
                ACTIVITYID="003",
                RECAREANAME="Second Area",
                ACTIVITYNAME="Hiking",
            ),
            source_row(RECAREAID="010", RECAREANAME="Zulu Area"),
            source_row(ACTIVITYID="004", ACTIVITYNAME="Fishing"),
            source_row(),
        ],
    )

    summary = run_cleaning(source, processed, reports)

    areas = read_csv(processed / "recreation_areas.csv")
    activities = read_csv(processed / "activities.csv")
    relationships = read_csv(processed / "recreation_area_activities.csv")
    conflicts = read_csv(reports / "activity_conflicts.csv")
    dropped = read_csv(reports / "dropped_activity_rows.csv")

    assert list(areas[0]) == list(RECREATION_AREA_COLUMNS)
    assert list(activities[0]) == list(ACTIVITY_COLUMNS)
    assert [row["RECAREAID"] for row in areas] == ["002", "010"]
    assert [row["ACTIVITYID"] for row in activities] == ["001", "002", "003", "004"]
    assert areas[1]["RECAREANAME"] == "Zulu Area"
    assert areas[1]["OPEN_SEASON_START"] == "weather permitting"
    assert areas[1]["RECAREADESCRIPTION"] == "A useful area."
    assert areas[1]["ACCESSIBILITY"] == "Ramp available"
    assert relationships == [
        {"RECAREAID": "002", "ACTIVITYID": "003"},
        {"RECAREAID": "010", "ACTIVITYID": "001"},
        {"RECAREAID": "010", "ACTIVITYID": "002"},
    ]
    assert [row["drop_reason"] for row in dropped] == [
        "MISSING_ACTIVITYID",
        "MISSING_RECAREAID",
        "MISSING_RECAREAID_AND_ACTIVITYID",
    ]
    name_conflict = next(row for row in conflicts if row["source_column"] == "RECAREANAME")
    assert name_conflict["selected_value"] == "Zulu Area"
    assert json.loads(name_conflict["value_counts"]) == {
        "Zulu Area": 3,
        "Alpha Area": 1,
    }
    assert summary["duplicate_relationship_rows_removed"] == 1
    assert summary["dropped_relationship_source_row_count"] == 3
    assert summary["foreign_key_validation"] == "passed"
    assert summary["later_phases"] == {
        "sqlite_database": "implemented separately",
        "query_layer": "implemented separately",
        "streamlit": "not implemented",
    }
    assert json.loads((reports / "activity_cleaning_summary.json").read_text(encoding="utf-8")) == summary


def test_canonical_tie_break_is_casefolded_lexical(tmp_path):
    source = tmp_path / "source.csv"
    write_source(
        source,
        [
            source_row(RECAREAID="1", ACTIVITYID="1", RECAREANAME="Zulu", ACTIVITYNAME="Walk"),
            source_row(RECAREAID="1", ACTIVITYID="2", RECAREANAME="Alpha", ACTIVITYNAME="Swim"),
        ],
    )
    run_cleaning(source, tmp_path / "processed", tmp_path / "reports")
    areas = read_csv(tmp_path / "processed" / "recreation_areas.csv")
    assert areas[0]["RECAREANAME"] == "Alpha"


def test_missing_columns_fail_before_outputs_are_written(tmp_path):
    source = tmp_path / "source.csv"
    source.write_text("RECAREAID,ACTIVITYID\n1,2\n", encoding="utf-8")
    processed = tmp_path / "processed"
    reports = tmp_path / "reports"

    with pytest.raises(ActivityCleaningError, match="missing columns"):
        run_cleaning(source, processed, reports)

    assert not processed.exists()
    assert not reports.exists()


def test_foreign_key_validation_rejects_orphan_relationships():
    with pytest.raises(ActivityCleaningError, match="missing Activities"):
        validate_foreign_keys(
            [{"RECAREAID": "1"}],
            [{"ACTIVITYID": "10"}],
            [{"RECAREAID": "1", "ACTIVITYID": "11"}],
        )
