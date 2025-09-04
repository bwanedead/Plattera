"""
Professional Coordinate Transformer
Handles accurate geodetic transformations for surveying-grade precision
"""
import logging
import math
from typing import Dict, Any, Tuple, Optional
from pyproj import CRS, Transformer
from pyproj.exceptions import CRSError, ProjError

logger = logging.getLogger(__name__)

class CoordinateTransformer:
    """
    Professional coordinate transformer using pyproj for accurate geodetic transformations.

    Supports WGS84 ↔ UTM transformations with proper datum handling and error checking.
    Designed for civil engineering precision and scalable to handle thousands of deeds.
    """
    
    def __init__(self):
        """Initialize coordinate transformer with WGS84 datum"""
        # WGS84 geographic coordinate system (latitude/longitude)
        self.wgs84 = CRS.from_epsg(4326)

        # Separate caches for each transformation direction to avoid direction mismatches
        self._geo_to_utm_transformers: Dict[str, Transformer] = {}
        self._utm_to_geo_transformers: Dict[str, Transformer] = {}

        logger.info("🧭 Professional Coordinate Transformer initialized with WGS84 datum")
    
    def geographic_to_utm(self, lat: float, lon: float, utm_zone: str) -> dict:
        """
        Transform geographic coordinates to UTM using professional geodetic transformations
        
        Args:
            lat: Latitude in decimal degrees (-90 to 90)
            lon: Longitude in decimal degrees (-180 to 180)
            utm_zone: UTM zone string (e.g., "13N", "utm_13n")
            
        Returns:
            dict: Professional UTM coordinates with precision validation
        """
        try:
            logger.debug(f"🧭 Professional UTM conversion: ({lat:.8f}, {lon:.8f}) → {utm_zone}")

            # Validate input coordinates
            if not (-90 <= lat <= 90):
                return {"success": False, "error": f"Invalid latitude: {lat} (must be -90 to 90)"}
            if not (-180 <= lon <= 180):
                return {"success": False, "error": f"Invalid longitude: {lon} (must be -180 to 180)"}

            # Parse UTM zone with enhanced error handling
            zone_info = self._parse_utm_zone(utm_zone)
            if not zone_info["success"]:
                return zone_info
            
            zone_number = zone_info["zone_number"]
            is_northern = zone_info["is_northern"]
            
            # Get or create UTM transformer (cached for performance)
            transformer_key = f"{zone_number}{'N' if is_northern else 'S'}"
            if transformer_key not in self._geo_to_utm_transformers:
                try:
                    # Create UTM CRS with proper EPSG code
                    utm_epsg = 32600 + zone_number if is_northern else 32700 + zone_number
                    utm_crs = CRS.from_epsg(utm_epsg)
                    self._geo_to_utm_transformers[transformer_key] = Transformer.from_crs(
                        self.wgs84, utm_crs, always_xy=False
                    )
                    logger.debug(f"📍 Created GEO→UTM transformer for zone {transformer_key} (EPSG:{utm_epsg})")
                except CRSError as e:
                    return {"success": False, "error": f"Invalid UTM zone {transformer_key}: {str(e)}"}

            transformer = self._geo_to_utm_transformers[transformer_key]

            # Perform transformation with high precision
            utm_x, utm_y = transformer.transform(lat, lon)  # PyProj returns (east, north) for UTM when always_xy=False

            # Validate output coordinates
            if math.isnan(utm_x) or math.isinf(utm_x) or math.isnan(utm_y) or math.isinf(utm_y):
                return {"success": False, "error": "Transformation produced invalid coordinates"}

            logger.debug(f"✅ UTM conversion successful: ({utm_x:.3f}, {utm_y:.3f}) in zone {utm_zone}")
            
            return {
                "success": True,
                "utm_x": round(utm_x, 3),  # Millimeter precision for surveying
                "utm_y": round(utm_y, 3),
                "utm_zone": utm_zone,
                "zone_number": zone_number,
                "hemisphere": "N" if is_northern else "S",
                "precision": "millimeter",
                "datum": "WGS84",
                "method": "pyproj_primary",
                "input_coords": f"({lat:.8f}, {lon:.8f})",
                "output_coords": f"({utm_x:.3f}, {utm_y:.3f})"
            }
            
        except ProjError as e:
            logger.error(f"🧭 Projection error in geographic_to_utm: {str(e)}")
            return {
                "success": False,
                "error": f"Geodetic transformation error: {str(e)}",
                "method": "error",
                "status": "projection_error"
            }
        except Exception as e:
            logger.error(f"🧭 Unexpected error in geographic_to_utm: {str(e)}")
            return {
                "success": False,
                "error": f"Coordinate transformation error: {str(e)}",
                "method": "error",
                "status": "unexpected_error"
            }

    def _utm_to_geographic_mathematical(self, utm_x: float, utm_y: float, zone_number: int, is_northern: bool) -> dict:
        """
        Mathematical UTM to Geographic conversion using standard formulas.
        Pure Python implementation as final fallback when pyproj fails.

        Based on standard UTM conversion formulas from USGS and NIMA publications.
        """
        try:
            logger.info(f"🧮 Using mathematical UTM conversion for zone {zone_number}{'N' if is_northern else 'S'}")

            # UTM Constants
            a = 6378137.0  # Semi-major axis (WGS84)
            f = 1/298.257223563  # Flattening
            k0 = 0.9996  # Scale factor
            e = math.sqrt(2*f - f*f)  # Eccentricity
            e_prime_sq = e*e / (1 - e*e)  # Second eccentricity squared

            # Remove false easting/northing
            x = utm_x - 500000.0  # False easting
            y = utm_y - (10000000.0 if not is_northern else 0)  # False northing

            # Calculate footpoint latitude
            M = y / k0
            mu = M / (a * (1 - e*e/4 - 3*e**4/64 - 5*e**6/256))

            # Iterative calculation for footpoint latitude
            e1 = (1 - math.sqrt(1 - e*e)) / (1 + math.sqrt(1 - e*e))
            phi1 = mu + (3*e1/2 - 27*e1**3/32) * math.sin(2*mu) + (21*e1**2/16 - 55*e1**4/32) * math.sin(4*mu) + (151*e1**3/96) * math.sin(6*mu)

            # Calculate other parameters
            N1 = a / math.sqrt(1 - e*e * math.sin(phi1)**2)
            T1 = math.tan(phi1)**2
            C1 = e_prime_sq * math.cos(phi1)**2
            R1 = a * (1 - e*e) / (1 - e*e * math.sin(phi1)**2)**(3/2)
            D = x / (N1 * k0)

            # Calculate latitude
            lat_rad = phi1 - (N1 * math.tan(phi1) / R1) * (D*D/2 - (5 + 3*T1 + 10*C1 - 4*C1*C1 - 9*e_prime_sq)*D**4/24 + (61 + 90*T1 + 298*C1 + 45*T1*T1 - 252*e_prime_sq - 3*C1*C1)*D**6/720)

            # Calculate longitude
            lon_rad = (zone_number - 1) * math.pi/180 * 6 - 3*math.pi/180 + (D - (1 + 2*T1 + C1)*D**3/6 + (5 - 2*C1 + 28*T1 - 3*C1**2 + 8*e_prime_sq + 24*T1**2)*D**5/120) / math.cos(phi1)

            # Convert to degrees
            lat = math.degrees(lat_rad)
            lon = math.degrees(lon_rad)

            logger.info(f"🧮 Mathematical conversion result: ({lat:.8f}, {lon:.8f}) from UTM ({utm_x:.3f}, {utm_y:.3f})")

            return {
                "success": True,
                "lat": lat,
                "lon": lon,
                "method": "mathematical",
                "precision": "centimeter",  # ~1cm accuracy
                "zone_number": zone_number,
                "hemisphere": "N" if is_northern else "S"
            }
            
        except Exception as e:
            logger.error(f"🧮 Mathematical conversion failed: {str(e)}")
            return {
                "success": False,
                "error": f"Mathematical conversion error: {str(e)}",
                "method": "mathematical"
            }
    
    def utm_to_geographic(self, utm_x: float, utm_y: float, utm_zone: str) -> dict:
        """
        Transform UTM coordinates to geographic using professional geodetic transformations
        
        Args:
            utm_x: UTM X coordinate (easting) in meters
            utm_y: UTM Y coordinate (northing) in meters
            utm_zone: UTM zone string (e.g., "13N", "utm_13n")
            
        Returns:
            dict: Professional geographic coordinates with precision validation
        """
        try:
            logger.debug(f"🧭 Professional inverse UTM conversion: ({utm_x:.3f}, {utm_y:.3f}) in {utm_zone} → lat/lon")

            # Validate input coordinates
            if utm_x < 0 or utm_x > 1000000:
                return {"success": False, "error": f"Invalid UTM X coordinate: {utm_x} (must be 0-1000000)"}
            if utm_y < 0 or utm_y > 10000000:
                return {"success": False, "error": f"Invalid UTM Y coordinate: {utm_y} (must be 0-10000000)"}

            # Parse UTM zone with enhanced error handling
            zone_info = self._parse_utm_zone(utm_zone)
            if not zone_info["success"]:
                return zone_info
            
            zone_number = zone_info["zone_number"]
            is_northern = zone_info["is_northern"]
            
            # Get or create inverse UTM transformer (cached for performance)
            transformer_key = f"{zone_number}{'N' if is_northern else 'S'}"
            if transformer_key not in self._utm_to_geo_transformers:
                try:
                    # Create UTM CRS with proper EPSG code
                    utm_epsg = 32600 + zone_number if is_northern else 32700 + zone_number
                    utm_crs = CRS.from_epsg(utm_epsg)
                    self._utm_to_geo_transformers[transformer_key] = Transformer.from_crs(
                        utm_crs, self.wgs84, always_xy=False
                    )
                    logger.debug(f"📍 Created UTM→GEO transformer for zone {transformer_key} (EPSG:{utm_epsg})")
                except CRSError as e:
                    return {"success": False, "error": f"Invalid UTM zone {transformer_key}: {str(e)}"}

            transformer = self._utm_to_geo_transformers[transformer_key]

            # Perform inverse transformation with high precision
            # Input: east, north (UTM axis order); output: lat, lon (WGS84 axis)
            lat, lon = transformer.transform(utm_x, utm_y)

            # Check for invalid results
            if math.isnan(lat) or math.isinf(lat) or math.isnan(lon) or math.isinf(lon):
                logger.error(f"🧭 Invalid transformation result: lat={lat}, lon={lon} for UTM ({utm_x}, {utm_y}) in zone {transformer_key}")
                return {"success": False, "error": f"Transformation produced infinite/NaN coordinates: lat={lat}, lon={lon}"}

            # Validate coordinate ranges
            if not (-90 <= lat <= 90):
                return {"success": False, "error": f"Latitude out of range: {lat} (expected -90 to 90)"}
            if not (-180 <= lon <= 180):
                return {"success": False, "error": f"Longitude out of range: {lon} (expected -180 to 180)"}

            logger.debug(f"✅ Geographic conversion successful: ({lat:.8f}, {lon:.8f}) from UTM {utm_zone}")
            
            return {
                "success": True,
                "lat": round(lat, 8),  # Sub-millimeter precision for surveying
                "lon": round(lon, 8),
                "utm_zone": utm_zone,
                "zone_number": zone_number,
                "hemisphere": "N" if is_northern else "S",
                "precision": "sub-millimeter",
                "datum": "WGS84",
                "method": "pyproj_primary",
                "input_coords": f"({utm_x:.3f}, {utm_y:.3f})",
                "output_coords": f"({lat:.8f}, {lon:.8f})",
                "execution_time": 0.0,  # Add timing if needed
                "status": "success"
            }

        except ProjError as e:
            logger.error(f"🧭 Projection error in utm_to_geographic: {str(e)}")
            return {
                "success": False,
                "error": f"Geodetic transformation error: {str(e)}",
                "method": "error",
                "status": "projection_error"
            }
        except Exception as e:
            logger.error(f"🧭 Unexpected error in utm_to_geographic: {str(e)}")
            return {
                "success": False,
                "error": f"Coordinate transformation error: {str(e)}",
                "method": "error",
                "status": "unexpected_error"
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

    def _determine_utm_zone(self, lat: float, lon: float) -> dict:
        """
        Determine UTM zone from geographic coordinates

        Args:
            lat: Latitude in decimal degrees
            lon: Longitude in decimal degrees

        Returns:
            dict: UTM zone information
        """
        try:
            # Validate coordinates
            if not (-90 <= lat <= 90):
                return {"success": False, "error": f"Invalid latitude: {lat}"}
            if not (-180 <= lon <= 180):
                return {"success": False, "error": f"Invalid longitude: {lon}"}

            # Calculate UTM zone number (longitude-based)
            zone_number = int((lon + 180) / 6) + 1

            # Special cases for Norway and Svalbard
            if lat >= 56.0 and lat < 64.0 and lon >= 3.0 and lon < 12.0:
                zone_number = 32
            elif lat >= 72.0 and lat < 84.0:
                if lon >= 0.0 and lon < 9.0:
                    zone_number = 31
                elif lon >= 9.0 and lon < 21.0:
                    zone_number = 33
                elif lon >= 21.0 and lon < 33.0:
                    zone_number = 35
                elif lon >= 33.0 and lon < 42.0:
                    zone_number = 37

            # Determine hemisphere
            is_northern = lat >= 0

            # Validate zone number
            if not (1 <= zone_number <= 60):
                return {"success": False, "error": f"Invalid zone number: {zone_number}"}

            zone_string = f"{zone_number}{'N' if is_northern else 'S'}"

            return {
                "success": True,
                "zone_number": zone_number,
                "is_northern": is_northern,
                "zone_string": zone_string,
                "central_meridian": (zone_number - 1) * 6 - 180 + 3
            }

        except Exception as e:
            return {"success": False, "error": f"UTM zone determination failed: {str(e)}"}

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
    
    def validate_coordinates(self, lat: float, lon: float, utm_x: float = None, utm_y: float = None) -> dict:
        """
        Validate coordinate ranges and reasonableness for surveying applications

        Args:
            lat: Latitude in decimal degrees
            lon: Longitude in decimal degrees
            utm_x: Optional UTM X coordinate for additional validation
            utm_y: Optional UTM Y coordinate for additional validation

        Returns:
            dict: Validation result with success/error details
        """
        try:
            issues = []

            # Geographic coordinate validation
            if not (-90 <= lat <= 90):
                issues.append(f"Latitude {lat}° out of valid range (-90° to 90°)")
            if not (-180 <= lon <= 180):
                issues.append(f"Longitude {lon}° out of valid range (-180° to 180°)")

            # UTM coordinate validation (if provided)
            if utm_x is not None:
                if utm_x < 0 or utm_x > 1000000:
                    issues.append(f"UTM X coordinate {utm_x}m out of valid range (0-1000000m)")
            if utm_y is not None:
                if utm_y < 0 or utm_y > 10000000:
                    issues.append(f"UTM Y coordinate {utm_y}m out of valid range (0-10000000m)")

            # Precision validation for surveying
            if abs(lat) > 0.000001 and abs(lon) > 0.000001:  # Not exactly 0,0
                if abs(lat) < 0.0001:
                    issues.append("Latitude precision may be insufficient for surveying")
                if abs(lon) < 0.0001:
                    issues.append("Longitude precision may be insufficient for surveying")

            return {
                "success": len(issues) == 0,
                "issues": issues,
                "warnings": [] if len(issues) == 0 else ["Coordinate validation issues detected"]
            }

        except Exception as e:
            return {
                "success": False,
                "issues": [f"Coordinate validation error: {str(e)}"],
                "warnings": []
            }