"""
Polygon Drawing Pipeline
Converts structured parcel data into drawable polygon coordinates
"""
import logging
import math
from typing import Dict, Any, List, Optional, Tuple
from pathlib import Path
import json

from .draw_polygon import PolygonDrawer, DrawingError

logger = logging.getLogger(__name__)

class PolygonPipeline:
    """
    Pipeline for converting structured parcel data into polygon coordinates
    """
    
    def __init__(self):
        self.drawer = PolygonDrawer()
        self.schema_version = "parcel_v0.2"
    
    def process(self, parcel_data: dict, options: Optional[Dict[str, Any]] = None) -> dict:
        """
        Process structured parcel data to generate polygon coordinates
        
        Args:
            parcel_data: Structured parcel data from text-to-schema pipeline
            options: Processing options (coordinate_system, units, etc.)
            
        Returns:
            dict: Processing result with polygon coordinates and metadata
        """
        try:
            # Validate input
            validation_result = self._validate_input(parcel_data)
            if not validation_result["valid"]:
                return {
                    "success": False,
                    "error": f"Input validation failed: {validation_result['errors']}"
                }
            
            # Set processing options
            processing_options = self._get_processing_options(options)
            
            # Process each complete description
            polygons = []
            processing_metadata = []
            
            for desc in parcel_data.get("descriptions", []):
                if not desc.get("is_complete", False):
                    logger.info(f"Skipping incomplete description {desc.get('description_id')}")
                    continue
                
                try:
                    polygon_result = self._process_single_description(desc, processing_options)
                    if polygon_result["success"]:
                        polygons.append(polygon_result["polygon"])
                        processing_metadata.append(polygon_result["metadata"])
                    else:
                        logger.warning(f"Failed to process description {desc.get('description_id')}: {polygon_result.get('error')}")
                        
                except Exception as e:
                    logger.error(f"Error processing description {desc.get('description_id')}: {str(e)}")
                    continue
            
            if not polygons:
                return {
                    "success": False,
                    "error": "No complete descriptions could be processed into polygons"
                }
            
            # Calculate summary statistics
            summary = self._calculate_summary_statistics(polygons, processing_metadata)
            
            return {
                "success": True,
                "polygons": polygons,
                "metadata": {
                    "parcel_id": parcel_data.get("parcel_id"),
                    "schema_version": self.schema_version,
                    "processing_options": processing_options,
                    "total_descriptions": len(parcel_data.get("descriptions", [])),
                    "processed_descriptions": len(polygons),
                    "summary_statistics": summary,
                    "individual_metadata": processing_metadata
                }
            }
            
        except Exception as e:
            logger.error(f"Pipeline processing failed: {str(e)}")
            return {
                "success": False,
                "error": f"Processing failed: {str(e)}"
            }
    
    def _validate_input(self, parcel_data: dict) -> dict:
        """Validate that input data has required structure"""
        errors = []
        
        if not isinstance(parcel_data, dict):
            errors.append("Input must be a dictionary")
            return {"valid": False, "errors": errors}
        
        if "descriptions" not in parcel_data:
            errors.append("Missing 'descriptions' field")
            return {"valid": False, "errors": errors}
        
        descriptions = parcel_data["descriptions"]
        if not isinstance(descriptions, list) or len(descriptions) == 0:
            errors.append("Descriptions must be a non-empty list")
            return {"valid": False, "errors": errors}
        
        # Check for at least one complete description
        complete_descriptions = [d for d in descriptions if d.get("is_complete", False)]
        if not complete_descriptions:
            errors.append("No complete descriptions found for polygon generation")
        
        # Validate complete descriptions have required fields
        for i, desc in enumerate(complete_descriptions):
            desc_errors = self._validate_description(desc, i)
            errors.extend(desc_errors)
        
        return {
            "valid": len(errors) == 0,
            "errors": errors
        }
    
    def _validate_description(self, desc: dict, index: int) -> List[str]:
        """Validate a single description has required fields for polygon generation"""
        errors = []
        
        # Check required top-level fields
        required_fields = ["plss", "metes_and_bounds"]
        for field in required_fields:
            if field not in desc:
                errors.append(f"Description {index} missing required field: {field}")
        
        # Validate metes and bounds
        if "metes_and_bounds" in desc:
            mb = desc["metes_and_bounds"]
            if "boundary_courses" not in mb:
                errors.append(f"Description {index} missing boundary_courses")
            else:
                courses = mb["boundary_courses"]
                if not isinstance(courses, list) or len(courses) < 3:
                    errors.append(f"Description {index} needs at least 3 boundary courses for polygon")
                
                # Check each course has required fields
                for j, course in enumerate(courses):
                    if not isinstance(course, dict):
                        errors.append(f"Description {index} course {j} must be an object")
                        continue
                    
                    course_required = ["course", "distance", "distance_units"]
                    for field in course_required:
                        if field not in course or course[field] is None:
                            errors.append(f"Description {index} course {j} missing {field}")
        
        # Validate PLSS starting point
        if "plss" in desc and "starting_point" in desc["plss"]:
            sp = desc["plss"]["starting_point"]
            pob_status = sp.get("pob_status")
            if pob_status not in ["explicit", "deducible", "resolved"]:
                errors.append(f"Description {index} has unsupported POB status: {pob_status}")
        
        return errors
    
    def _get_processing_options(self, options: Optional[Dict[str, Any]]) -> dict:
        """Get processing options with defaults"""
        default_options = {
            "coordinate_system": "local",  # local, utm, geographic
            "origin_method": "auto",  # auto, plss_corner, explicit
            "distance_units": "feet",  # default unit if not specified in data
            "bearing_format": "surveyor",  # surveyor (N45E) vs azimuth (45 degrees from north)
            "closure_tolerance_feet": 1.0,  # tolerance for polygon closure validation
            "output_format": "geojson"  # geojson, wkt, coordinates
        }
        
        if options:
            default_options.update(options)
        
        return default_options
    
    def _process_single_description(self, desc: dict, options: dict) -> dict:
        """Process a single complete description into a polygon"""
        try:
            description_id = desc.get("description_id", "unknown")
            
            # Determine starting point
            origin_result = self._determine_origin(desc["plss"]["starting_point"], options)
            if not origin_result["success"]:
                return {
                    "success": False,
                    "error": f"Could not determine origin: {origin_result['error']}"
                }
            
            # Generate polygon from metes and bounds
            polygon_result = self.drawer.draw_polygon(
                origin=origin_result["origin"],
                boundary_courses=desc["metes_and_bounds"]["boundary_courses"],
                options=options
            )
            
            if not polygon_result["success"]:
                return {
                    "success": False,
                    "error": f"Polygon generation failed: {polygon_result['error']}"
                }
            
            # Validate polygon quality
            quality_result = self._validate_polygon_quality(
                polygon_result["coordinates"],
                desc,
                options
            )
            
            return {
                "success": True,
                "polygon": {
                    "description_id": description_id,
                    "coordinates": polygon_result["coordinates"],
                    "geometry_type": "Polygon",
                    "coordinate_system": options["coordinate_system"],
                    "origin": origin_result["origin"],
                    "properties": {
                        "area_calculated": polygon_result.get("area_calculated"),
                        "area_stated": desc["plss"].get("stated_area_acres"),
                        "perimeter": polygon_result.get("perimeter"),
                        "closure_error": polygon_result.get("closure_error"),
                        "courses_count": len(desc["metes_and_bounds"]["boundary_courses"])
                    }
                },
                "metadata": {
                    "origin_method": origin_result["method"],
                    "quality_score": quality_result["quality_score"],
                    "quality_warnings": quality_result["warnings"],
                    "processing_notes": polygon_result.get("notes", [])
                }
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": f"Processing failed: {str(e)}"
            }
    
    def _determine_origin(self, starting_point: dict, options: dict) -> dict:
        """Determine the starting point coordinates based on POB status"""
        pob_status = starting_point.get("pob_status")
        
        if pob_status == "explicit":
            # Use provided lat/lon coordinates
            lat = starting_point.get("lat")
            lon = starting_point.get("lon")
            if lat is not None and lon is not None:
                return {
                    "success": True,
                    "origin": {"type": "geographic", "lat": lat, "lon": lon},
                    "method": "explicit_coordinates"
                }
            else:
                return {
                    "success": False,
                    "error": "POB marked as explicit but no lat/lon provided"
                }
        
        elif pob_status == "deducible":
            # Use tie to corner information
            tie_to_corner = starting_point.get("tie_to_corner")
            if tie_to_corner:
                return self._resolve_deducible_origin(tie_to_corner, options)
            else:
                return {
                    "success": False,
                    "error": "POB marked as deducible but no tie_to_corner provided"
                }
        
        elif pob_status == "resolved":
            # For now, treat as local origin - could be enhanced to use resolved coordinates
            return {
                "success": True,
                "origin": {"type": "local", "x": 0, "y": 0},
                "method": "local_origin_resolved"
            }
        
        else:
            # Default to local coordinate system
            return {
                "success": True,
                "origin": {"type": "local", "x": 0, "y": 0},
                "method": "local_origin_default"
            }
    
    def _resolve_deducible_origin(self, tie_to_corner: dict, options: dict) -> dict:
        """Resolve origin from tie to PLSS corner (simplified version)"""
        # For now, use local coordinates with bearing/distance offset
        # In production, this would look up actual PLSS corner coordinates
        
        try:
            bearing_raw = tie_to_corner.get("bearing_raw", "")
            distance_value = tie_to_corner.get("distance_value", 0)
            distance_units = tie_to_corner.get("distance_units", "feet")
            
            # Convert to standard units (feet)
            distance_feet = self._convert_distance_to_feet(distance_value, distance_units)
            
            # Parse bearing (simplified - assumes format like "N45E")
            bearing_degrees = self._parse_bearing_to_degrees(bearing_raw)
            
            # Calculate offset from assumed corner at (0,0)
            offset_x, offset_y = self._calculate_offset(bearing_degrees, distance_feet)
            
            return {
                "success": True,
                "origin": {
                    "type": "plss_offset",
                    "x": offset_x,
                    "y": offset_y,
                    "reference_corner": tie_to_corner.get("corner_label", ""),
                    "bearing": bearing_raw,
                    "distance_feet": distance_feet
                },
                "method": "plss_corner_offset"
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to resolve deducible origin: {str(e)}"
            }
    
    def _convert_distance_to_feet(self, value: float, units: str) -> float:
        """Convert distance to feet"""
        units_lower = units.lower()
        
        conversion_factors = {
            "feet": 1.0,
            "foot": 1.0,
            "ft": 1.0,
            "chains": 66.0,  # 1 chain = 66 feet
            "chain": 66.0,
            "rods": 16.5,    # 1 rod = 16.5 feet
            "rod": 16.5,
            "meters": 3.28084,  # 1 meter = 3.28084 feet
            "meter": 3.28084,
            "m": 3.28084
        }
        
        factor = conversion_factors.get(units_lower, 1.0)
        return value * factor
    
    def _parse_bearing_to_degrees(self, bearing_raw: str) -> float:
        """Parse surveyor bearing to degrees from north"""
        try:
            import re
            
            # Normalize the bearing string first
            bearing_normalized = bearing_raw.strip()
            
            # Remove extra spaces and standardize format
            # Convert "N. 4° 00' W." → "N. 4°00'W."
            bearing_normalized = re.sub(r'\s+', ' ', bearing_normalized)  # Multiple spaces → single space
            bearing_normalized = re.sub(r'°\s+', '°', bearing_normalized)  # Remove space after degree
            bearing_normalized = re.sub(r'\s+\'', '\'', bearing_normalized)  # Remove space before prime
            
            logger.debug(f"Normalized bearing: '{bearing_raw}' → '{bearing_normalized}'")
            
            # Now use the simple regex pattern
            pattern = r'([NS])\.\s*(\d+)°(\d+)\'([EW])\.'
            match = re.match(pattern, bearing_normalized)
            
            if not match:
                raise ValueError(f"Could not parse bearing: {bearing_raw}")
            
            direction, degrees, minutes, east_west = match.groups()
            degrees_val = int(degrees)
            minutes_val = int(minutes)
            
            # Convert to decimal degrees
            decimal_degrees = degrees_val + (minutes_val / 60.0)
            
            # Convert to azimuth from north
            if direction == 'N':
                if east_west == 'E':
                    azimuth = decimal_degrees
                else:  # W
                    azimuth = 360 - decimal_degrees
            else:  # S
                if east_west == 'E':
                    azimuth = 180 - decimal_degrees
                else:  # W
                    azimuth = 180 + decimal_degrees
            
            logger.debug(f"Parsed bearing '{bearing_raw}' → {azimuth}°")
            return azimuth
            
        except Exception as e:
            logger.error(f"Failed to parse bearing '{bearing_raw}': {str(e)}")
            raise ValueError(f"Could not parse bearing: {bearing_raw}")
    
    def _calculate_offset(self, bearing_degrees: float, distance_feet: float) -> Tuple[float, float]:
        """Calculate x,y offset from bearing and distance"""
        # Convert bearing to radians
        bearing_radians = math.radians(bearing_degrees)
        
        # Calculate offset (note: surveying convention vs. math convention)
        offset_x = distance_feet * math.sin(bearing_radians)
        offset_y = distance_feet * math.cos(bearing_radians)
        
        return offset_x, offset_y
    
    def _validate_polygon_quality(self, coordinates: List[Tuple[float, float]], desc: dict, options: dict) -> dict:
        """Validate polygon quality and generate quality score"""
        warnings = []
        quality_score = 1.0
        
        try:
            # Check closure
            if len(coordinates) > 2:
                start_point = coordinates[0]
                end_point = coordinates[-1]
                closure_error = math.sqrt(
                    (end_point[0] - start_point[0])**2 + 
                    (end_point[1] - start_point[1])**2
                )
                
                tolerance = options.get("closure_tolerance_feet", 1.0)
                if closure_error > tolerance:
                    warnings.append(f"Polygon does not close within tolerance: {closure_error:.2f} feet error")
                    quality_score *= 0.8
            
            # Check for stated vs calculated area if available
            stated_area = desc.get("plss", {}).get("stated_area_acres")
            if stated_area:
                # Would calculate actual area here and compare
                pass
            
            # Check for very small or very large polygons
            if len(coordinates) >= 3:
                # Simple area calculation
                area = self._calculate_polygon_area(coordinates)
                if area < 100:  # Less than 100 sq ft
                    warnings.append("Polygon area is very small")
                    quality_score *= 0.9
                elif area > 50 * 43560:  # More than 50 acres in sq ft
                    warnings.append("Polygon area is very large")
                    quality_score *= 0.9
            
        except Exception as e:
            warnings.append(f"Quality validation error: {str(e)}")
            quality_score *= 0.5
        
        return {
            "quality_score": max(0.0, min(1.0, quality_score)),
            "warnings": warnings
        }
    
    def _calculate_polygon_area(self, coordinates: List[Tuple[float, float]]) -> float:
        """Calculate polygon area using shoelace formula"""
        if len(coordinates) < 3:
            return 0.0
        
        area = 0.0
        n = len(coordinates)
        
        for i in range(n):
            j = (i + 1) % n
            area += coordinates[i][0] * coordinates[j][1]
            area -= coordinates[j][0] * coordinates[i][1]
        
        return abs(area) / 2.0
    
    def _calculate_summary_statistics(self, polygons: List[dict], metadata: List[dict]) -> dict:
        """Calculate summary statistics for all processed polygons"""
        if not polygons:
            return {}
        
        total_area = sum(p.get("properties", {}).get("area_calculated", 0) for p in polygons)
        quality_scores = [m.get("quality_score", 0) for m in metadata]
        
        return {
            "total_polygons": len(polygons),
            "total_area_sqft": total_area,
            "total_area_acres": total_area / 43560,
            "average_quality_score": sum(quality_scores) / len(quality_scores) if quality_scores else 0,
            "min_quality_score": min(quality_scores) if quality_scores else 0,
            "max_quality_score": max(quality_scores) if quality_scores else 0
        }
    
    def get_available_options(self) -> dict:
        """Get available processing options and their descriptions"""
        return {
            "coordinate_system": {
                "description": "Output coordinate system",
                "options": ["local", "utm", "geographic"],
                "default": "local"
            },
            "origin_method": {
                "description": "Method for determining polygon origin",
                "options": ["auto", "plss_corner", "explicit"],
                "default": "auto"
            },
            "distance_units": {
                "description": "Default distance units if not specified",
                "options": ["feet", "meters", "chains"],
                "default": "feet"
            },
            "closure_tolerance_feet": {
                "description": "Tolerance for polygon closure validation in feet",
                "type": "float",
                "default": 1.0
            },
            "output_format": {
                "description": "Output coordinate format",
                "options": ["geojson", "wkt", "coordinates"],
                "default": "geojson"
            }
        }
