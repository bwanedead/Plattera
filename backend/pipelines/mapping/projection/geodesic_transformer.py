"""
Geodesic Transformer
Handles geodesic coordinate transformations with GeographicLib
"""
import logging
from typing import Dict, Any, Tuple, Optional
from geographiclib.geodesic import Geodesic

logger = logging.getLogger(__name__)

class GeodesicTransformer:
    """
    Geodesic coordinate transformer using GeographicLib for maximum accuracy
    Follows same interface as CoordinateTransformer for modularity
    """

    def __init__(self):
        """Initialize geodesic transformer with WGS84 ellipsoid"""
        # Use WGS84 ellipsoid (same as GPS)
        self.geod = Geodesic.WGS84

        # Cache for frequently used transformations
        self._transformation_cache: Dict[str, Dict[str, Any]] = {}

        logger.info("🧭 Geodesic Transformer initialized with WGS84 ellipsoid")

    def geographic_to_utm(self, lat: float, lon: float, utm_zone: str) -> dict:
        """
        Geographic to UTM transformation using geodesic methods
        Note: This is primarily for compatibility - geodesic methods work directly with geographic coords

        Args:
            lat: Latitude in decimal degrees
            lon: Longitude in decimal degrees
            utm_zone: UTM zone string (ignored for geodesic)

        Returns:
            dict: Geographic coordinates (no transformation needed for geodesic)
        """
        # For geodesic methods, we work directly with geographic coordinates
        # Return the input coordinates for compatibility
        return {
            "success": True,
            "utm_x": lon,  # Just return lon for compatibility
            "utm_y": lat,  # Just return lat for compatibility
            "utm_zone": utm_zone,
            "zone_number": 0,  # Not applicable
            "hemisphere": "N" if lat >= 0 else "S",
            "precision": "geodesic_native",
            "datum": "WGS84",
            "method": "geodesic_passthrough",
            "input_coords": f"({lat:.8f}, {lon:.8f})",
            "output_coords": f"({lon:.8f}, {lat:.8f})"
        }

    def utm_to_geographic(self, utm_x: float, utm_y: float, utm_zone: str) -> dict:
        """
        UTM to Geographic transformation (compatibility method)
        For geodesic workflows, coordinates are already geographic

        Args:
            utm_x: X coordinate (longitude for geodesic compatibility)
            utm_y: Y coordinate (latitude for geodesic compatibility)
            utm_zone: UTM zone string (ignored for geodesic)

        Returns:
            dict: Geographic coordinates
        """
        # For geodesic compatibility, treat utm_x/utm_y as lon/lat
        return {
            "success": True,
            "lat": utm_y,
            "lon": utm_x,
            "utm_zone": utm_zone,
            "zone_number": 0,
            "hemisphere": "N" if utm_y >= 0 else "S",
            "precision": "geodesic_native",
            "datum": "WGS84",
            "method": "geodesic_passthrough",
            "input_coords": f"({utm_x:.3f}, {utm_y:.3f})",
            "output_coords": f"({utm_x:.8f}, {utm_y:.8f})"
        }

    def geodesic_endpoint(self, start_lat: float, start_lng: float, bearing_degrees: float, distance_meters: float) -> dict:
        """
        Calculate endpoint using geodesic calculations
        This is the primary method for geodesic transformations

        Args:
            start_lat: Starting latitude in decimal degrees
            start_lng: Starting longitude in decimal degrees
            bearing_degrees: Bearing from north in degrees
            distance_meters: Distance in meters

        Returns:
            dict: Endpoint coordinates and metadata
        """
        try:
            cache_key = f"endpoint_{start_lat:.6f}_{start_lng:.6f}_{bearing_degrees:.1f}_{distance_meters:.1f}"

            # Check cache
            if cache_key in self._transformation_cache:
                return self._transformation_cache[cache_key]

            # Solve the direct geodesic problem
            result = self.geod.Direct(
                lat1=start_lat,
                lon1=start_lng,
                azi1=bearing_degrees,
                s12=distance_meters
            )

            endpoint_data = {
                "success": True,
                "end_lat": result['lat2'],
                "end_lng": result['lon2'],
                "final_azimuth": result['azi2'],
                "method": "geodesic_direct",
                "algorithm": "karney_geodesic",
                "precision": "millimeter",
                "datum": "WGS84",
                "distance_meters": distance_meters,
                "bearing_degrees": bearing_degrees,
                "start_coords": f"({start_lat:.8f}, {start_lng:.8f})",
                "end_coords": f"({result['lat2']:.8f}, {result['lon2']:.8f})"
            }

            # Cache result
            self._transformation_cache[cache_key] = endpoint_data

            return endpoint_data

        except Exception as e:
            logger.error(f"🧭 Geodesic endpoint calculation failed: {str(e)}")
            return {
                "success": False,
                "error": f"Geodesic calculation failed: {str(e)}",
                "method": "geodesic_error"
            }

    def geodesic_inverse(self, start_lat: float, start_lng: float, end_lat: float, end_lng: float) -> dict:
        """
        Calculate distance and bearing between two points using inverse geodesic

        Args:
            start_lat, start_lng: Starting point coordinates
            end_lat, end_lng: Ending point coordinates

        Returns:
            dict: Distance, bearing, and precision information
        """
        try:
            cache_key = f"inverse_{start_lat:.6f}_{start_lng:.6f}_{end_lat:.6f}_{end_lng:.6f}"

            # Check cache
            if cache_key in self._transformation_cache:
                return self._transformation_cache[cache_key]

            # Solve the inverse geodesic problem
            result = self.geod.Inverse(
                lat1=start_lat,
                lon1=start_lng,
                lat2=end_lat,
                lon2=end_lng
            )

            inverse_data = {
                "success": True,
                "distance_meters": result['s12'],
                "initial_bearing_degrees": result['azi1'],
                "final_bearing_degrees": result['azi2'],
                "bearing_change_degrees": result['azi2'] - result['azi1'],
                "method": "geodesic_inverse",
                "algorithm": "karney_geodesic",
                "precision": "millimeter",
                "datum": "WGS84"
            }

            # Cache result
            self._transformation_cache[cache_key] = inverse_data

            return inverse_data

        except Exception as e:
            logger.error(f"🧭 Geodesic inverse calculation failed: {str(e)}")
            return {
                "success": False,
                "error": f"Geodesic inverse calculation failed: {str(e)}",
                "method": "geodesic_inverse_error"
            }

    def transform_point(self, x: float, y: float, source_crs: str, target_crs: str) -> dict:
        """
        Transform a point between coordinate reference systems
        For geodesic, we primarily work with geographic coordinates

        Args:
            x: X coordinate
            y: Y coordinate
            source_crs: Source CRS identifier
            target_crs: Target CRS identifier

        Returns:
            dict: Transformed coordinates
        """
        try:
            # Handle geodesic-native transformations
            if source_crs == "EPSG:4326" and target_crs == "EPSG:4326":
                return {"success": True, "x": x, "y": y}

            # For compatibility with UTM-based systems
            if source_crs == "EPSG:4326" and target_crs.startswith("geodesic_"):
                return {"success": True, "x": x, "y": y, "method": "geodesic_passthrough"}

            if source_crs.startswith("geodesic_") and target_crs == "EPSG:4326":
                return {"success": True, "x": x, "y": y, "method": "geodesic_passthrough"}

            # For other transformations, return error
            return {
                "success": False,
                "error": f"Geodesic transformation from {source_crs} to {target_crs} not implemented"
            }

        except Exception as e:
            return {
                "success": False,
                "error": f"Geodesic point transformation error: {str(e)}"
            }

    def clear_cache(self):
        """
        Clear geodesic transformation cache
        This only affects geodesic calculation caches
        """
        try:
            cache_size = len(self._transformation_cache)
            self._transformation_cache.clear()
            logger.info(f"🧹 Cleared {cache_size} geodesic transformation cache entries")
        except Exception as e:
            logger.error(f"🧹 Geodesic cache cleanup error: {str(e)}")

    def get_ellipsoid_parameters(self) -> Dict[str, Any]:
        """
        Get WGS84 ellipsoid parameters used in geodesic calculations

        Returns:
            dict: Ellipsoid parameters
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
