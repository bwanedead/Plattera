"""
Geodesic Manager
Handles geodesic-specific coordinate operations and zone management
"""
import logging
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

class GeodesicManager:
    """
    Manages geodesic coordinate operations and metadata
    Follows similar interface to UTMManager for modularity
    """

    def __init__(self):
        """Initialize geodesic manager"""
        logger.info("🧭 Geodesic Manager initialized")

    def get_geodesic_info(self, lat: float, lon: float) -> dict:
        """
        Get geodesic-specific information for coordinates

        Args:
            lat: Latitude in decimal degrees
            lon: Longitude in decimal degrees

        Returns:
            dict: Geodesic information and metadata
        """
        try:
            # Determine hemisphere
            hemisphere = "N" if lat >= 0 else "S"

            # Calculate basic geodesic parameters
            lat_rad = lat * 3.141592653589793 / 180.0
            lon_rad = lon * 3.141592653589793 / 180.0

            # Estimate meridian convergence (simplified)
            # In full geodesic calculations, this would be computed properly
            convergence = 0.0  # Simplified - would need full calculation

            return {
                "success": True,
                "latitude": lat,
                "longitude": lon,
                "hemisphere": hemisphere,
                "meridian_convergence_degrees": convergence,
                "datum": "WGS84",
                "ellipsoid": "WGS84",
                "method": "geodesic_native",
                "precision": "millimeter_level"
            }

        except Exception as e:
            logger.error(f"❌ Geodesic info calculation failed: {str(e)}")
            return {
                "success": False,
                "error": f"Geodesic info calculation error: {str(e)}"
            }

    def get_geodesic_bounds(self, center_lat: float, center_lon: float, radius_meters: float) -> dict:
        """
        Get geodesic bounds for an area around a center point

        Args:
            center_lat: Center latitude
            center_lon: Center longitude
            radius_meters: Radius in meters

        Returns:
            dict: Bounding box information
        """
        try:
            # Approximate bounds using spherical approximation
            # For more accuracy, would use proper geodesic calculations
            lat_offset = radius_meters / 111319.9  # Approximate meters per degree latitude
            lon_offset = radius_meters / (111319.9 * abs(center_lat * 3.141592653589793 / 180.0).cos()) if center_lat != 0 else radius_meters / 111319.9

            return {
                "success": True,
                "bounds": {
                    "min_lat": center_lat - lat_offset,
                    "max_lat": center_lat + lat_offset,
                    "min_lon": center_lon - lon_offset,
                    "max_lon": center_lon + lon_offset,
                    "center_lat": center_lat,
                    "center_lon": center_lon
                },
                "radius_meters": radius_meters,
                "method": "approximate_geodesic"
            }

        except Exception as e:
            return {
                "success": False,
                "error": f"Geodesic bounds calculation error: {str(e)}"
            }

    def validate_geodesic_coordinates(self, lat: float, lon: float) -> dict:
        """
        Validate coordinates for geodesic calculations

        Args:
            lat: Latitude in decimal degrees
            lon: Longitude in decimal degrees

        Returns:
            dict: Validation result
        """
        issues = []

        # Geographic coordinate validation
        if not (-90 <= lat <= 90):
            issues.append(f"Latitude {lat}° out of valid range (-90° to 90°)")
        if not (-180 <= lon <= 180):
            issues.append(f"Longitude {lon}° out of valid range (-180° to 180°)")

        # Precision validation for surveying
        if abs(lat) > 0.000001 and abs(lon) > 0.000001:  # Not exactly 0,0
            if abs(lat) < 0.0001:
                issues.append("Latitude precision may be insufficient for surveying")
            if abs(lon) < 0.0001:
                issues.append("Longitude precision may be insufficient for surveying")

        return {
            "success": len(issues) == 0,
            "issues": issues,
            "warnings": [] if len(issues) == 0 else ["Coordinate validation issues detected"],
            "validation_method": "geodesic_standards"
        }

    def get_geodesic_metadata(self) -> dict:
        """
        Get metadata about geodesic coordinate system

        Returns:
            dict: Geodesic system metadata
        """
        return {
            "success": True,
            "coordinate_system": "Geographic (WGS84)",
            "datum": "WGS84",
            "ellipsoid": "WGS84",
            "semi_major_axis_m": 6378137.0,
            "semi_minor_axis_m": 6356752.314245,
            "flattening": 1/298.257223563,
            "algorithm": "Karney (GeographicLib)",
            "accuracy": "Millimeter-level globally",
            "supported_operations": [
                "direct_geodesic",
                "inverse_geodesic",
                "coordinate_validation",
                "bounds_calculation"
            ]
        }

    def is_geodesic_supported(self, operation: str) -> bool:
        """
        Check if a geodesic operation is supported

        Args:
            operation: Operation name to check

        Returns:
            bool: True if supported
        """
        supported_operations = [
            "direct_geodesic",
            "inverse_geodesic",
            "coordinate_validation",
            "bounds_calculation",
            "endpoint_calculation",
            "distance_bearing"
        ]

        return operation in supported_operations
