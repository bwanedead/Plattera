"""
Georeference Pipeline
Converts local/display polygon coordinates + PLSS anchor/tie to geographic WGS84 (lat/lon).

Design goals:
- Single responsibility: orchestrate PLSS resolution + POB tie + projection.
- Reuse existing modules in mapping/plss and mapping/projection.
- Keep units explicit; treat local/display coordinates as feet; convert to meters for UTM.
"""
from typing import Any, Dict, List, Tuple, Optional
import logging

from pipelines.mapping.plss.pipeline import PLSSPipeline
from pipelines.mapping.projection.pipeline import ProjectionPipeline
from pipelines.polygon.draw_polygon import BearingParser

logger = logging.getLogger(__name__)

FeetToMeters = 0.3048


class GeoreferencePipeline:
    """
    Orchestrates georeferencing of deed-derived polygons.
    Input: local/display coordinates (feet), PLSS anchor, optional tie_to_corner.
    Output: GeoJSON-ready geographic polygon (lon/lat) and bounds.
    """

    def __init__(self) -> None:
        self.plss = PLSSPipeline()
        self.projection = ProjectionPipeline()
        self.bearing_parser = BearingParser()

    def _flip_display_to_survey(self, display_coords: List[Dict[str, float]] | List[Tuple[float, float]]
                               ) -> List[Tuple[float, float]]:
        """Convert display-ready coordinates back to survey frame (Y northing positive).

        The drawing engine flips Y for display; survey frame is (x east, y north).
        Accepts [{x, y}, ...] or [(x, y), ...].
        """
        survey: List[Tuple[float, float]] = []
        for pt in display_coords:
            if isinstance(pt, dict):
                x = float(pt.get("x", 0.0))
                y = float(pt.get("y", 0.0))
            else:
                x = float(pt[0])
                y = float(pt[1])
            survey.append((x, -y))  # invert Y back to survey frame
        return survey

    def _parse_tie(self, tie: Dict[str, Any]) -> Tuple[float, float]:
        """Parse tie_to_corner into survey offsets in feet (dx, dy) from reference corner.

        Returns (dx_feet, dy_feet) where +x east, +y north.
        """
        if not tie:
            return (0.0, 0.0)

        bearing_raw = tie.get("bearing_raw") or tie.get("bearing") or ""
        distance_value = float(tie.get("distance_value") or tie.get("distance_feet") or 0.0)
        distance_units = tie.get("distance_units", "feet")

        # Convert distance to feet
        units = distance_units.lower()
        if units in ("meter", "meters", "m"):
            distance_feet = distance_value / FeetToMeters
        elif units in ("chain", "chains"):
            distance_feet = distance_value * 66.0
        elif units in ("rod", "rods"):
            distance_feet = distance_value * 16.5
        else:
            distance_feet = distance_value

        # Parse bearing (surveyor quadrant to azimuth)
        bearing_result = self.bearing_parser.parse_bearing(bearing_raw)
        if not bearing_result.get("success"):
            logger.warning(f"Failed to parse bearing '{bearing_raw}': {bearing_result.get('error')}")
            return (0.0, 0.0)

        azimuth_deg = float(bearing_result["bearing_degrees"])  # clockwise from north

        # Convert to dx/dy in feet (north=+y, east=+x)
        import math
        theta = math.radians(azimuth_deg)
        dx_feet = distance_feet * math.sin(theta)
        dy_feet = distance_feet * math.cos(theta)
        return (dx_feet, dy_feet)

    def project(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """
        Project local/display polygon to geographic coordinates.

        Expected request shape:
        {
          "local_coordinates": [{x, y}, ...] OR [[x, y], ...]  // display-ready (feet)
          "plss_anchor": { state, township_number, township_direction, range_number, range_direction, section_number, quarter_sections? },
          "starting_point": { "tie_to_corner": { corner_label, bearing_raw, distance_value, distance_units } }?
        }
        """
        try:
            local_coords_raw = request.get("local_coordinates") or []
            plss_anchor = request.get("plss_anchor") or {}
            starting_point = request.get("starting_point") or {}
            tie_to_corner = starting_point.get("tie_to_corner") or {}

            if not local_coords_raw or len(local_coords_raw) < 3:
                return {"success": False, "error": "At least 3 local coordinates required"}

            # 1) Resolve PLSS anchor to a geographic coordinate (section-based reference)
            plss_result = self.plss.resolve_starting_point(plss_anchor)
            if not plss_result.get("success"):
                return {"success": False, "error": f"PLSS resolution failed: {plss_result.get('error')}"}

            # Use resolved coordinates as the reference corner base (section-based reference point)
            anchor_geo = plss_result["coordinates"]  # {lat, lon}

            # 2) Compute POB from tie (if provided) in UTM
            # Determine UTM zone for anchor
            utm_zone = self.projection.utm_manager.get_utm_zone(anchor_geo["lat"], anchor_geo["lon"])  # e.g., "13N"

            # Anchor in UTM
            anchor_utm = self.projection.transformer.geographic_to_utm(anchor_geo["lat"], anchor_geo["lon"], utm_zone)
            if not anchor_utm.get("success"):
                return {"success": False, "error": f"UTM transform failed: {anchor_utm.get('error')}"}

            # Tie offsets from corner to POB (feet → meters)
            tie_dx_feet, tie_dy_feet = self._parse_tie(tie_to_corner)
            pob_utm_x = anchor_utm["utm_x"] + tie_dx_feet * FeetToMeters
            pob_utm_y = anchor_utm["utm_y"] + tie_dy_feet * FeetToMeters

            # 3) Convert display coordinates back to survey frame and walk vertices in UTM
            survey_coords_feet: List[Tuple[float, float]] = self._flip_display_to_survey(local_coords_raw)

            # Ensure ring closure if not closed
            if survey_coords_feet[0] != survey_coords_feet[-1]:
                survey_coords_feet = survey_coords_feet + [survey_coords_feet[0]]

            # Normalize local coordinates so that the first vertex is (0,0) at the POB.
            # Display/survey coordinates include the origin offset (tie). Without normalization
            # we'd double-apply the tie. This ensures the first vertex aligns exactly with POB.
            start_x_feet, start_y_feet = survey_coords_feet[0]
            normalized_feet: List[Tuple[float, float]] = [
                (x - start_x_feet, y - start_y_feet) for (x, y) in survey_coords_feet
            ]

            # Build UTM vertices by offsetting normalized coordinates from POB
            utm_vertices: List[Tuple[float, float]] = []
            for x_feet, y_feet in normalized_feet:
                utm_vertices.append((pob_utm_x + x_feet * FeetToMeters, pob_utm_y + y_feet * FeetToMeters))

            # 4) Convert UTM vertices to geographic lon/lat
            geographic_ring: List[Tuple[float, float]] = []
            for utm_x, utm_y in utm_vertices:
                to_geo = self.projection.transformer.utm_to_geographic(utm_x, utm_y, utm_zone)
                if not to_geo.get("success"):
                    return {"success": False, "error": f"Vertex transform failed: {to_geo.get('error')}"}
                # transformer returns {lat, lon}
                geographic_ring.append((to_geo["lon"], to_geo["lat"]))

            # Compute geographic POB (from POB UTM)
            pob_geo_res = self.projection.transformer.utm_to_geographic(pob_utm_x, pob_utm_y, utm_zone)
            pob_geo = None
            if pob_geo_res.get("success"):
                pob_geo = {"lat": pob_geo_res["lat"], "lon": pob_geo_res["lon"]}

            # 5) Compute bounds
            lons = [pt[0] for pt in geographic_ring]
            lats = [pt[1] for pt in geographic_ring]
            bounds = {
                "min_lon": min(lons),
                "max_lon": max(lons),
                "min_lat": min(lats),
                "max_lat": max(lats),
            }

            plss_ref = f"T{plss_anchor.get('township_number')}{plss_anchor.get('township_direction')} " \
                       f"R{plss_anchor.get('range_number')}{plss_anchor.get('range_direction')} Sec {plss_anchor.get('section_number')}"

            return {
                "success": True,
                "geographic_polygon": {
                    "type": "Polygon",
                    "coordinates": [geographic_ring],
                    "bounds": bounds,
                },
                "anchor_info": {
                    "plss_reference": plss_ref,
                    # resolved_coordinates represents the resolved section reference (e.g., centroid)
                    "resolved_coordinates": {"lat": anchor_geo["lat"], "lon": anchor_geo["lon"]},
                    # pob_coordinates is the computed Point of Beginning on the parcel boundary
                    **({"pob_coordinates": pob_geo} if pob_geo else {}),
                },
                "projection_metadata": {
                    "utm_zone": utm_zone,
                    "vertex_count": len(geographic_ring),
                },
            }

        except Exception as e:
            logger.error(f"Georeference pipeline error: {e}")
            return {"success": False, "error": str(e)}


