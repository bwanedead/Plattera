"""Mechanical bearing/distance syntax parsing for mapping operands (no semantic inference)."""

from __future__ import annotations

import re
from typing import Any

_DISTANCE_PATTERN = re.compile(
    r"^\s*(?P<value>[0-9]+(?:\.[0-9]+)?)\s*(?P<unit>feet|foot|ft|meters|meter|m|chains|chain|rods|rod|yards|yard|yd|links|link)?\s*\.?\s*$",
    re.IGNORECASE,
)

_DISTANCE_UNIT_TO_FEET = {
    "feet": 1.0,
    "foot": 1.0,
    "ft": 1.0,
    "meters": 3.28084,
    "meter": 3.28084,
    "m": 3.28084,
    "chains": 66.0,
    "chain": 66.0,
    "rods": 16.5,
    "rod": 16.5,
    "yards": 3.0,
    "yard": 3.0,
    "yd": 3.0,
    "links": 0.66,
    "link": 0.66,
}


def parse_bearing_operand(raw_value: Any) -> dict[str, Any]:
    """Parse a bearing string into numeric degrees (azimuth from north)."""
    bearing_raw = _as_raw_text(raw_value)
    if not bearing_raw:
        return {"bearing_raw": None, "parse_status": "missing"}
    ok, degrees = _parse_quadrant_bearing(bearing_raw)
    if not ok or degrees is None:
        return {
            "bearing_raw": bearing_raw,
            "parse_status": "parse_failed",
            "parse_warnings": ["bearing_parse_failed"],
        }
    return {
        "bearing_raw": bearing_raw,
        "bearing_degrees": round(degrees, 6),
        "parse_status": "parsed",
    }


def parse_distance_operand(raw_value: Any) -> dict[str, Any]:
    """Parse a distance string into numeric feet."""
    distance_raw = _as_raw_text(raw_value)
    if not distance_raw:
        return {"distance_raw": None, "parse_status": "missing"}
    match = _DISTANCE_PATTERN.match(distance_raw)
    if match is None:
        return {
            "distance_raw": distance_raw,
            "parse_status": "parse_failed",
            "parse_warnings": ["distance_parse_failed"],
        }
    try:
        value = float(match.group("value"))
    except (TypeError, ValueError):
        return {
            "distance_raw": distance_raw,
            "parse_status": "parse_failed",
            "parse_warnings": ["distance_parse_failed"],
        }
    unit = (match.group("unit") or "feet").lower()
    feet = value * _DISTANCE_UNIT_TO_FEET.get(unit, 1.0)
    return {
        "distance_raw": distance_raw,
        "distance_feet": round(feet, 6),
        "parse_status": "parsed",
    }


def build_course_compile_fields(
    *,
    bearing_raw: str | None,
    distance_raw: str | None,
    bearing_degrees: float | None = None,
    distance_feet: float | None = None,
) -> dict[str, Any]:
    """Build compiler-ready course helper fields for grouped call rows."""
    warnings: list[str] = []
    bearing = bearing_degrees
    distance = distance_feet
    if bearing is None and bearing_raw:
        parsed = parse_bearing_operand(bearing_raw)
        if parsed.get("parse_status") == "parsed":
            bearing = parsed.get("bearing_degrees")
        else:
            warnings.extend(parsed.get("parse_warnings") or ["bearing_parse_failed"])
    if distance is None and distance_raw:
        parsed = parse_distance_operand(distance_raw)
        if parsed.get("parse_status") == "parsed":
            distance = parsed.get("distance_feet")
        else:
            warnings.extend(parsed.get("parse_warnings") or ["distance_parse_failed"])
    row: dict[str, Any] = {}
    if bearing_raw is not None:
        row["bearing_raw"] = bearing_raw
    if distance_raw is not None:
        row["distance_raw"] = distance_raw
    if bearing is not None:
        row["bearing"] = bearing
    if distance is not None:
        row["distance"] = distance
    compile_ready = bearing is not None and distance is not None
    row["course_compile_ready"] = compile_ready
    if warnings:
        row["parse_warnings"] = _unique_warnings(warnings)
    return row


def _parse_quadrant_bearing(raw: str) -> tuple[bool, float | None]:
    normalized = _normalize_bearing_string(raw)
    match = re.match(
        r"^([NS])\s*([0-9]+(?:\.[0-9]+)?)\s*(?:°)?\s*(?:([0-9]+)(?:['′])?)?\s*(?:([0-9]+)(?:[\"″])?)?\s*([EW])\s*\.?\s*$",
        normalized,
    )
    if match:
        first = match.group(1)
        deg = float(match.group(2))
        minutes = float(match.group(3)) if match.group(3) is not None else 0.0
        seconds = float(match.group(4)) if match.group(4) is not None else 0.0
        second = match.group(5)
        deg_total = deg + minutes / 60.0 + seconds / 3600.0
    else:
        compact = normalized.replace(" ", "")
        match2 = re.match(r"^([NS])([0-9]+(?:\.[0-9]+)?)([EW])\.?$", compact)
        if not match2:
            return False, None
        first = match2.group(1)
        deg_total = float(match2.group(2))
        second = match2.group(3)

    if first == "N":
        azimuth = deg_total if second == "E" else (360.0 - deg_total) % 360.0
    else:
        azimuth = (180.0 - deg_total) % 360.0 if second == "E" else (180.0 + deg_total) % 360.0
    return True, azimuth % 360.0


def _normalize_bearing_string(value: str) -> str:
    text = str(value or "").upper()
    # Drop abbreviation periods (N./E.) but preserve decimal points inside numbers (45.5).
    text = re.sub(r"(?<![0-9])\.(?![0-9])", " ", text)
    text = text.replace(",", " ")
    text = text.replace("DEGREES", "°").replace("DEGREE", "°")
    text = text.replace("º", "°")
    text = text.replace("NORTH", "N").replace("SOUTH", "S").replace("EAST", "E").replace("WEST", "W")
    return re.sub(r"\s+", " ", text).strip()


def _as_raw_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _unique_warnings(values: list[str]) -> list[str]:
    out: list[str] = []
    for item in values:
        if item and item not in out:
            out.append(item)
    return out
