"""
Haversine Calculator Module
Quick spherical coordinate calculations for measurement tools
"""
import math
from typing import Dict, Any, Tuple
import logging

logger = logging.getLogger(__name__)

class HaversineCalculator:
    """
    Fast spherical coordinate calculations using Haversine formula
    Best for quick measurements and rough estimates
    """

    # Earth's radius in miles (for compatibility with existing code)
    EARTH_RADIUS_MILES = 3959.0
    EARTH_RADIUS_METERS = 6371000.0  # Average radius for meters

    @staticmethod
    def calculate_endpoint(
        start_lat: float,
        start_lng: float,
        bearing_degrees: float,
        distance_meters: float
    ) -> Dict[str, Any]:
        """
        Calculate endpoint using Haversine formula
        Fast but less accurate for surveying applications

        Args:
            start_lat: Starting latitude in decimal degrees
            start_lng: Starting longitude in decimal degrees
            bearing_degrees: Bearing from north in degrees
            distance_meters: Distance in meters

        Returns:
            dict: Endpoint coordinates and metadata
        """
        try:
            logger.debug(".3f")

            # Convert distance to radians using Earth's radius in meters
            d = distance_meters / HaversineCalculator.EARTH_RADIUS_METERS

            # Convert bearing to radians
            bearing_rad = math.radians(bearing_degrees)

            # Convert start coordinates to radians
            lat1 = math.radians(start_lat)
            lon1 = math.radians(start_lng)

            # Haversine formula for endpoint calculation
            lat2 = math.asin(
                math.sin(lat1) * math.cos(d) +
                math.cos(lat1) * math.sin(d) * math.cos(bearing_rad)
            )

            lon2 = lon1 + math.atan2(
                math.sin(bearing_rad) * math.sin(d) * math.cos(lat1),
                math.cos(d) - math.sin(lat1) * math.sin(lat2)
            )

            # Convert back to degrees
            end_lat = math.degrees(lat2)
            end_lng = math.degrees(lon2)

            logger.debug(".8f")

            return {
                "success": True,
                "end_lat": end_lat,
                "end_lng": end_lng,
                "method": "haversine_spherical",
                "precision": "rough_estimate",
                "accuracy_note": "~100-500m accuracy depending on distance",
                "computation_time": "fast",
                "input_distance_meters": distance_meters,
                "input_bearing_degrees": bearing_degrees
            }

        except Exception as e:
            logger.error(f"🚨 Haversine calculation error: {str(e)}")
            return {
                "success": False,
                "error": f"Haversine calculation failed: {str(e)}",
                "method": "haversine_error"
            }

    @staticmethod
    def calculate_distance(
        lat1: float,
        lng1: float,
        lat2: float,
        lng2: float,
        units: str = "meters"
    ) -> float:
        """
        Calculate distance between two points using Haversine formula

        Args:
            lat1, lng1: First point coordinates
            lat2, lng2: Second point coordinates
            units: "meters", "feet", "miles", or "kilometers"

        Returns:
            float: Distance in specified units
        """
        try:
            # Convert to radians
            lat1_rad, lng1_rad = math.radians(lat1), math.radians(lng1)
            lat2_rad, lng2_rad = math.radians(lat2), math.radians(lng2)

            # Haversine formula
            dlat = lat2_rad - lat1_rad
            dlng = lng2_rad - lng1_rad

            a = math.sin(dlat/2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlng/2)**2
            c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

            # Distance in meters
            distance_meters = HaversineCalculator.EARTH_RADIUS_METERS * c

            # Convert to requested units
            if units == "feet":
                return distance_meters * 3.28084
            elif units == "miles":
                return distance_meters * 0.000621371
            elif units == "kilometers":
                return distance_meters / 1000
            else:  # meters
                return distance_meters

        except Exception as e:
            logger.error(f"🚨 Haversine distance calculation error: {str(e)}")
            return 0.0

    @staticmethod
    def calculate_bearing(
        lat1: float,
        lng1: float,
        lat2: float,
        lng2: float
    ) -> float:
        """
        Calculate bearing from point 1 to point 2

        Args:
            lat1, lng1: Starting point coordinates
            lat2, lng2: Ending point coordinates

        Returns:
            float: Bearing in degrees (0-360, clockwise from north)
        """
        try:
            # Convert to radians
            lat1_rad, lng1_rad = math.radians(lat1), math.radians(lng1)
            lat2_rad, lng2_rad = math.radians(lat2), math.radians(lng2)

            # Calculate bearing
            dlng = lng2_rad - lng1_rad

            y = math.sin(dlng) * math.cos(lat2_rad)
            x = math.cos(lat1_rad) * math.sin(lat2_rad) - math.sin(lat1_rad) * math.cos(lat2_rad) * math.cos(dlng)

            bearing_rad = math.atan2(y, x)
            bearing_deg = math.degrees(bearing_rad)

            # Normalize to 0-360
            return (bearing_deg + 360) % 360

        except Exception as e:
            logger.error(f"🚨 Haversine bearing calculation error: {str(e)}")
            return 0.0

    @staticmethod
    def validate_inputs(
        start_lat: float,
        start_lng: float,
        bearing_degrees: float,
        distance_meters: float
    ) -> Dict[str, Any]:
        """
        Validate inputs for Haversine calculations

        Returns:
            dict: Validation results with success/error details
        """
        issues = []

        # Coordinate validation
        if not (-90 <= start_lat <= 90):
            issues.append(f"Invalid latitude: {start_lat} (must be -90 to 90)")
        if not (-180 <= start_lng <= 180):
            issues.append(f"Invalid longitude: {start_lng} (must be -180 to 180)")

        # Bearing validation
        if not (0 <= bearing_degrees < 360):
            issues.append(f"Invalid bearing: {bearing_degrees} (must be 0-360)")

        # Distance validation
        if distance_meters <= 0:
            issues.append(f"Invalid distance: {distance_meters} (must be positive)")
        elif distance_meters > 100000:  # 100km limit for Haversine accuracy
            issues.append("Distance too large for Haversine accuracy (>100km)")

        return {
            "valid": len(issues) == 0,
            "issues": issues,
            "recommended_for_distance": distance_meters <= 50000,  # 50km
            "accuracy_estimate": "~50-200m for distances under 50km"
        }