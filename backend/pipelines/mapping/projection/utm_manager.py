"""
UTM Manager
Handles UTM zone determination and management
"""
import logging
import math
from typing import Dict, Any, Tuple

logger = logging.getLogger(__name__)

class UTMManager:
    """
    Manages UTM zone determination and utilities
    """
    
    def __init__(self):
        """Initialize UTM manager"""
        # Special UTM zones for certain regions
        self.special_zones = {
            # Norway
            (56, 3): 32,  # Use zone 32 instead of 31
            # Svalbard
            (72, 9): 33,   # Use zone 33 for some areas
            (72, 21): 35,  # Use zone 35 for some areas
        }
    
    def get_utm_zone(self, lat: float, lon: float) -> str:
        """
        Determine appropriate UTM zone for lat/lon coordinates
        
        Args:
            lat: Latitude in decimal degrees
            lon: Longitude in decimal degrees
            
        Returns:
            str: UTM zone string (e.g., "13N", "utm_13n")
        """
        try:
            # Standard UTM zone calculation
            zone_number = int((lon + 180) / 6) + 1
            
            # Handle longitude edge cases
            if lon >= 180:
                zone_number = 60
            elif lon < -180:
                zone_number = 1
            
            # Determine hemisphere
            hemisphere = "N" if lat >= 0 else "S"
            
            # Check for special cases (Norway, Svalbard, etc.)
            zone_number = self._apply_special_zones(lat, lon, zone_number)
            
            utm_zone = f"{zone_number}{hemisphere}"
            
            logger.debug(f"📍 Determined UTM zone {utm_zone} for coordinates ({lat}, {lon})")
            return utm_zone
            
        except Exception as e:
            logger.error(f"❌ UTM zone determination failed: {str(e)}")
            # Return default zone 1N as fallback
            return "1N"
    
    def _apply_special_zones(self, lat: float, lon: float, default_zone: int) -> int:
        """Apply special UTM zone rules for certain regions"""
        # Norway: Use zone 32 for western areas
        if 56 <= lat < 64 and 3 <= lon < 12:
            return 32
        
        # Svalbard: Special zone assignments
        if 72 <= lat < 84:
            if 0 <= lon < 9:
                return 31
            elif 9 <= lon < 21:
                return 33
            elif 21 <= lon < 33:
                return 35
            elif 33 <= lon < 42:
                return 37
        
        return default_zone
    
    def get_zone_bounds(self, utm_zone: str) -> dict:
        """
        Get the geographic bounds of a UTM zone
        
        Args:
            utm_zone: UTM zone string (e.g., "13N")
            
        Returns:
            dict: Zone bounds with min/max lat/lon
        """
        try:
            # Parse zone
            zone_number = int(utm_zone[:-1])
            hemisphere = utm_zone[-1].upper()
            
            # Calculate longitude bounds (6-degree zones)
            min_lon = (zone_number - 1) * 6 - 180
            max_lon = zone_number * 6 - 180
            
            # Latitude bounds depend on hemisphere
            if hemisphere == "N":
                min_lat = 0
                max_lat = 84  # UTM northern limit
            else:
                min_lat = -80  # UTM southern limit
                max_lat = 0
            
            return {
                "success": True,
                "bounds": {
                    "min_lon": min_lon,
                    "max_lon": max_lon,
                    "min_lat": min_lat,
                    "max_lat": max_lat
                },
                "center_lon": (min_lon + max_lon) / 2,
                "center_lat": (min_lat + max_lat) / 2
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": f"Zone bounds calculation error: {str(e)}"
            }
    
    def get_adjacent_zones(self, utm_zone: str) -> dict:
        """Get adjacent UTM zones"""
        try:
            zone_number = int(utm_zone[:-1])
            hemisphere = utm_zone[-1].upper()
            
            adjacent = {
                "west": None,
                "east": None,
                "north": None,
                "south": None
            }
            
            # Western adjacent zone
            if zone_number > 1:
                adjacent["west"] = f"{zone_number - 1}{hemisphere}"
            else:
                adjacent["west"] = f"60{hemisphere}"  # Wrap around
            
            # Eastern adjacent zone
            if zone_number < 60:
                adjacent["east"] = f"{zone_number + 1}{hemisphere}"
            else:
                adjacent["east"] = f"1{hemisphere}"  # Wrap around
            
            # Northern/southern adjacent zones
            if hemisphere == "N":
                adjacent["south"] = f"{zone_number}S"
            else:
                adjacent["north"] = f"{zone_number}N"
            
            return {
                "success": True,
                "adjacent_zones": adjacent
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": f"Adjacent zones calculation error: {str(e)}"
            }
    
    def get_zone_info(self, utm_zone: str) -> dict:
        """Get comprehensive information about a UTM zone"""
        try:
            zone_number = int(utm_zone[:-1])
            hemisphere = utm_zone[-1].upper()
            
            # Get bounds
            bounds_result = self.get_zone_bounds(utm_zone)
            
            # Get adjacent zones
            adjacent_result = self.get_adjacent_zones(utm_zone)
            
            # Calculate central meridian
            central_meridian = (zone_number - 1) * 6 - 180 + 3
            
            info = {
                "zone_number": zone_number,
                "hemisphere": hemisphere,
                "central_meridian": central_meridian,
                "zone_width_degrees": 6,
                "datum": "WGS84",
                "epsg_code": self._get_epsg_code(zone_number, hemisphere)
            }
            
            if bounds_result["success"]:
                info["bounds"] = bounds_result["bounds"]
                info["center_lon"] = bounds_result["center_lon"]
                info["center_lat"] = bounds_result["center_lat"]
            
            if adjacent_result["success"]:
                info["adjacent_zones"] = adjacent_result["adjacent_zones"]
            
            return {
                "success": True,
                "zone_info": info
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": f"Zone info calculation error: {str(e)}"
            }
    
    def _get_epsg_code(self, zone_number: int, hemisphere: str) -> int:
        """Get EPSG code for UTM zone"""
        if hemisphere.upper() == "N":
            return 32600 + zone_number  # Northern hemisphere
        else:
            return 32700 + zone_number  # Southern hemisphere
    
    def is_valid_utm_zone(self, utm_zone: str) -> bool:
        """Check if UTM zone string is valid"""
        try:
            if len(utm_zone) < 2:
                return False
            
            zone_number = int(utm_zone[:-1])
            hemisphere = utm_zone[-1].upper()
            
            return (1 <= zone_number <= 60 and 
                   hemisphere in ["N", "S"])
            
        except (ValueError, IndexError):
            return False
    
    def find_zones_for_bounds(self, min_lat: float, max_lat: float, min_lon: float, max_lon: float) -> List[str]:
        """Find all UTM zones that intersect with given bounds"""
        zones = []
        
        # Calculate zone range
        min_zone = max(1, int((min_lon + 180) / 6) + 1)
        max_zone = min(60, int((max_lon + 180) / 6) + 1)
        
        # Determine hemispheres needed
        hemispheres = []
        if max_lat >= 0:
            hemispheres.append("N")
        if min_lat < 0:
            hemispheres.append("S")
        
        # Generate zone list
        for zone in range(min_zone, max_zone + 1):
            for hemisphere in hemispheres:
                zones.append(f"{zone}{hemisphere}")
        
        return zones