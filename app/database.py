"""Streamlit-facing database operations with no persistent connections."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Mapping, Optional

import streamlit as st

from . import queries
from db.connection import PathLike, resolve_database_path


SETUP_COMMAND = "python -m db.build_database --reset"


class DatabaseUnavailableError(RuntimeError):
    """Raised when the local CampScout database cannot be used by the app."""


def require_database(database_path: Optional[PathLike] = None) -> Path:
    """Resolve the configured database without exposing its path to the UI."""

    path = resolve_database_path(database_path)
    if not path.is_file():
        raise DatabaseUnavailableError(
            "The CampScout database is not available. Build it from the processed data."
        )
    return path


@st.cache_data(show_spinner=False)
def load_lookup_data(database_path: str) -> dict[str, list[dict[str, Any]]]:
    """Cache stable park and activity values, not a mutable connection."""

    try:
        return {
            "parks": queries.list_national_parks(database_path),
            "activities": queries.list_available_activities(database_path),
        }
    except (OSError, sqlite3.Error) as exc:
        raise DatabaseUnavailableError(
            "The CampScout database could not be read. Rebuild and validate it."
        ) from exc


def search_campgrounds(
    filters: Mapping[str, Any],
    database_path: PathLike,
) -> list[dict[str, Any]]:
    """Run the bounded park/radius query with converted UI filter values."""

    try:
        return queries.find_campgrounds(
            filters["park_id"],
            filters["radius_km"],
            limit=filters["limit"],
            campground_type=filters.get("campground_type"),
            fee_status=filters.get("fee_status"),
            water_category=filters.get("water_category"),
            restroom_category=filters.get("restroom_category"),
            activity_ids=filters.get("activity_ids"),
            database_path=database_path,
        )
    except (OSError, sqlite3.Error) as exc:
        raise DatabaseUnavailableError(
            "The campground search could not read the database."
        ) from exc


def load_campground_detail(
    campground_id: str,
    database_path: PathLike,
) -> tuple[Optional[dict[str, Any]], list[dict[str, Any]]]:
    """Load one campground and its Recreation Area activities."""

    try:
        detail = queries.get_campground_details(campground_id, database_path)
        activities = queries.list_campground_activities(campground_id, database_path)
        return detail, activities
    except (OSError, sqlite3.Error) as exc:
        raise DatabaseUnavailableError(
            "The campground details could not be read from the database."
        ) from exc
