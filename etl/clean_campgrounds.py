"""Clean the Forest Service recreation-site source into campground records.

This phase reads identifiers as text, retains only explicitly supported
campground subtypes, and validates Recreation Area links against the processed
activity-phase output. It never modifies raw input data or merges duplicates.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
import sys
from collections import Counter, defaultdict
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple
from urllib.parse import parse_qs, urlsplit


SOURCE_PATH = Path("data/raw/Recreation_Sites_INFRA.csv")
RECREATION_AREAS_PATH = Path("data/processed/recreation_areas.csv")
PROCESSED_DIR = Path("data/processed")
REPORT_DIR = Path("reports/generated")

ALLOWED_SUBTYPES = frozenset({"CAMPGROUND", "GROUP CAMPGROUND", "HORSE CAMP"})
ALLOWED_WATER_CATEGORIES = (
    "AVAILABLE",
    "NOT_AVAILABLE",
    "NATURAL_SOURCE",
    "NEARBY",
    "OTHER",
    "UNKNOWN",
)
ALLOWED_RESTROOM_CATEGORIES = (
    "FLUSH",
    "VAULT",
    "COMPOSTING",
    "PORTABLE",
    "MULTIPLE",
    "NONE",
    "OTHER",
    "UNKNOWN",
)
ALLOWED_FEE_CATEGORIES = frozenset({"YES", "NO", "UNKNOWN"})
SELECTED_IDENTIFIER_COLUMN = "globalid"
DUPLICATE_DISTANCE_THRESHOLD_KM = 1.0

REQUIRED_SOURCE_COLUMNS = (
    "objectid",
    "site_cn",
    "root_cn",
    "parent_cn",
    "site_id",
    "site_name",
    "site_subtype",
    "total_capacity",
    "fee_charged",
    "fee_type",
    "recarea_name",
    "fee_description",
    "operational_hours",
    "public_site_name",
    "site_directions",
    "rec1stop_url",
    "usda_portal_url",
    "closest_towns",
    "water_availability",
    "restroom_availability",
    "directions",
    "latitude",
    "longitude",
    "last_update",
    "globalid",
)

CAMPGROUND_COLUMNS = (
    "campground_id",
    "globalid",
    "site_cn",
    "site_id",
    "objectid",
    "root_cn",
    "parent_cn",
    "name",
    "public_site_name",
    "site_name",
    "recarea_name",
    "site_subtype",
    "site_subtype_raw",
    "recarea_id",
    "recid_extracted",
    "fee_charged",
    "fee_charged_raw",
    "fee_type",
    "fee_description",
    "total_capacity",
    "total_capacity_raw",
    "water_availability",
    "water_availability_raw",
    "restroom_availability",
    "restroom_availability_raw",
    "directions",
    "site_directions",
    "closest_towns",
    "operational_hours",
    "official_url",
    "usda_portal_url",
    "rec1stop_url",
    "latitude",
    "longitude",
    "last_update",
)

UNMATCHED_COLUMNS = (
    "campground_id",
    "site_cn",
    "site_id",
    "name",
    "site_subtype",
    "usda_portal_url",
    "recid_extracted",
    "unmatched_reason",
)

DUPLICATE_COLUMNS = (
    "campground_id_1",
    "campground_id_2",
    "name_1",
    "name_2",
    "normalized_name",
    "latitude_1",
    "longitude_1",
    "latitude_2",
    "longitude_2",
    "distance_km",
    "candidate_rule",
)

DROPPED_COLUMNS = (
    "source_row_number",
    "drop_category",
    "drop_reason",
    "globalid",
    "site_cn",
    "site_id",
    "public_site_name",
    "site_name",
    "recarea_name",
    "site_subtype",
    "latitude",
    "longitude",
)

_SPACE_RE = re.compile(r"\s+")
_NON_NAME_RE = re.compile(r"[^A-Z0-9]+")
_SAFE_NUMBER_RE = re.compile(r"^(?:0|[1-9]\d*)(?:\.\d+)?$")
_ACCIDENTAL_FLOAT_ID_RE = re.compile(r"^\d+\.0$")


class CampgroundCleaningError(RuntimeError):
    """An actionable failure raised by the campground-cleaning phase."""


def _set_csv_field_size_limit() -> None:
    try:
        csv.field_size_limit(min(sys.maxsize, 2_147_483_647))
    except OverflowError:
        csv.field_size_limit(2_147_483_647)


def clean_text(value: Optional[str]) -> str:
    """Trim and collapse source whitespace without inferring content."""

    return _SPACE_RE.sub(" ", value or "").strip()


def preserve_identifier(value: Optional[str]) -> str:
    """Preserve identifier characters and leading zeroes; trim edges only."""

    return (value or "").strip()


def normalize_site_subtype(value: Optional[str]) -> str:
    """Normalize case and whitespace for exact campground eligibility."""

    return clean_text(value).upper()


def choose_display_name(
    public_site_name: Optional[str],
    site_name: Optional[str],
    recarea_name: Optional[str],
) -> str:
    """Select the first non-blank name in the required source priority."""

    for value in (public_site_name, site_name, recarea_name):
        cleaned = clean_text(value)
        if cleaned:
            return cleaned
    return ""


def _phrase_text(value: Optional[str]) -> str:
    return clean_text(value).casefold()


def normalize_water(value: Optional[str]) -> str:
    """Map source water text conservatively to the approved categories."""

    text = _phrase_text(value)
    if not text or text in {"unknown", "n/a", "na", "not specified"}:
        return "UNKNOWN"

    # Specific alternatives are checked before generic negative and positive
    # wording so, for example, nearby or treatable water is not lost as NO.
    nearby = any(
        token in text
        for token in ("nearby", "adjacent", "about 1 mile away", "work center")
    )
    natural = any(
        token in text
        for token in (
            "treat",
            "filter",
            "untreated",
            "creek",
            "river",
            "spring",
            "stream",
            "lake",
            "natural source",
        )
    )
    negative = (
        text in {"no", "none", "not available", "not provided", "not potable"}
        or bool(
            re.search(
                r"\b(no|not)\b.{0,45}\b(water|drinking|potable|provided|available)\b",
                text,
            )
        )
        or "water is not available" in text
        or "water not available" in text
        or "unavailable" in text
        or "currently offline" in text
        or "water system is closed" in text
        or "none provided" in text
        or "none available" in text
        or "handpump has been discontinued" in text
    )
    if nearby:
        return "NEARBY"
    if natural:
        return "NATURAL_SOURCE"
    if negative:
        return "NOT_AVAILABLE"

    positive = (
        text.rstrip(".") == "yes"
        or any(
            token in text
            for token in (
                "drinking water",
                "potable water",
                "water available",
                "water is available",
                "available during",
                "hand pump",
                "handpump",
                "handpumps",
                "faucet",
                "hydrant",
                "pressurized water",
                "gravity water",
                "solar well",
                "well water",
                "water spigot",
                " pumps",
                "onsite",
            )
        )
        or text in {"available", "potable", "drinking", "water", "yes, seasonally"}
        or text.startswith("available early")
    )
    if positive:
        return "AVAILABLE"
    if any(
        token in text
        for token in ("non-potable", "non potable", "boil", "livestock", "stock", "trough")
    ) or text == "portable water":
        return "OTHER"
    return "UNKNOWN"


def normalize_restroom(value: Optional[str]) -> str:
    """Map source restroom text conservatively to approved categories."""

    text = _phrase_text(value)
    if (
        not text
        or text in {"unknown", "n/a", "na", "not specified"}
        or text.startswith("unknown toilet")
    ):
        return "UNKNOWN"

    negative = (
        text in {"no", "none", "not available", "no restroom", "no restrooms"}
        or bool(re.search(r"\bno\b.{0,35}\b(restroom|toilet|facilit)", text))
        or bool(re.search(r"\b(restroom|toilet)s?\b.{0,20}\bnot available\b", text))
    )
    if negative:
        return "NONE"

    detected = []
    if "flush" in text or "flushing" in text:
        detected.append("FLUSH")
    if any(token in text for token in ("vault", "pit toilet", "pit", "outhouse")):
        detected.append("VAULT")
    if "compost" in text:
        detected.append("COMPOSTING")
    if "portable" in text or "porta-pot" in text or "porta pot" in text:
        detected.append("PORTABLE")
    detected = list(dict.fromkeys(detected))
    if len(detected) > 1:
        return "MULTIPLE"
    if detected:
        return detected[0]
    if (
        text.rstrip(".") == "yes"
        or any(token in text for token in ("restroom", "toilet", "facilit", "shower"))
        or (
            "available" in text
            and "reservation" not in text
            and "camp site" not in text
            and "campsite" not in text
        )
    ):
        return "OTHER"
    return "UNKNOWN"


def convert_fee(value: Optional[str]) -> str:
    """Convert only explicit source Y/N values; everything else is unknown."""

    normalized = clean_text(value).upper()
    if normalized == "Y":
        return "YES"
    if normalized == "N":
        return "NO"
    return "UNKNOWN"


def parse_total_capacity(value: Optional[str]) -> str:
    """Return a plain non-negative decimal only when the source is unambiguous."""

    text = clean_text(value)
    if not text or not _SAFE_NUMBER_RE.fullmatch(text):
        return ""
    try:
        number = Decimal(text)
    except InvalidOperation:
        return ""
    if not number.is_finite() or number < 0:
        return ""
    normalized = format(number.normalize(), "f")
    return normalized.rstrip("0").rstrip(".") if "." in normalized else normalized


def parse_coordinate(value: Optional[str], minimum: float, maximum: float) -> Optional[float]:
    """Parse a finite coordinate and enforce its geographic range."""

    text = clean_text(value)
    if not text:
        return None
    try:
        coordinate = float(text)
    except ValueError:
        return None
    if not math.isfinite(coordinate) or not minimum <= coordinate <= maximum:
        return None
    return coordinate


def validate_coordinates(latitude: Optional[str], longitude: Optional[str]) -> Tuple[float, float]:
    """Return valid coordinate values or raise a clear validation error."""

    parsed_latitude = parse_coordinate(latitude, -90.0, 90.0)
    parsed_longitude = parse_coordinate(longitude, -180.0, 180.0)
    if parsed_latitude is None or parsed_longitude is None:
        raise CampgroundCleaningError(
            f"Invalid coordinates: latitude={latitude!r}, longitude={longitude!r}"
        )
    return parsed_latitude, parsed_longitude


def extract_recid(usda_portal_url: Optional[str]) -> str:
    """Extract a non-blank ``recid`` query parameter from the USDA URL only."""

    url = clean_text(usda_portal_url)
    if not url:
        return ""
    try:
        query = urlsplit(url if "://" in url else "//" + url).query
        values = parse_qs(query, keep_blank_values=True)
    except ValueError:
        return ""
    for key, candidates in values.items():
        if key.casefold() == "recid" and candidates:
            return preserve_identifier(candidates[0])
    return ""


def normalize_campground_name(value: Optional[str]) -> str:
    """Normalize a name for candidate generation without changing output names."""

    return _SPACE_RE.sub(" ", _NON_NAME_RE.sub(" ", clean_text(value).upper())).strip()


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate approximate great-circle distance using a 6,371.0088 km Earth."""

    radius = 6371.0088
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    a = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    )
    return radius * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def find_duplicate_candidates(
    campgrounds: Iterable[Mapping[str, str]],
    threshold_km: float = DUPLICATE_DISTANCE_THRESHOLD_KM,
) -> List[Dict[str, str]]:
    """Report exact normalized-name pairs within the distance threshold."""

    groups: Dict[str, List[Mapping[str, str]]] = defaultdict(list)
    for row in campgrounds:
        normalized_name = normalize_campground_name(row.get("name"))
        if normalized_name:
            groups[normalized_name].append(row)

    candidates: List[Dict[str, str]] = []
    for normalized_name in sorted(groups):
        rows = sorted(groups[normalized_name], key=lambda row: row["campground_id"])
        for index, first in enumerate(rows):
            for second in rows[index + 1 :]:
                distance = haversine_km(
                    float(first["latitude"]),
                    float(first["longitude"]),
                    float(second["latitude"]),
                    float(second["longitude"]),
                )
                if distance <= threshold_km:
                    candidates.append(
                        {
                            "campground_id_1": first["campground_id"],
                            "campground_id_2": second["campground_id"],
                            "name_1": first["name"],
                            "name_2": second["name"],
                            "normalized_name": normalized_name,
                            "latitude_1": first["latitude"],
                            "longitude_1": first["longitude"],
                            "latitude_2": second["latitude"],
                            "longitude_2": second["longitude"],
                            "distance_km": f"{distance:.6f}",
                            "candidate_rule": (
                                "EXACT_NORMALIZED_NAME_AND_DISTANCE_LE_1_KM"
                            ),
                        }
                    )
    return candidates


def _missing_stat(rows: Sequence[Mapping[str, str]], source_column: str) -> Dict[str, float]:
    count = sum(not clean_text(row.get(source_column)) for row in rows)
    total = len(rows)
    return {
        "missing_count": count,
        "missing_percentage": round(100.0 * count / total, 6) if total else 0.0,
    }


def build_subset_statistics(
    source_rows: Sequence[Mapping[str, str]],
    campgrounds: Sequence[Mapping[str, str]],
    dropped_rows: Sequence[Mapping[str, str]],
    unmatched_rows: Sequence[Mapping[str, str]],
    duplicate_candidates: Sequence[Mapping[str, str]],
) -> Dict[str, object]:
    """Build statistics using only final retained campgrounds as denominator."""

    total = len(campgrounds)
    subtype_counts = Counter(row["site_subtype"] for row in campgrounds)
    water_counts = Counter(row["water_availability"] for row in campgrounds)
    restroom_counts = Counter(row["restroom_availability"] for row in campgrounds)
    validated = sum(bool(row["recarea_id"]) for row in campgrounds)
    unmatched = total - validated
    drop_reasons = Counter(row["drop_reason"] for row in dropped_rows)
    drop_categories = Counter(row["drop_category"] for row in dropped_rows)
    missingness = {
        column: _missing_stat(source_rows, column)
        for column in (
            "water_availability",
            "restroom_availability",
            "directions",
            "usda_portal_url",
            "fee_charged",
            "total_capacity",
        )
    }
    percentage = lambda count: round(100.0 * count / total, 6) if total else 0.0
    return {
        "final_campground_row_count": total,
        "retained_subtype_counts": {
            category: subtype_counts.get(category, 0) for category in sorted(ALLOWED_SUBTYPES)
        },
        "selected_identifier_column": SELECTED_IDENTIFIER_COLUMN,
        "unique_identifier_count": len({row["campground_id"] for row in campgrounds}),
        "campground_subset_missingness": missingness,
        "validated_recarea_link_count": validated,
        "validated_recarea_link_percentage": percentage(validated),
        "unmatched_recarea_link_count": unmatched,
        "unmatched_recarea_link_percentage": percentage(unmatched),
        "water_category_counts": {
            category: water_counts.get(category, 0) for category in ALLOWED_WATER_CATEGORIES
        },
        "restroom_category_counts": {
            category: restroom_counts.get(category, 0)
            for category in ALLOWED_RESTROOM_CATEGORIES
        },
        "dropped_row_count": len(dropped_rows),
        "dropped_row_counts_by_category": {
            "UNSUPPORTED_SITE_SUBTYPE": drop_categories.get(
                "UNSUPPORTED_SITE_SUBTYPE", 0
            ),
            "INVALID_REQUIRED_DATA": drop_categories.get("INVALID_REQUIRED_DATA", 0),
        },
        "dropped_row_counts_by_reason": dict(sorted(drop_reasons.items())),
        "unmatched_campground_count": len(unmatched_rows),
        "duplicate_candidate_pair_count": len(duplicate_candidates),
    }


def _load_recreation_area_ids(path: Path) -> set[str]:
    if not path.is_file():
        raise CampgroundCleaningError(
            f"Required processed Recreation Area CSV is missing: {path.as_posix()}"
        )
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if not reader.fieldnames or "RECAREAID" not in reader.fieldnames:
                raise CampgroundCleaningError(
                    f"Processed Recreation Area CSV lacks RECAREAID: {path.as_posix()}"
                )
            return {
                preserve_identifier(row.get("RECAREAID"))
                for row in reader
                if preserve_identifier(row.get("RECAREAID"))
            }
    except (UnicodeDecodeError, csv.Error) as exc:
        raise CampgroundCleaningError(
            f"Cannot read processed Recreation Area CSV {path.as_posix()}: {exc}"
        ) from exc


def _dropped_row(
    row_number: int,
    raw: Mapping[str, str],
    category: str,
    reason: str,
) -> Dict[str, str]:
    return {
        "source_row_number": str(row_number),
        "drop_category": category,
        "drop_reason": reason,
        **{column: raw.get(column, "") for column in DROPPED_COLUMNS[3:]},
    }


def _validate_output(
    campgrounds: Sequence[Mapping[str, str]],
    recreation_area_ids: set[str],
    expected_count: int,
) -> None:
    identifiers = [row["campground_id"] for row in campgrounds]
    if any(not identifier for identifier in identifiers):
        raise CampgroundCleaningError("Validation failed: campground identifier is null")
    if len(set(identifiers)) != len(identifiers):
        duplicates = [key for key, count in Counter(identifiers).items() if count > 1]
        raise CampgroundCleaningError(
            f"Validation failed: campground identifier is not unique: {duplicates[:5]}"
        )
    for column in (
        "campground_id",
        "globalid",
        "site_cn",
        "site_id",
        "objectid",
        "root_cn",
        "parent_cn",
        "recid_extracted",
        "recarea_id",
    ):
        if any(
            _ACCIDENTAL_FLOAT_ID_RE.fullmatch(row[column])
            for row in campgrounds
            if row[column]
        ):
            raise CampgroundCleaningError(
                f"Validation failed: identifier column {column} contains an accidental .0 suffix"
            )
    invalid_subtypes = {row["site_subtype"] for row in campgrounds} - ALLOWED_SUBTYPES
    if invalid_subtypes:
        raise CampgroundCleaningError(
            f"Validation failed: unsupported campground subtypes: {sorted(invalid_subtypes)}"
        )
    invalid_water = {
        row["water_availability"] for row in campgrounds
    } - set(ALLOWED_WATER_CATEGORIES)
    if invalid_water:
        raise CampgroundCleaningError(
            f"Validation failed: unsupported water categories: {sorted(invalid_water)}"
        )
    invalid_restroom = {
        row["restroom_availability"] for row in campgrounds
    } - set(ALLOWED_RESTROOM_CATEGORIES)
    if invalid_restroom:
        raise CampgroundCleaningError(
            f"Validation failed: unsupported restroom categories: {sorted(invalid_restroom)}"
        )
    if any(row["fee_charged"] not in ALLOWED_FEE_CATEGORIES for row in campgrounds):
        raise CampgroundCleaningError("Validation failed: unsupported fee category")
    for row in campgrounds:
        validate_coordinates(row["latitude"], row["longitude"])
    orphan_ids = sorted(
        {row["recarea_id"] for row in campgrounds if row["recarea_id"]}
        - recreation_area_ids
    )
    if orphan_ids:
        raise CampgroundCleaningError(
            f"Validation failed: Recreation Area links are invalid: {orphan_ids[:5]}"
        )
    if len(campgrounds) != expected_count:
        raise CampgroundCleaningError(
            "Validation failed: output row count does not match retained campground count"
        )


def _write_csv(
    path: Path, rows: Iterable[Mapping[str, object]], fieldnames: Sequence[str]
) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="raise")
        writer.writeheader()
        writer.writerows(rows)


def _write_json(path: Path, value: Mapping[str, object]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def run_cleaning(
    source_path: Path = SOURCE_PATH,
    recreation_areas_path: Path = RECREATION_AREAS_PATH,
    processed_dir: Path = PROCESSED_DIR,
    report_dir: Path = REPORT_DIR,
) -> Dict[str, object]:
    """Clean campground rows, validate them, then publish data and reports."""

    _set_csv_field_size_limit()
    if not source_path.is_file():
        raise CampgroundCleaningError(f"Required raw CSV is missing: {source_path.as_posix()}")
    recreation_area_ids = _load_recreation_area_ids(recreation_areas_path)

    source_row_count = 0
    retained_source_rows: List[Dict[str, str]] = []
    campgrounds: List[Dict[str, str]] = []
    unmatched_rows: List[Dict[str, str]] = []
    dropped_rows: List[Dict[str, str]] = []

    try:
        with source_path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames is None:
                raise CampgroundCleaningError(f"Raw CSV has no header: {source_path.as_posix()}")
            missing_columns = [
                column for column in REQUIRED_SOURCE_COLUMNS if column not in reader.fieldnames
            ]
            if missing_columns:
                raise CampgroundCleaningError(
                    "Source schema mismatch; missing columns: " + ", ".join(missing_columns)
                )

            for row_number, raw in enumerate(reader, start=2):
                source_row_count += 1
                if None in raw:
                    raise CampgroundCleaningError(
                        f"Row {row_number} has more fields than the source header"
                    )
                subtype = normalize_site_subtype(raw.get("site_subtype"))
                if subtype not in ALLOWED_SUBTYPES:
                    dropped_rows.append(
                        _dropped_row(
                            row_number,
                            raw,
                            "UNSUPPORTED_SITE_SUBTYPE",
                            "UNSUPPORTED_SITE_SUBTYPE",
                        )
                    )
                    continue

                campground_id = preserve_identifier(raw.get(SELECTED_IDENTIFIER_COLUMN))
                if not campground_id:
                    dropped_rows.append(
                        _dropped_row(
                            row_number,
                            raw,
                            "INVALID_REQUIRED_DATA",
                            "MISSING_GLOBALID",
                        )
                    )
                    continue
                latitude = parse_coordinate(raw.get("latitude"), -90.0, 90.0)
                longitude = parse_coordinate(raw.get("longitude"), -180.0, 180.0)
                if latitude is None or longitude is None:
                    reason = (
                        "INVALID_LATITUDE_AND_LONGITUDE"
                        if latitude is None and longitude is None
                        else "INVALID_LATITUDE"
                        if latitude is None
                        else "INVALID_LONGITUDE"
                    )
                    dropped_rows.append(
                        _dropped_row(row_number, raw, "INVALID_REQUIRED_DATA", reason)
                    )
                    continue

                retained_source_rows.append(dict(raw))
                usda_url = clean_text(raw.get("usda_portal_url"))
                recid = extract_recid(usda_url)
                recarea_id = recid if recid and recid in recreation_area_ids else ""
                name = choose_display_name(
                    raw.get("public_site_name"), raw.get("site_name"), raw.get("recarea_name")
                )
                campground = {
                    "campground_id": campground_id,
                    "globalid": campground_id,
                    "site_cn": preserve_identifier(raw.get("site_cn")),
                    "site_id": preserve_identifier(raw.get("site_id")),
                    "objectid": preserve_identifier(raw.get("objectid")),
                    "root_cn": preserve_identifier(raw.get("root_cn")),
                    "parent_cn": preserve_identifier(raw.get("parent_cn")),
                    "name": name,
                    "public_site_name": clean_text(raw.get("public_site_name")),
                    "site_name": clean_text(raw.get("site_name")),
                    "recarea_name": clean_text(raw.get("recarea_name")),
                    "site_subtype": subtype,
                    "site_subtype_raw": raw.get("site_subtype", ""),
                    "recarea_id": recarea_id,
                    "recid_extracted": recid,
                    "fee_charged": convert_fee(raw.get("fee_charged")),
                    "fee_charged_raw": raw.get("fee_charged", ""),
                    "fee_type": clean_text(raw.get("fee_type")),
                    "fee_description": clean_text(raw.get("fee_description")),
                    "total_capacity": parse_total_capacity(raw.get("total_capacity")),
                    "total_capacity_raw": raw.get("total_capacity", ""),
                    "water_availability": normalize_water(raw.get("water_availability")),
                    "water_availability_raw": raw.get("water_availability", ""),
                    "restroom_availability": normalize_restroom(raw.get("restroom_availability")),
                    "restroom_availability_raw": raw.get("restroom_availability", ""),
                    "directions": clean_text(raw.get("directions")),
                    "site_directions": clean_text(raw.get("site_directions")),
                    "closest_towns": clean_text(raw.get("closest_towns")),
                    "operational_hours": clean_text(raw.get("operational_hours")),
                    "official_url": usda_url,
                    "usda_portal_url": usda_url,
                    "rec1stop_url": clean_text(raw.get("rec1stop_url")),
                    "latitude": clean_text(raw.get("latitude")),
                    "longitude": clean_text(raw.get("longitude")),
                    "last_update": clean_text(raw.get("last_update")),
                }
                campgrounds.append(campground)

                if not recarea_id:
                    if not usda_url:
                        reason = "MISSING_USDA_PORTAL_URL"
                    elif not recid:
                        reason = "RECID_NOT_FOUND_IN_USDA_PORTAL_URL"
                    else:
                        reason = "RECID_NOT_IN_RECREATION_AREAS"
                    unmatched_rows.append(
                        {
                            **{column: campground[column] for column in UNMATCHED_COLUMNS[:-1]},
                            "unmatched_reason": reason,
                        }
                    )
    except UnicodeDecodeError as exc:
        raise CampgroundCleaningError(
            f"Cannot decode {source_path.as_posix()} as UTF-8: {exc}"
        ) from exc
    except csv.Error as exc:
        raise CampgroundCleaningError(
            f"Cannot parse {source_path.as_posix()} as CSV: {exc}"
        ) from exc

    campgrounds.sort(key=lambda row: row["campground_id"])
    unmatched_rows.sort(key=lambda row: row["campground_id"])
    dropped_rows.sort(key=lambda row: int(row["source_row_number"]))
    duplicate_candidates = find_duplicate_candidates(campgrounds)

    _validate_output(campgrounds, recreation_area_ids, len(retained_source_rows))
    summary = {
        "source_file": source_path.as_posix(),
        "recreation_areas_file": recreation_areas_path.as_posix(),
        "source_row_count": source_row_count,
        "eligible_subtype_source_row_count": len(retained_source_rows)
        + sum(row["drop_category"] == "INVALID_REQUIRED_DATA" for row in dropped_rows),
        **build_subset_statistics(
            retained_source_rows,
            campgrounds,
            dropped_rows,
            unmatched_rows,
            duplicate_candidates,
        ),
        "identifier_evidence": {
            "profiled_source_row_count": 32114,
            "globalid_non_missing_count": 32114,
            "globalid_unique_count": 32114,
            "site_cn_non_missing_count": 32114,
            "site_cn_unique_count": 32114,
            "site_id_non_missing_count": 32114,
            "site_id_unique_count": 29972,
        },
        "duplicate_candidate_rule": {
            "name": "exact normalized display name",
            "maximum_distance_km": DUPLICATE_DISTANCE_THRESHOLD_KM,
            "automatic_merge": False,
        },
        "validation": "passed",
        "later_phases": {
            "national_parks": "implemented in a downstream phase",
            "park_campground_distances": "implemented in a downstream phase",
            "mysql_loading": "not implemented",
            "streamlit": "not implemented",
        },
    }

    processed_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)
    _write_csv(processed_dir / "campgrounds.csv", campgrounds, CAMPGROUND_COLUMNS)
    _write_csv(report_dir / "unmatched_campgrounds.csv", unmatched_rows, UNMATCHED_COLUMNS)
    _write_csv(
        report_dir / "duplicate_candidates.csv", duplicate_candidates, DUPLICATE_COLUMNS
    )
    _write_csv(report_dir / "dropped_campground_rows.csv", dropped_rows, DROPPED_COLUMNS)
    _write_json(report_dir / "campground_cleaning_summary.json", summary)
    return summary


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Clean and validate campground records.")
    parser.add_argument("--source", type=Path, default=SOURCE_PATH)
    parser.add_argument("--recreation-areas", type=Path, default=RECREATION_AREAS_PATH)
    parser.add_argument("--processed-dir", type=Path, default=PROCESSED_DIR)
    parser.add_argument("--report-dir", type=Path, default=REPORT_DIR)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        summary = run_cleaning(
            args.source, args.recreation_areas, args.processed_dir, args.report_dir
        )
    except CampgroundCleaningError as exc:
        print(f"Campground cleaning failed: {exc}", file=sys.stderr)
        return 1

    print("Campground cleaning completed.")
    print(f"- Campgrounds: {summary['final_campground_row_count']}")
    print(f"- Validated Recreation Area links: {summary['validated_recarea_link_count']}")
    print(f"- Unmatched campgrounds retained: {summary['unmatched_campground_count']}")
    print(f"- Duplicate candidate pairs: {summary['duplicate_candidate_pair_count']}")
    print(f"- Dropped source rows: {summary['dropped_row_count']}")
    print("National-park cleaning and distance calculation are available downstream.")
    print("MySQL loading and Streamlit are not implemented.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
