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


def parse_corner_plss(corner_label: str) -> Dict[str, Any] | None:
    """Parse TRS tokens out of a tie corner label like 'NW corner Sec 2 T14N R74W'.

    Returns dict with keys: section_number, township_number, township_direction, range_number, range_direction
    when all tokens are present; otherwise None.
    """
    if not corner_label:
        return None
    import re
    text = corner_label.strip()
    sec_m = re.search(r"\bS(?:ec(?:tion)?)?\s*(\d{1,2})\b", text, flags=re.IGNORECASE)
    twp_m = re.search(r"\bT\s*(\d{1,2})\s*([NS])\b", text, flags=re.IGNORECASE)
    rng_m = re.search(r"\bR\s*(\d{1,3})\s*([EW])\b", text, flags=re.IGNORECASE)
    if not (sec_m and twp_m and rng_m):
        return None
    return {
        "section_number": int(sec_m.group(1)),
        "township_number": int(twp_m.group(1)),
        "township_direction": twp_m.group(2).upper(),
        "range_number": int(rng_m.group(1)),
        "range_direction": rng_m.group(2).upper(),
    }


