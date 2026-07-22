"""Centralized SQLite connection creation for CampScout."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Optional, Union


PathLike = Union[str, os.PathLike[str]]
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATABASE_PATH = REPOSITORY_ROOT / "data" / "campscout.db"
MINIMUM_SQLITE_VERSION = (3, 37, 0)


class SQLiteVersionError(RuntimeError):
    """Raised when Python is linked to an unsupported SQLite runtime."""


class DatabaseConnectionError(RuntimeError):
    """Raised when a required connection setting cannot be activated."""


def require_supported_sqlite() -> None:
    """Require the SQLite release that introduced STRICT tables."""

    if sqlite3.sqlite_version_info < MINIMUM_SQLITE_VERSION:
        required = ".".join(map(str, MINIMUM_SQLITE_VERSION))
        raise SQLiteVersionError(
            f"CampScout requires SQLite {required} or newer for STRICT tables; "
            f"this Python runtime provides SQLite {sqlite3.sqlite_version}."
        )


def resolve_database_path(database_path: Optional[PathLike] = None) -> Path:
    """Resolve an explicit path, environment override, or repository default."""

    candidate: Path
    if database_path is not None:
        candidate = Path(database_path).expanduser()
    else:
        override = os.environ.get("CAMPSCOUT_DB_PATH")
        candidate = Path(override).expanduser() if override else DEFAULT_DATABASE_PATH

    if not candidate.is_absolute():
        candidate = REPOSITORY_ROOT / candidate
    return candidate.resolve(strict=False)


def connect_database(
    database_path: Optional[PathLike] = None,
    *,
    read_only: bool = False,
) -> sqlite3.Connection:
    """Return a new SQLite connection with foreign keys enabled and verified."""

    require_supported_sqlite()
    path = resolve_database_path(database_path)

    if read_only:
        if not path.is_file():
            raise FileNotFoundError(f"SQLite database does not exist: {path}")
        connection = sqlite3.connect(
            f"{path.as_uri()}?mode=ro",
            uri=True,
            isolation_level=None,
        )
    else:
        connection = sqlite3.connect(path, isolation_level=None)

    try:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        enabled = connection.execute("PRAGMA foreign_keys").fetchone()[0]
        if enabled != 1:
            raise DatabaseConnectionError(
                "SQLite foreign-key enforcement could not be enabled."
            )
        return connection
    except Exception:
        connection.close()
        raise
