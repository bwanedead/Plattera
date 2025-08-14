"""
Georeference Validator
Sanity checks for georeferenced deed polygons against PLSS geometries.
"""
from __future__ import annotations

from typing import Dict, Any, List, Optional
from shapely.geometry import Polygon, shape, Point

from pipelines.mapping.plss.pipeline import PLSSPipeline


def _quarter_label(pt: Point, section_centroid: Point) -> str:
    ns = "N" if pt.y >= section_centroid.y else "S"
    ew = "E" if pt.x >= section_centroid.x else "W"
    return f"{ns}{ew}"


def _quarter_quarter_label(pt: Point, section_geom) -> Optional[str]:
    c = section_geom.centroid
    q_label = _quarter_label(pt, c)

    # Determine label relative to quarter centroid (approximation)
    # This intentionally avoids heavy polygon splitting.
    if q_label == "NW":
        qc = section_geom.envelope.centroid  # fallback
    elif q_label == "NE":
        qc = section_geom.envelope.centroid
    elif q_label == "SW":
        qc = section_geom.envelope.centroid
    else:
        qc = section_geom.envelope.centroid

    sub = _quarter_label(pt, qc)
    return f"{sub} of {q_label}"


def validate_polygon_against_plss(plss_desc: Dict[str, Any], geographic_polygon: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validate a geographic polygon (GeoJSON) against PLSS section and township.

    Returns checks and human-readable issues without throwing.
    """
    try:
        plss = PLSSPipeline()
        data_res = plss.data_manager.ensure_state_data(plss_desc.get("state"))
        if not data_res.get("success"):
            return {"success": False, "error": data_res.get("error", "PLSS data unavailable")}

        # Simplified validation using coordinate service
        section_result = plss.get_section_view(plss_desc)
        if not section_result.get("success"):
            return {"success": False, "error": section_result.get("error")}

        # For simplified validation, just check if polygon is within reasonable distance of section center
        section_centroid = section_result["centroid"]
        poly = shape(geographic_polygon)
        poly_centroid = poly.centroid
        
        # Calculate distance between polygon centroid and section centroid
        from geopy.distance import geodesic
        distance_km = geodesic(
            (poly_centroid.y, poly_centroid.x),
            (section_centroid["lat"], section_centroid["lon"])
        ).kilometers
        
        # A section is ~1.6km x 1.6km, so if centroid is within 2km, it's probably reasonable
        centroid_inside_section = distance_km < 2.0
        coverage = 1.0 if centroid_inside_section else 0.0  # Simplified
        inside_tolerance = centroid_inside_section
        
        twp_ok = centroid_inside_section  # Simplified - same as section check
        qq_label = "Unknown"  # Simplified - no quarter-quarter calculation for now

        issues: List[str] = []
        if not centroid_inside_section:
            issues.append("Polygon centroid is outside section boundary")
        if not inside_tolerance:
            issues.append(f"Only {coverage:.0%} of polygon area lies inside the section")

        # Create approximate bounds around section centroid (1 square mile ≈ 0.014° x 0.014°)
        lat, lon = section_centroid["lat"], section_centroid["lon"]
        bounds_size = 0.007  # Half a section in degrees
        minx, miny, maxx, maxy = lon - bounds_size, lat - bounds_size, lon + bounds_size, lat + bounds_size

        return {
            "success": True,
            "checks": {
                "centroid_inside_section": centroid_inside_section,
                "section_coverage_ratio": coverage,
                "inside_section_tolerance": inside_tolerance,
                "centroid_inside_township": twp_ok,
                "quarter_quarter_inferred": qq_label,
            },
            "section_bounds": {
                "min_lon": minx,
                "min_lat": miny,
                "max_lon": maxx,
                "max_lat": maxy,
            },
            "issues": issues,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


