"""Profile CampScout's immutable raw CSV inputs.

Run from the repository root with::

    python -m etl.profile_raw_data

This module deliberately performs profiling only. It does not clean values, infer
business mappings, or write processed data.
"""

from __future__ import annotations

import csv
import json
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, MutableMapping, Optional, Sequence, Set, Tuple


RAW_DIR = Path("data/raw")
REPORT_DIR = Path("reports/profiling")
EXPECTED_FILES = (
    "Recreation_Sites_INFRA.csv",
    "Recreation_Area_Activities.csv",
    "national_parks_raw.csv",
)
ENCODING = "utf-8-sig"
SAMPLE_LIMIT = 5
COMMON_VALUE_LIMIT = 20

SITE_KEY_COLUMNS = ("site_cn", "globalid", "objectid", "site_id")
SITE_MISSINGNESS_COLUMNS = (
    "latitude",
    "longitude",
    "fee_charged",
    "water_availability",
    "restroom_availability",
    "directions",
    "usda_portal_url",
    "total_capacity",
)
SITE_CATEGORIES = ("CAMPGROUND", "GROUP CAMPGROUND", "HORSE CAMP")

ACTIVITY_AREA_ATTRIBUTES = (
    "X",
    "Y",
    "RECAREANAME",
    "LONGITUDE",
    "LATITUDE",
    "RECAREAURL",
    "OPEN_SEASON_START",
    "OPEN_SEASON_END",
    "FORESTNAME",
    "MARKERTYPE",
    "MARKERACTIVITY",
    "MARKERACTIVITYGROUP",
    "RECAREADESCRIPTION",
    "SPOTLIGHTDISPLAY",
    "ATTRACTIONDISPLAY",
    "ACCESSIBILITY",
    "OPENSTATUS",
    "SHAPE",
)

PARK_EXAMPLE_COLUMNS = (
    "Location",
    "Area (2021)[13]",
    "Date established as park[7][12]",
    "Recreation visitors (2021)[11]",
)


class ProfilingError(RuntimeError):
    """An actionable error while reading or profiling a source file."""


def _is_missing(value: str) -> bool:
    """Treat empty and whitespace-only CSV fields as missing without altering them."""

    return value.strip() == ""


def _identifier_column(column_name: str) -> bool:
    normalized = column_name.strip().lower()
    if normalized == "":
        return True
    return (
        normalized in {"objectid", "globalid"}
        or normalized.endswith("id")
        or normalized.endswith("_id")
        or normalized.endswith("_cn")
        or normalized == "cn"
    )


INTEGER_RE = re.compile(r"^[+-]?\d+$")
FLOAT_RE = re.compile(r"^[+-]?(?:\d+\.\d*|\d*\.\d+)(?:[eE][+-]?\d+)?$")
ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
ISO_DATETIME_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:?\d{2})?$"
)


def infer_data_type(column_name: str, values: Iterable[str]) -> str:
    """Infer a conservative logical type while forcing identifier fields to text."""

    observed = list(values)
    if not observed:
        return "empty"
    if _identifier_column(column_name):
        return "string"

    upper_values = {value.upper() for value in observed}
    if upper_values and upper_values <= {"Y", "N", "YES", "NO", "TRUE", "FALSE", "T", "F"}:
        return "boolean"

    if all(INTEGER_RE.fullmatch(value) for value in observed):
        # Numeric-looking values with meaningful leading zeroes remain strings.
        if any(
            re.fullmatch(r"[+-]?0\d+", value) and int(value) != 0
            for value in observed
        ):
            return "string"
        return "integer"

    if all(INTEGER_RE.fullmatch(value) or FLOAT_RE.fullmatch(value) for value in observed):
        return "float"

    if all(ISO_DATETIME_RE.fullmatch(value) for value in observed):
        return "datetime"
    if all(ISO_DATE_RE.fullmatch(value) for value in observed):
        return "date"
    try:
        if all(datetime.strptime(value, "%B %d, %Y") for value in observed):
            return "date"
    except ValueError:
        pass
    return "string"


def _percentage(numerator: int, denominator: int) -> float:
    return round((numerator / denominator * 100.0) if denominator else 0.0, 6)


def _require_columns(path: Path, header: Sequence[str], required: Sequence[str]) -> None:
    missing = [name for name in required if name not in header]
    if missing:
        raise ProfilingError(
            f"{path.as_posix()} is missing required columns: {', '.join(repr(name) for name in missing)}"
        )


def _open_reader(path: Path):
    if not path.is_file():
        raise ProfilingError(f"Required raw CSV file is missing: {path.as_posix()}")
    try:
        handle = path.open("r", encoding=ENCODING, newline="")
        reader = csv.reader(handle)
        header = next(reader)
    except UnicodeDecodeError as exc:
        try:
            handle.close()
        except UnboundLocalError:
            pass
        raise ProfilingError(
            f"Cannot decode {path.as_posix()} as UTF-8: byte {exc.start}. "
            "The raw file was not modified."
        ) from exc
    except (OSError, csv.Error) as exc:
        try:
            handle.close()
        except UnboundLocalError:
            pass
        raise ProfilingError(f"Cannot read CSV file {path.as_posix()}: {exc}") from exc
    except StopIteration as exc:
        handle.close()
        raise ProfilingError(f"CSV file has no header row: {path.as_posix()}") from exc

    if not header:
        handle.close()
        raise ProfilingError(f"CSV file has an empty header row: {path.as_posix()}")
    duplicates = sorted(name for name, count in Counter(header).items() if count > 1)
    if duplicates:
        handle.close()
        raise ProfilingError(
            f"CSV file {path.as_posix()} has duplicate column names: {duplicates!r}"
        )
    return handle, reader, header


def _rows(path: Path):
    """Yield the literal header and rows, with clear decode/shape errors."""

    handle, reader, header = _open_reader(path)
    try:
        yield header
        for row in reader:
            if len(row) != len(header):
                raise ProfilingError(
                    f"Malformed CSV row in {path.as_posix()} at physical line {reader.line_num}: "
                    f"expected {len(header)} fields, found {len(row)}"
                )
            yield row
    except UnicodeDecodeError as exc:
        raise ProfilingError(
            f"Cannot decode {path.as_posix()} as UTF-8: byte {exc.start}. "
            "The raw file was not modified."
        ) from exc
    except csv.Error as exc:
        raise ProfilingError(
            f"Cannot parse CSV file {path.as_posix()} near physical line {reader.line_num}: {exc}"
        ) from exc
    finally:
        handle.close()


@dataclass
class DatasetProfile:
    summary: Dict[str, object]
    column_profiles: List[Dict[str, object]]
    key_analysis: List[Dict[str, object]]
    column_samples: Dict[str, List[str]]


def _key_record(
    dataset: str,
    columns: Sequence[str],
    row_count: int,
    missing_key_rows: int,
    distinct_non_missing_count: int,
) -> Dict[str, object]:
    non_missing = row_count - missing_key_rows
    unique_non_missing = non_missing > 0 and distinct_non_missing_count == non_missing
    complete = row_count > 0 and missing_key_rows == 0
    return {
        "dataset": dataset,
        "candidate": json.dumps(list(columns), ensure_ascii=False),
        "column_count": len(columns),
        "row_count": row_count,
        "non_missing_key_rows": non_missing,
        "missing_key_rows": missing_key_rows,
        "distinct_non_missing_count": distinct_non_missing_count,
        "duplicate_non_missing_rows": non_missing - distinct_non_missing_count,
        "is_unique_among_non_missing": unique_non_missing,
        "is_complete": complete,
        "is_candidate_key": complete and unique_non_missing,
    }


def profile_dataset(path: Path, extra_keys: Sequence[Sequence[str]] = ()) -> DatasetProfile:
    """Stream a CSV once and calculate exact column, row, and key statistics."""

    iterator = _rows(path)
    header = next(iterator)
    indexes = {name: position for position, name in enumerate(header)}
    for key in extra_keys:
        _require_columns(path, header, list(key))

    missing_counts = [0] * len(header)
    max_lengths = [0] * len(header)
    distinct_values: List[Set[str]] = [set() for _ in header]
    samples: List[List[str]] = [[] for _ in header]
    exact_row_counts: Counter = Counter()
    extra_key_values: List[Set[Tuple[str, ...]]] = [set() for _ in extra_keys]
    extra_key_missing = [0] * len(extra_keys)
    row_count = 0

    for row in iterator:
        row_count += 1
        exact_row_counts[tuple(row)] += 1
        for position, value in enumerate(row):
            max_lengths[position] = max(max_lengths[position], len(value))
            if _is_missing(value):
                missing_counts[position] += 1
                continue
            distinct_values[position].add(value)
            if value not in samples[position] and len(samples[position]) < SAMPLE_LIMIT:
                samples[position].append(value)

        for key_position, key in enumerate(extra_keys):
            values = tuple(row[indexes[name]] for name in key)
            if any(_is_missing(value) for value in values):
                extra_key_missing[key_position] += 1
            else:
                extra_key_values[key_position].add(values)

    duplicate_groups = sum(1 for count in exact_row_counts.values() if count > 1)
    duplicate_rows = sum(count - 1 for count in exact_row_counts.values() if count > 1)
    duplicate_rows_involved = sum(count for count in exact_row_counts.values() if count > 1)

    column_rows: List[Dict[str, object]] = []
    key_rows: List[Dict[str, object]] = []
    inferred_types: Dict[str, str] = {}
    candidate_key_columns: List[str] = []
    for position, name in enumerate(header):
        non_missing = row_count - missing_counts[position]
        inferred = infer_data_type(name, distinct_values[position])
        inferred_types[name] = inferred
        column_rows.append(
            {
                "dataset": path.name,
                "column_position": position + 1,
                "column_name": name,
                "inferred_data_type": inferred,
                "row_count": row_count,
                "non_missing_count": non_missing,
                "missing_count": missing_counts[position],
                "missing_percentage": _percentage(missing_counts[position], row_count),
                "distinct_count": len(distinct_values[position]),
                "sample_non_null_values": json.dumps(samples[position], ensure_ascii=False),
                "maximum_text_length": max_lengths[position],
            }
        )
        key_row = _key_record(
            path.name,
            [name],
            row_count,
            missing_counts[position],
            len(distinct_values[position]),
        )
        key_rows.append(key_row)
        if key_row["is_candidate_key"]:
            candidate_key_columns.append(name)

    for position, key in enumerate(extra_keys):
        key_rows.append(
            _key_record(
                path.name,
                key,
                row_count,
                extra_key_missing[position],
                len(extra_key_values[position]),
            )
        )

    summary: Dict[str, object] = {
        "relative_path": path.as_posix(),
        "encoding": "UTF-8 with optional BOM",
        "file_size_bytes": path.stat().st_size,
        "row_count": row_count,
        "column_count": len(header),
        "column_names": list(header),
        "inferred_data_types": inferred_types,
        "exact_duplicate_row_count": duplicate_rows,
        "exact_duplicate_group_count": duplicate_groups,
        "exact_duplicate_rows_involved": duplicate_rows_involved,
        "single_column_candidate_keys": candidate_key_columns,
    }
    return DatasetProfile(
        summary=summary,
        column_profiles=column_rows,
        key_analysis=key_rows,
        column_samples={name: samples[position] for position, name in enumerate(header)},
    )


def _profile_lookup(profile: DatasetProfile) -> Dict[str, Dict[str, object]]:
    return {str(row["column_name"]): row for row in profile.column_profiles}


def _frequency_rows(counter: Counter, limit: Optional[int] = None) -> List[Dict[str, object]]:
    items = sorted(counter.items(), key=lambda item: (-item[1], item[0]))
    if limit is not None:
        items = items[:limit]
    return [{"value": value, "count": count} for value, count in items]


def analyze_sites(path: Path, profile: DatasetProfile) -> Tuple[Dict[str, object], Dict[str, object]]:
    iterator = _rows(path)
    header = next(iterator)
    required = list(SITE_KEY_COLUMNS) + list(SITE_MISSINGNESS_COLUMNS) + [
        "site_subtype",
        "site_name",
    ]
    _require_columns(path, header, required)
    indexes = {name: position for position, name in enumerate(header)}

    subtype_counts: Counter = Counter()
    water_counts: Counter = Counter()
    restroom_counts: Counter = Counter()
    site_id_counts: Counter = Counter()
    site_id_records: MutableMapping[str, List[Dict[str, str]]] = defaultdict(list)

    for row in iterator:
        subtype = row[indexes["site_subtype"]]
        subtype_counts[subtype] += 1
        for column, counter in (
            ("water_availability", water_counts),
            ("restroom_availability", restroom_counts),
        ):
            value = row[indexes[column]]
            if not _is_missing(value):
                counter[value] += 1

        site_id = row[indexes["site_id"]]
        if not _is_missing(site_id):
            site_id_counts[site_id] += 1
            if len(site_id_records[site_id]) < 3:
                site_id_records[site_id].append(
                    {
                        "site_cn": row[indexes["site_cn"]],
                        "globalid": row[indexes["globalid"]],
                        "objectid": row[indexes["objectid"]],
                        "site_name": row[indexes["site_name"]],
                        "site_subtype": subtype,
                    }
                )

    columns = _profile_lookup(profile)
    category_counts = {category: subtype_counts[category] for category in SITE_CATEGORIES}
    combined_count = sum(category_counts.values())
    key_uniqueness: Dict[str, object] = {}
    key_rows = {json.loads(str(row["candidate"]))[0]: row for row in profile.key_analysis if row["column_count"] == 1}
    for column in SITE_KEY_COLUMNS:
        key_uniqueness[column] = {
            name: key_rows[column][name]
            for name in (
                "non_missing_key_rows",
                "missing_key_rows",
                "distinct_non_missing_count",
                "duplicate_non_missing_rows",
                "is_unique_among_non_missing",
                "is_complete",
                "is_candidate_key",
            )
        }

    selected_missingness = {
        column: {
            "missing_count": columns[column]["missing_count"],
            "missing_percentage": columns[column]["missing_percentage"],
        }
        for column in SITE_MISSINGNESS_COLUMNS
    }
    duplicate_ids = [
        {
            "site_id": site_id,
            "count": count,
            "sample_records": site_id_records[site_id],
        }
        for site_id, count in sorted(site_id_counts.items(), key=lambda item: (-item[1], item[0]))
        if count > 1
    ][:10]

    analysis = {
        "site_subtype_frequencies": _frequency_rows(subtype_counts),
        "selected_subtype_counts": category_counts,
        "selected_subtype_combined_count": combined_count,
        "selected_key_uniqueness": key_uniqueness,
        "selected_column_missingness": selected_missingness,
        "duplicated_site_id_distinct_value_count": sum(
            1 for count in site_id_counts.values() if count > 1
        ),
        "duplicated_site_id_excess_row_count": sum(
            count - 1 for count in site_id_counts.values() if count > 1
        ),
    }
    examples = {
        "duplicated_site_id_examples": duplicate_ids,
        "common_raw_water_values": _frequency_rows(water_counts, COMMON_VALUE_LIMIT),
        "common_raw_restroom_values": _frequency_rows(restroom_counts, COMMON_VALUE_LIMIT),
    }
    return analysis, examples


def analyze_activities(path: Path) -> Tuple[Dict[str, object], Dict[str, object]]:
    iterator = _rows(path)
    header = next(iterator)
    required = ["RECAREAID", "ACTIVITYID", "ACTIVITYNAME"] + list(ACTIVITY_AREA_ATTRIBUTES)
    _require_columns(path, header, required)
    indexes = {name: position for position, name in enumerate(header)}

    recarea_ids: Set[str] = set()
    activity_ids: Set[str] = set()
    missing_either = 0
    pair_counts: Counter = Counter()
    name_to_ids: MutableMapping[str, Set[str]] = defaultdict(set)
    id_to_names: MutableMapping[str, Set[str]] = defaultdict(set)
    area_values: Dict[str, MutableMapping[str, Set[str]]] = {
        attribute: defaultdict(set) for attribute in ACTIVITY_AREA_ATTRIBUTES
    }

    for row in iterator:
        recarea_id = row[indexes["RECAREAID"]]
        activity_id = row[indexes["ACTIVITYID"]]
        activity_name = row[indexes["ACTIVITYNAME"]]
        if not _is_missing(recarea_id):
            recarea_ids.add(recarea_id)
            for attribute in ACTIVITY_AREA_ATTRIBUTES:
                value = row[indexes[attribute]]
                if not _is_missing(value):
                    area_values[attribute][recarea_id].add(value)
        if not _is_missing(activity_id):
            activity_ids.add(activity_id)

        if _is_missing(recarea_id) or _is_missing(activity_id):
            missing_either += 1
        else:
            pair_counts[(recarea_id, activity_id)] += 1

        if not _is_missing(activity_name) and not _is_missing(activity_id):
            name_to_ids[activity_name].add(activity_id)
            id_to_names[activity_id].add(activity_name)

    duplicate_pair_count = sum(count - 1 for count in pair_counts.values() if count > 1)
    duplicate_pair_examples = [
        {"RECAREAID": pair[0], "ACTIVITYID": pair[1], "count": count}
        for pair, count in sorted(pair_counts.items(), key=lambda item: (-item[1], item[0]))
        if count > 1
    ][:10]
    multiple_id_names = [
        {"ACTIVITYNAME": name, "ACTIVITYIDs": sorted(ids), "id_count": len(ids)}
        for name, ids in sorted(name_to_ids.items())
        if len(ids) > 1
    ]
    multiple_name_ids = [
        {"ACTIVITYID": activity_id, "ACTIVITYNAMEs": sorted(names), "name_count": len(names)}
        for activity_id, names in sorted(id_to_names.items())
        if len(names) > 1
    ]

    conflicts: Dict[str, object] = {}
    for attribute in ACTIVITY_AREA_ATTRIBUTES:
        conflict_rows = [
            {
                "RECAREAID": recarea_id,
                "distinct_non_null_value_count": len(values),
                "values": sorted(values)[:5],
            }
            for recarea_id, values in sorted(area_values[attribute].items())
            if len(values) > 1
        ]
        conflicts[attribute] = {
            "conflicting_recarea_count": len(conflict_rows),
            "examples": conflict_rows[:10],
        }

    analysis = {
        "unique_RECAREAID_count": len(recarea_ids),
        "unique_ACTIVITYID_count": len(activity_ids),
        "rows_missing_either_identifier": missing_either,
        "duplicate_RECAREAID_ACTIVITYID_pair_count": duplicate_pair_count,
        "activity_name_to_multiple_ids_count": len(multiple_id_names),
        "activity_id_to_multiple_names_count": len(multiple_name_ids),
        "recreation_area_attribute_conflicts": conflicts,
    }
    examples = {
        "duplicate_RECAREAID_ACTIVITYID_pair_examples": duplicate_pair_examples,
        "activity_names_mapping_to_multiple_ids": multiple_id_names,
        "activity_ids_mapping_to_multiple_names": multiple_name_ids,
    }
    return analysis, examples


def _has_unusual_whitespace(value: str) -> bool:
    if value != value.strip() or re.search(r"\s{2,}", value):
        return True
    return any(
        unicodedata.category(character) in {"Cf", "Zl", "Zp"}
        or (unicodedata.category(character) == "Zs" and character != " ")
        for character in value
    )


def analyze_parks(path: Path, profile: DatasetProfile) -> Tuple[Dict[str, object], Dict[str, object]]:
    iterator = _rows(path)
    header = next(iterator)
    _require_columns(path, header, ["Name"] + list(PARK_EXAMPLE_COLUMNS))
    indexes = {name: position for position, name in enumerate(header)}

    star_names: List[str] = []
    citation_names: List[str] = []
    whitespace_names: List[str] = []
    for row in iterator:
        name = row[indexes["Name"]]
        if "*" in name:
            star_names.append(name)
        if re.search(r"\[[^\]]+\]", name):
            citation_names.append(name)
        if _has_unusual_whitespace(name):
            whitespace_names.append(name)

    columns = _profile_lookup(profile)
    empty_columns = [
        name for name in header if int(columns[name]["missing_count"]) == int(columns[name]["row_count"])
    ]
    unusual_combined = sorted(set(star_names + citation_names + whitespace_names))
    analysis = {
        "empty_columns": empty_columns,
        "names_with_stars_count": len(star_names),
        "names_with_citations_count": len(citation_names),
        "names_with_unusual_whitespace_count": len(whitespace_names),
        "names_with_any_flag_count": len(unusual_combined),
    }
    examples = {
        "Location_examples": profile.column_samples["Location"],
        "Area_examples": profile.column_samples["Area (2021)[13]"],
        "Date_established_examples": profile.column_samples["Date established as park[7][12]"],
        "Recreation_visitors_examples": profile.column_samples[
            "Recreation visitors (2021)[11]"
        ],
        "names_containing_stars": star_names,
        "names_containing_citations": citation_names,
        "names_with_unusual_whitespace": whitespace_names,
        "names_with_any_flag": unusual_combined,
    }
    return analysis, examples


def _write_json(path: Path, value: object) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def _write_csv(path: Path, rows: Sequence[Mapping[str, object]], fieldnames: Sequence[str]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="raise")
        writer.writeheader()
        writer.writerows(rows)


def _yes_no(value: object) -> str:
    return "yes" if value else "no"


def render_findings(summary: Mapping[str, object], examples: Mapping[str, object]) -> str:
    datasets = summary["datasets"]
    sites = datasets["Recreation_Sites_INFRA.csv"]
    activities = datasets["Recreation_Area_Activities.csv"]
    parks = datasets["national_parks_raw.csv"]
    site_analysis = sites["special_analysis"]
    activity_analysis = activities["special_analysis"]
    park_analysis = parks["special_analysis"]

    lines = [
        "# Raw data profiling findings",
        "",
        "This report is generated by `python -m etl.profile_raw_data` from the immutable raw CSV files. Missing means an empty or whitespace-only field. Distinct counts exclude missing values, and an exact duplicate-row count counts repeated rows beyond the first occurrence.",
        "",
        "## Dataset inventory",
        "",
        "| Dataset | Bytes | Rows | Columns | Exact duplicate rows |",
        "|---|---:|---:|---:|---:|",
    ]
    for filename in EXPECTED_FILES:
        dataset = datasets[filename]
        lines.append(
            f"| `{filename}` | {dataset['file_size_bytes']:,} | {dataset['row_count']:,} | "
            f"{dataset['column_count']:,} | {dataset['exact_duplicate_row_count']:,} |"
        )

    lines.extend(
        [
            "",
            "## Recreation sites",
            "",
            "### Selected subtype counts",
            "",
            "| Raw `site_subtype` | Rows |",
            "|---|---:|",
        ]
    )
    for category in SITE_CATEGORIES:
        lines.append(
            f"| `{category}` | {site_analysis['selected_subtype_counts'][category]:,} |"
        )
    lines.append(
        f"| **Combined exact-match count** | **{site_analysis['selected_subtype_combined_count']:,}** |"
    )
    lines.extend(
        [
            "",
            "These counts describe literal source categories; they do not establish a campground eligibility rule.",
            "",
            "### Identifier uniqueness",
            "",
            "| Column | Non-missing | Distinct | Duplicate excess rows | Complete | Unique |",
            "|---|---:|---:|---:|---|---|",
        ]
    )
    for column in SITE_KEY_COLUMNS:
        record = site_analysis["selected_key_uniqueness"][column]
        lines.append(
            f"| `{column}` | {record['non_missing_key_rows']:,} | "
            f"{record['distinct_non_missing_count']:,} | {record['duplicate_non_missing_rows']:,} | "
            f"{_yes_no(record['is_complete'])} | {_yes_no(record['is_unique_among_non_missing'])} |"
        )
    lines.extend(
        [
            "",
            "### Selected missingness",
            "",
            "| Column | Missing | Missing % |",
            "|---|---:|---:|",
        ]
    )
    for column in SITE_MISSINGNESS_COLUMNS:
        record = site_analysis["selected_column_missingness"][column]
        lines.append(
            f"| `{column}` | {record['missing_count']:,} | {record['missing_percentage']:.6f}% |"
        )
    lines.extend(
        [
            "",
            f"`site_id` has {site_analysis['duplicated_site_id_distinct_value_count']:,} distinct duplicated values and {site_analysis['duplicated_site_id_excess_row_count']:,} excess rows. Examples and common raw water/restroom values are in `value_examples.json`; no amenity mapping is applied.",
            "",
            "## Recreation Area activities",
            "",
            f"- Unique non-missing `RECAREAID`: {activity_analysis['unique_RECAREAID_count']:,}",
            f"- Unique non-missing `ACTIVITYID`: {activity_analysis['unique_ACTIVITYID_count']:,}",
            f"- Rows missing either identifier: {activity_analysis['rows_missing_either_identifier']:,}",
            f"- Duplicate non-missing `(RECAREAID, ACTIVITYID)` pairs beyond the first: {activity_analysis['duplicate_RECAREAID_ACTIVITYID_pair_count']:,}",
            f"- Activity names mapping to multiple IDs: {activity_analysis['activity_name_to_multiple_ids_count']:,}",
            f"- Activity IDs mapping to multiple names: {activity_analysis['activity_id_to_multiple_names_count']:,}",
            "",
            "### Repeated Recreation Area attribute conflicts",
            "",
            "| Attribute | Recreation Areas with multiple non-missing values |",
            "|---|---:|",
        ]
    )
    for attribute in ACTIVITY_AREA_ATTRIBUTES:
        count = activity_analysis["recreation_area_attribute_conflicts"][attribute][
            "conflicting_recarea_count"
        ]
        lines.append(f"| `{attribute}` | {count:,} |")

    lines.extend(
        [
            "",
            "## National parks",
            "",
            "- Empty columns: "
            + (", ".join(f"`{name}`" for name in park_analysis["empty_columns"]) or "none"),
            f"- Names containing `*`: {park_analysis['names_with_stars_count']:,}",
            f"- Names containing citation brackets: {park_analysis['names_with_citations_count']:,}",
            f"- Names containing unusual whitespace: {park_analysis['names_with_unusual_whitespace_count']:,}",
            "- Literal examples for `Location`, `Area (2021)[13]`, `Date established as park[7][12]`, and `Recreation visitors (2021)[11]` are in `value_examples.json`.",
            "",
            "## Interpretation limits",
            "",
            "- Profiling records source facts only; it does not clean, normalize, build the SQLite database, query application data, or implement Streamlit.",
            "- Uniqueness proves only uniqueness in this local snapshot, not stability across future source releases.",
            "- Missing amenity text remains unknown; the profiler does not convert it to `NO`.",
            "- Source categories and duplicate examples are review evidence, not automatic merge or eligibility decisions.",
            "",
        ]
    )
    return "\n".join(lines)


def run_profiling(raw_dir: Path = RAW_DIR, report_dir: Path = REPORT_DIR) -> Dict[str, object]:
    """Profile all expected raw datasets and write the required reports."""

    try:
        csv.field_size_limit(min(sys.maxsize, 2_147_483_647))
    except OverflowError:
        csv.field_size_limit(2_147_483_647)

    paths = {filename: raw_dir / filename for filename in EXPECTED_FILES}
    for path in paths.values():
        if not path.is_file():
            raise ProfilingError(f"Required raw CSV file is missing: {path.as_posix()}")

    profiles = {
        "Recreation_Sites_INFRA.csv": profile_dataset(paths["Recreation_Sites_INFRA.csv"]),
        "Recreation_Area_Activities.csv": profile_dataset(
            paths["Recreation_Area_Activities.csv"],
            extra_keys=(("RECAREAID", "ACTIVITYID"),),
        ),
        "national_parks_raw.csv": profile_dataset(paths["national_parks_raw.csv"]),
    }

    site_analysis, site_examples = analyze_sites(paths["Recreation_Sites_INFRA.csv"], profiles["Recreation_Sites_INFRA.csv"])
    activity_analysis, activity_examples = analyze_activities(paths["Recreation_Area_Activities.csv"])
    park_analysis, park_examples = analyze_parks(paths["national_parks_raw.csv"], profiles["national_parks_raw.csv"])

    profiles["Recreation_Sites_INFRA.csv"].summary["special_analysis"] = site_analysis
    profiles["Recreation_Area_Activities.csv"].summary["special_analysis"] = activity_analysis
    profiles["national_parks_raw.csv"].summary["special_analysis"] = park_analysis

    summary: Dict[str, object] = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "profiling_rules": {
            "missing_value": "empty or whitespace-only CSV field",
            "distinct_count": "distinct non-missing literal values",
            "exact_duplicate_row_count": "repeated rows beyond the first occurrence",
            "identifier_handling": "all CSV fields are read as strings; identifier-like columns infer as string",
            "normalization_performed": False,
        },
        "datasets": {filename: profiles[filename].summary for filename in EXPECTED_FILES},
    }
    value_examples: Dict[str, object] = {
        "Recreation_Sites_INFRA.csv": {
            "column_samples": profiles["Recreation_Sites_INFRA.csv"].column_samples,
            "special_examples": site_examples,
        },
        "Recreation_Area_Activities.csv": {
            "column_samples": profiles["Recreation_Area_Activities.csv"].column_samples,
            "special_examples": activity_examples,
        },
        "national_parks_raw.csv": {
            "column_samples": profiles["national_parks_raw.csv"].column_samples,
            "special_examples": park_examples,
        },
    }

    column_rows = [
        row for filename in EXPECTED_FILES for row in profiles[filename].column_profiles
    ]
    key_rows = [row for filename in EXPECTED_FILES for row in profiles[filename].key_analysis]

    report_dir.mkdir(parents=True, exist_ok=True)
    _write_json(report_dir / "profile_summary.json", summary)
    _write_csv(
        report_dir / "column_profiles.csv",
        column_rows,
        (
            "dataset",
            "column_position",
            "column_name",
            "inferred_data_type",
            "row_count",
            "non_missing_count",
            "missing_count",
            "missing_percentage",
            "distinct_count",
            "sample_non_null_values",
            "maximum_text_length",
        ),
    )
    _write_csv(
        report_dir / "key_analysis.csv",
        key_rows,
        (
            "dataset",
            "candidate",
            "column_count",
            "row_count",
            "non_missing_key_rows",
            "missing_key_rows",
            "distinct_non_missing_count",
            "duplicate_non_missing_rows",
            "is_unique_among_non_missing",
            "is_complete",
            "is_candidate_key",
        ),
    )
    _write_json(report_dir / "value_examples.json", value_examples)
    with (report_dir / "data_quality_findings.md").open(
        "w", encoding="utf-8", newline="\n"
    ) as handle:
        handle.write(render_findings(summary, value_examples))
    return summary


def main() -> int:
    try:
        summary = run_profiling()
    except ProfilingError as exc:
        print(f"Raw-data profiling failed: {exc}", file=sys.stderr)
        return 1

    print("Raw-data profiling completed.")
    for filename in EXPECTED_FILES:
        dataset = summary["datasets"][filename]
        print(
            f"- {filename}: {dataset['row_count']} rows, {dataset['column_count']} columns, "
            f"{dataset['file_size_bytes']} bytes"
        )
    print(f"Reports written to {REPORT_DIR.as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
