"""Build the CampScout SQLite database from the six processed CSV files."""

from __future__ import annotations

import argparse
import csv
import math
import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Optional, Sequence

from db.connection import (
    DEFAULT_DATABASE_PATH,
    REPOSITORY_ROOT,
    PathLike,
    connect_database,
    require_supported_sqlite,
    resolve_database_path,
)


SCHEMA_PATH = REPOSITORY_ROOT / "sql" / "schema.sql"
VIEWS_PATH = REPOSITORY_ROOT / "sql" / "views.sql"
DEFAULT_PROCESSED_DIR = REPOSITORY_ROOT / "data" / "processed"


class DatabaseBuildError(RuntimeError):
    """Raised when the database cannot be built and validated atomically."""


Converter = Callable[[Any], Any]


@dataclass(frozen=True)
class ColumnSpec:
    csv_name: str
    database_name: str
    converter: Converter


@dataclass(frozen=True)
class TableSpec:
    table_name: str
    csv_filename: str
    columns: tuple[ColumnSpec, ...]

    @property
    def csv_fields(self) -> tuple[str, ...]:
        return tuple(column.csv_name for column in self.columns)

    @property
    def database_fields(self) -> tuple[str, ...]:
        return tuple(column.database_name for column in self.columns)


def null_if_missing(value: Any) -> Any:
    """Convert CSV blanks and in-memory NaN-like values to SQL NULL."""

    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    if isinstance(value, str) and value == "":
        return None
    return value


def as_text(value: Any) -> Optional[str]:
    value = null_if_missing(value)
    return None if value is None else str(value)


def as_real(value: Any) -> Optional[float]:
    value = null_if_missing(value)
    return None if value is None else float(value)


def as_integer(value: Any) -> Optional[int]:
    value = null_if_missing(value)
    if value is None:
        return None
    text = str(value)
    if not text.isdigit():
        raise ValueError(f"expected a non-negative integer, got {text!r}")
    return int(text)


def as_yn_boolean(value: Any) -> Optional[int]:
    value = null_if_missing(value)
    if value is None:
        return None
    if value == "Y":
        return 1
    if value == "N":
        return 0
    raise ValueError(f"expected Y or N, got {value!r}")


def column(csv_name: str, database_name: Optional[str] = None, converter: Converter = as_text) -> ColumnSpec:
    return ColumnSpec(csv_name, database_name or csv_name, converter)


TABLE_SPECS = (
    TableSpec(
        "national_parks",
        "national_parks.csv",
        (
            column("park_id"),
            column("name"),
            column("state_or_territory"),
            column("latitude", converter=as_real),
            column("longitude", converter=as_real),
            column("established_date"),
            column("area_acres", converter=as_real),
            column("recreation_visitors_2021", converter=as_integer),
            column("description"),
        ),
    ),
    TableSpec(
        "recreation_areas",
        "recreation_areas.csv",
        (
            column("RECAREAID", "recarea_id"),
            column("X", "longitude", as_real),
            column("Y", "latitude", as_real),
            column("RECAREANAME", "name"),
            column("LONGITUDE", "source_longitude"),
            column("LATITUDE", "source_latitude"),
            column("RECAREAURL", "official_url"),
            column("OPEN_SEASON_START", "open_season_start"),
            column("OPEN_SEASON_END", "open_season_end"),
            column("FORESTNAME", "forest_name"),
            column("MARKERTYPE", "marker_type"),
            column("MARKERACTIVITY", "marker_activity"),
            column("MARKERACTIVITYGROUP", "marker_activity_group"),
            column("RECAREADESCRIPTION", "description"),
            column("SPOTLIGHTDISPLAY", "spotlight_display", as_yn_boolean),
            column("ATTRACTIONDISPLAY", "attraction_display", as_yn_boolean),
            column("ACCESSIBILITY", "accessibility"),
            column("OPENSTATUS", "open_status"),
            column("SHAPE", "shape"),
        ),
    ),
    TableSpec(
        "activities",
        "activities.csv",
        (
            column("ACTIVITYID", "activity_id"),
            column("ACTIVITYNAME", "name"),
            column("PARENTACTIVITYID", "parent_activity_id"),
            column("PARENTACTIVITYNAME", "parent_activity_name"),
        ),
    ),
    TableSpec(
        "campgrounds",
        "campgrounds.csv",
        (
            column("campground_id"),
            column("globalid"),
            column("site_cn"),
            column("site_id"),
            column("objectid"),
            column("root_cn"),
            column("parent_cn"),
            column("name"),
            column("public_site_name"),
            column("site_name"),
            column("recarea_name"),
            column("site_subtype", "campground_type"),
            column("site_subtype_raw", "campground_type_raw"),
            column("recarea_id"),
            column("recid_extracted"),
            column("fee_charged"),
            column("fee_charged_raw"),
            column("fee_type"),
            column("fee_description"),
            column("total_capacity", converter=as_real),
            column("total_capacity_raw"),
            column("water_availability", "water_category"),
            column("water_availability_raw"),
            column("restroom_availability", "restroom_category"),
            column("restroom_availability_raw"),
            column("directions"),
            column("site_directions"),
            column("closest_towns"),
            column("operational_hours"),
            column("official_url"),
            column("usda_portal_url"),
            column("rec1stop_url"),
            column("latitude", converter=as_real),
            column("longitude", converter=as_real),
            column("last_update"),
        ),
    ),
    TableSpec(
        "recreation_area_activities",
        "recreation_area_activities.csv",
        (
            column("RECAREAID", "recarea_id"),
            column("ACTIVITYID", "activity_id"),
        ),
    ),
    TableSpec(
        "park_campground_distances",
        "park_campground_distances.csv",
        (
            column("park_id"),
            column("campground_id"),
            column("distance_km", converter=as_real),
        ),
    ),
)


def iter_sql_statements(sql_text: str) -> Iterable[str]:
    """Split a trusted SQL resource using SQLite's own completeness parser."""

    buffer: list[str] = []
    for line in sql_text.splitlines(keepends=True):
        buffer.append(line)
        candidate = "".join(buffer)
        if sqlite3.complete_statement(candidate):
            if candidate.strip():
                yield candidate
            buffer.clear()
    if "".join(buffer).strip():
        raise DatabaseBuildError("SQL resource ends with an incomplete statement.")


def create_schema(connection: sqlite3.Connection, schema_path: Path = SCHEMA_PATH) -> None:
    """Create the schema on an active transaction."""

    for statement in iter_sql_statements(schema_path.read_text(encoding="utf-8")):
        connection.execute(statement)


def create_views(connection: sqlite3.Connection, views_path: Path = VIEWS_PATH) -> None:
    """Create the database views on an active transaction."""

    for statement in iter_sql_statements(views_path.read_text(encoding="utf-8")):
        connection.execute(statement)


def _row_values(row: dict[str, str], spec: TableSpec) -> tuple[Any, ...]:
    return tuple(item.converter(row[item.csv_name]) for item in spec.columns)


def load_table(
    connection: sqlite3.Connection,
    spec: TableSpec,
    processed_dir: Path,
) -> int:
    """Load and immediately count one processed CSV table."""

    csv_path = processed_dir / spec.csv_filename
    if not csv_path.is_file():
        raise DatabaseBuildError(f"Required processed CSV is missing: {csv_path}")

    placeholders = ", ".join("?" for _ in spec.database_fields)
    columns = ", ".join(spec.database_fields)
    insert_sql = f"INSERT INTO {spec.table_name} ({columns}) VALUES ({placeholders})"
    expected_count = 0

    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        actual_fields = tuple(reader.fieldnames or ())
        if actual_fields != spec.csv_fields:
            raise DatabaseBuildError(
                f"Unexpected headers in {csv_path}: expected {spec.csv_fields}, "
                f"found {actual_fields}."
            )

        def converted_rows() -> Iterable[tuple[Any, ...]]:
            nonlocal expected_count
            for source_row_number, row in enumerate(reader, start=2):
                expected_count += 1
                try:
                    yield _row_values(row, spec)
                except (TypeError, ValueError) as exc:
                    raise DatabaseBuildError(
                        f"Invalid value in {csv_path} at source row "
                        f"{source_row_number}: {exc}"
                    ) from exc

        connection.executemany(insert_sql, converted_rows())

    inserted_count = connection.execute(
        f"SELECT COUNT(*) FROM {spec.table_name}"
    ).fetchone()[0]
    if inserted_count != expected_count:
        raise DatabaseBuildError(
            f"Row-count mismatch for {spec.table_name}: CSV has {expected_count}, "
            f"database has {inserted_count}."
        )
    return expected_count


def _validate_loaded_database(connection: sqlite3.Connection) -> None:
    foreign_key_rows = connection.execute("PRAGMA foreign_key_check").fetchall()
    if foreign_key_rows:
        raise DatabaseBuildError(
            f"Foreign-key validation failed with {len(foreign_key_rows)} violation(s)."
        )

    integrity_rows = connection.execute("PRAGMA integrity_check").fetchall()
    if [row[0] for row in integrity_rows] != ["ok"]:
        details = "; ".join(str(row[0]) for row in integrity_rows)
        raise DatabaseBuildError(f"SQLite integrity_check failed: {details}")


def _prepare_target(database_path: Path, *, reset: bool) -> None:
    if reset:
        approved_path = DEFAULT_DATABASE_PATH.resolve(strict=False)
        if database_path != approved_path:
            raise DatabaseBuildError(
                "--reset is restricted to the repository database "
                f"{approved_path}; refusing to delete {database_path}."
            )
        if database_path.exists():
            if not database_path.is_file():
                raise DatabaseBuildError(f"Database target is not a file: {database_path}")
            database_path.unlink()
    elif database_path.exists():
        raise DatabaseBuildError(
            f"Database already exists: {database_path}. Use --reset only for "
            "data/campscout.db."
        )


def build_database(
    database_path: Optional[PathLike] = None,
    *,
    processed_dir: Optional[PathLike] = None,
    reset: bool = False,
) -> dict[str, int]:
    """Create and transactionally load a new CampScout database."""

    require_supported_sqlite()
    target = resolve_database_path(database_path)
    source_dir = Path(processed_dir) if processed_dir is not None else DEFAULT_PROCESSED_DIR
    if not source_dir.is_absolute():
        source_dir = REPOSITORY_ROOT / source_dir
    source_dir = source_dir.resolve(strict=False)

    _prepare_target(target, reset=reset)
    target.parent.mkdir(parents=True, exist_ok=True)
    connection: Optional[sqlite3.Connection] = None
    try:
        connection = connect_database(target)
        connection.execute("BEGIN IMMEDIATE")
        create_schema(connection)
        row_counts = {
            spec.table_name: load_table(connection, spec, source_dir)
            for spec in TABLE_SPECS
        }
        create_views(connection)
        _validate_loaded_database(connection)
        connection.commit()
        return row_counts
    except Exception as exc:
        if connection is not None and connection.in_transaction:
            connection.rollback()
        if connection is not None:
            connection.close()
            connection = None
        if target.exists():
            target.unlink()
        if isinstance(exc, DatabaseBuildError):
            raise
        raise DatabaseBuildError(f"Database build failed: {exc}") from exc
    finally:
        if connection is not None:
            connection.close()


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build data/campscout.db from the six processed CSV files."
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="safely recreate only the default data/campscout.db file",
    )
    args = parser.parse_args(argv)

    try:
        counts = build_database(reset=args.reset)
        target = resolve_database_path()
    except (DatabaseBuildError, OSError, sqlite3.Error) as exc:
        print(f"Database build failed: {exc}", file=sys.stderr)
        return 1

    print(f"Built {target}")
    for table_name, count in counts.items():
        print(f"  {table_name}: {count:,} rows")
    print(f"Database size: {target.stat().st_size:,} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
