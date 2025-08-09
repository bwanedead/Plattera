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

        sec_res = plss.section_view.get_section_geometry(data_res["vector_data"], plss_desc)
        if not sec_res.get("success"):
            return {"success": False, "error": sec_res.get("error")}

        section_geom = shape(sec_res["geometry"])
        poly = shape(geographic_polygon)

        centroid_inside_section = section_geom.contains(poly.centroid)
        area_inside = section_geom.intersection(poly).area
        coverage = float(area_inside / poly.area) if poly.area > 0 else 0.0
        inside_tolerance = coverage > 0.8

        twp_ok = None
        twp_res = plss.section_view.get_township_geometry(data_res["vector_data"], plss_desc)
        if twp_res.get("success"):
            twp_geom = shape(twp_res["geometry"])
            twp_ok = twp_geom.contains(poly.centroid)

        qq_label = _quarter_quarter_label(poly.centroid, section_geom)

        issues: List[str] = []
        if not centroid_inside_section:
            issues.append("Polygon centroid is outside section boundary")
        if not inside_tolerance:
            issues.append(f"Only {coverage:.0%} of polygon area lies inside the section")

        minx, miny, maxx, maxy = section_geom.bounds

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


