"""
Simple Geographic Projection Service
Fast, accurate local-to-geographic coordinate transformation
"""
import logging
import math
from typing import Dict, Any, List, Tuple, Optional

logger = logging.getLogger(__name__)

class SimpleProjector:
    """
    Simple but accurate coordinate projection
    Converts local survey coordinates to geographic (WGS84)
    """
    
    def __init__(self):
        # Standard conversions
        self.feet_to_meters = 0.3048006096012192  # US Survey feet
        
        # Approximate conversion factors for Wyoming area (~41-45° latitude)
        self.meters_per_degree_lat = 111319.9   # Nearly constant
        self.meters_per_degree_lon = 85394.0    # At ~42° latitude
    
    def project_polygon(
        self,
        local_coordinates: List[Dict[str, float]],
        anchor_lat: float,
        anchor_lon: float,
        starting_point_offset: Optional[Tuple[float, float]] = None
    ) -> Dict[str, Any]:
        """
        Project local coordinates to geographic
        
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
            
            # Convert local coordinates to geographic
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
                
                # Convert meters to degrees
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
            
            logger.info(f"✅ Projected {len(local_coordinates)} coordinates to geographic")
            
            return {
                "success": True,
                "geographic_polygon": {
                    "type": "Polygon",
                    "coordinates": [geographic_coords]
                },
                "bounds": bounds
            }
            
        except Exception as e:
            logger.error(f"Projection failed: {e}")
            return {"success": False, "error": str(e)}
    
    def calculate_bearing_distance_offset(
        self,
        bearing_degrees: float,
        distance_feet: float
    ) -> Tuple[float, float]:
        """
        Calculate lat/lon offset from bearing and distance
        
        Args:
            bearing_degrees: Bearing in degrees (0-360, 0=North)
            distance_feet: Distance in feet
            
        Returns:
            (lat_offset, lon_offset) in degrees
        """
        try:
            # Convert to radians and adjust for coordinate system
            bearing_rad = math.radians(bearing_degrees)
            distance_meters = distance_feet * self.feet_to_meters
            
            # Calculate offsets
            lat_offset = distance_meters * math.cos(bearing_rad) / self.meters_per_degree_lat
            lon_offset = distance_meters * math.sin(bearing_rad) / self.meters_per_degree_lon
            
            return (lat_offset, lon_offset)
            
        except Exception as e:
            logger.error(f"Bearing/distance calculation failed: {e}")
            return (0.0, 0.0)
