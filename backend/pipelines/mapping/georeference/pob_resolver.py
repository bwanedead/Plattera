"""
Point of Beginning (POB) Resolver
Fresh implementation for calculating the Point of Beginning from PLSS and tie information.
"""
from __future__ import annotations

from typing import Any, Dict, Optional
import logging

from pipelines.mapping.plss.section_index import SectionIndex
from pipelines.mapping.plss.coordinate_service import PLSSCoordinateService
from pipelines.mapping.projection.transformer import CoordinateTransformer
from pipelines.mapping.projection.utm_manager import UTMManager
from .pob_math import parse_bearing_and_distance

logger = logging.getLogger(__name__)


class POBResolver:
    """
    Resolves the Point of Beginning (POB) for a deed polygon.
    
    The POB is the starting point of the polygon boundary. It can be:
    1. A PLSS corner (NW, NE, SW, SE corner of a section)
    2. A point offset from a PLSS corner by bearing and distance
    3. The centroid of a PLSS section (fallback)
    """
    
    def __init__(self) -> None:
        """Initialize the POB resolver."""
        self._idx = SectionIndex()  # uses project_root/plss by default
        self._coord_service = PLSSCoordinateService()
        self._transformer = CoordinateTransformer()
        self._utm = UTMManager()
    
    def _short_corner_label(self, label: str) -> str:
        lab = (label or "").upper()
        if "NE" in lab:
            return "NE"
        if "SE" in lab:
            return "SE"
        if "SW" in lab:
            return "SW"
        return "NW"
    
    def resolve_pob(self, plss_anchor: Dict[str, Any], tie_to_corner: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Resolve the Point of Beginning from PLSS anchor and optional tie.
        """
        try:
            state = plss_anchor.get("state") or "Wyoming"
            # Ensure expected plss keys exist for index match
            for k in ["township_number","township_direction","range_number","range_direction","section_number"]:
                if k not in plss_anchor:
                    return {"success": False, "error": f"Missing PLSS key: {k}"}

            # If tie is provided: resolve the specified corner and offset to POB
            if tie_to_corner:
                corner_label = tie_to_corner.get("corner_label") or ""
                short_label = self._short_corner_label(corner_label)
                corner_geo = self._idx.get_corner(state, plss_anchor, short_label)
                if not corner_geo:
                    return {"success": False, "error": f"Could not resolve corner: {corner_label}"}
                
                # Parse bearing/distance to offset (feet)
                bearing_raw = tie_to_corner.get("bearing_raw")
                dist_val = float(tie_to_corner.get("distance_value", 0.0))
                dist_units = tie_to_corner.get("distance_units", "feet")
                parsed = parse_bearing_and_distance(bearing_raw, dist_val, dist_units)
                if not parsed.get("success"):
                    return {"success": False, "error": parsed.get("error", "Invalid tie bearing/distance")}
                
                # Transform corner to UTM
                utm_zone = self._utm.get_utm_zone(corner_geo["lat"], corner_geo["lon"])
                corner_utm = self._transformer.geographic_to_utm(corner_geo["lat"], corner_geo["lon"], utm_zone)
                if not corner_utm.get("success"):
                    return {"success": False, "error": f"Corner UTM transform failed: {corner_utm.get('error')}"}
                
                # Offset in meters (east=x, north=y)
                f2m = 0.3048
                dx_m = parsed["offset_x"] * f2m
                dy_m = parsed["offset_y"] * f2m

                tie_dir = (tie_to_corner.get("tie_direction") or "corner_bears_from_pob").lower()
                if tie_dir == "corner_bears_from_pob":
                    # Vector from POB -> corner is v; so POB = corner - v
                    pob_x = corner_utm["utm_x"] - dx_m
                    pob_y = corner_utm["utm_y"] - dy_m
                else:
                    # Vector from corner -> POB is v; so POB = corner + v
                    pob_x = corner_utm["utm_x"] + dx_m
                    pob_y = corner_utm["utm_y"] + dy_m

                pob_geo_res = self._transformer.utm_to_geographic(pob_x, pob_y, utm_zone)
                if not pob_geo_res.get("success"):
                    return {"success": False, "error": f"POB geographic transform failed: {pob_geo_res.get('error')}"}
                
                return {
                    "success": True,
                    "pob_geographic": {"lat": pob_geo_res["lat"], "lon": pob_geo_res["lon"]},
                    "pob_utm": {"x": pob_x, "y": pob_y, "zone": utm_zone},
                    "method": "corner_with_tie",
                    "corner_info": {"corner": short_label, "section": str(plss_anchor.get("section_number"))},
                    "resolved_corner_geographic": {"lat": corner_geo["lat"], "lon": corner_geo["lon"]}
                }
            
            # Otherwise: use section centroid as POB
            idx_res = self._idx.get_centroid_bounds(state, plss_anchor)
            if idx_res and idx_res.get("center"):
                center = idx_res["center"]
                utm_zone = self._utm.get_utm_zone(center["lat"], center["lon"])
                utm_res = self._transformer.geographic_to_utm(center["lat"], center["lon"], utm_zone)
                if not utm_res.get("success"):
                    return {"success": False, "error": utm_res.get("error", "UTM transform failed")}
                return {
                    "success": True,
                    "pob_geographic": {"lat": center["lat"], "lon": center["lon"]},
                    "pob_utm": {"x": utm_res["utm_x"], "y": utm_res["utm_y"], "zone": utm_zone},
                    "method": "section_centroid",
                    "resolved_centroid_geographic": {"lat": center["lat"], "lon": center["lon"]}
                }

            # Final fallback via coordinate service centroid
            svc = self._coord_service.resolve_coordinates(
                state=state,
                township=plss_anchor["township_number"],
                township_direction=plss_anchor["township_direction"],
                range_number=plss_anchor["range_number"],
                range_direction=plss_anchor["range_direction"],
                section=plss_anchor["section_number"],
                principal_meridian=plss_anchor.get("principal_meridian")
            )
            if svc.get("success"):
                coord = svc["coordinates"]
                utm_zone = self._utm.get_utm_zone(coord["lat"], coord["lon"])
                utm_res = self._transformer.geographic_to_utm(coord["lat"], coord["lon"], utm_zone)
                return {
                    "success": True,
                    "pob_geographic": {"lat": coord["lat"], "lon": coord["lon"]},
                    "pob_utm": {"x": utm_res["utm_x"], "y": utm_res["utm_y"], "zone": utm_zone},
                    "method": "section_centroid",
                    "resolved_centroid_geographic": {"lat": coord["lat"], "lon": coord["lon"]}
                }

            return {"success": False, "error": "Unable to resolve POB from PLSS anchor"}
            
        except Exception as e:
            logger.error(f"POB resolution failed: {str(e)}")
            return {
                "success": False,
                "error": f"POB resolution error: {str(e)}"
            }
    
    def resolve_plss_corner(self, plss_description: Dict[str, Any], corner_label: str) -> Dict[str, Any]:
        """
        Resolve a specific PLSS corner to geographic coordinates.
        """
        try:
            state = plss_description.get("state") or "Wyoming"
            short = self._short_corner_label(corner_label)
            corner = self._idx.get_corner(state, plss_description, short)
            if not corner:
                return {"success": False, "error": f"Corner not found: {corner_label}"}
            return {
                "success": True,
                "corner": {"lat": corner["lat"], "lon": corner["lon"]},
                "corner_label": short
            }
        except Exception as e:
            logger.error(f"PLSS corner resolution failed: {str(e)}")
            return {
                "success": False,
                "error": f"PLSS corner resolution error: {str(e)}"
            }