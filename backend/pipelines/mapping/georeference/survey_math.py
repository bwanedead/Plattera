"""
Professional Surveying Mathematics
Civil engineering-grade coordinate calculations with error propagation and validation
"""
import math
from typing import Dict, Any, List, Tuple, Optional
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)

# Import geodesic calculator for accurate coordinate calculations
from pipelines.mapping.calculators.geodesic_calculator import GeodesicCalculator

@dataclass
class TraverseLeg:
    """Represents a single traverse leg with bearing and distance"""
    bearing_degrees: float
    distance_feet: float
    distance_meters: float
    leg_number: int
    description: str = ""

@dataclass
class CoordinatePoint:
    """Represents a coordinate point in geographic coordinates with geodesic accuracy"""
    latitude: float
    longitude: float
    utm_x: float = 0.0  # Optional UTM coordinates for compatibility
    utm_y: float = 0.0
    zone_number: int = 0
    hemisphere: str = "N"
    point_id: str = ""
    description: str = ""

class SurveyingMathematics:
    """
    Professional surveying mathematics for civil engineering applications.

    Implements:
    - Traverse coordinate calculations
    - Bearing corrections for different tie directions
    - Error propagation analysis
    - Traverse closure validation
    - Coordinate precision analysis
    """

    # Surveying constants
    FEET_TO_METERS = 0.3048
    METERS_TO_FEET = 3.28084
    ARC_SECONDS_PER_DEGREE = 3600.0

    def __init__(self):
        """Initialize surveying mathematics engine with geodesic calculator"""
        self.geodesic_calc = GeodesicCalculator()
        logger.info("🧮 Professional Surveying Mathematics initialized with geodesic accuracy")

    def calculate_traverse_coordinates(
        self,
        start_point: CoordinatePoint,
        traverse_legs: List[TraverseLeg],
        tie_direction: str = "pob_bears_from_corner"
    ) -> Dict[str, Any]:
        """
        Calculate coordinates for all points in a traverse using professional surveying methods

        Args:
            start_point: Starting coordinate point
            traverse_legs: List of traverse legs with bearing and distance
            tie_direction: Direction of bearing ("pob_bears_from_corner" or "corner_bears_from_pob")

        Returns:
            dict: Complete traverse calculation results with error analysis
        """
        try:
            logger.info(f"🧮 Calculating traverse with {len(traverse_legs)} legs from {start_point.point_id}")

            calculated_points = [start_point]
            current_point = start_point

            for leg in traverse_legs:
                # Apply bearing corrections for different tie directions
                corrected_bearing = self._apply_bearing_corrections(
                    leg.bearing_degrees,
                    tie_direction
                )

                # Calculate next point coordinates
                next_point = self._calculate_next_point(
                    current_point,
                    corrected_bearing,
                    leg.distance_meters,
                    leg.leg_number
                )

                calculated_points.append(next_point)
                current_point = next_point

                logger.debug(f"📍 Point {leg.leg_number}: ({next_point.utm_x:.3f}, {next_point.utm_y:.3f})")

            # Validate traverse closure
            closure_analysis = self._analyze_traverse_closure(calculated_points)

            # Calculate error propagation
            error_analysis = self._calculate_error_propagation(traverse_legs)

            return {
                "success": True,
                "points": calculated_points,
                "closure_analysis": closure_analysis,
                "error_analysis": error_analysis,
                "total_distance_meters": sum(leg.distance_meters for leg in traverse_legs),
                "total_distance_feet": sum(leg.distance_feet for leg in traverse_legs),
                "tie_direction": tie_direction
            }

        except Exception as e:
            logger.error(f"🧮 Traverse calculation error: {str(e)}")
            return {
                "success": False,
                "error": f"Traverse calculation failed: {str(e)}"
            }

    def _apply_bearing_corrections(self, bearing_degrees: float, tie_direction: str) -> float:
        """
        Apply bearing corrections based on tie direction

        For "corner_bears_from_pob": bearing is from corner to POB, so we need to add 180°
        to compute the bearing from POB to corner for traverse calculations.
        """
        if tie_direction.lower() == "corner_bears_from_pob":
            corrected = (bearing_degrees + 180.0) % 360.0
            logger.debug(f"🧭 Bearing correction: {bearing_degrees:.1f}° → {corrected:.1f}° ({tie_direction})")
            return corrected
        else:
            # pob_bears_from_corner - bearing is already from POB to corner
            return bearing_degrees

    def _calculate_next_point(
        self,
        current_point: CoordinatePoint,
        bearing_degrees: float,
        distance_meters: float,
        leg_number: int
    ) -> CoordinatePoint:
        """
        Calculate the next point coordinates using geodesic calculations for maximum accuracy
        """
        logger.debug(f"🧮 Geodesic point calculation: Bearing {bearing_degrees:.1f}°, Distance {distance_meters:.3f}m")
        logger.debug(f"🧮 From point: ({current_point.latitude:.8f}, {current_point.longitude:.8f})")

        # Use geodesic calculation for accurate coordinate projection
        result = self.geodesic_calc.calculate_endpoint(
            current_point.latitude,
            current_point.longitude,
            bearing_degrees,
            distance_meters
        )

        if not result["success"]:
            logger.error(f"🧮 Geodesic calculation failed for point {leg_number}: {result.get('error')}")
            # Return current point as fallback
            return CoordinatePoint(
                latitude=current_point.latitude,
                longitude=current_point.longitude,
                point_id=f"Point_{leg_number}_error",
                description=f"Traverse point {leg_number} - calculation failed"
            )

        new_lat = result["end_lat"]
        new_lng = result["end_lng"]

        logger.debug(f"🧮 Geodesic result: ({new_lat:.8f}, {new_lng:.8f})")

        # For compatibility, we'll also calculate approximate UTM coordinates
        # This is mainly for backward compatibility with existing code
        try:
            # Rough approximation for UTM coordinates (not as accurate as geodesic)
            # These will be used for compatibility but the primary coordinates are geographic
            lat_rad = math.radians(new_lat)
            lng_rad = math.radians(new_lng)

            # Approximate UTM zone calculation
            zone_number = int((new_lng + 180) / 6) + 1
            if new_lat < 0:
                hemisphere = "S"
            else:
                hemisphere = "N"

            # Very rough UTM approximation (not accurate for surveying)
            # In production, you'd want to use proper UTM transformation
            central_meridian = (zone_number - 1) * 6 - 180 + 3  # Central meridian of zone
            delta_lng = lng_rad - math.radians(central_meridian)

            # Simplified UTM formulas (not accurate for high-precision work)
            a = 6378137.0  # WGS84 semi-major axis
            k0 = 0.9996    # UTM scale factor
            e_squared = 0.00669438  # eccentricity squared

            N = a / math.sqrt(1 - e_squared * math.sin(lat_rad)**2)
            T = math.tan(lat_rad)**2
            C = e_squared * math.cos(lat_rad)**2 / (1 - e_squared)
            A = delta_lng * math.cos(lat_rad)

            # Easting (very approximate)
            easting = 500000 + k0 * N * (A + (1 - T + C) * A**3 / 6)

            # Northing (very approximate)
            M = a * ((1 - e_squared/4 - 3*e_squared**2/64 - 5*e_squared**3/256) * lat_rad
                    - (3*e_squared/8 + 3*e_squared**2/32 + 45*e_squared**3/1024) * math.sin(2*lat_rad)
                    + (15*e_squared**2/256 + 45*e_squared**3/1024) * math.sin(4*lat_rad)
                    - (35*e_squared**3/3072) * math.sin(6*lat_rad))

            if hemisphere == "S":
                northing = 10000000 + k0 * M
            else:
                northing = k0 * M

            utm_x = round(easting, 3)
            utm_y = round(northing, 3)

        except Exception as e:
            logger.warning(f"🧮 UTM approximation failed: {str(e)}")
            utm_x = 0.0
            utm_y = 0.0
            zone_number = 13  # Default for Wyoming
            hemisphere = "N"

        return CoordinatePoint(
            latitude=round(new_lat, 8),      # High precision for geographic coordinates
            longitude=round(new_lng, 8),
            utm_x=utm_x,                     # Approximate UTM for compatibility
            utm_y=utm_y,
            zone_number=zone_number,
            hemisphere=hemisphere,
            point_id=f"Point_{leg_number}",
            description=f"Traverse point {leg_number} - geodesic calculation"
        )

    def _analyze_traverse_closure(self, points: List[CoordinatePoint]) -> Dict[str, Any]:
        """
        Analyze traverse closure and calculate misclosure using geodesic distances
        """
        if len(points) < 3:
            return {"closure_ratio": 0.0, "acceptable": True, "notes": "Insufficient points for closure analysis"}

        # Calculate geodesic distance from start to end point
        start_point = points[0]
        end_point = points[-1]

        closure_result = self.geodesic_calc.calculate_inverse(
            start_point.latitude,
            start_point.longitude,
            end_point.latitude,
            end_point.longitude
        )

        if not closure_result["success"]:
            logger.warning("🧮 Could not calculate closure distance using geodesic method")
            closure_distance = 0.0
        else:
            closure_distance = closure_result["distance_meters"]

        # Calculate total traverse distance using geodesic calculations
        total_distance = 0.0
        for i in range(len(points) - 1):
            leg_result = self.geodesic_calc.calculate_inverse(
                points[i].latitude,
                points[i].longitude,
                points[i + 1].latitude,
                points[i + 1].longitude
            )
            if leg_result["success"]:
                total_distance += leg_result["distance_meters"]
            else:
                logger.warning(f"🧮 Could not calculate distance for leg {i+1}")

        # Calculate closure ratio
        closure_ratio = closure_distance / total_distance if total_distance > 0 else 0.0

        # Professional surveying standards: closure should be < 1:10,000
        acceptable = closure_ratio < 0.0001

        return {
            "closure_distance_meters": round(closure_distance, 3),
            "total_traverse_distance_meters": round(total_distance, 3),
            "closure_ratio": round(closure_ratio, 8),
            "closure_ratio_string": f"1:{round(1/closure_ratio) if closure_ratio > 0 else '∞':,}",
            "acceptable": acceptable,
            "standard": "< 1:10,000",
            "method": "geodesic_distance_calculation",
            "notes": "Excellent closure" if acceptable else f"Closure exceeds 1:10,000 standard"
        }

    def _calculate_error_propagation(self, traverse_legs: List[TraverseLeg]) -> Dict[str, Any]:
        """
        Calculate error propagation through the traverse
        """
        # Simplified error propagation - in production would use full covariance analysis
        distance_errors = []
        bearing_errors = []

        for leg in traverse_legs:
            # Estimate distance measurement error (typical EDM precision: ±1mm + 1ppm)
            distance_error_mm = 1.0 + (leg.distance_meters * 1000 * 0.000001)
            distance_errors.append(distance_error_mm)

            # Estimate bearing measurement error (typical total station: ±1")
            bearing_error_arcsec = 1.0
            bearing_errors.append(bearing_error_arcsec)

        total_distance_error = math.sqrt(sum(err ** 2 for err in distance_errors))
        total_bearing_error = math.sqrt(sum(err ** 2 for err in bearing_errors))

        return {
            "total_distance_error_mm": round(total_distance_error, 2),
            "total_bearing_error_arcsec": round(total_bearing_error, 2),
            "distance_precision_ratio": round(total_distance_error / sum(leg.distance_meters * 1000 for leg in traverse_legs), 8),
            "recommended_closure_tolerance": "1:10,000",
            "notes": "Error propagation calculated using simplified model"
        }

    def validate_bearing_accuracy(self, bearing_degrees: float, tolerance_arcsec: float = 15.0) -> Dict[str, Any]:
        """
        Validate bearing angle for surveying precision

        Args:
            bearing_degrees: Bearing angle in decimal degrees
            tolerance_arcsec: Acceptable tolerance in arc seconds

        Returns:
            dict: Validation results
        """
        issues = []

        # Check bearing range
        if not (0 <= bearing_degrees < 360):
            issues.append(f"Bearing {bearing_degrees}° out of valid range (0°-360°)")

        # Check for suspicious precision (bearings shouldn't be specified to unreasonable precision)
        decimal_places = len(str(bearing_degrees).split('.')[-1]) if '.' in str(bearing_degrees) else 0
        if decimal_places > 4:  # More than 4 decimal places is suspicious
            issues.append(f"Bearing precision ({decimal_places} decimal places) exceeds typical surveying accuracy")

        # Check for cardinal directions that should be exact
        cardinal_directions = [0.0, 90.0, 180.0, 270.0]
        for cardinal in cardinal_directions:
            if abs(bearing_degrees - cardinal) < 0.0001 and str(bearing_degrees) != str(cardinal):
                issues.append(f"Bearing {bearing_degrees}° should be exactly {cardinal}° for cardinal direction")

        return {
            "success": len(issues) == 0,
            "issues": issues,
            "tolerance_arcsec": tolerance_arcsec,
            "precision_check": "passed" if len(issues) == 0 else "failed"
        }

    def convert_distance_units(self, distance: float, from_unit: str, to_unit: str) -> float:
        """
        Convert distance between different units with high precision
        """
        # Convert to meters first
        if from_unit.lower() in ['feet', 'foot', 'ft']:
            meters = distance * self.FEET_TO_METERS
        elif from_unit.lower() in ['meters', 'meter', 'm']:
            meters = distance
        elif from_unit.lower() in ['chains']:
            meters = distance * 20.1168  # 1 chain = 20.1168 meters
        elif from_unit.lower() in ['rods', 'rod']:
            meters = distance * 5.0292  # 1 rod = 5.0292 meters
        elif from_unit.lower() in ['yards', 'yard', 'yd']:
            meters = distance * 0.9144  # 1 yard = 0.9144 meters
        elif from_unit.lower() in ['links']:
            meters = distance * 0.201168  # 1 link = 0.201168 meters
        else:
            raise ValueError(f"Unsupported distance unit: {from_unit}")

        # Convert from meters to target unit
        if to_unit.lower() in ['feet', 'foot', 'ft']:
            return meters * self.METERS_TO_FEET
        elif to_unit.lower() in ['meters', 'meter', 'm']:
            return meters
        elif to_unit.lower() in ['chains']:
            return meters / 20.1168
        elif to_unit.lower() in ['rods', 'rod']:
            return meters / 5.0292
        elif to_unit.lower() in ['yards', 'yard', 'yd']:
            return meters / 0.9144
        elif to_unit.lower() in ['links']:
            return meters / 0.201168
        else:
            raise ValueError(f"Unsupported distance unit: {to_unit}")

    def calculate_bearing_from_coordinates(
        self,
        point1: CoordinatePoint,
        point2: CoordinatePoint
    ) -> float:
        """
        Calculate bearing from point1 to point2 in degrees clockwise from north
        """
        delta_x = point2.utm_x - point1.utm_x
        delta_y = point2.utm_y - point1.utm_y

        # Calculate angle in radians
        angle_radians = math.atan2(delta_x, delta_y)

        # Convert to degrees and normalize to 0-360 range
        angle_degrees = math.degrees(angle_radians)
        bearing = (angle_degrees + 360) % 360

        return round(bearing, 4)  # 0.0001° precision (about 0.1mm at 100m distance)
