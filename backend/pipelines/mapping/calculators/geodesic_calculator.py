"""
Geodesic Calculator Module
Professional ellipsoidal geodesic calculations using GeographicLib
"""
import math
from typing import Dict, Any
from geographiclib.geodesic import Geodesic
import logging

logger = logging.getLogger(__name__)

class GeodesicCalculator:
    """
    Professional ellipsoidal geodesic calculations using GeographicLib/Karney's algorithm
    Most accurate method for surveying and geodetic applications
    """

    def __init__(self):
        """Initialize geodesic calculator with WGS84 ellipsoid"""
        # Use WGS84 ellipsoid (same as GPS)
        self.geod = Geodesic.WGS84

        # Cache for frequently used calculations
        self._calculation_cache: Dict[str, Dict[str, Any]] = {}

        logger.info("🧭 Geodesic Calculator initialized with WGS84 ellipsoid")

    def calculate_endpoint(
        self,
        start_lat: float,
        start_lng: float,
        bearing_degrees: float,
        distance_meters: float
    ) -> Dict[str, Any]:
        """
        Calculate endpoint using GeographicLib's ellipsoidal geodesic calculation
        Most accurate method for surveying applications

        Args:
            start_lat: Starting latitude in decimal degrees
            start_lng: Starting longitude in decimal degrees
            bearing_degrees: True bearing (azimuth) from north in degrees
            distance_meters: Distance in meters

        Returns:
            dict: Endpoint coordinates with precision metadata
        """
        try:
            logger.debug(".3f")

            # Create cache key for potential optimization
            cache_key = f"{start_lat:.6f}_{start_lng:.6f}_{bearing_degrees:.1f}_{distance_meters:.1f}"

            # Check cache (optional - can be disabled for real-time calculations)
            if cache_key in self._calculation_cache:
                logger.debug("📋 Using cached geodesic calculation")
                return self._calculation_cache[cache_key]

            # Solve the direct geodesic problem using GeographicLib
            result = self.geod.Direct(
                lat1=start_lat,
                lon1=start_lng,
                azi1=bearing_degrees,
                s12=distance_meters
            )

            # Extract results
            end_lat = result['lat2']
            end_lng = result['lon2']
            final_azimuth = result['azi2']

            logger.debug(".8f")

            # Calculate additional precision metrics
            precision_info = self._calculate_precision_metrics(
                start_lat, start_lng, bearing_degrees, distance_meters, result
            )

            result_data = {
                "success": True,
                "end_lat": end_lat,
                "end_lng": end_lng,
                "final_azimuth": final_azimuth,
                "method": "geographiclib_ellipsoidal",
                "algorithm": "karney_geodesic",
                "precision": "millimeter",
                "datum": "WGS84",
                "accuracy_note": "~1mm accuracy globally",
                "input_distance_meters": distance_meters,
                "input_bearing_degrees": bearing_degrees,
                "computation_time": "medium",
                "precision_metrics": precision_info
            }

            # Cache result for potential reuse
            self._calculation_cache[cache_key] = result_data

            return result_data

        except Exception as e:
            logger.error(f"🧭 GeographicLib calculation error: {str(e)}")
            return {
                "success": False,
                "error": f"Geodesic calculation failed: {str(e)}",
                "method": "geodesic_error"
            }

    def _calculate_precision_metrics(
        self,
        start_lat: float,
        start_lng: float,
        bearing_degrees: float,
        distance_meters: float,
        result: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Calculate additional precision and validation metrics

        Args:
            start_lat, start_lng: Starting coordinates
            bearing_degrees: Input bearing
            distance_meters: Input distance
            result: GeographicLib result dictionary

        Returns:
            dict: Precision metrics and validation data
        """
        try:
            # Calculate scale factors (how much distances are stretched/compressed)
            scale_factor = result.get('a12', 1.0)  # Arc distance scale

            # Calculate area of the geodesic quadrilateral (for precision validation)
            area = result.get('S12', 0.0)  # Area between geodesic and equator

            # Calculate convergence of meridians along the path
            convergence_change = result.get('azi2', bearing_degrees) - bearing_degrees

            # Estimate positional uncertainty based on distance
            # GeographicLib is accurate to ~1mm globally
            positional_uncertainty_m = max(0.001, distance_meters * 1e-9)  # ~1mm + 1ppb of distance

            return {
                "scale_factor": scale_factor,
                "area_m2": area,
                "azimuth_change_degrees": convergence_change,
                "positional_uncertainty_m": positional_uncertainty_m,
                "relative_precision": f"1:{int(1/positional_uncertainty_m)}" if positional_uncertainty_m > 0 else "1:∞",
                "ellipsoidal_effects": {
                    "flattening_considered": True,
                    "datum": "WGS84",
                    "semi_major_axis_m": 6378137.0,
                    "flattening": 1/298.257223563
                }
            }

        except Exception as e:
            logger.warning(f"🧭 Precision metrics calculation failed: {str(e)}")
            return {
                "scale_factor": 1.0,
                "positional_uncertainty_m": 0.001,  # Default to 1mm
                "relative_precision": "1:1000",
                "calculation_error": str(e)
            }

    def calculate_inverse(
        self,
        start_lat: float,
        start_lng: float,
        end_lat: float,
        end_lng: float
    ) -> Dict[str, Any]:
        """
        Calculate distance and bearing between two points using inverse geodesic

        Args:
            start_lat, start_lng: Starting point coordinates
            end_lat, end_lng: Ending point coordinates

        Returns:
            dict: Distance, bearing, and precision information
        """
        try:
            # Solve the inverse geodesic problem
            result = self.geod.Inverse(
                lat1=start_lat,
                lon1=start_lng,
                lat2=end_lat,
                lon2=end_lng
            )

            distance_meters = result['s12']
            bearing_degrees = result['azi1']
            final_bearing = result['azi2']

            return {
                "success": True,
                "distance_meters": distance_meters,
                "initial_bearing_degrees": bearing_degrees,
                "final_bearing_degrees": final_bearing,
                "bearing_change_degrees": final_bearing - bearing_degrees,
                "method": "geographiclib_inverse",
                "precision": "millimeter"
            }

        except Exception as e:
            logger.error(f"🧭 Inverse geodesic calculation error: {str(e)}")
            return {
                "success": False,
                "error": f"Inverse calculation failed: {str(e)}",
                "method": "inverse_error"
            }

    def validate_inputs(
        self,
        start_lat: float,
        start_lng: float,
        bearing_degrees: float,
        distance_meters: float
    ) -> Dict[str, Any]:
        """
        Validate inputs for geodesic calculations

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
        elif distance_meters > 40000000:  # Quarter of Earth's circumference
            issues.append("Distance too large (>40,000km)")

        return {
            "valid": len(issues) == 0,
            "issues": issues,
            "recommended_for_distance": distance_meters <= 20000000,  # 20,000km
            "accuracy_estimate": "~1mm globally regardless of distance",
            "algorithm": "karney_geodesic_ellipsoidal"
        }

    def clear_cache(self):
        """
        Clear geodesic calculation cache
        This only affects coordinate calculation caches, not PLSS data
        """
        try:
            cache_size = len(self._calculation_cache)
            self._calculation_cache.clear()
            logger.info(f"🧹 Cleared {cache_size} geodesic calculation cache entries")
        except Exception as e:
            logger.error(f"🧹 Geodesic cache cleanup error: {str(e)}")

    def get_ellipsoid_parameters(self) -> Dict[str, Any]:
        """
        Get WGS84 ellipsoid parameters for reference

        Returns:
            dict: Ellipsoid parameters used in calculations
        """
        return {
            "name": "WGS84",
            "semi_major_axis_m": 6378137.0,
            "semi_minor_axis_m": 6356752.314245,
            "flattening": 1/298.257223563,
            "eccentricity": 0.08181919084262149,
            "algorithm": "Karney (GeographicLib)",
            "accuracy": "Millimeter-level globally"
        }