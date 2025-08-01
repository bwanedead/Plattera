"""
Coordinate Transformer
Handles coordinate transformations between different CRS
"""
import logging
import math
from typing import Dict, Any, Tuple

logger = logging.getLogger(__name__)

class CoordinateTransformer:
    """
    Handles coordinate transformations between different coordinate reference systems
    """
    
    def __init__(self):
        """Initialize coordinate transformer"""
        # In production, this would use pyproj or similar library
        # For now, we'll implement basic transformations
        pass
    
    def geographic_to_utm(self, lat: float, lon: float, utm_zone: str) -> dict:
        """
        Transform geographic coordinates to UTM
        
        Args:
            lat: Latitude in decimal degrees
            lon: Longitude in decimal degrees
            utm_zone: UTM zone string (e.g., "13N", "utm_13n")
            
        Returns:
            dict: UTM coordinates or error
        """
        try:
            logger.debug(f"🧭 Converting lat/lon ({lat}, {lon}) to UTM {utm_zone}")
            
            # Parse UTM zone
            zone_info = self._parse_utm_zone(utm_zone)
            if not zone_info["success"]:
                return zone_info
            
            zone_number = zone_info["zone_number"]
            is_northern = zone_info["is_northern"]
            
            # Convert to UTM using simplified projection math
            # In production, this would use proper projection libraries
            utm_coords = self._ll_to_utm(lat, lon, zone_number, is_northern)
            
            return {
                "success": True,
                "utm_x": utm_coords[0],
                "utm_y": utm_coords[1],
                "utm_zone": utm_zone,
                "zone_number": zone_number,
                "hemisphere": "N" if is_northern else "S"
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": f"Geographic to UTM conversion error: {str(e)}"
            }
    
    def utm_to_geographic(self, utm_x: float, utm_y: float, utm_zone: str) -> dict:
        """
        Transform UTM coordinates to geographic
        
        Args:
            utm_x: UTM X coordinate (easting)
            utm_y: UTM Y coordinate (northing)
            utm_zone: UTM zone string
            
        Returns:
            dict: Geographic coordinates or error
        """
        try:
            logger.debug(f"🧭 Converting UTM ({utm_x}, {utm_y}) in zone {utm_zone} to lat/lon")
            
            # Parse UTM zone
            zone_info = self._parse_utm_zone(utm_zone)
            if not zone_info["success"]:
                return zone_info
            
            zone_number = zone_info["zone_number"]
            is_northern = zone_info["is_northern"]
            
            # Convert to geographic using simplified projection math
            geo_coords = self._utm_to_ll(utm_x, utm_y, zone_number, is_northern)
            
            return {
                "success": True,
                "lat": geo_coords[0],
                "lon": geo_coords[1],
                "utm_zone": utm_zone
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": f"UTM to geographic conversion error: {str(e)}"
            }
    
    def transform_point(self, x: float, y: float, source_crs: str, target_crs: str) -> dict:
        """
        Transform a point between coordinate reference systems
        
        Args:
            x: X coordinate
            y: Y coordinate
            source_crs: Source CRS identifier
            target_crs: Target CRS identifier
            
        Returns:
            dict: Transformed coordinates
        """
        try:
            # Handle common transformation cases
            if source_crs == target_crs:
                return {"success": True, "x": x, "y": y}
            
            # Geographic to UTM
            if source_crs == "EPSG:4326" and target_crs.startswith("utm_"):
                return self.geographic_to_utm(y, x, target_crs)  # Note: x=lon, y=lat for geographic
            
            # UTM to Geographic
            if source_crs.startswith("utm_") and target_crs == "EPSG:4326":
                utm_result = self.utm_to_geographic(x, y, source_crs)
                if utm_result["success"]:
                    return {
                        "success": True,
                        "x": utm_result["lon"],
                        "y": utm_result["lat"]
                    }
                else:
                    return utm_result
            
            # For other transformations, return error (would implement as needed)
            return {
                "success": False,
                "error": f"Transformation from {source_crs} to {target_crs} not implemented"
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": f"Point transformation error: {str(e)}"
            }
    
    def _parse_utm_zone(self, utm_zone: str) -> dict:
        """Parse UTM zone string"""
        try:
            zone_str = utm_zone.lower().replace("utm_", "")
            
            if zone_str[-1] in ['n', 's']:
                zone_number = int(zone_str[:-1])
                is_northern = zone_str[-1] == 'n'
            else:
                # Try to parse as just number (assume northern)
                zone_number = int(zone_str)
                is_northern = True
            
            if not (1 <= zone_number <= 60):
                return {
                    "success": False,
                    "error": f"Invalid UTM zone number: {zone_number}"
                }
            
            return {
                "success": True,
                "zone_number": zone_number,
                "is_northern": is_northern
            }
            
        except ValueError:
            return {
                "success": False,
                "error": f"Cannot parse UTM zone: {utm_zone}"
            }
    
    def _ll_to_utm(self, lat: float, lon: float, zone_number: int, northern: bool) -> Tuple[float, float]:
        """
        Convert lat/lon to UTM coordinates
        Simplified implementation - in production use pyproj
        """
        # Constants for WGS84
        a = 6378137.0  # semi-major axis
        e = 0.081819190842622  # eccentricity
        e1sq = 0.006739496742276  # e prime squared
        k0 = 0.9996  # scale factor
        
        # Convert to radians
        lat_rad = math.radians(lat)
        lon_rad = math.radians(lon)
        
        # Calculate central meridian
        lon_origin = (zone_number - 1) * 6 - 180 + 3
        lon_origin_rad = math.radians(lon_origin)
        
        # Calculate UTM coordinates (simplified)
        N = a / math.sqrt(1 - e * e * math.sin(lat_rad) * math.sin(lat_rad))
        T = math.tan(lat_rad) * math.tan(lat_rad)
        C = e1sq * math.cos(lat_rad) * math.cos(lat_rad)
        A = math.cos(lat_rad) * (lon_rad - lon_origin_rad)
        
        M = a * ((1 - e * e / 4 - 3 * e * e * e * e / 64) * lat_rad -
                (3 * e * e / 8 + 3 * e * e * e * e / 32) * math.sin(2 * lat_rad) +
                (15 * e * e * e * e / 256) * math.sin(4 * lat_rad))
        
        utm_x = k0 * N * (A + (1 - T + C) * A * A * A / 6 +
                         (5 - 18 * T + T * T + 72 * C - 58 * e1sq) * A * A * A * A * A / 120) + 500000.0
        
        utm_y = k0 * (M + N * math.tan(lat_rad) * (A * A / 2 + (5 - T + 9 * C + 4 * C * C) * A * A * A * A / 24 +
                     (61 - 58 * T + T * T + 600 * C - 330 * e1sq) * A * A * A * A * A * A / 720))
        
        if not northern:
            utm_y += 10000000.0
        
        return (utm_x, utm_y)
    
    def _utm_to_ll(self, utm_x: float, utm_y: float, zone_number: int, northern: bool) -> Tuple[float, float]:
        """
        Convert UTM coordinates to lat/lon
        Simplified implementation - in production use pyproj
        """
        # Constants for WGS84
        a = 6378137.0
        e = 0.081819190842622
        e1sq = 0.006739496742276
        k0 = 0.9996
        
        # Remove false easting/northing
        x = utm_x - 500000.0
        y = utm_y
        if not northern:
            y -= 10000000.0
        
        # Calculate central meridian
        lon_origin = (zone_number - 1) * 6 - 180 + 3
        
        # Calculate M
        M = y / k0
        mu = M / (a * (1 - e * e / 4 - 3 * e * e * e * e / 64))
        
        # Calculate footprint latitude
        e1 = (1 - math.sqrt(1 - e * e)) / (1 + math.sqrt(1 - e * e))
        J1 = (3 * e1 / 2 - 27 * e1 * e1 * e1 / 32)
        J2 = (21 * e1 * e1 / 16 - 55 * e1 * e1 * e1 * e1 / 32)
        J3 = (151 * e1 * e1 * e1 / 96)
        J4 = (1097 * e1 * e1 * e1 * e1 / 512)
        
        fp = mu + J1 * math.sin(2 * mu) + J2 * math.sin(4 * mu) + J3 * math.sin(6 * mu) + J4 * math.sin(8 * mu)
        
        # Calculate latitude and longitude
        e1sq = e * e / (1 - e * e)
        C1 = e1sq * math.cos(fp) * math.cos(fp)
        T1 = math.tan(fp) * math.tan(fp)
        N1 = a / math.sqrt(1 - e * e * math.sin(fp) * math.sin(fp))
        R1 = a * (1 - e * e) / pow(1 - e * e * math.sin(fp) * math.sin(fp), 1.5)
        D = x / (N1 * k0)
        
        lat = fp - (N1 * math.tan(fp) / R1) * (D * D / 2 - (5 + 3 * T1 + 10 * C1 - 4 * C1 * C1 - 9 * e1sq) * D * D * D * D / 24 +
              (61 + 90 * T1 + 298 * C1 + 45 * T1 * T1 - 252 * e1sq - 3 * C1 * C1) * D * D * D * D * D * D / 720)
        
        lon = (D - (1 + 2 * T1 + C1) * D * D * D / 6 + (5 - 2 * C1 + 28 * T1 - 3 * C1 * C1 + 8 * e1sq + 24 * T1 * T1) * D * D * D * D * D / 120) / math.cos(fp)
        
        lat = math.degrees(lat)
        lon = math.degrees(lon) + lon_origin
        
        return (lat, lon)