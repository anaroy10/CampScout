"""Calculate every valid national-park/campground straight-line distance."""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from pathlib import Path
from typing import Dict, List, Mapping, Optional, Sequence, Tuple


PARKS_PATH = Path("data/processed/national_parks.csv")
CAMPGROUNDS_PATH = Path("data/processed/campgrounds.csv")
PROCESSED_DIR = Path("data/processed")
REPORT_DIR = Path("reports/generated")
OUTPUT_COLUMNS = ("park_id", "campground_id", "distance_km")
EARTH_RADIUS_KM = 6371.0088
EXPORTED_DECIMAL_PLACES = 6


class DistanceCalculationError(RuntimeError):
    """An actionable failure raised by the distance-calculation phase."""


def haversine_km(
    latitude_1: float,
    longitude_1: float,
    latitude_2: float,
    longitude_2: float,
) -> float:
    """Return great-circle distance using the IUGG mean Earth radius."""

    lat_1 = math.radians(latitude_1)
    lon_1 = math.radians(longitude_1)
    lat_2 = math.radians(latitude_2)
    lon_2 = math.radians(longitude_2)
    delta_latitude = lat_2 - lat_1
    delta_longitude = lon_2 - lon_1
    haversine = (
        math.sin(delta_latitude / 2) ** 2
        + math.cos(lat_1) * math.cos(lat_2) * math.sin(delta_longitude / 2) ** 2
    )
    central_angle = 2 * math.asin(math.sqrt(min(1.0, max(0.0, haversine))))
    return EARTH_RADIUS_KM * central_angle


def _parse_coordinate(value: Optional[str], minimum: float, maximum: float) -> Optional[float]:
    text = (value or "").strip()
    if not text:
        return None
    try:
        coordinate = float(text)
    except ValueError:
        return None
    if not math.isfinite(coordinate) or not minimum <= coordinate <= maximum:
        return None
    return coordinate


def _load_valid_coordinates(
    path: Path, identifier_column: str
) -> Tuple[List[Tuple[str, float, float]], int, int]:
    if not path.is_file():
        raise DistanceCalculationError(f"Required processed CSV is missing: {path.as_posix()}")
    records: List[Tuple[str, float, float]] = []
    total_count = 0
    invalid_coordinate_count = 0
    identifiers = set()
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            required = {identifier_column, "latitude", "longitude"}
            missing = sorted(required - set(reader.fieldnames or ()))
            if missing:
                raise DistanceCalculationError(
                    f"Processed schema mismatch in {path.as_posix()}; missing columns: "
                    + ", ".join(missing)
                )
            for row_number, row in enumerate(reader, start=2):
                total_count += 1
                if None in row:
                    raise DistanceCalculationError(
                        f"Row {row_number} in {path.as_posix()} has more fields than the header"
                    )
                identifier = (row.get(identifier_column) or "").strip()
                if not identifier:
                    raise DistanceCalculationError(
                        f"Blank {identifier_column} at row {row_number} in {path.as_posix()}"
                    )
                if identifier in identifiers:
                    raise DistanceCalculationError(
                        f"Duplicate {identifier_column} {identifier!r} in {path.as_posix()}"
                    )
                identifiers.add(identifier)
                latitude = _parse_coordinate(row.get("latitude"), -90.0, 90.0)
                longitude = _parse_coordinate(row.get("longitude"), -180.0, 180.0)
                if latitude is None or longitude is None:
                    invalid_coordinate_count += 1
                    continue
                records.append((identifier, latitude, longitude))
    except UnicodeDecodeError as exc:
        raise DistanceCalculationError(
            f"Cannot decode {path.as_posix()} as UTF-8: {exc}"
        ) from exc
    except csv.Error as exc:
        raise DistanceCalculationError(f"Cannot parse {path.as_posix()} as CSV: {exc}") from exc

    records.sort(key=lambda record: record[0])
    return records, total_count, invalid_coordinate_count


def _write_json(path: Path, value: Mapping[str, object]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def run_calculation(
    parks_path: Path = PARKS_PATH,
    campgrounds_path: Path = CAMPGROUNDS_PATH,
    processed_dir: Path = PROCESSED_DIR,
    report_dir: Path = REPORT_DIR,
) -> Dict[str, object]:
    """Calculate, validate, and publish the complete valid coordinate cross product."""

    parks, park_input_count, invalid_park_count = _load_valid_coordinates(
        parks_path, "park_id"
    )
    campgrounds, campground_input_count, invalid_campground_count = (
        _load_valid_coordinates(campgrounds_path, "campground_id")
    )
    expected_pair_count = len(parks) * len(campgrounds)

    distances: List[Tuple[str, str, float]] = []
    for park_id, park_latitude, park_longitude in parks:
        for campground_id, campground_latitude, campground_longitude in campgrounds:
            distance = haversine_km(
                park_latitude,
                park_longitude,
                campground_latitude,
                campground_longitude,
            )
            if not math.isfinite(distance) or distance < 0:
                raise DistanceCalculationError(
                    "Validation failed: calculated distance is negative or non-finite"
                )
            distances.append((park_id, campground_id, distance))

    if len(distances) != expected_pair_count:
        raise DistanceCalculationError(
            "Validation failed: distance row count does not equal valid park count "
            "multiplied by valid campground count"
        )

    processed_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)
    output_path = processed_dir / "park_campground_distances.csv"
    with output_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(OUTPUT_COLUMNS)
        for park_id, campground_id, distance in distances:
            writer.writerow(
                (
                    park_id,
                    campground_id,
                    f"{distance:.{EXPORTED_DECIMAL_PLACES}f}",
                )
            )

    summary: Dict[str, object] = {
        "parks_file": parks_path.as_posix(),
        "campgrounds_file": campgrounds_path.as_posix(),
        "park_input_row_count": park_input_count,
        "valid_park_count": len(parks),
        "invalid_park_coordinate_count": invalid_park_count,
        "campground_input_row_count": campground_input_count,
        "valid_campground_count": len(campgrounds),
        "invalid_campground_coordinate_count": invalid_campground_count,
        "expected_pair_count": expected_pair_count,
        "distance_row_count": len(distances),
        "earth_radius_km": EARTH_RADIUS_KM,
        "earth_radius_definition": "IUGG mean Earth radius",
        "exported_distance_decimal_places": EXPORTED_DECIMAL_PLACES,
        "distance_interpretation": (
            "straight-line great-circle distance from the park representative coordinate; "
            "not road distance or entrance distance"
        ),
        "sort_order": ["park_id", "campground_id"],
        "cardinality_validation": "passed",
        "non_negative_distance_validation": "passed",
        "later_phases": {
            "sqlite_database": "not implemented",
            "query_layer": "not implemented",
            "streamlit": "not implemented",
        },
    }
    _write_json(report_dir / "distance_summary.json", summary)
    return summary


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Calculate all valid park-campground Haversine distances."
    )
    parser.add_argument("--parks", type=Path, default=PARKS_PATH)
    parser.add_argument("--campgrounds", type=Path, default=CAMPGROUNDS_PATH)
    parser.add_argument("--processed-dir", type=Path, default=PROCESSED_DIR)
    parser.add_argument("--report-dir", type=Path, default=REPORT_DIR)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        summary = run_calculation(
            args.parks, args.campgrounds, args.processed_dir, args.report_dir
        )
    except DistanceCalculationError as exc:
        print(f"Distance calculation failed: {exc}", file=sys.stderr)
        return 1

    print("Distance calculation completed.")
    print(f"- Valid parks: {summary['valid_park_count']}")
    print(f"- Valid campgrounds: {summary['valid_campground_count']}")
    print(f"- Distance rows: {summary['distance_row_count']}")
    print("SQLite database build, query layer, and Streamlit are not implemented.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
