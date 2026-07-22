"""Install and verify the justified CampScout application indexes."""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path
from typing import Optional, Sequence

from db.build_database import VIEWS_PATH, iter_sql_statements
from db.connection import REPOSITORY_ROOT, PathLike, connect_database, resolve_database_path


INDEXES_PATH = REPOSITORY_ROOT / "sql" / "indexes.sql"
EXPECTED_INDEXES = {
    "idx_park_distance_campground": (
        "park_id",
        "distance_km",
        "campground_id",
    ),
    "idx_activity_recarea": ("activity_id", "recarea_id"),
    "idx_campgrounds_recarea_id": ("recarea_id",),
}
EXPECTED_VIEWS = {"campground_activity_details", "campground_data_completeness"}


class IndexApplicationError(RuntimeError):
    """Raised when application query objects cannot be installed or verified."""


def _execute_resource(connection: sqlite3.Connection, path: Path) -> None:
    for statement in iter_sql_statements(path.read_text(encoding="utf-8")):
        connection.execute(statement)


def _verify_query_objects(connection: sqlite3.Connection) -> dict[str, tuple[str, ...]]:
    installed: dict[str, tuple[str, ...]] = {}
    for index_name, expected_columns in EXPECTED_INDEXES.items():
        rows = connection.execute(f"PRAGMA index_info({index_name})").fetchall()
        actual_columns = tuple(row[2] for row in rows)
        if actual_columns != expected_columns:
            raise IndexApplicationError(
                f"Index {index_name} has columns {actual_columns}; "
                f"expected {expected_columns}."
            )
        installed[index_name] = actual_columns

    actual_views = {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_schema WHERE type = ?", ("view",)
        )
    }
    missing_views = EXPECTED_VIEWS - actual_views
    if missing_views:
        raise IndexApplicationError(
            f"Missing query view(s): {', '.join(sorted(missing_views))}"
        )
    return installed


def apply_indexes(
    database_path: Optional[PathLike] = None,
    *,
    indexes_path: Path = INDEXES_PATH,
    views_path: Path = VIEWS_PATH,
) -> dict[str, tuple[str, ...]]:
    """Install views and indexes atomically, then verify exact index columns."""

    target = resolve_database_path(database_path)
    if not target.is_file():
        raise FileNotFoundError(f"SQLite database does not exist: {target}")

    connection = connect_database(target)
    try:
        connection.execute("BEGIN IMMEDIATE")
        _execute_resource(connection, views_path)
        _execute_resource(connection, indexes_path)
        installed = _verify_query_objects(connection)
        connection.commit()
        return installed
    except Exception:
        if connection.in_transaction:
            connection.rollback()
        raise
    finally:
        connection.close()


def main(argv: Optional[Sequence[str]] = None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    if argv:
        print("apply_indexes does not accept arguments", file=sys.stderr)
        return 2
    try:
        installed = apply_indexes()
    except (IndexApplicationError, OSError, sqlite3.Error) as exc:
        print(f"Index application failed: {exc}", file=sys.stderr)
        return 1

    print("Installed CampScout query views and indexes:")
    for index_name, columns in installed.items():
        print(f"  {index_name} ({', '.join(columns)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
