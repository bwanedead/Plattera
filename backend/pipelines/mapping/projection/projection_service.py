"""
Main Projection Service
Orchestrates PLSS resolution and coordinate projection
"""
import logging
from typing import Dict, Any, Optional
import re
import math

logger = logging.getLogger(__name__)

class ProjectionService:
    """
    Main service for converting local survey coordinates to geographic
    """
    
    def __init__(self):
        from ..plss.coordinate_service import PLSSCoordinateService
        from .simple_projector import SimpleProjector
        
        self.plss_service = PLSSCoordinateService()
        self.projector = SimpleProjector()
    
    def project_polygon(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """
        Main projection entry point
        
        Args:
            request: {
                "local_coordinates": [...],
                "plss_anchor": {...},
                "starting_point": {...}  # Optional
            }
        """
        try:
            local_coordinates = request.get("local_coordinates", [])
            plss_anchor = request.get("plss_anchor", {})
            starting_point = request.get("starting_point", {})
            
            if not local_coordinates:
                return {"success": False, "error": "No local coordinates provided"}
            
            if not plss_anchor:
                return {"success": False, "error": "No PLSS anchor provided"}
            
            # Step 1: Resolve PLSS anchor to geographic coordinates
            plss_result = self.plss_service.resolve_coordinates(
                state=plss_anchor.get("state"),
                township=plss_anchor.get("township_number"),
                township_direction=plss_anchor.get("township_direction"),
                range_number=plss_anchor.get("range_number"),
                range_direction=plss_anchor.get("range_direction"),
                section=plss_anchor.get("section_number"),
                quarter_sections=plss_anchor.get("quarter_sections"),
                principal_meridian=plss_anchor.get("principal_meridian")
            )
            
            if not plss_result.get("success"):
                return {"success": False, "error": f"PLSS resolution failed: {plss_result.get('error')}"}
            
            anchor_lat = plss_result["coordinates"]["lat"]
            anchor_lon = plss_result["coordinates"]["lon"]
            
            # Step 2: Calculate starting point offset if provided
            starting_point_offset = None
            if starting_point and starting_point.get("tie_to_corner"):
                tie = starting_point["tie_to_corner"]
                raw_bearing = tie.get("bearing_raw")
                raw_distance = tie.get("distance_value")

                # Parse distance (accept strings or numbers)
                distance_feet: Optional[float] = None
                try:
                    if raw_distance is not None:
                        distance_feet = float(raw_distance)
                except (TypeError, ValueError):
                    logger.warning(f"Invalid distance value provided: {raw_distance}")

                # Parse bearing in degrees from common formats (e.g., 45, '45', 'N45E', 'S 12.5 W')
                bearing_degrees: Optional[float] = self._parse_bearing_degrees(raw_bearing)

                if bearing_degrees is not None and distance_feet is not None:
                    starting_point_offset = self.projector.calculate_bearing_distance_offset(
                        bearing_degrees, distance_feet
                    )
                    logger.info(f"Applied starting point offset: {distance_feet}ft @ {bearing_degrees}°")
            
            # Step 3: Project coordinates
            projection_result = self.projector.project_polygon(
                local_coordinates=local_coordinates,
                anchor_lat=anchor_lat,
                anchor_lon=anchor_lon,
                starting_point_offset=starting_point_offset
            )
            
            if not projection_result.get("success"):
                return projection_result
            
            # Step 4: Build complete response
            return {
                "success": True,
                "geographic_polygon": projection_result["geographic_polygon"],
                "bounds": projection_result["bounds"],
                "anchor_info": {
                    "plss_reference": plss_result["plss_reference"],
                    "resolved_coordinates": {
                        "lat": anchor_lat,
                        "lon": anchor_lon
                    }
                },
                "projection_metadata": {
                    "method": plss_result.get("method", "unknown"),
                    "coordinate_count": len(local_coordinates)
                }
            }
            
        except Exception as e:
            logger.error(f"Projection service failed: {e}")
            return {"success": False, "error": str(e)}

    def _parse_bearing_degrees(self, bearing: Any) -> Optional[float]:
        """Parse a bearing which can be a float, numeric string, or quadrant format like 'N45E'.
        Returns azimuth degrees clockwise from north, or None if not parseable.
        """
        try:
            if bearing is None:
                return None
            # If already numeric
            if isinstance(bearing, (int, float)):
                return float(bearing)
            b = str(bearing).strip().upper().replace("\u00B0", "")
            # Pure number string
            try:
                return float(b)
            except ValueError:
                pass
            # Quadrant format e.g., N45E, N 45 E, S12.5W
            m = re.match(r"^([NS])\s*(\d+(?:\.\d+)?)\s*([EW])$", re.sub(r"\s+", " ", b))
            if m:
                ns = m.group(1)
                deg = float(m.group(2))
                ew = m.group(3)
                if ns == 'N' and ew == 'E':
                    return deg
                if ns == 'N' and ew == 'W':
                    return (360.0 - deg) % 360.0
                if ns == 'S' and ew == 'E':
                    return (180.0 - deg) % 360.0
                if ns == 'S' and ew == 'W':
                    return (180.0 + deg) % 360.0
            return None
        except Exception:
            return None
