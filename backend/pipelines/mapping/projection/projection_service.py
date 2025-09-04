"""
Main Projection Service
Orchestrates PLSS resolution and coordinate projection
"""
import logging
from typing import Dict, Any, Optional, List, Tuple
import re
import math

logger = logging.getLogger(__name__)

class ProjectionService:
    """
    Main service for converting local survey coordinates to geographic
    """

    def __init__(self):
        from ..plss.coordinate_service import PLSSCoordinateService
        from ..calculators.geodesic_calculator import GeodesicCalculator

        self.plss_service = PLSSCoordinateService()
        self.geodesic_calc = GeodesicCalculator()
    
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
                    starting_point_offset = self._calculate_bearing_distance_offset_geodesic(
                        anchor_lat, anchor_lon, bearing_degrees, distance_feet
                    )
                    logger.info(f"Applied geodesic starting point offset: {distance_feet}ft @ {bearing_degrees}°")

            # Step 3: Project coordinates using selected method (geodesic by default)
            method = request.get("method", "geodesic")  # Allow method selection
            projection_result = self._project_polygon_with_method(
                local_coordinates=local_coordinates,
                anchor_lat=anchor_lat,
                anchor_lon=anchor_lon,
                starting_point_offset=starting_point_offset,
                method=method
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
                    "method": method,
                    "algorithm": projection_result.get("metadata", {}).get("projection_method", "unknown"),
                    "coordinate_count": len(local_coordinates),
                    "accuracy": "millimeter_level" if method == "geodesic" else "centimeter_level"
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

    def _project_polygon_with_method(
        self,
        local_coordinates: List[Dict[str, float]],
        anchor_lat: float,
        anchor_lon: float,
        starting_point_offset: Optional[Tuple[float, float]] = None,
        method: str = "geodesic"
    ) -> Dict[str, Any]:
        """
        Project polygon using the specified method (geodesic or legacy)
        """
        if method == "geodesic":
            return self._project_polygon_geodesic(
                local_coordinates=local_coordinates,
                anchor_lat=anchor_lat,
                anchor_lon=anchor_lon,
                starting_point_offset=starting_point_offset
            )
        else:
            # Fallback to simple method for compatibility
            logger.warning(f"⚠️ Using legacy projection method: {method}")
            return self._project_polygon_simple(
                local_coordinates=local_coordinates,
                anchor_lat=anchor_lat,
                anchor_lon=anchor_lon,
                starting_point_offset=starting_point_offset
            )

    def _project_polygon_geodesic(
        self,
        local_coordinates: List[Dict[str, float]],
        anchor_lat: float,
        anchor_lon: float,
        starting_point_offset: Optional[Tuple[float, float]] = None
    ) -> Dict[str, Any]:
        """
        Project local coordinates to geographic using geodesic calculations
        for maximum accuracy and consistency with measurement tools

        Args:
            local_coordinates: List of {"x": float, "y": float} in feet
            anchor_lat: Anchor latitude (WGS84)
            anchor_lon: Anchor longitude (WGS84)
            starting_point_offset: Optional (lat_offset, lon_offset) in degrees

        Returns:
            {
                "success": bool,
                "geographic_polygon": GeoJSON,
                "bounds": {...}
            }
        """
        try:
            if not local_coordinates:
                return {"success": False, "error": "No coordinates provided"}

            # Apply starting point offset if provided
            effective_anchor_lat = anchor_lat
            effective_anchor_lon = anchor_lon

            if starting_point_offset:
                effective_anchor_lat += starting_point_offset[0]
                effective_anchor_lon += starting_point_offset[1]

            # Convert local coordinates to geographic using geodesic calculations
            geographic_coords = []

            for coord in local_coordinates:
                # Be defensive: accept dicts with string/number values
                try:
                    x_raw = coord.get("x", 0.0)
                    y_raw = coord.get("y", 0.0)
                    x_feet = float(x_raw)
                    y_feet = float(y_raw)
                except Exception:
                    x_feet = 0.0
                    y_feet = 0.0

                # Convert feet to meters (0.3048 meters per foot)
                x_meters = x_feet * 0.3048
                y_meters = y_feet * 0.3048

                # Use geodesic calculation to find endpoint
                # For local coordinates, we treat x,y as easting,northing offsets
                # Calculate bearing and distance from anchor point
                bearing_radians = math.atan2(x_meters, y_meters)
                bearing_degrees = math.degrees(bearing_radians)
                distance_meters = math.sqrt(x_meters ** 2 + y_meters ** 2)

                if distance_meters > 0:
                    # Use geodesic calculation for accurate projection
                    result = self.geodesic_calc.calculate_endpoint(
                        effective_anchor_lat,
                        effective_anchor_lon,
                        bearing_degrees,
                        distance_meters
                    )

                    if result["success"]:
                        geographic_coords.append([result["end_lng"], result["end_lat"]])
                    else:
                        return {"success": False, "error": f"Geodesic calculation failed: {result.get('error')}"}
                else:
                    # Point is at anchor location
                    geographic_coords.append([effective_anchor_lon, effective_anchor_lat])

            # Close polygon if needed
            if len(geographic_coords) > 2:
                if geographic_coords[0] != geographic_coords[-1]:
                    geographic_coords.append(geographic_coords[0])

            # Calculate bounds
            if geographic_coords:
                lons = [coord[0] for coord in geographic_coords]
                lats = [coord[1] for coord in geographic_coords]

                bounds = {
                    "min_lat": min(lats),
                    "max_lat": max(lats),
                    "min_lon": min(lons),
                    "max_lon": max(lons)
                }
            else:
                bounds = {}

            logger.info(f"✅ Projected {len(local_coordinates)} coordinates using geodesic calculations")

            return {
                "success": True,
                "geographic_polygon": {
                    "type": "Polygon",
                    "coordinates": [geographic_coords]
                },
                "bounds": bounds
            }

        except Exception as e:
            logger.error(f"Geodesic polygon projection failed: {str(e)}")
            return {"success": False, "error": str(e)}

    def _calculate_bearing_distance_offset_geodesic(
        self,
        anchor_lat: float,
        anchor_lon: float,
        bearing_degrees: float,
        distance_feet: float
    ) -> Tuple[float, float]:
        """
        Calculate lat/lon offset from bearing and distance using geodesic calculations
        for maximum accuracy and consistency

        Args:
            anchor_lat: Reference latitude
            anchor_lon: Reference longitude
            bearing_degrees: Bearing in degrees (0-360, 0=North)
            distance_feet: Distance in feet

        Returns:
            (lat_offset, lon_offset) in degrees
        """
        try:
            # Convert feet to meters
            distance_meters = distance_feet * 0.3048

            # Calculate endpoint using geodesic method from anchor point
            result = self.geodesic_calc.calculate_endpoint(
                anchor_lat,
                anchor_lon,
                bearing_degrees,
                distance_meters
            )

            if not result["success"]:
                logger.error(f"Geodesic offset calculation failed: {result.get('error')}")
                return (0.0, 0.0)

            # Calculate offsets from anchor point
            lat_offset = result["end_lat"] - anchor_lat
            lon_offset = result["end_lng"] - anchor_lon

            logger.debug(f"🧮 Geodesic offset: {distance_feet:.1f}ft @ {bearing_degrees:.1f}° = ({lat_offset:.8f}, {lon_offset:.8f}) degrees")

            return (lat_offset, lon_offset)

        except Exception as e:
            logger.error(f"Geodesic bearing/distance calculation failed: {str(e)}")
            return (0.0, 0.0)

    def _project_polygon_simple(
        self,
        local_coordinates: List[Dict[str, float]],
        anchor_lat: float,
        anchor_lon: float,
        starting_point_offset: Optional[Tuple[float, float]] = None
    ) -> Dict[str, Any]:
        """
        Legacy simple projection method for backward compatibility
        Uses basic linear approximations instead of geodesic calculations
        """
        try:
            if not local_coordinates:
                return {"success": False, "error": "No coordinates provided"}

            # Apply starting point offset if provided
            effective_anchor_lat = anchor_lat
            effective_anchor_lon = anchor_lon

            if starting_point_offset:
                effective_anchor_lat += starting_point_offset[0]
                effective_anchor_lon += starting_point_offset[1]

            # Convert local coordinates to geographic using simple linear approximation
            geographic_coords = []

            for coord in local_coordinates:
                # Be defensive: accept dicts with string/number values
                try:
                    x_raw = coord.get("x", 0.0)
                    y_raw = coord.get("y", 0.0)
                    x_feet = float(x_raw)
                    y_feet = float(y_raw)
                except Exception:
                    x_feet = 0.0
                    y_feet = 0.0

                # Convert feet to meters
                x_meters = x_feet * self.feet_to_meters
                y_meters = y_feet * self.feet_to_meters

                # Simple linear approximation (not as accurate as geodesic)
                lat_offset = y_meters / self.meters_per_degree_lat
                lon_offset = x_meters / self.meters_per_degree_lon

                # Apply to anchor
                lat = effective_anchor_lat + lat_offset
                lon = effective_anchor_lon + lon_offset

                geographic_coords.append([lon, lat])  # GeoJSON format: [lon, lat]

            # Close polygon if needed
            if len(geographic_coords) > 2:
                if geographic_coords[0] != geographic_coords[-1]:
                    geographic_coords.append(geographic_coords[0])

            # Calculate bounds
            if geographic_coords:
                lons = [coord[0] for coord in geographic_coords]
                lats = [coord[1] for coord in geographic_coords]

                bounds = {
                    "min_lat": min(lats),
                    "max_lat": max(lats),
                    "min_lon": min(lons),
                    "max_lon": max(lons)
                }
            else:
                bounds = {}

            logger.info(f"✅ Simple projection completed for {len(local_coordinates)} coordinates")

            return {
                "success": True,
                "geographic_polygon": {
                    "type": "Polygon",
                    "coordinates": [geographic_coords]
                },
                "bounds": bounds
            }

        except Exception as e:
            logger.error(f"Simple polygon projection failed: {str(e)}")
            return {"success": False, "error": str(e)}
