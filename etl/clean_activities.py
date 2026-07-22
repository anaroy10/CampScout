"""Clean Recreation Areas, Activities, and their many-to-many relationship.

This phase intentionally reads only ``data/raw/Recreation_Area_Activities.csv``.
Identifiers remain strings throughout the transformation.
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, MutableMapping, Optional, Sequence, Tuple

from bs4 import BeautifulSoup


SOURCE_PATH = Path("data/raw/Recreation_Area_Activities.csv")
PROCESSED_DIR = Path("data/processed")
REPORT_DIR = Path("reports/generated")

SOURCE_COLUMNS = (
    "X",
    "Y",
    "OBJECTID",
    "RECAREANAME",
    "LONGITUDE",
    "LATITUDE",
    "RECAREAURL",
    "OPEN_SEASON_START",
    "OPEN_SEASON_END",
    "FORESTNAME",
    "RECAREAID",
    "MARKERTYPE",
    "MARKERACTIVITY",
    "MARKERACTIVITYGROUP",
    "RECAREADESCRIPTION",
    "ACTIVITYDESCRIPTION",
    "PARENTACTIVITYNAME",
    "ACTIVITYNAME",
    "ACTIVITYID",
    "PARENTACTIVITYID",
    "SPOTLIGHTDISPLAY",
    "ATTRACTIONDISPLAY",
    "ACCESSIBILITY",
    "OPENSTATUS",
    "SHAPE",
)

# OBJECTID is row-grained and activity columns describe the other entities.
RECREATION_AREA_COLUMNS = (
    "RECAREAID",
    "X",
    "Y",
    "RECAREANAME",
    "LONGITUDE",
    "LATITUDE",
    "RECAREAURL",
    "OPEN_SEASON_START",
    "OPEN_SEASON_END",
    "FORESTNAME",
    "MARKERTYPE",
    "MARKERACTIVITY",
    "MARKERACTIVITYGROUP",
    "RECAREADESCRIPTION",
    "SPOTLIGHTDISPLAY",
    "ATTRACTIONDISPLAY",
    "ACCESSIBILITY",
    "OPENSTATUS",
    "SHAPE",
)
ACTIVITY_COLUMNS = (
    "ACTIVITYID",
    "ACTIVITYNAME",
    "PARENTACTIVITYID",
    "PARENTACTIVITYNAME",
)
RELATIONSHIP_COLUMNS = ("RECAREAID", "ACTIVITYID")
HTML_TEXT_COLUMNS = {"RECAREADESCRIPTION", "ACCESSIBILITY", "ACTIVITYDESCRIPTION"}
IDENTIFIER_COLUMNS = {"RECAREAID", "ACTIVITYID", "PARENTACTIVITYID"}

CONFLICT_COLUMNS = (
    "entity_type",
    "entity_id",
    "source_column",
    "selected_value",
    "selected_count",
    "distinct_non_blank_value_count",
    "value_counts",
)
DROPPED_PREFIX_COLUMNS = ("source_row_number", "drop_reason")


class ActivityCleaningError(RuntimeError):
    """An actionable error raised by the activity-cleaning phase."""


def _set_csv_field_size_limit() -> None:
    try:
        csv.field_size_limit(min(sys.maxsize, 2_147_483_647))
    except OverflowError:
        csv.field_size_limit(2_147_483_647)


def normalize_text(value: str, *, strip_html: bool = False) -> str:
    """Decode entities, optionally remove markup, and collapse whitespace."""

    decoded = html.unescape(value)
    if strip_html and decoded:
        decoded = BeautifulSoup(decoded, "html.parser").get_text(" ")
    return re.sub(r"\s+", " ", decoded).strip()


def _clean_value(column: str, value: Optional[str]) -> str:
    if value is None:
        return ""
    if column in IDENTIFIER_COLUMNS:
        # Keep identifier characters and leading zeroes; trim only surrounding
        # whitespace used by the CSV field itself.
        return value.strip()
    return normalize_text(value, strip_html=column in HTML_TEXT_COLUMNS)


def _choice_sort_key(item: Tuple[str, int]) -> Tuple[int, str, str]:
    value, count = item
    return (-count, value.casefold(), value)


def _canonical_value(counts: Counter[str]) -> Tuple[str, int]:
    if not counts:
        return "", 0
    return sorted(counts.items(), key=_choice_sort_key)[0]


def _build_entities(
    values_by_id: Mapping[str, Mapping[str, Counter[str]]],
    columns: Sequence[str],
    entity_type: str,
) -> Tuple[List[Dict[str, str]], List[Dict[str, object]]]:
    identifier_column = columns[0]
    entity_rows: List[Dict[str, str]] = []
    conflicts: List[Dict[str, object]] = []

    for entity_id in sorted(values_by_id):
        field_counts = values_by_id[entity_id]
        output_row = {identifier_column: entity_id}
        for column in columns[1:]:
            counts = field_counts.get(column, Counter())
            selected_value, selected_count = _canonical_value(counts)
            output_row[column] = selected_value
            if len(counts) > 1:
                ordered_counts = {
                    value: count
                    for value, count in sorted(counts.items(), key=_choice_sort_key)
                }
                conflicts.append(
                    {
                        "entity_type": entity_type,
                        "entity_id": entity_id,
                        "source_column": column,
                        "selected_value": selected_value,
                        "selected_count": selected_count,
                        "distinct_non_blank_value_count": len(counts),
                        "value_counts": json.dumps(
                            ordered_counts, ensure_ascii=False, separators=(",", ":")
                        ),
                    }
                )
        entity_rows.append(output_row)
    return entity_rows, conflicts


def validate_foreign_keys(
    recreation_areas: Iterable[Mapping[str, str]],
    activities: Iterable[Mapping[str, str]],
    relationships: Iterable[Mapping[str, str]],
) -> None:
    """Fail if a relationship references an entity absent from its output."""

    recreation_area_ids = {row["RECAREAID"] for row in recreation_areas}
    activity_ids = {row["ACTIVITYID"] for row in activities}
    missing_areas = sorted(
        {row["RECAREAID"] for row in relationships} - recreation_area_ids
    )
    missing_activities = sorted(
        {row["ACTIVITYID"] for row in relationships} - activity_ids
    )
    if missing_areas or missing_activities:
        details = []
        if missing_areas:
            details.append(f"missing Recreation Areas: {missing_areas[:5]}")
        if missing_activities:
            details.append(f"missing Activities: {missing_activities[:5]}")
        raise ActivityCleaningError(
            "Foreign-key validation failed (" + "; ".join(details) + ")"
        )


def _write_csv(
    path: Path, rows: Iterable[Mapping[str, object]], fieldnames: Sequence[str]
) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="raise")
        writer.writeheader()
        writer.writerows(rows)


def _write_json(path: Path, value: Mapping[str, object]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def run_cleaning(
    source_path: Path = SOURCE_PATH,
    processed_dir: Path = PROCESSED_DIR,
    report_dir: Path = REPORT_DIR,
) -> Dict[str, object]:
    """Clean the activity source and write all entity and audit artifacts."""

    _set_csv_field_size_limit()
    if not source_path.is_file():
        raise ActivityCleaningError(
            f"Required raw CSV file is missing: {source_path.as_posix()}"
        )

    area_values: MutableMapping[str, MutableMapping[str, Counter[str]]] = defaultdict(
        lambda: defaultdict(Counter)
    )
    activity_values: MutableMapping[
        str, MutableMapping[str, Counter[str]]
    ] = defaultdict(lambda: defaultdict(Counter))
    relationship_counts: Counter[Tuple[str, str]] = Counter()
    dropped_rows: List[Dict[str, str]] = []
    source_row_count = 0

    try:
        with source_path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames is None:
                raise ActivityCleaningError(
                    f"Raw CSV has no header: {source_path.as_posix()}"
                )
            missing_columns = [
                column for column in SOURCE_COLUMNS if column not in reader.fieldnames
            ]
            unexpected_columns = [
                column for column in reader.fieldnames if column not in SOURCE_COLUMNS
            ]
            if missing_columns or unexpected_columns:
                parts = []
                if missing_columns:
                    parts.append("missing columns: " + ", ".join(missing_columns))
                if unexpected_columns:
                    parts.append("unexpected columns: " + ", ".join(unexpected_columns))
                raise ActivityCleaningError(
                    f"Source schema mismatch in {source_path.as_posix()} ("
                    + "; ".join(parts)
                    + ")"
                )

            for source_row_number, raw_row in enumerate(reader, start=2):
                source_row_count += 1
                if None in raw_row:
                    raise ActivityCleaningError(
                        f"Row {source_row_number} has more fields than the header"
                    )
                cleaned = {
                    column: _clean_value(column, raw_row.get(column))
                    for column in SOURCE_COLUMNS
                }
                recreation_area_id = cleaned["RECAREAID"]
                activity_id = cleaned["ACTIVITYID"]

                if recreation_area_id:
                    for column in RECREATION_AREA_COLUMNS[1:]:
                        value = cleaned[column]
                        if value:
                            area_values[recreation_area_id][column][value] += 1

                if activity_id:
                    for column in ACTIVITY_COLUMNS[1:]:
                        value = cleaned[column]
                        if value:
                            activity_values[activity_id][column][value] += 1

                if recreation_area_id and activity_id:
                    relationship_counts[(recreation_area_id, activity_id)] += 1
                else:
                    if not recreation_area_id and not activity_id:
                        reason = "MISSING_RECAREAID_AND_ACTIVITYID"
                    elif not recreation_area_id:
                        reason = "MISSING_RECAREAID"
                    else:
                        reason = "MISSING_ACTIVITYID"
                    dropped_rows.append(
                        {
                            "source_row_number": str(source_row_number),
                            "drop_reason": reason,
                            **{column: raw_row.get(column, "") for column in SOURCE_COLUMNS},
                        }
                    )
    except UnicodeDecodeError as exc:
        raise ActivityCleaningError(
            f"Cannot decode {source_path.as_posix()} as UTF-8: {exc}"
        ) from exc
    except csv.Error as exc:
        raise ActivityCleaningError(
            f"Cannot parse {source_path.as_posix()} as CSV: {exc}"
        ) from exc

    recreation_areas, area_conflicts = _build_entities(
        area_values, RECREATION_AREA_COLUMNS, "recreation_area"
    )
    activities, activity_conflicts = _build_entities(
        activity_values, ACTIVITY_COLUMNS, "activity"
    )
    relationships = [
        {"RECAREAID": recreation_area_id, "ACTIVITYID": activity_id}
        for recreation_area_id, activity_id in sorted(relationship_counts)
    ]
    conflicts = sorted(
        area_conflicts + activity_conflicts,
        key=lambda row: (
            str(row["entity_type"]),
            str(row["entity_id"]),
            str(row["source_column"]),
        ),
    )
    dropped_rows.sort(key=lambda row: int(row["source_row_number"]))

    validate_foreign_keys(recreation_areas, activities, relationships)
    if len(relationships) != len(relationship_counts):
        raise ActivityCleaningError("Relationship deduplication validation failed")

    duplicate_relationship_rows_removed = sum(
        count - 1 for count in relationship_counts.values()
    )
    summary: Dict[str, object] = {
        "source_file": source_path.as_posix(),
        "source_row_count": source_row_count,
        "recreation_area_row_count": len(recreation_areas),
        "activity_row_count": len(activities),
        "recreation_area_activity_row_count": len(relationships),
        "dropped_relationship_source_row_count": len(dropped_rows),
        "duplicate_relationship_rows_removed": duplicate_relationship_rows_removed,
        "conflict_count": len(conflicts),
        "recreation_area_conflict_count": len(area_conflicts),
        "activity_conflict_count": len(activity_conflicts),
        "foreign_key_validation": "passed",
        "later_phases": {
            "sqlite_database": "implemented separately",
            "query_layer": "implemented separately",
            "streamlit": "not implemented",
        },
    }

    processed_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)
    _write_csv(
        processed_dir / "recreation_areas.csv",
        recreation_areas,
        RECREATION_AREA_COLUMNS,
    )
    _write_csv(processed_dir / "activities.csv", activities, ACTIVITY_COLUMNS)
    _write_csv(
        processed_dir / "recreation_area_activities.csv",
        relationships,
        RELATIONSHIP_COLUMNS,
    )
    _write_csv(report_dir / "activity_conflicts.csv", conflicts, CONFLICT_COLUMNS)
    _write_csv(
        report_dir / "dropped_activity_rows.csv",
        dropped_rows,
        DROPPED_PREFIX_COLUMNS + SOURCE_COLUMNS,
    )
    _write_json(report_dir / "activity_cleaning_summary.json", summary)
    return summary


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Clean Recreation Areas, Activities, and their relationship."
    )
    parser.add_argument("--source", type=Path, default=SOURCE_PATH)
    parser.add_argument("--processed-dir", type=Path, default=PROCESSED_DIR)
    parser.add_argument("--report-dir", type=Path, default=REPORT_DIR)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        summary = run_cleaning(args.source, args.processed_dir, args.report_dir)
    except ActivityCleaningError as exc:
        print(f"Activity cleaning failed: {exc}", file=sys.stderr)
        return 1

    print("Activity cleaning completed.")
    print(f"- Recreation Areas: {summary['recreation_area_row_count']}")
    print(f"- Activities: {summary['activity_row_count']}")
    print(
        "- Recreation Area-Activity relationships: "
        f"{summary['recreation_area_activity_row_count']}"
    )
    print(
        "- Dropped relationship source rows: "
        f"{summary['dropped_relationship_source_row_count']}"
    )
    print("Build/query layers are separate; the Streamlit interface is not implemented.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
