"""Clean the national-park source into deterministic processed records.

The raw file is a scraped table.  This phase removes presentation-only
columns, cleans text, parses typed values, and records every parse failure
without inventing replacements.
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import math
import re
import sys
import uuid
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple


SOURCE_PATH = Path("data/raw/national_parks_raw.csv")
PROCESSED_DIR = Path("data/processed")
REPORT_DIR = Path("reports/generated")

DATE_COLUMN = "Date established as park[7][12]"
AREA_COLUMN = "Area (2021)[13]"
VISITORS_COLUMN = "Recreation visitors (2021)[11]"
REQUIRED_SOURCE_COLUMNS = (
    "Name",
    "Image",
    "Location",
    DATE_COLUMN,
    AREA_COLUMN,
    VISITORS_COLUMN,
    "Description",
)
PARK_COLUMNS = (
    "park_id",
    "name",
    "state_or_territory",
    "latitude",
    "longitude",
    "established_date",
    "area_acres",
    "recreation_visitors_2021",
    "description",
)
FAILURE_COLUMNS = (
    "source_row_number",
    "park_id",
    "park_name",
    "source_field",
    "raw_value",
    "failure_reason",
)

PARK_ID_NAMESPACE = uuid.NAMESPACE_URL
PARK_ID_PREFIX = "https://campscout.local/national-park/"

_SPACE_RE = re.compile(r"\s+")
_CITATION_RE = re.compile(r"\[\s*\d+(?:\s*[\u2013-]\s*\d+)?\s*\]")
_TRAILING_STAR_RE = re.compile(r"\s*\*+\s*$")
_STYLE_RE = re.compile(r"<style\b[^>]*>.*?</style\s*>", re.IGNORECASE | re.DOTALL)
_SCRIPT_RE = re.compile(r"<script\b[^>]*>.*?</script\s*>", re.IGNORECASE | re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")
_COORDINATE_START_RE = re.compile(r"(?<!\d)\d{1,2}\s*\u00b0")
_DECIMAL_PAIR_RE = re.compile(
    r"(?P<lat>\d{1,2}(?:\.\d+)?)\s*\u00b0\s*(?P<lat_dir>[NS])"
    r"\s*[,;/]?\s*"
    r"(?P<lon>\d{1,3}(?:\.\d+)?)\s*\u00b0\s*(?P<lon_dir>[EW])",
    re.IGNORECASE,
)
_DMS_PAIR_RE = re.compile(
    r"(?P<lat_deg>\d{1,2})\s*\u00b0\s*"
    r"(?P<lat_min>\d{1,2})(?:\s*[\u2032'])"
    r"(?:\s*(?P<lat_sec>\d{1,2}(?:\.\d+)?)\s*[\u2033\"])?\s*"
    r"(?P<lat_dir>[NS])\s*[,;/]?\s*"
    r"(?P<lon_deg>\d{1,3})\s*\u00b0\s*"
    r"(?P<lon_min>\d{1,2})(?:\s*[\u2032'])"
    r"(?:\s*(?P<lon_sec>\d{1,2}(?:\.\d+)?)\s*[\u2033\"])?\s*"
    r"(?P<lon_dir>[EW])",
    re.IGNORECASE,
)
_ACREAGE_RE = re.compile(
    r"(?P<value>\d[\d,]*(?:\.\d+)?)\s*acres?\b", re.IGNORECASE
)
_VISITOR_RE = re.compile(r"^\d[\d,]*$")


class ParkCleaningError(RuntimeError):
    """An actionable failure raised by the national-park cleaning phase."""


def normalize_text(value: Optional[str]) -> str:
    """Decode entities and normalize spaces, non-breaking spaces, and BOMs."""

    decoded = html.unescape(value or "").replace("\ufeff", " ").replace("\xa0", " ")
    return _SPACE_RE.sub(" ", decoded).strip()


def clean_park_name(value: Optional[str]) -> str:
    """Normalize a park name and remove only trailing marker stars."""

    return _TRAILING_STAR_RE.sub("", normalize_text(value)).strip()


def remove_citation_markers(value: Optional[str]) -> str:
    """Remove numeric bracket citations while preserving descriptive text."""

    return normalize_text(_CITATION_RE.sub("", value or ""))


def make_park_id(name: str) -> str:
    """Return a stable UUIDv5 based on the normalized cleaned park name."""

    identity = normalize_text(name).casefold()
    if not identity:
        return ""
    return str(uuid.uuid5(PARK_ID_NAMESPACE, PARK_ID_PREFIX + identity))


def parse_date(value: Optional[str]) -> Optional[str]:
    """Parse a citation-free full month date to ISO ``YYYY-MM-DD``."""

    text = remove_citation_markers(value)
    if not text:
        return None
    try:
        return datetime.strptime(text, "%B %d, %Y").date().isoformat()
    except ValueError:
        return None


def parse_acreage(value: Optional[str]) -> Optional[Decimal]:
    """Extract the non-negative numeric acres value from the area field."""

    text = normalize_text(value)
    match = _ACREAGE_RE.search(text)
    if not match:
        return None
    try:
        acreage = Decimal(match.group("value").replace(",", ""))
    except InvalidOperation:
        return None
    if not acreage.is_finite() or acreage < 0:
        return None
    return acreage


def parse_visitors(value: Optional[str]) -> Optional[int]:
    """Parse a non-negative integer visitor count without coercing decimals."""

    text = normalize_text(value)
    if not text or not _VISITOR_RE.fullmatch(text):
        return None
    try:
        return int(text.replace(",", ""))
    except ValueError:
        return None


def _clean_location_label(value: str) -> str:
    text = html.unescape(value or "")
    text = _STYLE_RE.sub(" ", text)
    text = _SCRIPT_RE.sub(" ", text)
    text = _TAG_RE.sub(" ", text)
    css_start = text.find(".mw-parser-output")
    if css_start >= 0:
        text = text[:css_start]
    return normalize_text(text).strip(" ,;/")


def _directed_coordinate(value: float, direction: str) -> float:
    magnitude = abs(value)
    return -magnitude if direction.upper() in {"S", "W"} else magnitude


def _validate_coordinate_pair(latitude: float, longitude: float) -> bool:
    return (
        math.isfinite(latitude)
        and math.isfinite(longitude)
        and -90.0 <= latitude <= 90.0
        and -180.0 <= longitude <= 180.0
    )


def parse_coordinates(value: Optional[str]) -> Optional[Tuple[float, float]]:
    """Extract decimal coordinates, falling back to DMS when necessary."""

    text = normalize_text(value)
    decimal_matches = list(_DECIMAL_PAIR_RE.finditer(text))
    if decimal_matches:
        match = decimal_matches[-1]
        latitude = _directed_coordinate(float(match.group("lat")), match.group("lat_dir"))
        longitude = _directed_coordinate(
            float(match.group("lon")), match.group("lon_dir")
        )
        return (latitude, longitude) if _validate_coordinate_pair(latitude, longitude) else None

    match = _DMS_PAIR_RE.search(text)
    if not match:
        return None
    lat_minutes = float(match.group("lat_min"))
    lon_minutes = float(match.group("lon_min"))
    lat_seconds = float(match.group("lat_sec") or 0)
    lon_seconds = float(match.group("lon_sec") or 0)
    if lat_minutes >= 60 or lon_minutes >= 60 or lat_seconds >= 60 or lon_seconds >= 60:
        return None
    latitude = float(match.group("lat_deg")) + lat_minutes / 60 + lat_seconds / 3600
    longitude = float(match.group("lon_deg")) + lon_minutes / 60 + lon_seconds / 3600
    latitude = _directed_coordinate(latitude, match.group("lat_dir"))
    longitude = _directed_coordinate(longitude, match.group("lon_dir"))
    return (latitude, longitude) if _validate_coordinate_pair(latitude, longitude) else None


def parse_location(value: Optional[str]) -> Tuple[str, Optional[float], Optional[float]]:
    """Return cleaned state/location text and separately parsed coordinates."""

    text = normalize_text(value)
    start = _COORDINATE_START_RE.search(text)
    label_source = text[: start.start()] if start else text
    label = _clean_location_label(label_source)
    coordinates = parse_coordinates(text)
    if coordinates is None:
        return label, None, None
    return label, coordinates[0], coordinates[1]


def _format_decimal(value: Decimal) -> str:
    return format(value, "f")


def _format_coordinate(value: float) -> str:
    return format(value, ".15g")


def _failure(
    source_row_number: int,
    park_id: str,
    park_name: str,
    source_field: str,
    raw_value: Optional[str],
    reason: str,
) -> Dict[str, str]:
    return {
        "source_row_number": str(source_row_number),
        "park_id": park_id,
        "park_name": park_name,
        "source_field": source_field,
        "raw_value": raw_value or "",
        "failure_reason": reason,
    }


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
    """Clean parks, validate the result, then publish data and reports."""

    if not source_path.is_file():
        raise ParkCleaningError(f"Required raw CSV is missing: {source_path.as_posix()}")

    parks: List[Dict[str, str]] = []
    failures: List[Dict[str, str]] = []
    source_row_count = 0
    excluded_empty_columns: List[str] = []
    removed_unnamed_columns: List[str] = []

    try:
        with source_path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames is None:
                raise ParkCleaningError(f"Raw CSV has no header: {source_path.as_posix()}")
            unnamed_columns = [
                column for column in reader.fieldnames if not normalize_text(column)
            ]
            named_columns = [column for column in reader.fieldnames if normalize_text(column)]
            missing_columns = [
                column for column in REQUIRED_SOURCE_COLUMNS if column not in named_columns
            ]
            unexpected_columns = [
                column for column in named_columns if column not in REQUIRED_SOURCE_COLUMNS
            ]
            if missing_columns or unexpected_columns:
                details = []
                if missing_columns:
                    details.append("missing columns: " + ", ".join(missing_columns))
                if unexpected_columns:
                    details.append("unexpected columns: " + ", ".join(unexpected_columns))
                raise ParkCleaningError(
                    f"Source schema mismatch in {source_path.as_posix()} ("
                    + "; ".join(details)
                    + ")"
                )

            raw_rows = list(reader)
            source_row_count = len(raw_rows)
            removed_unnamed_columns = unnamed_columns
            if raw_rows and all(not normalize_text(row.get("Image")) for row in raw_rows):
                excluded_empty_columns.append("Image")
            else:
                raise ParkCleaningError(
                    "Source Image column is no longer fully empty; review the processed schema"
                )

            for source_row_number, raw in enumerate(raw_rows, start=2):
                if None in raw:
                    raise ParkCleaningError(
                        f"Row {source_row_number} has more fields than the source header"
                    )
                name = clean_park_name(raw.get("Name"))
                park_id = make_park_id(name)
                if not name:
                    failures.append(
                        _failure(
                            source_row_number,
                            "",
                            "",
                            "Name",
                            raw.get("Name"),
                            "MISSING_PARK_NAME",
                        )
                    )
                    continue

                state_or_territory, latitude, longitude = parse_location(
                    raw.get("Location")
                )
                if not state_or_territory:
                    failures.append(
                        _failure(
                            source_row_number,
                            park_id,
                            name,
                            "Location",
                            raw.get("Location"),
                            "MISSING_LOCATION_TEXT",
                        )
                    )
                if latitude is None or longitude is None:
                    failures.append(
                        _failure(
                            source_row_number,
                            park_id,
                            name,
                            "Location",
                            raw.get("Location"),
                            "UNPARSEABLE_OR_OUT_OF_RANGE_COORDINATES",
                        )
                    )

                established_date = parse_date(raw.get(DATE_COLUMN))
                if established_date is None:
                    failures.append(
                        _failure(
                            source_row_number,
                            park_id,
                            name,
                            DATE_COLUMN,
                            raw.get(DATE_COLUMN),
                            "UNPARSEABLE_DATE",
                        )
                    )

                acreage = parse_acreage(raw.get(AREA_COLUMN))
                if acreage is None:
                    failures.append(
                        _failure(
                            source_row_number,
                            park_id,
                            name,
                            AREA_COLUMN,
                            raw.get(AREA_COLUMN),
                            "UNPARSEABLE_ACREAGE",
                        )
                    )

                visitors = parse_visitors(raw.get(VISITORS_COLUMN))
                if visitors is None:
                    failures.append(
                        _failure(
                            source_row_number,
                            park_id,
                            name,
                            VISITORS_COLUMN,
                            raw.get(VISITORS_COLUMN),
                            "UNPARSEABLE_VISITOR_COUNT",
                        )
                    )

                parks.append(
                    {
                        "park_id": park_id,
                        "name": name,
                        "state_or_territory": state_or_territory,
                        "latitude": _format_coordinate(latitude)
                        if latitude is not None
                        else "",
                        "longitude": _format_coordinate(longitude)
                        if longitude is not None
                        else "",
                        "established_date": established_date or "",
                        "area_acres": _format_decimal(acreage) if acreage is not None else "",
                        "recreation_visitors_2021": str(visitors)
                        if visitors is not None
                        else "",
                        "description": remove_citation_markers(raw.get("Description")),
                    }
                )
    except UnicodeDecodeError as exc:
        raise ParkCleaningError(
            f"Cannot decode {source_path.as_posix()} as UTF-8: {exc}"
        ) from exc
    except csv.Error as exc:
        raise ParkCleaningError(
            f"Cannot parse {source_path.as_posix()} as CSV: {exc}"
        ) from exc

    parks.sort(key=lambda row: (row["name"].casefold(), row["park_id"]))
    failures.sort(
        key=lambda row: (
            int(row["source_row_number"]),
            row["source_field"],
            row["failure_reason"],
        )
    )
    identifiers = [row["park_id"] for row in parks]
    if any(not identifier for identifier in identifiers):
        raise ParkCleaningError("Validation failed: park identifier is blank")
    if len(set(identifiers)) != len(identifiers):
        raise ParkCleaningError("Validation failed: deterministic park identifier is not unique")
    if len(parks) + sum(
        row["failure_reason"] == "MISSING_PARK_NAME" for row in failures
    ) != source_row_count:
        raise ParkCleaningError("Validation failed: source row accounting does not balance")

    valid_coordinate_count = sum(
        bool(row["latitude"] and row["longitude"]) for row in parks
    )
    failure_counts: Dict[str, int] = {}
    for failure in failures:
        reason = failure["failure_reason"]
        failure_counts[reason] = failure_counts.get(reason, 0) + 1

    summary: Dict[str, object] = {
        "source_file": source_path.as_posix(),
        "source_row_count": source_row_count,
        "processed_park_row_count": len(parks),
        "valid_coordinate_park_count": valid_coordinate_count,
        "invalid_coordinate_park_count": len(parks) - valid_coordinate_count,
        "parse_failure_count": len(failures),
        "parse_failure_counts_by_reason": dict(sorted(failure_counts.items())),
        "removed_unnamed_columns": removed_unnamed_columns,
        "excluded_fully_empty_columns": excluded_empty_columns,
        "park_identifier_rule": (
            "UUIDv5 URL namespace over the case-folded, whitespace-normalized cleaned name"
        ),
        "validation": "passed",
    }

    processed_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)
    _write_csv(processed_dir / "national_parks.csv", parks, PARK_COLUMNS)
    _write_csv(report_dir / "park_parse_failures.csv", failures, FAILURE_COLUMNS)
    _write_json(report_dir / "park_cleaning_summary.json", summary)
    return summary


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Clean and validate national parks.")
    parser.add_argument("--source", type=Path, default=SOURCE_PATH)
    parser.add_argument("--processed-dir", type=Path, default=PROCESSED_DIR)
    parser.add_argument("--report-dir", type=Path, default=REPORT_DIR)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        summary = run_cleaning(args.source, args.processed_dir, args.report_dir)
    except ParkCleaningError as exc:
        print(f"National-park cleaning failed: {exc}", file=sys.stderr)
        return 1

    print("National-park cleaning completed.")
    print(f"- Processed parks: {summary['processed_park_row_count']}")
    print(f"- Parks with valid coordinates: {summary['valid_coordinate_park_count']}")
    print(f"- Recorded parse failures: {summary['parse_failure_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
