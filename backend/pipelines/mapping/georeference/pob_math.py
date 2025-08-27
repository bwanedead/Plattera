"""
POB Math Utilities
Fresh implementation of mathematical utilities for POB calculations.
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple
import math
import logging
import re

logger = logging.getLogger(__name__)


def convert_distance_to_feet(distance_value: float, units: str) -> float:
    """
    Convert distance to feet.
    """
    factors = {
        "feet": 1.0, "foot": 1.0, "ft": 1.0,
        "meters": 3.28084, "meter": 3.28084, "m": 3.28084,
        "chains": 66.0, "chain": 66.0,
        "rods": 16.5, "rod": 16.5,
        "yards": 3.0, "yard": 3.0, "yd": 3.0,
        "links": 0.66, "link": 0.66
    }
    u = (units or "feet").strip().lower()
    return float(distance_value) * factors.get(u, 1.0)


def _normalize_bearing_string(s: str) -> str:
    s = (s or "").upper()
    s = s.replace(".", " ").replace(",", " ")
    s = s.replace("DEGREES", "°").replace("DEGREE", "°")
    s = s.replace("º", "°")
    s = s.replace("NORTH", "N").replace("SOUTH", "S").replace("EAST", "E").replace("WEST", "W")
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _parse_quadrant_bearing(b: str) -> Tuple[bool, float]:
    """
    Parse quadrant bearing like 'N 4° 00' W' or 'S 68 30 E' into azimuth degrees clockwise from north.
    Returns (ok, azimuth_deg)
    """
    b = _normalize_bearing_string(b)
    # N dd mm ss E | N dd° mm' ss" E
    m = re.match(r"^([NS])\s*([0-9]+(?:\.[0-9]+)?)\s*(?:[°]?)\s*(?:([0-9]+)(?:['′])?)?\s*(?:([0-9]+)(?:[\"″])?)?\s*([EW])$", b)
    if not m:
        # try compact like N4W
        m2 = re.match(r"^([NS])\s*([0-9]+(?:\.[0-9]+)?)\s*([EW])$", b.replace(" ", ""))
        if not m2:
            return (False, 0.0)
        ns, deg, ew = m2.group(1), float(m2.group(2)), m2.group(3)
        deg_total = float(deg)
        first, second = ns, ew
    else:
        first = m.group(1)
        deg = float(m.group(2))
        minutes = float(m.group(3)) if m.group(3) is not None else 0.0
        seconds = float(m.group(4)) if m.group(4) is not None else 0.0
        second = m.group(5)
        deg_total = deg + minutes / 60.0 + seconds / 3600.0

    # Convert quadrant to azimuth
    if first == "N":
        if second == "E":
            az = deg_total  # 0..90
        else:  # W
            az = (360.0 - deg_total) % 360.0
    else:  # first == "S"
        if second == "E":
            az = (180.0 - deg_total) % 360.0
        else:  # W
            az = (180.0 + deg_total) % 360.0
    return (True, az)


def calculate_offset_from_bearing(bearing_degrees: float, distance_feet: float) -> Tuple[float, float]:
    """
    Calculate x,y offset from bearing and distance.
    Bearing is azimuth clockwise from north.
    Returns (offset_x_east, offset_y_north) in feet.
    """
    ang = math.radians(float(bearing_degrees))
    x = float(distance_feet) * math.sin(ang)  # east
    y = float(distance_feet) * math.cos(ang)  # north
    return (x, y)


def parse_bearing_and_distance(bearing_raw: str, distance_value: float, distance_units: str = "feet") -> Dict[str, Any]:
    """
    Parse bearing and distance into offset components.
    """
    try:
        ok, az = _parse_quadrant_bearing(bearing_raw or "")
        if not ok:
            return {"success": False, "error": f"Cannot parse bearing: {bearing_raw}"}
        dist_feet = convert_distance_to_feet(distance_value, distance_units)
        dx, dy = calculate_offset_from_bearing(az, dist_feet)
        return {
            "success": True,
            "offset_x": dx,
            "offset_y": dy,
            "bearing_degrees": az,
            "distance_feet": dist_feet
        }
    except Exception as e:
        logger.error(f"Bearing and distance parsing failed: {str(e)}")
        return {"success": False, "error": f"Bearing and distance parsing error: {str(e)}"}


def normalize_local_coordinates(coordinates: List[Dict[str, float]] | List[Tuple[float, float]]) -> List[Tuple[float, float]]:
    """
    Normalize local coordinates to start from given origin (no shifting).
    Accepts [{x,y}] or [(x,y)] and returns [(x,y)].
    """
    out: List[Tuple[float, float]] = []
    if not coordinates:
        return out
    first = coordinates[0]
    if isinstance(first, dict):
        for c in coordinates:
            out.append((float(c.get("x", 0.0)), float(c.get("y", 0.0))))
    else:
        out = [(float(c[0]), float(c[1])) for c in coordinates]  # type: ignore
    return out


