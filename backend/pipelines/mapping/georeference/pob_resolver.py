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
from shapely.geometry import LineString, Point
from math import atan2, degrees, hypot

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
    
    def _west_boundary_line(self, section_geom) -> LineString:
        """Extract the west boundary line from a section geometry."""
        # Accept Polygon or MultiPolygon; choose largest polygon by area
        try:
            geom = section_geom
            if hasattr(section_geom, "geoms"):  # MultiPolygon
                geom = max(section_geom.geoms, key=lambda g: g.area)
            ext = list(geom.exterior.coords)
            xs = [p[0] for p in ext]
            minx = min(xs)
            eps = (max(xs) - minx) * 0.005 or 1e-8
            west = sorted([p for p in ext if abs(p[0] - minx) < eps], key=lambda p: p[1])
            if len(west) >= 2 and (west[0] != west[-1]):
                return LineString([west[0], west[-1]])
            # fallback: bbox left edge
            minx, miny, maxx, maxy = geom.bounds
            return LineString([(minx, miny), (minx, maxy)])
        except Exception:
            # last resort: bounds of whatever we got
            minx, miny, maxx, maxy = section_geom.bounds
            return LineString([(minx, miny), (minx, maxy)])
    
    def _azimuth_deg(self, p0, p1) -> float:
        """Calculate azimuth in degrees from point p0 to p1 (0=N, clockwise)."""
        dx = p1[0] - p0[0]
        dy = p1[1] - p0[1]
        ang = (degrees(atan2(dx, dy)) + 360.0) % 360.0  # 0=N, cw
        return ang
    
    def _signed_offset_to_line(self, pt, line) -> float:
        """Calculate signed offset from point to line (right-hand positive relative to line direction)."""
        a, b = line.coords[0], line.coords[-1]
        ax, ay = a
        bx, by = b
        px, py = pt
        vx, vy = bx-ax, by-ay
        wx, wy = px-ax, py-ay
        # area sign gives side
        cross = vx*wy - vy*wx
        L = hypot(vx, vy) or 1e-9
        return cross / L  # meters; >0 = right of line, <0 = left

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

                # NOTE: DO NOT project tie vector onto west edge direction
                # The original bearing from the deed should be preserved exactly
                # as it represents the true surveyed direction, not constrained to section boundaries
                
                print(f"🔍 PRESERVING ORIGINAL BEARING: dx_m={dx_m:.3f}, dy_m={dy_m:.3f}")

                tie_dir = (tie_to_corner.get("tie_direction") or "corner_bears_from_pob").lower()
                if tie_dir == "corner_bears_from_pob":
                    # Vector from POB -> corner is v; so POB = corner - v
                    pob_x = corner_utm["utm_x"] - dx_m
                    pob_y = corner_utm["utm_y"] - dy_m
                else:
                    # Vector from corner -> POB is v; so POB = corner + v
                    pob_x = corner_utm["utm_x"] + dx_m
                    pob_y = corner_utm["utm_y"] + dy_m

                # FIX 3: Optional POB boundary snapping
                project_to_boundary = tie_to_corner.get("project_to_boundary", True)  # Default True for west boundary ties
                if project_to_boundary and "west" in corner_label.lower():
                    print(f"🔧 ATTEMPTING BOUNDARY SNAPPING...")
                    # Get section geometry for boundary projection
                    sec_data = self._plss_joiner.find_section_in_township(
                        plss_anchor['section_number'],
                        self._plss_joiner.find_township_range(
                            plss_anchor['township_number'], plss_anchor['township_direction'],
                            plss_anchor['range_number'], plss_anchor['range_direction'],
                            plss_anchor.get('principal_meridian')
                        )
                    )
                    section_geom = sec_data.get('geometry') if sec_data else None
                    
                    if section_geom is not None:
                        # Build west boundary line and project POB onto it
                        west_line_ll = self._west_boundary_line(section_geom)
                        wl0 = self._transformer.geographic_to_utm(west_line_ll.coords[0][1], west_line_ll.coords[0][0], utm_zone)
                        wl1 = self._transformer.geographic_to_utm(west_line_ll.coords[-1][1], west_line_ll.coords[-1][0], utm_zone)
                        west_line_utm = LineString([(wl0["utm_x"], wl0["utm_y"]), (wl1["utm_x"], wl1["utm_y"])])
                        
                        # Project POB to closest point on west boundary
                        pob_pt = Point(pob_x, pob_y)
                        proj_dist = west_line_utm.project(pob_pt)  # Distance along line from south
                        projected = west_line_utm.interpolate(proj_dist)
                        pob_x, pob_y = projected.x, projected.y
                        print(f"🔧 POB SNAPPED TO WEST BOUNDARY: x={pob_x:.3f}, y={pob_y:.3f}")
                    else:
                        print(f"⚠️ Could not get section geometry for boundary snapping")

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
                
                # Fetch section geometry for diagnostics
                sec_data = self._plss_joiner.find_section_in_township(
                    plss_anchor['section_number'],
                    self._plss_joiner.find_township_range(
                        plss_anchor['township_number'], plss_anchor['township_direction'],
                        plss_anchor['range_number'], plss_anchor['range_direction'],
                        plss_anchor.get('principal_meridian')
                    )
                )
                section_geom = sec_data.get('geometry') if sec_data else None

                print("🔎 TIE DEBUG:",
                      {"corner_label": short_label,
                       "tie_direction": tie_to_corner.get("tie_direction"),
                       "bearing_raw": tie_to_corner.get("bearing_raw"),
                       "bearing_deg": parsed.get("bearing_degrees"),
                       "distance_ft": parsed.get("distance_feet"),
                       "dx_m": round(dx_m, 3),
                       "dy_m": round(dy_m, 3)})

                print("🔎 COORD DEBUG:",
                      {"corner_geo": corner_geo,
                       "corner_utm": corner_utm,
                       "pob_utm": {"x": pob_x, "y": pob_y, "zone": utm_zone},
                       "utm_zone": corner_utm.get("utm_zone")})

                if section_geom is not None and corner_utm["success"] and pob_geo_res["success"]:
                    # Build west boundary line and measure
                    west_line_ll = self._west_boundary_line(section_geom)
                    # project to UTM via your transformer
                    wl0 = self._transformer.geographic_to_utm(west_line_ll.coords[0][1], west_line_ll.coords[0][0], corner_utm["utm_zone"])
                    wl1 = self._transformer.geographic_to_utm(west_line_ll.coords[-1][1], west_line_ll.coords[-1][0], corner_utm["utm_zone"])
                    west_line_utm = LineString([(wl0["utm_x"], wl0["utm_y"]), (wl1["utm_x"], wl1["utm_y"])])
                    west_az = self._azimuth_deg(west_line_utm.coords[0], west_line_utm.coords[-1])
                    pob_pt = (pob_x, pob_y)
                    off_signed = self._signed_offset_to_line(pob_pt, west_line_utm)
                    # perpendicular distance
                    dist_perp = west_line_utm.distance(Point(pob_pt))

                    # Measure relative position of POB along west edge (south→north)
                    edge_len_m = float(west_line_utm.length)
                    s_along_m = float(west_line_utm.project(Point(pob_pt)))
                    frac_from_south = (s_along_m / edge_len_m) if edge_len_m > 0 else 0.0
                    dist_from_north_m = max(edge_len_m - s_along_m, 0.0)
                    tie_expected_m = 1638.0 * 0.3048  # from deed
                    delta_tie_m = dist_from_north_m - tie_expected_m

                    side = "east" if off_signed < 0 else "west"

                    print("🔎 SECTION/WEST-EDGE DEBUG:",
                          {"west_azimuth_deg": round(west_az, 3),
                           "edge_height_m": round(edge_len_m, 3),
                           "pob_perp_offset_m": round(dist_perp, 3),
                           "pob_side_of_west_edge": side,
                           "pob_fraction_from_south": round(frac_from_south, 5),
                           "pob_distance_from_north_m": round(dist_from_north_m, 3),
                           "tie_expected_m": round(tie_expected_m, 3),
                           "delta_tie_m": round(delta_tie_m, 3)})

                    # Optional: flag if we are not “on west boundary” (informational)
                    if dist_perp > 1.0:
                        print("⚠️ POB is not on west boundary (>", round(dist_perp, 3), "m).")

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