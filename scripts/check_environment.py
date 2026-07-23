"""Validate the local Python, processed-data, and optional runtime environment."""

from __future__ import annotations

import argparse
import csv
import importlib
import sqlite3
import sys
from pathlib import Path
from typing import Sequence


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from db.build_database import TABLE_SPECS  # noqa: E402
from db.connection import (  # noqa: E402
    MINIMUM_SQLITE_VERSION,
    connect_database,
    resolve_database_path,
)


MINIMUM_PYTHON_VERSION = (3, 10)
REQUIRED_IMPORTS = {
    "pandas": "pandas",
    "numpy": "numpy",
    "streamlit": "streamlit",
    "beautifulsoup4": "bs4",
    "rapidfuzz": "rapidfuzz",
    "pytest": "pytest",
}
RAW_FILENAMES = (
    "Recreation_Sites_INFRA.csv",
    "Recreation_Area_Activities.csv",
    "national_parks_raw.csv",
)


class EnvironmentCheckError(RuntimeError):
    """Raised when the local CampScout runtime contract is not satisfied."""


def check_python_runtime() -> None:
    if sys.version_info < MINIMUM_PYTHON_VERSION:
        required = ".".join(map(str, MINIMUM_PYTHON_VERSION))
        raise EnvironmentCheckError(
            f"Python {required} or newer is required; found {sys.version.split()[0]}."
        )
    if sqlite3.sqlite_version_info < MINIMUM_SQLITE_VERSION:
        required = ".".join(map(str, MINIMUM_SQLITE_VERSION))
        raise EnvironmentCheckError(
            f"SQLite {required} or newer is required; found {sqlite3.sqlite_version}."
        )


def check_package_imports() -> tuple[str, ...]:
    failures: list[str] = []
    for distribution, module_name in REQUIRED_IMPORTS.items():
        try:
            importlib.import_module(module_name)
        except ImportError:
            failures.append(distribution)
    if failures:
        raise EnvironmentCheckError(
            "Required package imports failed: " + ", ".join(failures)
        )
    return tuple(REQUIRED_IMPORTS)


def check_processed_files(repository_root: Path = REPOSITORY_ROOT) -> dict[str, int]:
    processed_dir = repository_root / "data" / "processed"
    counts: dict[str, int] = {}
    for spec in TABLE_SPECS:
        path = processed_dir / spec.csv_filename
        if not path.is_file():
            raise EnvironmentCheckError(
                f"Required processed CSV is missing: data/processed/{spec.csv_filename}"
            )
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.reader(handle)
            try:
                headers = tuple(next(reader))
            except StopIteration as exc:
                raise EnvironmentCheckError(
                    f"Processed CSV is empty: data/processed/{spec.csv_filename}"
                ) from exc
            if headers != spec.csv_fields:
                raise EnvironmentCheckError(
                    f"Unexpected headers in data/processed/{spec.csv_filename}: "
                    f"expected {spec.csv_fields}, found {headers}."
                )
            counts[spec.csv_filename] = sum(1 for _ in reader)
    return counts


def check_raw_files(repository_root: Path = REPOSITORY_ROOT) -> tuple[str, ...]:
    missing = [
        filename
        for filename in RAW_FILENAMES
        if not (repository_root / "data" / "raw" / filename).is_file()
    ]
    if missing:
        raise EnvironmentCheckError(
            "Optional ETL mode requires these raw files under data/raw: "
            + ", ".join(missing)
        )
    return RAW_FILENAMES


def check_application_imports() -> None:
    importlib.import_module("app.app")
    importlib.import_module("streamlit_app")


def check_database_queries() -> dict[str, int]:
    """Execute live read-only queries, including an ALL-activity query."""

    from app import queries
    from db.validate_database import validate_database

    validation = validate_database()
    database_path = resolve_database_path()
    parks = queries.list_national_parks(database_path)
    activities = queries.list_available_activities(database_path)
    if not parks or not activities:
        raise EnvironmentCheckError("Park and activity lookup queries must return rows.")

    nearby = queries.find_campgrounds(
        parks[0]["park_id"], 20_000.0, limit=5, database_path=database_path
    )
    if not nearby:
        raise EnvironmentCheckError("The representative campground search returned no rows.")

    detail = queries.get_campground_details(nearby[0]["campground_id"], database_path)
    if detail is None:
        raise EnvironmentCheckError("The representative campground detail query failed.")
    queries.list_campground_activities(nearby[0]["campground_id"], database_path)
    completeness = queries.get_data_completeness_report(database_path)
    if completeness["campground_count"] != validation.row_counts["campgrounds"]:
        raise EnvironmentCheckError("The completeness query campground count is inconsistent.")

    connection = connect_database(database_path, read_only=True)
    try:
        pair = connection.execute(
            """
            SELECT first.activity_id, second.activity_id
            FROM recreation_area_activities AS first
            JOIN recreation_area_activities AS second
              ON second.recarea_id = first.recarea_id
             AND second.activity_id > first.activity_id
            JOIN campgrounds AS campground ON campground.recarea_id = first.recarea_id
            ORDER BY first.recarea_id, first.activity_id, second.activity_id
            LIMIT 1
            """
        ).fetchone()
        if pair is None:
            raise EnvironmentCheckError(
                "No linked Recreation Area has two activities for the ALL-semantics check."
            )
        selected = (pair[0], pair[1])
        all_activity_results = queries.find_campgrounds(
            parks[0]["park_id"],
            20_000.0,
            activity_ids=selected,
            limit=500,
            database_path=database_path,
        )
        if not all_activity_results:
            raise EnvironmentCheckError("The live ALL-activities query returned no rows.")
        for row in all_activity_results:
            matched = connection.execute(
                """
                SELECT COUNT(DISTINCT activity_id)
                FROM recreation_area_activities
                WHERE recarea_id = ? AND activity_id IN (?, ?)
                """,
                (row["recarea_id"], *selected),
            ).fetchone()[0]
            if matched != len(selected):
                raise EnvironmentCheckError(
                    "A live activity-filter result does not contain every selected activity."
                )

        try:
            connection.execute("CREATE TABLE readonly_probe (value TEXT)")
        except sqlite3.OperationalError as exc:
            if "readonly" not in str(exc).lower():
                raise
        else:
            raise EnvironmentCheckError("Application database access is not read-only.")
    finally:
        connection.close()

    return {
        "parks": len(parks),
        "activities": len(activities),
        "representative_results": len(nearby),
        "all_activity_results": len(all_activity_results),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--require-raw",
        action="store_true",
        help="also require the three local raw files used by the optional ETL workflow",
    )
    parser.add_argument(
        "--check-database",
        action="store_true",
        help="validate the database and execute representative read-only queries",
    )
    parser.add_argument(
        "--check-app-import",
        action="store_true",
        help="verify both the package application module and root entrypoint import",
    )
    args = parser.parse_args(argv)

    try:
        check_python_runtime()
        packages = check_package_imports()
        processed_counts = check_processed_files()
        if args.require_raw:
            check_raw_files()
        if args.check_app_import:
            check_application_imports()
        query_counts = check_database_queries() if args.check_database else None
    except (EnvironmentCheckError, OSError, sqlite3.Error) as exc:
        print(f"Environment check failed: {exc}", file=sys.stderr)
        return 1

    print(f"Python: {sys.version.split()[0]}")
    print(f"SQLite: {sqlite3.sqlite_version}")
    print("Required package imports: " + ", ".join(packages))
    print("Processed CSVs:")
    for filename, count in processed_counts.items():
        print(f"  {filename}: {count:,} rows")
    if args.require_raw:
        print("Optional raw ETL inputs: present")
    if args.check_app_import:
        print("Streamlit application imports: passed")
    if query_counts is not None:
        print("Core read-only application queries:")
        for name, count in query_counts.items():
            print(f"  {name}: {count:,}")
        print("ALL-selected-activities semantics: passed")
        print("Read-only application access: passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
