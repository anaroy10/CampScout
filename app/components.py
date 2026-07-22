"""Pure presentation and state helpers for the CampScout Streamlit UI."""

from __future__ import annotations

import math
from typing import Any, Mapping, MutableMapping, Optional, Sequence
from urllib.parse import urlparse


DISTANCE_WORDING = (
    "Approximate straight-line distance from the park's representative coordinate"
)
ACTIVITY_WORDING = "Activities available in the campground's recreation area"
ANY_OPTION = "Any"
DEFAULT_FILTER_STATE = {
    "radius_km": 100.0,
    "activity_ids": [],
    "campground_type": ANY_OPTION,
    "fee_status": ANY_OPTION,
    "water_category": ANY_OPTION,
    "restroom_category": ANY_OPTION,
    "limit": 500,
}

PARK_FILTER_KEY = "park_filter"
RADIUS_FILTER_KEY = "radius_filter"
ACTIVITY_FILTER_KEY = "activity_filter"
CAMPGROUND_TYPE_FILTER_KEY = "campground_type_filter"
FEE_FILTER_KEY = "fee_filter"
WATER_FILTER_KEY = "water_filter"
RESTROOM_FILTER_KEY = "restroom_filter"
SEARCH_TEXT_FILTER_KEY = "search_text_filter"

FILTER_WIDGET_KEYS = (
    PARK_FILTER_KEY,
    RADIUS_FILTER_KEY,
    ACTIVITY_FILTER_KEY,
    CAMPGROUND_TYPE_FILTER_KEY,
    FEE_FILTER_KEY,
    WATER_FILTER_KEY,
    RESTROOM_FILTER_KEY,
    SEARCH_TEXT_FILTER_KEY,
)

CATEGORY_LABELS = {
    "UNKNOWN": "Unknown",
    "NONE": "None",
    "NOT_AVAILABLE": "Not available",
    "NATURAL_SOURCE": "Natural source",
    "GROUP CAMPGROUND": "Group campground",
    "HORSE CAMP": "Horse camp",
    "CAMPGROUND": "Campground",
}


def optional_filter(value: Any) -> Optional[str]:
    """Convert the UI's unrestricted option to the query layer's None value."""

    if value is None or value == ANY_OPTION:
        return None
    return str(value)


def convert_filter_state(state: Mapping[str, Any]) -> dict[str, Any]:
    """Convert widget state to the query layer's explicit filter contract."""

    return {
        "park_id": state["park_id"],
        "radius_km": float(state["radius_km"]),
        "activity_ids": list(state.get("activity_ids") or []),
        "campground_type": optional_filter(state.get("campground_type")),
        "fee_status": optional_filter(state.get("fee_status")),
        "water_category": optional_filter(state.get("water_category")),
        "restroom_category": optional_filter(state.get("restroom_category")),
        "limit": int(state.get("limit", DEFAULT_FILTER_STATE["limit"])),
    }


def reset_filter_values(park_id: str) -> dict[str, Any]:
    """Return a fresh reset state without sharing mutable default lists."""

    return {"park_id": park_id, **DEFAULT_FILTER_STATE, "activity_ids": []}


def filter_widget_defaults(park_id: str) -> dict[str, Any]:
    """Return the exact Streamlit session-state defaults for search filters."""

    return {
        PARK_FILTER_KEY: park_id,
        RADIUS_FILTER_KEY: DEFAULT_FILTER_STATE["radius_km"],
        ACTIVITY_FILTER_KEY: [],
        CAMPGROUND_TYPE_FILTER_KEY: DEFAULT_FILTER_STATE["campground_type"],
        FEE_FILTER_KEY: DEFAULT_FILTER_STATE["fee_status"],
        WATER_FILTER_KEY: DEFAULT_FILTER_STATE["water_category"],
        RESTROOM_FILTER_KEY: DEFAULT_FILTER_STATE["restroom_category"],
        # Reserved for the name-search control without changing current query behavior.
        SEARCH_TEXT_FILTER_KEY: "",
    }


def reset_filter_session_state(
    session_state: MutableMapping[str, Any], park_id: str
) -> None:
    """Reset only search/filter keys, preserving result, detail, and paging state."""

    session_state.update(filter_widget_defaults(park_id))


def initialize_filter_session_state(
    session_state: MutableMapping[str, Any], park_id: str
) -> None:
    """Initialize missing filter keys without overwriting current selections."""

    for key, value in filter_widget_defaults(park_id).items():
        session_state.setdefault(key, value)


def format_missing(value: Any) -> str:
    """Format absent source data without converting it to a negative answer."""

    if value is None:
        return "Not available"
    if isinstance(value, str) and not value.strip():
        return "Not available"
    return str(value)


def format_category(value: Any) -> str:
    """Format controlled categories while preserving UNKNOWN and negative states."""

    missing = format_missing(value)
    if missing == "Not available":
        return missing
    normalized = str(value).strip().upper()
    return CATEGORY_LABELS.get(normalized, normalized.replace("_", " ").title())


def format_fee(value: Any) -> str:
    """Turn the normalized fee flag into a clear display label."""

    return {"YES": "Paid", "NO": "Free", "UNKNOWN": "Unknown"}.get(
        str(value).strip().upper() if value is not None else "",
        "Not available",
    )


def format_distance(value: Any) -> str:
    """Format a finite kilometer value without changing its meaning."""

    try:
        distance = float(value)
    except (TypeError, ValueError):
        return "Not available"
    if not math.isfinite(distance):
        return "Not available"
    return f"{distance:.1f} km"


def safe_http_url(value: Any) -> Optional[str]:
    """Return source URLs only when they are absolute HTTP(S) links."""

    if not isinstance(value, str) or not value.strip():
        return None
    candidate = value.strip()
    parsed = urlparse(candidate)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        return None
    return candidate


def format_result(result: Mapping[str, Any]) -> dict[str, str]:
    """Create the complete non-visual result-card representation."""

    return {
        "name": format_missing(result.get("name")),
        "distance": format_distance(result.get("distance_km")),
        "campground_type": format_category(result.get("campground_type")),
        "fee_status": format_fee(result.get("fee_charged")),
        "water_category": format_category(result.get("water_category")),
        "restroom_category": format_category(result.get("restroom_category")),
        "recreation_area": format_missing(result.get("recreation_area_name")),
        "activity_information": (
            "Available" if result.get("has_activity_information") else "Not available"
        ),
    }


def source_name(detail: Mapping[str, Any]) -> str:
    """Select the most relevant retained source name without inventing one."""

    for field in ("public_site_name", "site_name", "recarea_name"):
        value = detail.get(field)
        if value is not None and str(value).strip():
            return str(value)
    return "Not available"


def results_message(result_count: int, *, capped: bool = False) -> str:
    """Return a stable status message for zero, bounded, or ordinary results."""

    if result_count == 0:
        return "No campgrounds matched the selected park, radius, and filters."
    if capped:
        return f"Showing the first {result_count} matching campgrounds."
    suffix = "campground" if result_count == 1 else "campgrounds"
    return f"Found {result_count} matching {suffix}."


def page_slice(
    results: Sequence[Mapping[str, Any]],
    page: int,
    page_size: int,
) -> tuple[list[Mapping[str, Any]], int, int]:
    """Return one safe page plus its normalized page index and total page count."""

    if page_size <= 0:
        raise ValueError("page_size must be positive")
    total_pages = max(1, math.ceil(len(results) / page_size))
    safe_page = min(max(page, 0), total_pages - 1)
    start = safe_page * page_size
    return list(results[start : start + page_size]), safe_page, total_pages
