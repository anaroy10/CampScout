import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from urllib.error import URLError
from urllib.request import urlopen

import pytest
from streamlit.testing.v1 import AppTest

from app import database
from app import queries
from app import app as streamlit_application
from app.components import (
    ACTIVITY_FILTER_KEY,
    ACTIVITY_WORDING,
    CAMPGROUND_TYPE_FILTER_KEY,
    DISTANCE_WORDING,
    FEE_FILTER_KEY,
    FILTER_WIDGET_KEYS,
    PARK_FILTER_KEY,
    RADIUS_FILTER_KEY,
    RESTROOM_FILTER_KEY,
    SEARCH_TEXT_FILTER_KEY,
    WATER_FILTER_KEY,
    convert_filter_state,
    filter_widget_defaults,
    format_category,
    format_distance,
    format_fee,
    format_missing,
    format_result,
    initialize_filter_session_state,
    page_slice,
    reset_filter_session_state,
    reset_filter_values,
    results_message,
    safe_http_url,
    source_name,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def test_filter_state_conversion_preserves_unknown_and_optional_filters():
    converted = convert_filter_state(
        {
            "park_id": "park-1",
            "radius_km": 125,
            "activity_ids": ["29", "31"],
            "campground_type": "Any",
            "fee_status": "Free",
            "water_category": "UNKNOWN",
            "restroom_category": "Any",
            "limit": 500,
        }
    )

    assert converted == {
        "park_id": "park-1",
        "radius_km": 125.0,
        "activity_ids": ["29", "31"],
        "campground_type": None,
        "fee_status": "Free",
        "water_category": "UNKNOWN",
        "restroom_category": None,
        "limit": 500,
    }


def test_reset_filter_values_returns_independent_activity_lists():
    first = reset_filter_values("park-1")
    second = reset_filter_values("park-1")
    first["activity_ids"].append("29")

    assert second["activity_ids"] == []
    assert second["campground_type"] == "Any"


def test_reset_filter_session_state_resets_every_filter_and_preserves_ui_state():
    session_state = {
        PARK_FILTER_KEY: "park-9",
        RADIUS_FILTER_KEY: 725.0,
        ACTIVITY_FILTER_KEY: ["29", "31"],
        CAMPGROUND_TYPE_FILTER_KEY: "HORSE CAMP",
        FEE_FILTER_KEY: "Paid",
        WATER_FILTER_KEY: "UNKNOWN",
        RESTROOM_FILTER_KEY: "VAULT",
        SEARCH_TEXT_FILTER_KEY: "lakeside",
        "search_results": [{"campground_id": "camp-1"}],
        "search_park": "park-9",
        "selected_detail_id": "camp-1",
        "results_page": 3,
        "results_page_size": 50,
    }

    reset_filter_session_state(session_state, "park-1")

    expected = filter_widget_defaults("park-1")
    assert tuple(expected) == FILTER_WIDGET_KEYS
    assert {key: session_state[key] for key in FILTER_WIDGET_KEYS} == expected
    assert session_state["search_results"] == [{"campground_id": "camp-1"}]
    assert session_state["search_park"] == "park-9"
    assert session_state["selected_detail_id"] == "camp-1"
    assert session_state["results_page"] == 3
    assert session_state["results_page_size"] == 50


def test_reset_button_requests_exactly_one_rerun(monkeypatch):
    class FakeStreamlit:
        def __init__(self):
            self.session_state = {
                WATER_FILTER_KEY: "AVAILABLE",
                "selected_detail_id": "camp-1",
            }
            self.rerun_count = 0

        def rerun(self):
            self.rerun_count += 1

    fake_streamlit = FakeStreamlit()
    monkeypatch.setattr(streamlit_application, "st", fake_streamlit)

    streamlit_application._reset_filters_and_rerun("park-1")

    assert fake_streamlit.rerun_count == 1
    assert fake_streamlit.session_state == {
        **filter_widget_defaults("park-1"),
        "selected_detail_id": "camp-1",
    }


def test_filter_initialization_preserves_existing_widget_values():
    session_state = {
        PARK_FILTER_KEY: "park-9",
        RADIUS_FILTER_KEY: 250.0,
        SEARCH_TEXT_FILTER_KEY: "forest",
    }

    initialize_filter_session_state(session_state, "park-1")

    assert session_state[PARK_FILTER_KEY] == "park-9"
    assert session_state[RADIUS_FILTER_KEY] == 250.0
    assert session_state[SEARCH_TEXT_FILTER_KEY] == "forest"
    assert session_state[ACTIVITY_FILTER_KEY] == []
    assert session_state[WATER_FILTER_KEY] == "Any"


def test_activity_all_semantics_and_parameter_construction():
    sql, parameters = queries.build_search_query(
        park_id="park-1",
        radius_km=100,
        activity_ids=["29", "31", "29"],
        limit=25,
    )

    assert "HAVING COUNT(DISTINCT raa.activity_id) = ?" in sql
    assert "IN (?, ?)" in sql
    assert parameters[:3] == ("29", "31", 2)
    assert parameters[-3:] == ("park-1", 100.0, 25)
    assert "park-1" not in sql


def test_missing_and_unknown_formatting_remain_distinct():
    assert format_missing(None) == "Not available"
    assert format_missing("") == "Not available"
    assert format_category("UNKNOWN") == "Unknown"
    assert format_category("NONE") == "None"
    assert format_category("NOT_AVAILABLE") == "Not available"
    assert format_fee("UNKNOWN") == "Unknown"
    assert format_fee("NO") == "Free"


def test_result_formatting_contains_required_user_facing_values():
    formatted = format_result(
        {
            "name": "Forest Camp",
            "distance_km": 12.345,
            "campground_type": "GROUP CAMPGROUND",
            "fee_charged": "YES",
            "water_category": "UNKNOWN",
            "restroom_category": "NONE",
            "recreation_area_name": None,
            "has_activity_information": 0,
        }
    )

    assert formatted == {
        "name": "Forest Camp",
        "distance": "12.3 km",
        "campground_type": "Group campground",
        "fee_status": "Paid",
        "water_category": "Unknown",
        "restroom_category": "None",
        "recreation_area": "Not available",
        "activity_information": "Not available",
    }
    assert format_distance(float("nan")) == "Not available"


def test_no_results_and_capped_results_messages():
    assert results_message(0).startswith("No campgrounds matched")
    assert results_message(1) == "Found 1 matching campground."
    assert results_message(500, capped=True) == (
        "Showing the first 500 matching campgrounds."
    )


def test_pagination_normalizes_out_of_range_pages():
    results = [{"id": value} for value in range(12)]

    page, page_index, total_pages = page_slice(results, 99, 5)

    assert [row["id"] for row in page] == [10, 11]
    assert page_index == 2
    assert total_pages == 3
    with pytest.raises(ValueError, match="page_size"):
        page_slice(results, 0, 0)


def test_url_and_source_name_formatting():
    assert safe_http_url("https://example.test/camp") == "https://example.test/camp"
    assert safe_http_url("http://example.test/camp") == "http://example.test/camp"
    assert safe_http_url("javascript:alert(1)") is None
    assert safe_http_url("/relative") is None
    assert source_name(
        {"public_site_name": "", "site_name": "Source Camp", "recarea_name": "Area"}
    ) == "Source Camp"


def test_missing_database_handling_does_not_require_environment(tmp_path):
    missing = tmp_path / "missing.db"

    with pytest.raises(database.DatabaseUnavailableError, match="not available"):
        database.require_database(missing)

    assert database.SETUP_COMMAND == "python -m db.build_database --reset"


def test_database_search_wrapper_passes_converted_filters_as_parameters(monkeypatch):
    captured = {}

    def fake_find(park_id, radius_km, **kwargs):
        captured.update(park_id=park_id, radius_km=radius_km, **kwargs)
        return []

    monkeypatch.setattr(database.queries, "find_campgrounds", fake_find)
    filters = {
        "park_id": "park-1",
        "radius_km": 100.0,
        "limit": 500,
        "campground_type": None,
        "fee_status": "Free",
        "water_category": "UNKNOWN",
        "restroom_category": None,
        "activity_ids": ["29", "31"],
    }

    assert database.search_campgrounds(filters, Path("test.db")) == []
    assert captured["park_id"] == "park-1"
    assert captured["radius_km"] == 100.0
    assert captured["activity_ids"] == ["29", "31"]
    assert captured["water_category"] == "UNKNOWN"
    assert captured["database_path"] == Path("test.db")


def test_required_wording_is_exact():
    assert ACTIVITY_WORDING == "Activities available in the campground's recreation area"
    assert DISTANCE_WORDING == (
        "Approximate straight-line distance from the park's representative coordinate"
    )


def test_root_entrypoint_executes_without_shadowing_app_package(monkeypatch, tmp_path):
    monkeypatch.setenv("CAMPSCOUT_DB_PATH", str(tmp_path / "missing.db"))

    application = AppTest.from_file(REPOSITORY_ROOT / "streamlit_app.py")
    application.run(timeout=20)

    assert not application.exception
    assert any(database.SETUP_COMMAND in block.value for block in application.code)


def test_documented_root_command_starts_healthy_and_stops_cleanly(tmp_path):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]

    environment = os.environ.copy()
    environment["CAMPSCOUT_DB_PATH"] = str(tmp_path / "missing.db")
    command = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        "streamlit_app.py",
        "--server.headless=true",
        f"--server.port={port}",
        "--browser.gatherUsageStats=false",
    ]
    process = subprocess.Popen(
        command,
        cwd=REPOSITORY_ROOT,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    healthy = False
    output = ""
    try:
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline and process.poll() is None:
            try:
                with urlopen(
                    f"http://127.0.0.1:{port}/_stcore/health", timeout=1
                ) as response:
                    healthy = response.status == 200 and response.read().strip() == b"ok"
                if healthy:
                    break
            except (OSError, URLError):
                time.sleep(0.2)
    finally:
        if process.poll() is None:
            process.terminate()
        try:
            output, _ = process.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            output, _ = process.communicate(timeout=10)

    assert healthy, output
    assert process.poll() is not None
    assert "python -m streamlit run streamlit_app.py" in (
        REPOSITORY_ROOT / "README.md"
    ).read_text(encoding="utf-8")

