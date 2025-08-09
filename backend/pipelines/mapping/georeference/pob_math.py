"""
POB Math Utilities
Pure helpers for POB computation: tie parsing, display<->survey conversion, normalization.
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

from pipelines.polygon.draw_polygon import BearingParser
from pipelines.mapping.common.units import FEET_TO_METERS


def flip_display_to_survey(
    display_coords: List[Dict[str, float] | Tuple[float, float]]
) -> List[Tuple[float, float]]:
    """Convert display coordinates back to survey frame (x east, y north).

    Display Y is inverted for UI drawing; invert back for survey math.
    Accepts list of dicts {x,y} or tuples (x,y).
    """
    survey: List[Tuple[float, float]] = []
    for pt in display_coords:
        if isinstance(pt, dict):
            x = float(pt.get("x", 0.0))
            y = float(pt.get("y", 0.0))
        else:
            x = float(pt[0])
            y = float(pt[1])
        survey.append((x, -y))
    return survey


def normalize_local(coords_feet: List[Tuple[float, float]]) -> List[Tuple[float, float]]:
    """Translate coordinates so that the first vertex is the origin (0,0)."""
    if not coords_feet:
        return []
    origin_x, origin_y = coords_feet[0]
    return [(x - origin_x, y - origin_y) for (x, y) in coords_feet]


def parse_tie_feet(tie: Dict[str, Any]) -> Tuple[float, float]:
    """Parse tie (bearing + distance) into survey offsets in feet (dx, dy).

    Returns (dx_feet, dy_feet) with +x east, +y north.
    """
    if not tie:
        return (0.0, 0.0)

    bearing_raw = (tie.get("bearing_raw") or tie.get("bearing") or "").strip()
    distance_value = float(tie.get("distance_value") or tie.get("distance_feet") or 0.0)
    units = (tie.get("distance_units") or "feet").lower()

    if units in ("meter", "meters", "m"):
        distance_feet = distance_value / FEET_TO_METERS
    elif units in ("chain", "chains"):
        distance_feet = distance_value * 66.0
    elif units in ("rod", "rods"):
        distance_feet = distance_value * 16.5
    else:
        distance_feet = distance_value

    parser = BearingParser()
    parsed = parser.parse_bearing(bearing_raw)
    if not parsed.get("success"):
        return (0.0, 0.0)

    import math
    theta = math.radians(float(parsed["bearing_degrees"]))  # clockwise from north
    dx_feet = distance_feet * math.sin(theta)
    dy_feet = distance_feet * math.cos(theta)
    return dx_feet, dy_feet


def needs_reciprocal_bearing(raw_text: str | None) -> bool:
    """Heuristic: detect deed phrasing 'whence the [corner] bears ... distant'.

    In that grammar, the bearing is from the POB to the corner. To apply a tie
    from the corner to the POB, we must add 180° (reciprocal).
    """
    if not raw_text:
        return False
    import re
    text = raw_text.lower()
    return bool(re.search(r"\bwhence\b.*\bbears\b.*\bdistant\b", text))


def parse_tie_with_azimuth(tie: Dict[str, Any]) -> Tuple[float, float, float, bool]:
    """Parse tie and return (dx_ft, dy_ft, azimuth_deg_used, reciprocal_applied).

    Applies 180° reciprocal if deed raw_text matches the 'whence ... bears ... distant' pattern.
    """
    if not tie:
        return (0.0, 0.0, 0.0, False)

    bearing_raw = (tie.get("bearing_raw") or tie.get("bearing") or "").strip()
    distance_value = float(tie.get("distance_value") or tie.get("distance_feet") or 0.0)
    units = (tie.get("distance_units") or "feet").lower()

    if units in ("meter", "meters", "m"):
        distance_feet = distance_value / FEET_TO_METERS
    elif units in ("chain", "chains"):
        distance_feet = distance_value * 66.0
    elif units in ("rod", "rods"):
        distance_feet = distance_value * 16.5
    else:
        distance_feet = distance_value

    parser = BearingParser()
    parsed = parser.parse_bearing(bearing_raw)
    if not parsed.get("success"):
        return (0.0, 0.0, 0.0, False)

    azimuth_deg = float(parsed["bearing_degrees"])  # clockwise from north

    # Explicit tie direction override if provided
    apply_recip = False
    dir_hint = (tie.get("tie_direction") or "").strip().lower()
    if dir_hint == "corner_bears_from_pob":
        apply_recip = True
    elif dir_hint == "pob_bears_from_corner":
        apply_recip = False
    else:
        # Fallback heuristic from raw_text
        apply_recip = needs_reciprocal_bearing(tie.get("raw_text"))

    if apply_recip:
        azimuth_deg = (azimuth_deg + 180.0) % 360.0

    import math
    theta = math.radians(azimuth_deg)
    dx_feet = distance_feet * math.sin(theta)
    dy_feet = distance_feet * math.cos(theta)
    return dx_feet, dy_feet, azimuth_deg, apply_recip


def parse_corner_plss(corner_label: str) -> Dict[str, Any] | None:
    """Extract TRS from natural-language corner labels.

    Supports verbose forms like:
      '... Section Two (2), Township Fourteen (14) North, Range Seventy-four (74) West ...'
    and compact tokens like 'Sec 2 T14N R74W'.
    Returns dict with: section_number, township_number, township_direction, range_number, range_direction.
    """
    if not corner_label:
        return None
    import re
    text = corner_label.strip()

    # Prefer numeric values inside parentheses when present
    sec_m = re.search(r"Section\s+[^\(]*\((\d{1,2})\)", text, flags=re.IGNORECASE)
    twp_m = re.search(r"Township\s+[^\(]*\((\d{1,2})\)\s*(North|South)", text, flags=re.IGNORECASE)
    rng_m = re.search(r"Range\s+[^\(]*\((\d{1,3})\)\s*(West|East)", text, flags=re.IGNORECASE)
    if sec_m and twp_m and rng_m:
        return {
            "section_number": int(sec_m.group(1)),
            "township_number": int(twp_m.group(1)),
            "township_direction": twp_m.group(2)[0].upper(),
            "range_number": int(rng_m.group(1)),
            "range_direction": rng_m.group(2)[0].upper(),
        }

    # Fallback to compact tokens
    sec_m2 = re.search(r"\bS(?:ec(?:tion)?)?\s*(\d{1,2})\b", text, flags=re.IGNORECASE)
    twp_m2 = re.search(r"\bT\s*(\d{1,2})\s*([NS])\b", text, flags=re.IGNORECASE)
    rng_m2 = re.search(r"\bR\s*(\d{1,3})\s*([EW])\b", text, flags=re.IGNORECASE)
    if sec_m2 and twp_m2 and rng_m2:
        return {
            "section_number": int(sec_m2.group(1)),
            "township_number": int(twp_m2.group(1)),
            "township_direction": twp_m2.group(2).upper(),
            "range_number": int(rng_m2.group(1)),
            "range_direction": rng_m2.group(2).upper(),
        }
    return None


