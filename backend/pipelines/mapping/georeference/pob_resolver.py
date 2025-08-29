"""
Point of Beginning (POB) Resolver
Fresh implementation for calculating the Point of Beginning from PLSS and tie information.
"""
from __future__ import annotations

from typing import Any, Dict, Optional, Tuple
import logging

from pipelines.mapping.plss.section_index import SectionIndex
from pipelines.mapping.plss.plss_joiner import PLSSJoiner
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
        self._plss_joiner = PLSSJoiner()  # for meridian-aware PLSS lookups
        self._coord_service = PLSSCoordinateService()
        self._transformer = CoordinateTransformer()
        self._utm = UTMManager()
    
    def _short_corner_label(self, label: str) -> str:
        lab = (label or "").upper().strip()
        
        # Use word boundaries to avoid substring matching issues
        import re
        
        # Check for exact matches first
        if re.search(r'\bNORTHWEST\b', lab) or re.search(r'\bNW\b', lab):
            return "NW"
        elif re.search(r'\bNORTHEAST\b', lab) or re.search(r'\bNE\b', lab):
            return "NE"
        elif re.search(r'\bSOUTHWEST\b', lab) or re.search(r'\bSW\b', lab):
            return "SW"
        elif re.search(r'\bSOUTHEAST\b', lab) or re.search(r'\bSE\b', lab):
            return "SE"
        
        # Fallback: check for directional combinations
        if "NORTH" in lab and "WEST" in lab:
            return "NW"
        elif "NORTH" in lab and "EAST" in lab:
            return "NE"
        elif "SOUTH" in lab and "WEST" in lab:
            return "SW"
        elif "SOUTH" in lab and "EAST" in lab:
            return "SE"
        
        # Default fallback
        return "NW"
    
    def resolve_pob(self, plss_anchor: Dict[str, Any], tie_to_corner: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Resolve the Point of Beginning from PLSS anchor and optional tie.
        """
        try:
            state = plss_anchor.get("state") or "Wyoming"
            print(f"🔍 POB RESOLVER: Starting resolution for {state}")
            print(f"📊 PLSS Anchor: {plss_anchor}")
            print(f"📊 Tie to Corner: {tie_to_corner}")
            print(f"📍 PLSS REFERENCE: T{plss_anchor.get('township_number')}{plss_anchor.get('township_direction')} R{plss_anchor.get('range_number')}{plss_anchor.get('range_direction')} Sec {plss_anchor.get('section_number')}")
            
            # Ensure expected plss keys exist for index match
            for k in ["township_number","township_direction","range_number","range_direction","section_number"]:
                if k not in plss_anchor:
                    return {"success": False, "error": f"Missing PLSS key: {k}"}

            # If tie is provided: resolve the specified corner and offset to POB
            if tie_to_corner:
                corner_label = tie_to_corner.get("corner_label") or ""
                short_label = self._short_corner_label(corner_label)
                print(f"🔍 POB RESOLVER: Resolving corner '{corner_label}' -> '{short_label}'")
                print(f"📍 PLSS CORNER REFERENCE: {short_label} corner of T{plss_anchor.get('township_number')}{plss_anchor.get('township_direction')} R{plss_anchor.get('range_number')}{plss_anchor.get('range_direction')} Sec {plss_anchor.get('section_number')}")
                # Try PLSS joiner first (with meridian support), fallback to section index
                corner_coords = self._get_section_corner_from_plss_joiner(plss_anchor, short_label)
                if corner_coords:
                    corner_geo = {"lat": corner_coords[1], "lon": corner_coords[0]}  # (lon, lat) -> (lat, lon)
                else:
                    corner_geo = self._idx.get_corner(state, plss_anchor, short_label)
                print(f"📊 Corner resolution result: {corner_geo}")
                print(f"📍 CORNER COORDINATES: lat={corner_geo.get('lat') if corner_geo else 'NOT FOUND'}, lon={corner_geo.get('lon') if corner_geo else 'NOT FOUND'}")
                if not corner_geo:
                    return {"success": False, "error": f"Could not resolve corner: {corner_label}"}
                
                # Parse bearing/distance to offset (feet)
                bearing_raw = tie_to_corner.get("bearing_raw")
                dist_val = float(tie_to_corner.get("distance_value", 0.0))
                dist_units = tie_to_corner.get("distance_units", "feet")
                print(f"🔍 POB RESOLVER: Parsing bearing '{bearing_raw}' distance {dist_val} {dist_units}")
                parsed = parse_bearing_and_distance(bearing_raw, dist_val, dist_units)
                print(f"📊 Bearing/distance parse result: {parsed}")
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

                # Optional: project the tie vector onto actual west edge direction to ensure point lies on boundary
                edge = self._section_west_edge_unit(state, plss_anchor)
                if edge and edge.get("utm_zone") == utm_zone:
                    # tie vector from POB -> corner in meters
                    vx, vy = dx_m, dy_m
                    # unit vectors along west edge (NW->SW) and its opposite (SW->NW)
                    ux, uy = edge["ux"], edge["uy"]        # NW->SW (roughly south + slight east)
                    uox, uoy = -ux, -uy                    # SW->NW (roughly north + slight west)
                    # Choose direction that best matches the intended tie (N4W from POB -> corner)
                    # That direction is generally toward NW, i.e., SW->NW
                    # Project tie onto uo to preserve distance while staying on boundary
                    mag = (vx**2 + vy**2) ** 0.5 or 1.0
                    proj_vx, proj_vy = uox * mag, uoy * mag
                    dx_m, dy_m = proj_vx, proj_vy

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
                
                print(f"🔍 POB RESOLVER: Final POB calculation:")
                print(f"📍 REFERENCE CORNER: {short_label} corner at lat={corner_geo['lat']:.6f}, lon={corner_geo['lon']:.6f}")
                print(f"📍 TIE INFORMATION: {bearing_raw} {dist_val} {dist_units}")
                print(f"📍 OFFSET VECTOR: dx={dx_m:.2f}m, dy={dy_m:.2f}m ({parsed['offset_x']:.2f}ft, {parsed['offset_y']:.2f}ft)")
                print(f"📍 TIE DIRECTION: {tie_dir}")
                print(f"📊 Corner UTM: {corner_utm}")
                print(f"📊 POB UTM: x={pob_x:.2f}, y={pob_y:.2f}, zone={utm_zone}")
                print(f"📍 FINAL POB COORDINATES: lat={pob_geo_res['lat']:.6f}, lon={pob_geo_res['lon']:.6f}")
                print(f"📊 POB Geographic: {pob_geo_res}")
                
                return {
                    "success": True,
                    "pob_geographic": {"lat": pob_geo_res["lat"], "lon": pob_geo_res["lon"]},
                    "pob_utm": {"x": pob_x, "y": pob_y, "zone": utm_zone},
                    "method": "corner_with_tie",
                    "corner_info": {"corner": short_label, "section": str(plss_anchor.get("section_number"))},
                    "resolved_corner_geographic": {"lat": corner_geo["lat"], "lon": corner_geo["lon"]}
                }
            
            # Otherwise: use section centroid as POB
            print(f"🔍 POB RESOLVER: No tie provided, using section centroid as POB")
            idx_res = self._idx.get_centroid_bounds(state, plss_anchor)
            if idx_res and idx_res.get("center"):
                center = idx_res["center"]
                print(f"📍 SECTION CENTROID: lat={center['lat']:.6f}, lon={center['lon']:.6f}")
                utm_zone = self._utm.get_utm_zone(center["lat"], center["lon"])
                utm_res = self._transformer.geographic_to_utm(center["lat"], center["lon"], utm_zone)
                if not utm_res.get("success"):
                    return {"success": False, "error": utm_res.get("error", "UTM transform failed")}
                print(f"📍 FINAL POB COORDINATES (centroid): lat={center['lat']:.6f}, lon={center['lon']:.6f}")
                return {
                    "success": True,
                    "pob_geographic": {"lat": center["lat"], "lon": center["lon"]},
                    "pob_utm": {"x": utm_res["utm_x"], "y": utm_res["utm_y"], "zone": utm_zone},
                    "method": "section_centroid",
                    "resolved_centroid_geographic": {"lat": center["lat"], "lon": center["lon"]}
                }

            # Final fallback via coordinate service centroid
            print(f"🔍 POB RESOLVER: Section index failed, trying coordinate service fallback")
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
                print(f"📍 COORDINATE SERVICE CENTROID: lat={coord['lat']:.6f}, lon={coord['lon']:.6f}")
                utm_zone = self._utm.get_utm_zone(coord["lat"], coord["lon"])
                utm_res = self._transformer.geographic_to_utm(coord["lat"], coord["lon"], utm_zone)
                print(f"📍 FINAL POB COORDINATES (service): lat={coord['lat']:.6f}, lon={coord['lon']:.6f}")
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
    
    def _get_section_corner_from_plss_joiner(self, plss_anchor: Dict[str, Any], corner_label: str) -> Optional[Tuple[float, float]]:
        """Get section corner coordinates using PLSSJoiner with meridian support."""
        try:
            # Extract principal meridian from schema if available
            principal_meridian = plss_anchor.get('principal_meridian')
            
            coordinates = self._plss_joiner.get_section_corner_coordinates(
                township=plss_anchor['township_number'],
                township_dir=plss_anchor['township_direction'], 
                range_num=plss_anchor['range_number'],
                range_dir=plss_anchor['range_direction'],
                section=plss_anchor['section_number'],
                corner=corner_label,
                principal_meridian=principal_meridian  # Pass meridian for filtering
            )
            
            if coordinates:
                logger.info(f"✅ PLSSJoiner found corner coordinates: {coordinates}")
                return coordinates
            else:
                logger.warning("❌ PLSSJoiner could not find corner coordinates")
                return None
                
        except Exception as e:
            logger.error(f"❌ Error getting corner from PLSSJoiner: {e}")
            return None

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

    def _section_west_edge_unit(self, state: str, plss_anchor: Dict[str, Any]) -> Optional[Dict[str, float]]:
        """Get unit vector (UTM) along west boundary of the section from NW->SW."""
        try:
            # Get NW and SW corners from index (these corners are already in WGS84)
            nw = self._idx.get_corner(state, plss_anchor, "NW")
            sw = self._idx.get_corner(state, plss_anchor, "SW")
            if not nw or not sw:
                return None
            zone = self._utm.get_utm_zone(nw["lat"], nw["lon"])
            nw_utm = self._transformer.geographic_to_utm(nw["lat"], nw["lon"], zone)
            sw_utm = self._transformer.geographic_to_utm(sw["lat"], sw["lon"], zone)
            if not nw_utm.get("success") or not sw_utm.get("success"):
                return None
            dx = sw_utm["utm_x"] - nw_utm["utm_x"]
            dy = sw_utm["utm_y"] - nw_utm["utm_y"]
            norm = (dx**2 + dy**2) ** 0.5 or 1.0
            return {"ux": dx / norm, "uy": dy / norm, "utm_zone": zone, "nw_utm": nw_utm}
        except Exception:
            return None