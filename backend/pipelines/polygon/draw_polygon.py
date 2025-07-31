"""
Polygon Drawing Engine
Core geometric operations for converting metes and bounds to polygon coordinates
"""
import math
import logging
from typing import List, Tuple, Dict, Any, Optional
import re

logger = logging.getLogger(__name__)

class DrawingError(Exception):
    """Custom exception for polygon drawing errors"""
    pass

class PolygonDrawer:
    """
    Core engine for converting metes and bounds descriptions into polygon coordinates
    """
    
    def __init__(self):
        self.bearing_parser = BearingParser()
        self.coordinate_calculator = CoordinateCalculator()
    
    def draw_polygon(self, origin: dict, boundary_courses: List[dict], options: dict) -> dict:
        """
        Generate polygon coordinates from metes and bounds data
        
        Args:
            origin: Starting point information
            boundary_courses: List of course dictionaries with bearing/distance
            options: Processing options
            
        Returns:
            dict: Result with coordinates and metadata
        """
        try:
            if not boundary_courses:
                raise DrawingError("No boundary courses provided")
            
            # Start at origin
            current_point = self._get_origin_coordinates(origin)
            coordinates = [current_point]
            
            # Process each course
            processing_notes = []
            total_distance = 0.0
            
            for i, course in enumerate(boundary_courses):
                try:
                    # Parse bearing
                    bearing_result = self.bearing_parser.parse_bearing(course.get("course", ""))
                    if not bearing_result["success"]:
                        processing_notes.append(f"Course {i+1}: {bearing_result['error']}")
                        continue
                    
                    # Get distance
                    distance = course.get("distance")
                    distance_units = course.get("distance_units", "feet")
                    
                    if distance is None:
                        processing_notes.append(f"Course {i+1}: No distance specified")
                        continue
                    
                    # Convert distance to standard units (feet)
                    distance_feet = self._convert_to_feet(distance, distance_units)
                    total_distance += distance_feet
                    
                    # Calculate next point
                    next_point = self.coordinate_calculator.calculate_next_point(
                        current_point,
                        bearing_result["bearing_degrees"],
                        distance_feet
                    )
                    
                    coordinates.append(next_point)
                    current_point = next_point
                    
                except Exception as e:
                    processing_notes.append(f"Course {i+1} error: {str(e)}")
                    continue
            
            # Ensure we have at least 3 points to form a polygon
            if len(coordinates) < 3:
                raise DrawingError(f"Insufficient valid courses for polygon: {len(coordinates)-1} courses processed")
            
            # Add closure leg to complete the polygon
            start_point = coordinates[0]
            end_point = coordinates[-1]
            
            # Calculate closure distance
            closure_distance = math.sqrt(
                (end_point[0] - start_point[0])**2 + 
                (end_point[1] - start_point[1])**2
            )
            
            # Add closure information to notes
            if closure_distance > 0.1:  # If there's any meaningful gap
                closure_bearing = self.coordinate_calculator.calculate_bearing_between_points(
                    end_point, start_point
                )
                processing_notes.append(
                    f"Closure leg: {closure_bearing:.1f}° bearing, {closure_distance:.1f} feet"
                )
                total_distance += closure_distance
            
            # Ensure polygon is closed by adding start point at the end
            coordinates.append(start_point)
            
            # Calculate polygon properties
            area_sqft = self._calculate_area(coordinates)
            perimeter_feet = self._calculate_perimeter(coordinates)
            closure_error_feet = closure_distance  # This is now the actual closure error
            
            return {
                "success": True,
                "coordinates": coordinates,
                "area_calculated": area_sqft,
                "perimeter": perimeter_feet,
                "closure_error": closure_error_feet,
                "notes": processing_notes
            }
            
        except DrawingError as e:
            return {
                "success": False,
                "error": str(e)
            }
        except Exception as e:
            logger.error(f"Unexpected error in polygon drawing: {str(e)}")
            return {
                "success": False,
                "error": f"Drawing failed: {str(e)}"
            }
    
    def _get_origin_coordinates(self, origin: dict) -> Tuple[float, float]:
        """Extract starting coordinates from origin dict"""
        origin_type = origin.get("type", "local")
        
        if origin_type == "geographic":
            # For now, just use lat/lon as x/y (would need proper projection in production)
            return (origin.get("lon", 0.0), origin.get("lat", 0.0))
        elif origin_type in ["local", "plss_offset"]:
            return (origin.get("x", 0.0), origin.get("y", 0.0))
        else:
            logger.warning(f"Unknown origin type: {origin_type}, using (0,0)")
            return (0.0, 0.0)
    
    def _convert_to_feet(self, value: float, units: str) -> float:
        """Convert distance value to feet"""
        units_lower = units.lower()
        
        conversion_factors = {
            "feet": 1.0,
            "foot": 1.0,
            "ft": 1.0,
            "chains": 66.0,
            "chain": 66.0,
            "rods": 16.5,
            "rod": 16.5,
            "meters": 3.28084,
            "meter": 3.28084,
            "m": 3.28084,
            "yards": 3.0,
            "yard": 3.0,
            "yd": 3.0
        }
        
        factor = conversion_factors.get(units_lower, 1.0)
        if factor == 1.0 and units_lower not in conversion_factors:
            logger.warning(f"Unknown distance unit '{units}', assuming feet")
        
        return value * factor
    
    def _calculate_area(self, coordinates: List[Tuple[float, float]]) -> float:
        """Calculate polygon area using shoelace formula (returns square feet)"""
        if len(coordinates) < 3:
            return 0.0
        
        area = 0.0
        n = len(coordinates)
        
        for i in range(n):
            j = (i + 1) % n
            area += coordinates[i][0] * coordinates[j][1]
            area -= coordinates[j][0] * coordinates[i][1]
        
        return abs(area) / 2.0
    
    def _calculate_perimeter(self, coordinates: List[Tuple[float, float]]) -> float:
        """Calculate polygon perimeter in feet"""
        if len(coordinates) < 2:
            return 0.0
        
        perimeter = 0.0
        for i in range(len(coordinates)):
            j = (i + 1) % len(coordinates)
            distance = math.sqrt(
                (coordinates[j][0] - coordinates[i][0])**2 +
                (coordinates[j][1] - coordinates[i][1])**2
            )
            perimeter += distance
        
        return perimeter
    
    def _calculate_closure_error(self, coordinates: List[Tuple[float, float]]) -> float:
        """Calculate closure error (distance between first and last point)"""
        if len(coordinates) < 2:
            return 0.0
        
        start = coordinates[0]
        end = coordinates[-1]
        
        return math.sqrt(
            (end[0] - start[0])**2 +
            (end[1] - start[1])**2
        )

class BearingParser:
    """Parser for converting surveyor bearings to mathematical angles"""
    
    def parse_bearing(self, bearing_text: str) -> dict:
        """
        Parse surveyor bearing text into degrees
        
        Args:
            bearing_text: Text like "N. 68°30'E." or "S. 87°35'W."
            
        Returns:
            dict: Result with success flag and bearing in degrees from north
        """
        try:
            if not bearing_text or not bearing_text.strip():
                return {
                    "success": False,
                    "error": "Empty bearing text"
                }
            
            bearing = bearing_text.strip()
            
            # Try full format with minutes: "N. 68°30'E."
            pattern1 = r'([NS])\.\s*(\d+)°(\d+)\'([EW])\.'
            match = re.match(pattern1, bearing, re.IGNORECASE)
            
            if match:
                ns, degrees, minutes, ew = match.groups()
                degrees = int(degrees)
                minutes = int(minutes)
            else:
                # Try format without minutes: "N. 68°E."
                pattern2 = r'([NS])\.\s*(\d+)°([EW])\.'
                match = re.match(pattern2, bearing, re.IGNORECASE)
                
                if match:
                    ns, degrees, ew = match.groups()
                    degrees = int(degrees)
                    minutes = 0
                else:
                    # Try simple format: "N68E" or "N68°E"
                    pattern3 = r'([NS])(\d+)°?([EW])'
                    match = re.match(pattern3, bearing, re.IGNORECASE)
                    
                    if match:
                        ns, degrees, ew = match.groups()
                        degrees = int(degrees)
                        minutes = 0
                    else:
                        return {
                            "success": False,
                            "error": f"Could not parse bearing format: '{bearing}'"
                        }
            
            # Convert to decimal degrees
            decimal_degrees = degrees + minutes / 60.0
            
            # Validate range
            if decimal_degrees > 90:
                return {
                    "success": False,
                    "error": f"Bearing angle too large: {decimal_degrees}° (max 90°)"
                }
            
            # Convert to azimuth (degrees clockwise from north)
            ns = ns.upper()
            ew = ew.upper()
            
            if ns == 'N' and ew == 'E':
                azimuth = decimal_degrees
            elif ns == 'S' and ew == 'E':
                azimuth = 180 - decimal_degrees
            elif ns == 'S' and ew == 'W':
                azimuth = 180 + decimal_degrees
            elif ns == 'N' and ew == 'W':
                azimuth = 360 - decimal_degrees
            else:
                return {
                    "success": False,
                    "error": f"Invalid bearing direction: {ns}{ew}"
                }
            
            return {
                "success": True,
                "bearing_degrees": azimuth,
                "original_text": bearing_text,
                "parsed_components": {
                    "direction": f"{ns}{ew}",
                    "degrees": degrees,
                    "minutes": minutes,
                    "decimal_degrees": decimal_degrees
                }
            }
            
        except ValueError as e:
            return {
                "success": False,
                "error": f"Invalid numeric values in bearing: {str(e)}"
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Bearing parsing error: {str(e)}"
            }

class CoordinateCalculator:
    """Calculator for coordinate geometry operations"""
    
    def calculate_next_point(self, current_point: Tuple[float, float], 
                           bearing_degrees: float, distance_feet: float) -> Tuple[float, float]:
        """
        Calculate next point from current point using bearing and distance
        
        Args:
            current_point: (x, y) coordinates of current point
            bearing_degrees: Bearing in degrees clockwise from north
            distance_feet: Distance in feet
            
        Returns:
            Tuple[float, float]: New (x, y) coordinates
        """
        x, y = current_point
        
        # Convert bearing to radians
        bearing_radians = math.radians(bearing_degrees)
        
        # Calculate offsets (surveying convention: north is positive Y, east is positive X)
        dx = distance_feet * math.sin(bearing_radians)
        dy = distance_feet * math.cos(bearing_radians)
        
        return (x + dx, y + dy)
    
    def calculate_bearing_between_points(self, point1: Tuple[float, float], 
                                       point2: Tuple[float, float]) -> float:
        """Calculate bearing between two points in degrees from north"""
        x1, y1 = point1
        x2, y2 = point2
        
        dx = x2 - x1
        dy = y2 - y1
        
        # Calculate angle in radians
        angle_radians = math.atan2(dx, dy)
        
        # Convert to degrees and normalize to 0-360
        angle_degrees = math.degrees(angle_radians)
        if angle_degrees < 0:
            angle_degrees += 360
        
        return angle_degrees
    
    def calculate_distance_between_points(self, point1: Tuple[float, float], 
                                        point2: Tuple[float, float]) -> float:
        """Calculate distance between two points in feet"""
        x1, y1 = point1
        x2, y2 = point2
        
        return math.sqrt((x2 - x1)**2 + (y2 - y1)**2)
