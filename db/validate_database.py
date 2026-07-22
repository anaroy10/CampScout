"""Validate the generated CampScout SQLite database against its CSV inputs."""

from __future__ import annotations

import csv
import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence

from db.build_database import DEFAULT_PROCESSED_DIR, TABLE_SPECS, iter_sql_statements
from db.connection import (
    REPOSITORY_ROOT,
    PathLike,
    connect_database,
    resolve_database_path,
)


VALIDATION_SQL_PATH = REPOSITORY_ROOT / "sql" / "validation.sql"
PRIMARY_KEYS = {
    "national_parks": ("park_id",),
    "recreation_areas": ("recarea_id",),
    "activities": ("activity_id",),
    "campgrounds": ("campground_id",),
    "recreation_area_activities": ("recarea_id", "activity_id"),
    "park_campground_distances": ("park_id", "campground_id"),
}


class DatabaseValidationError(RuntimeError):
    """Raised when the generated database fails one or more validations."""


@dataclass(frozen=True)
class ValidationResult:
    database_path: Path
    row_counts: dict[str, int]
    check_count: int


def _resolve_processed_dir(processed_dir: Optional[PathLike]) -> Path:
    path = Path(processed_dir) if processed_dir is not None else DEFAULT_PROCESSED_DIR
    if not path.is_absolute():
        path = REPOSITORY_ROOT / path
    return path.resolve(strict=False)


def _expected_csv_counts(processed_dir: Path) -> dict[str, int]:
    counts: dict[str, int] = {}
    for spec in TABLE_SPECS:
        csv_path = processed_dir / spec.csv_filename
        if not csv_path.is_file():
            raise DatabaseValidationError(f"Required processed CSV is missing: {csv_path}")
        with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.reader(handle)
            try:
                headers = tuple(next(reader))
            except StopIteration as exc:
                raise DatabaseValidationError(f"Processed CSV is empty: {csv_path}") from exc
            if headers != spec.csv_fields:
                raise DatabaseValidationError(
                    f"Unexpected headers in {csv_path}: expected {spec.csv_fields}, "
                    f"found {headers}."
                )
            counts[spec.table_name] = sum(1 for _ in reader)
    return counts


def _validate_tables(
    connection: sqlite3.Connection,
    expected_counts: dict[str, int],
) -> tuple[dict[str, int], int]:
    expected_tables = set(expected_counts)
    actual_tables = {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_schema WHERE type = ? AND name NOT LIKE ?",
            ("table", "sqlite_%"),
        )
    }
    missing_tables = expected_tables - actual_tables
    if missing_tables:
        raise DatabaseValidationError(
            f"Missing required table(s): {', '.join(sorted(missing_tables))}"
        )

    strict_by_table = {
        row[1]: row[5]
        for row in connection.execute("PRAGMA table_list")
        if row[1] in expected_tables
    }
    non_strict = sorted(name for name in expected_tables if strict_by_table.get(name) != 1)
    if non_strict:
        raise DatabaseValidationError(
            f"Required STRICT table(s) are not strict: {', '.join(non_strict)}"
        )

    checks = 1 + len(expected_tables)
    actual_counts: dict[str, int] = {}
    for table_name, expected_count in expected_counts.items():
        actual_count = connection.execute(
            f"SELECT COUNT(*) FROM {table_name}"
        ).fetchone()[0]
        actual_counts[table_name] = actual_count
        if actual_count != expected_count:
            raise DatabaseValidationError(
                f"Row-count mismatch for {table_name}: CSV has {expected_count}, "
                f"database has {actual_count}."
            )

    for table_name, key_columns in PRIMARY_KEYS.items():
        for key_column in key_columns:
            null_count = connection.execute(
                f"SELECT COUNT(*) FROM {table_name} WHERE {key_column} IS NULL"
            ).fetchone()[0]
            checks += 1
            if null_count:
                raise DatabaseValidationError(
                    f"Primary key {table_name}.{key_column} contains NULL values."
                )

        group_columns = ", ".join(key_columns)
        duplicate = connection.execute(
            f"SELECT 1 FROM {table_name} GROUP BY {group_columns} "
            "HAVING COUNT(*) > 1 LIMIT 1"
        ).fetchone()
        checks += 1
        if duplicate is not None:
            raise DatabaseValidationError(
                f"Primary key for {table_name} contains duplicate values."
            )

    foreign_key_rows = connection.execute("PRAGMA foreign_key_check").fetchall()
    checks += 1
    if foreign_key_rows:
        raise DatabaseValidationError(
            f"PRAGMA foreign_key_check found {len(foreign_key_rows)} violation(s)."
        )

    integrity_rows = connection.execute("PRAGMA integrity_check").fetchall()
    checks += 1
    if [row[0] for row in integrity_rows] != ["ok"]:
        details = "; ".join(str(row[0]) for row in integrity_rows)
        raise DatabaseValidationError(f"PRAGMA integrity_check failed: {details}")

    return actual_counts, checks


def _run_validation_sql(connection: sqlite3.Connection) -> int:
    failures: list[tuple[str, str]] = []
    check_count = 0
    sql_text = VALIDATION_SQL_PATH.read_text(encoding="utf-8")
    for statement in iter_sql_statements(sql_text):
        check_count += 1
        for row in connection.execute(statement).fetchall():
            failures.append((str(row[0]), str(row[1])))
    if failures:
        preview = ", ".join(
            f"{issue} ({record_key})" for issue, record_key in failures[:10]
        )
        suffix = "" if len(failures) <= 10 else f" and {len(failures) - 10} more"
        raise DatabaseValidationError(f"Data validation failed: {preview}{suffix}")
    return check_count


def validate_database(
    database_path: Optional[PathLike] = None,
    *,
    processed_dir: Optional[PathLike] = None,
) -> ValidationResult:
    """Validate schema, source counts, keys, relationships, and domain rules."""

    target = resolve_database_path(database_path)
    source_dir = _resolve_processed_dir(processed_dir)
    expected_counts = _expected_csv_counts(source_dir)
    connection = connect_database(target, read_only=True)
    try:
        actual_counts, check_count = _validate_tables(connection, expected_counts)
        check_count += _run_validation_sql(connection)
    finally:
        connection.close()
    return ValidationResult(target, actual_counts, check_count)


def main(argv: Optional[Sequence[str]] = None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    if argv:
        print("validate_database does not accept arguments", file=sys.stderr)
        return 2
    try:
        result = validate_database()
    except (DatabaseValidationError, OSError, sqlite3.Error) as exc:
        print(f"Database validation failed: {exc}", file=sys.stderr)
        return 1

    print(f"Validated {result.database_path}")
    for table_name, count in result.row_counts.items():
        print(f"  {table_name}: {count:,} rows")
    print(f"All {result.check_count} validation checks passed.")
    print("PRAGMA foreign_key_check: passed")
    print("PRAGMA integrity_check: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
