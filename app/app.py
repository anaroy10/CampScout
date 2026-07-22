"""CampScout Streamlit application."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Mapping, Sequence

import pandas as pd
import streamlit as st

from .components import (
    ACTIVITY_FILTER_KEY,
    ACTIVITY_WORDING,
    ANY_OPTION,
    CAMPGROUND_TYPE_FILTER_KEY,
    DISTANCE_WORDING,
    FEE_FILTER_KEY,
    PARK_FILTER_KEY,
    RADIUS_FILTER_KEY,
    RESTROOM_FILTER_KEY,
    WATER_FILTER_KEY,
    convert_filter_state,
    format_category,
    format_distance,
    format_fee,
    format_missing,
    format_result,
    initialize_filter_session_state,
    page_slice,
    reset_filter_session_state,
    results_message,
    safe_http_url,
    source_name,
)
from .database import (
    SETUP_COMMAND,
    DatabaseUnavailableError,
    load_campground_detail,
    load_lookup_data,
    require_database,
    search_campgrounds,
)
from .queries import MAX_SEARCH_RESULTS


PAGE_SIZE_OPTIONS = (10, 25, 50)


def _show_database_setup(message: str) -> None:
    st.error(message)
    st.write("Create the local SQLite database from the processed CampScout data:")
    st.code(SETUP_COMMAND, language="text")


def _reset_filters(first_park_id: str) -> None:
    reset_filter_session_state(st.session_state, first_park_id)


def _reset_filters_and_rerun(first_park_id: str) -> None:
    """Apply the reset and request exactly one immediate UI rerun."""

    _reset_filters(first_park_id)
    st.rerun()


def _render_map(park: Mapping[str, Any], results: Sequence[Mapping[str, Any]]) -> None:
    points = [
        {
            "latitude": park["latitude"],
            "longitude": park["longitude"],
            "label": park["name"],
            "kind": "Selected park",
            "color": "#D62828",
            "size": 180,
        }
    ]
    points.extend(
        {
            "latitude": result["latitude"],
            "longitude": result["longitude"],
            "label": result["name"],
            "kind": "Campground",
            "color": "#007F5F",
            "size": 55,
        }
        for result in results
    )
    st.subheader("Map")
    st.caption("Red marks the selected park; green marks returned campgrounds.")
    st.map(
        pd.DataFrame(points),
        latitude="latitude",
        longitude="longitude",
        color="color",
        size="size",
        height=460,
    )


def _display_value(label: str, value: Any) -> None:
    st.markdown(f"**{label}**")
    st.write(format_missing(value))


def _render_detail(
    result: Mapping[str, Any],
    detail: Mapping[str, Any],
    activities: Sequence[Mapping[str, Any]],
) -> None:
    st.divider()
    st.header(format_missing(detail.get("name")))
    st.metric(DISTANCE_WORDING, format_distance(result.get("distance_km")))

    overview_left, overview_right = st.columns(2)
    with overview_left:
        _display_value("Relevant source name", source_name(detail))
        _display_value(
            "Recreation Area",
            detail.get("linked_recreation_area_name"),
        )
        _display_value("Campground type", format_category(detail.get("campground_type")))
    with overview_right:
        _display_value("Latitude", detail.get("latitude"))
        _display_value("Longitude", detail.get("longitude"))
        _display_value("Nearby towns", detail.get("closest_towns"))

    st.subheader("Fees and amenities")
    fee_col, water_col, restroom_col = st.columns(3)
    with fee_col:
        _display_value("Fee status", format_fee(detail.get("fee_charged")))
        _display_value("Fee type", detail.get("fee_type"))
        _display_value("Fee details", detail.get("fee_description"))
    with water_col:
        _display_value("Water category", format_category(detail.get("water_category")))
        _display_value("Raw water information", detail.get("water_availability_raw"))
    with restroom_col:
        _display_value(
            "Restroom category", format_category(detail.get("restroom_category"))
        )
        _display_value(
            "Raw restroom information", detail.get("restroom_availability_raw")
        )

    st.subheader("Directions and operations")
    _display_value("Directions", detail.get("directions"))
    _display_value("Site directions", detail.get("site_directions"))
    _display_value("Operational information", detail.get("operational_hours"))
    _display_value("Last source update", detail.get("last_update"))

    official_url = safe_http_url(detail.get("official_url"))
    if official_url:
        st.link_button("Open official campground information", official_url)
    else:
        _display_value("Official URL", None)

    st.subheader(ACTIVITY_WORDING)
    if activities:
        for activity in activities:
            st.write(f"- {format_missing(activity.get('activity_name'))}")
    else:
        st.info("Activity information is not available for this campground.")


def _render_result_card(result: Mapping[str, Any]) -> None:
    display = format_result(result)
    with st.container(border=True):
        st.subheader(display["name"])
        st.caption(f"{DISTANCE_WORDING}: {display['distance']}")
        left, middle, right = st.columns(3)
        with left:
            st.write(f"**Type:** {display['campground_type']}")
            st.write(f"**Fee:** {display['fee_status']}")
        with middle:
            st.write(f"**Water:** {display['water_category']}")
            st.write(f"**Restroom:** {display['restroom_category']}")
        with right:
            st.write(f"**Recreation Area:** {display['recreation_area']}")
            st.write(
                f"**Activity information:** {display['activity_information']}"
            )
        if st.button(
            f"Show details for {display['name']}",
            key=f"detail_{result['campground_id']}",
        ):
            st.session_state["selected_detail_id"] = result["campground_id"]


def _render_results(
    database_path: Path,
    parks_by_id: Mapping[str, Mapping[str, Any]],
) -> None:
    if "search_results" not in st.session_state:
        st.info("Choose a park and filters, then press Search.")
        return

    results = st.session_state["search_results"]
    capped = len(results) == MAX_SEARCH_RESULTS
    message = results_message(len(results), capped=capped)
    if not results:
        st.info(message)
        return

    st.success(message)
    park = parks_by_id[st.session_state["search_park"]]
    _render_map(park, results)

    st.subheader("Matching campgrounds")
    page_size = st.selectbox(
        "Results per page",
        PAGE_SIZE_OPTIONS,
        index=1,
        key="results_page_size",
    )
    current_page = int(st.session_state.get("results_page", 0))
    page_results, current_page, total_pages = page_slice(
        results, current_page, page_size
    )
    st.session_state["results_page"] = current_page
    first = current_page * page_size + 1
    last = first + len(page_results) - 1
    st.caption(f"Showing results {first}–{last} of {len(results)}.")

    previous_col, page_col, next_col = st.columns([1, 2, 1])
    with previous_col:
        if st.button("Previous page", disabled=current_page == 0):
            st.session_state["results_page"] = current_page - 1
            st.rerun()
    with page_col:
        st.markdown(
            f"<p style='text-align:center'>Page {current_page + 1} of {total_pages}</p>",
            unsafe_allow_html=True,
        )
    with next_col:
        if st.button("Next page", disabled=current_page + 1 >= total_pages):
            st.session_state["results_page"] = current_page + 1
            st.rerun()

    for result in page_results:
        _render_result_card(result)

    selected_id = st.session_state.get("selected_detail_id")
    selected_result = next(
        (result for result in results if result["campground_id"] == selected_id),
        None,
    )
    if selected_result is None:
        return
    try:
        detail, activities = load_campground_detail(selected_id, database_path)
    except DatabaseUnavailableError as exc:
        st.error(str(exc))
        return
    if detail is None:
        st.warning("This campground is no longer available in the database.")
        return
    _render_detail(selected_result, detail, activities)


def main() -> None:
    st.set_page_config(page_title="CampScout", page_icon="🏕️", layout="wide")
    st.title("CampScout")
    st.write("Discover Forest Service campgrounds near a selected national park.")

    try:
        database_path = require_database()
        lookup_data = load_lookup_data(str(database_path))
    except DatabaseUnavailableError as exc:
        _show_database_setup(str(exc))
        st.stop()
    except (OSError, sqlite3.Error):
        _show_database_setup(
            "The CampScout database is unavailable or has not been initialized."
        )
        st.stop()

    parks = lookup_data["parks"]
    activities = lookup_data["activities"]
    if not parks:
        _show_database_setup("The CampScout database does not contain any parks.")
        st.stop()

    parks_by_id = {park["park_id"]: park for park in parks}
    activities_by_id = {
        activity["activity_id"]: activity for activity in activities
    }
    first_park_id = parks[0]["park_id"]
    initialize_filter_session_state(st.session_state, first_park_id)

    with st.sidebar:
        st.header("Search filters")
        if st.button(
            "Reset filters", key="reset_filters_button", use_container_width=True
        ):
            _reset_filters_and_rerun(first_park_id)

        with st.form("campground_search"):
            park_id = st.selectbox(
                "National park",
                options=list(parks_by_id),
                format_func=lambda value: parks_by_id[value]["name"],
                key=PARK_FILTER_KEY,
            )
            radius_km = st.number_input(
                "Search radius (kilometers)",
                min_value=1.0,
                max_value=1000.0,
                step=25.0,
                key=RADIUS_FILTER_KEY,
            )
            activity_ids = st.multiselect(
                "Activities",
                options=list(activities_by_id),
                format_func=lambda value: activities_by_id[value]["name"],
                help="Campgrounds must provide every selected activity through their recreation area.",
                key=ACTIVITY_FILTER_KEY,
            )
            campground_type = st.selectbox(
                "Campground type",
                [ANY_OPTION, "CAMPGROUND", "GROUP CAMPGROUND", "HORSE CAMP"],
                format_func=format_category,
                key=CAMPGROUND_TYPE_FILTER_KEY,
            )
            fee_status = st.selectbox(
                "Fee status",
                [ANY_OPTION, "Free", "Paid"],
                key=FEE_FILTER_KEY,
            )
            water_category = st.selectbox(
                "Water category",
                [
                    ANY_OPTION,
                    "AVAILABLE",
                    "NOT_AVAILABLE",
                    "NATURAL_SOURCE",
                    "NEARBY",
                    "OTHER",
                    "UNKNOWN",
                ],
                format_func=format_category,
                key=WATER_FILTER_KEY,
            )
            restroom_category = st.selectbox(
                "Restroom category",
                [
                    ANY_OPTION,
                    "FLUSH",
                    "VAULT",
                    "COMPOSTING",
                    "PORTABLE",
                    "MULTIPLE",
                    "NONE",
                    "OTHER",
                    "UNKNOWN",
                ],
                format_func=format_category,
                key=RESTROOM_FILTER_KEY,
            )
            submitted = st.form_submit_button(
                "Search",
                key="search_button",
                type="primary",
                use_container_width=True,
            )

    if submitted:
        filters = convert_filter_state(
            {
                "park_id": park_id,
                "radius_km": radius_km,
                "activity_ids": activity_ids,
                "campground_type": campground_type,
                "fee_status": fee_status,
                "water_category": water_category,
                "restroom_category": restroom_category,
                "limit": MAX_SEARCH_RESULTS,
            }
        )
        try:
            with st.spinner("Searching nearby campgrounds…"):
                results = search_campgrounds(filters, database_path)
        except (DatabaseUnavailableError, ValueError) as exc:
            st.error(str(exc))
        else:
            st.session_state["search_results"] = results
            st.session_state["search_park"] = park_id
            st.session_state["results_page"] = 0
            st.session_state.pop("selected_detail_id", None)

    _render_results(database_path, parks_by_id)
