"""
Georeference Service
Fresh implementation for converting local polygon coordinates to geographic coordinates.
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple
import logging
import math

from .pob_resolver import POBResolver
from .pob_math import normalize_local_coordinates
from .survey_math import SurveyingMathematics, TraverseLeg, CoordinatePoint
from .validator import ProfessionalGeoreferenceValidator
from pipelines.mapping.projection.pipeline import ProjectionPipeline

logger = logging.getLogger(__name__)


class GeoreferenceService:
    """
    Main service for georeferencing deed-derived polygons.
    
    Takes local coordinates (drawn by user) and PLSS anchor information,
    and returns a geographic polygon that can be plotted on a map.
    """
    
    def __init__(self) -> None:
        """Initialize the georeference service with professional surveying mathematics and validation."""
        self._pob_resolver = POBResolver()
        self._projection = ProjectionPipeline()
        self._survey_math = SurveyingMathematics()  # Professional surveying calculations
        self._validator = ProfessionalGeoreferenceValidator()  # Professional validation

        # Clear transformer cache on startup for clean state
        logger.info("🔧 Georeference Service: Clearing transformer cache on startup")
        self._pob_resolver.clear_transformer_cache()
        logger.info("✅ Georeference Service: Cache cleared, starting with clean transformer state")

    def cleanup(self) -> None:
        """Clean up resources on shutdown."""
        logger.info("🔧 Georeference Service cleanup initiated")
        self._pob_resolver.cleanup()
        logger.info("✅ Georeference Service cleanup completed")

    def _feet_to_meters(self, coords: List[Tuple[float, float]]) -> List[Tuple[float, float]]:
        f2m = 0.3048
        return [(x * f2m, y * f2m) for (x, y) in coords]

    def _create_traverse_legs_from_local_coords(self, local_coords_m: List[Tuple[float, float]]) -> List[TraverseLeg]:
        """
        Convert local polygon coordinates to professional surveying traverse legs.

        This creates proper bearing and distance measurements for each polygon segment,
        enabling professional surveying calculations with error analysis.
        """
        traverse_legs = []

        # Process each segment of the polygon
        for i in range(len(local_coords_m)):
            start_point = local_coords_m[i]
            end_point = local_coords_m[(i + 1) % len(local_coords_m)]  # Wrap around for closed polygon

            # Calculate bearing from start to end point
            delta_x = end_point[0] - start_point[0]  # Easting difference
            delta_y = end_point[1] - start_point[1]  # Northing difference

            # Calculate bearing in degrees (clockwise from north)
            bearing_radians = math.atan2(delta_x, delta_y)
            bearing_degrees = math.degrees(bearing_radians)
            if bearing_degrees < 0:
                bearing_degrees += 360.0

            # Calculate distance in meters
            distance_meters = math.sqrt(delta_x ** 2 + delta_y ** 2)

            # Convert distance to feet for traditional surveying units
            distance_feet = distance_meters * 3.28084

            # Create traverse leg
            leg = TraverseLeg(
                bearing_degrees=round(bearing_degrees, 4),
                distance_feet=round(distance_feet, 2),
                distance_meters=round(distance_meters, 3),
                leg_number=i + 1,
                description=f"Polygon segment {i + 1} from point {i} to {(i + 1) % len(local_coords_m)}"
            )

            traverse_legs.append(leg)

            print(f"🧮 TRAVERSE LEG {leg.leg_number}:")
            print(f"   📍 Bearing: {leg.bearing_degrees:.4f}°")
            print(f"   📏 Distance: {leg.distance_feet:.2f} ft ({leg.distance_meters:.3f} m)")
            print(f"   📍 Segment: ({start_point[0]:.3f}, {start_point[1]:.3f}) → ({end_point[0]:.3f}, {end_point[1]:.3f})")

        return traverse_legs

    def _compute_bounds(self, lonlat: List[Tuple[float, float]]) -> Dict[str, float]:
        lons = [pt[0] for pt in lonlat]
        lats = [pt[1] for pt in lonlat]
        return {
            "min_lat": min(lats),
            "max_lat": max(lats),
            "min_lon": min(lons),
            "max_lon": max(lons),
        }
    
    def georeference_polygon(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """
        Convert local polygon coordinates to geographic coordinates.
        
        Args:
            request: {
                "local_coordinates": [{x, y}, ...],  # User-drawn coordinates (feet by default)
                "plss_anchor": {state, township_number, township_direction, range_number, range_direction, section_number, principal_meridian?},
                "starting_point": {  # Optional tie to PLSS corner
                    "tie_to_corner": {
                        "corner_label": "NW corner Sec 2 T14N R75W" | "NW corner",
                        "bearing_raw": "N 4° 00' W.",
                        "distance_value": 1638,
                        "distance_units": "feet",
                        "tie_direction": "corner_bears_from_pob" | "pob_bears_from_corner"
                    }
                },
                "options": { "local_units": "feet" | "meters" }
            }
        
        Returns:
            {
                "success": True,
                "geographic_polygon": {
                    "type": "Polygon",
                    "coordinates": [[[lon, lat], ...]],  # GeoJSON format
                    "bounds": {min_lat, max_lat, min_lon, max_lon}
                },
                "anchor_info": {
                    "plss_reference": "T14N R75W Sec 2",
                    "resolved_coordinates": {"lat": 41.5, "lon": -107.5},  # corner/centroid used
                    "pob_coordinates": {"lat": 41.5, "lon": -107.5}  # Point of Beginning
                },
                "projection_metadata": {
                    "method": "utm_projection",
                    "utm_zone": "13N",
                    "vertex_count": 4
                }
            }
        """
        try:
            # 1) Validate inputs
            local_coords_in = request.get("local_coordinates") or []
            plss_anchor = request.get("plss_anchor") or {}
            starting_point = request.get("starting_point") or {}
            options = request.get("options") or {}
            if not isinstance(local_coords_in, list) or len(local_coords_in) < 3:
                return {"success": False, "error": "local_coordinates must be a list with at least 3 vertices"}
            required_plss = ["state", "township_number", "township_direction", "range_number", "range_direction", "section_number"]
            if not all(k in plss_anchor for k in required_plss):
                return {"success": False, "error": f"plss_anchor missing required fields: {required_plss}"}

            # 2) Resolve POB (uses PLSS index/parquet and tie if provided)
            tie_to_corner = (starting_point or {}).get("tie_to_corner")
            pob_result = self._pob_resolver.resolve_pob(plss_anchor, tie_to_corner)
            if not pob_result.get("success"):
                return {"success": False, "error": pob_result.get("error", "POB resolution failed")}
            pob_geo = pob_result["pob_geographic"]  # {"lat","lon"}

            # 3) Prepare local coordinates
            print(f'🔍 LOCAL COORDINATES:')
            print(f'📊 Original coordinates: {local_coords_in}')
            normalized = normalize_local_coordinates(local_coords_in)  # [(x,y)] preserving given origin
            print(f'📊 Normalized coordinates: {normalized}')
            
            # FIX 1: Shift local coordinates to POB origin (0,0)
            if normalized[0] != (0.0, 0.0):  # If not already at (0,0)
                ox, oy = normalized[0]
                normalized = [(x - ox, y - oy) for x, y in normalized]
                print(f'🔧 SHIFTED TO POB ORIGIN: {normalized}')
            
            local_units = (options.get("local_units") or "feet").lower()
            if local_units not in ["feet", "foot", "ft", "meters", "meter", "m"]:
                local_units = "feet"
            print(f'📊 Local units: {local_units}')
            if local_units in ["feet", "foot", "ft"]:
                local_coords_m = self._feet_to_meters(normalized)
                print(f'📊 Converted to meters: {local_coords_m}')
            else:
                local_coords_m = normalized  # already meters
                print(f'📊 Already in meters: {local_coords_m}')

            # FIX 2: Flip Y for screen coordinates (Y-down to Y-up)
            if options.get("screen_coords_y_down") is True:
                local_coords_m = [(x, -y) for (x, y) in local_coords_m]
                print(f'🔧 Y-AXIS FLIPPED FOR SCREEN COORDS: {local_coords_m}')

            # 4) Professional surveying projection using traverse methods
            print(f'🧮 PROFESSIONAL SURVEYING PROJECTION:')
            print(f'📍 POINT OF BEGINNING: lat={pob_geo["lat"]:.8f}, lon={pob_geo["lon"]:.8f}')
            print(f'📍 LOCAL COORDINATES: {local_coords_m}')

            # Create POB coordinate point
            utm_zone = self._pob_resolver._utm.get_utm_zone(pob_geo["lat"], pob_geo["lon"])
            pob_utm = self._pob_resolver._transformer.geographic_to_utm(
                pob_geo["lat"], pob_geo["lon"], utm_zone
            )

            if not pob_utm.get("success"):
                return {"success": False, "error": f"POB UTM transformation failed: {pob_utm.get('error')}"}

            pob_point = CoordinatePoint(
                utm_x=pob_utm["utm_x"],
                utm_y=pob_utm["utm_y"],
                latitude=pob_geo["lat"],
                longitude=pob_geo["lon"],
                zone_number=pob_utm["zone_number"],
                hemisphere=pob_utm["hemisphere"],
                point_id="POB",
                description="Point of Beginning"
            )

            # Convert local coordinates to traverse legs using professional surveying
            traverse_legs = self._create_traverse_legs_from_local_coords(local_coords_m)

            # Calculate polygon vertices using professional traverse methods
            traverse_result = self._survey_math.calculate_traverse_coordinates(
                start_point=pob_point,
                traverse_legs=traverse_legs,
                tie_direction="pob_bears_from_corner"  # POB is starting point
            )

            if not traverse_result["success"]:
                return {"success": False, "error": f"Polygon traverse calculation failed: {traverse_result.get('error')}"}

            # Extract geographic coordinates from traverse result
            geo_coords = []
            for point in traverse_result["points"]:
                # Transform each UTM point back to geographic coordinates
                geo_result = self._pob_resolver._transformer.utm_to_geographic(
                    point.utm_x, point.utm_y, utm_zone
                )
                if geo_result["success"]:
                    geo_coords.append((geo_result["lon"], geo_result["lat"]))
                else:
                    return {"success": False, "error": f"UTM to geographic conversion failed: {geo_result.get('error')}"}

            print(f'🧮 POLYGON TRAVERSE RESULTS:')
            print(f'📊 Traverse legs calculated: {len(traverse_legs)}')
            print(f'📊 Closure analysis: {traverse_result["closure_analysis"]}')
            print(f'📊 Error analysis: {traverse_result["error_analysis"]}')
            print(f'📍 CALCULATED GEOGRAPHIC COORDINATES: {geo_coords}')
            print(f'📍 PROJECTED GEOGRAPHIC COORDINATES: {geo_coords}')
            bounds = self._compute_bounds(geo_coords)
            print(f'📍 COMPUTED BOUNDS: {bounds}')

            # 5) Build response
            plss_ref = f"T{plss_anchor['township_number']}{plss_anchor['township_direction']} R{plss_anchor['range_number']}{plss_anchor['range_direction']} Sec {plss_anchor['section_number']}"
            resolved_coord = pob_result.get("resolved_corner_geographic") or pob_result.get("resolved_centroid_geographic") or pob_geo
            utm_zone = pob_result.get("utm_zone", "unknown")

            # COMPREHENSIVE LOGGING FOR DEBUGGING
            print(f'🔍 BACKEND GEOREFERENCE FINAL RESULT:')
            print(f'📍 PLSS REFERENCE: {plss_ref}')
            print(f'📍 POINT OF BEGINNING: lat={pob_geo["lat"]:.6f}, lon={pob_geo["lon"]:.6f}')
            print(f'📍 RESOLVED REFERENCE: lat={resolved_coord["lat"]:.6f}, lon={resolved_coord["lon"]:.6f}')
            print(f'📍 POB METHOD: {pob_result.get("method")}')
            print(f'📊 Geographic Coordinates: {geo_coords}')
            print(f'📊 Bounds: {bounds}')
            print(f'📊 UTM Zone: {utm_zone}')
            print(f'📊 Vertex Count: {len(geo_coords)}')
            
            result = {
                "success": True,
                "geographic_polygon": {
                    "type": "Polygon",
                    "coordinates": [geo_coords],  # single ring
                    "bounds": bounds
                },
                "anchor_info": {
                    "plss_reference": plss_ref,
                    "resolved_coordinates": {"lat": resolved_coord["lat"], "lon": resolved_coord["lon"]},
                    "pob_coordinates": {"lat": pob_geo["lat"], "lon": pob_geo["lon"]},
                    "pob_method": pob_result.get("method")
                },
                "projection_metadata": {
                    "method": "utm_projection",
                    "utm_zone": utm_zone,
                    "vertex_count": len(geo_coords)
                }
            }
            
            # 6) Professional Validation
            print(f'🧮 PROFESSIONAL VALIDATION:')
            validation_result = self._validator.validate_georeferenced_polygon(
                plss_desc=plss_anchor,
                geographic_polygon=result["geographic_polygon"],
                traverse_data=traverse_result if 'traverse_result' in locals() else None
            )

            print(f'📊 VALIDATION GRADE: {validation_result["overall_accuracy"]}')
            print(f'📊 VALIDATION CHECKS PASSED: {validation_result.get("accuracy_metrics", {}).get("passed_checks", 0)}/{validation_result.get("accuracy_metrics", {}).get("total_checks", 0)}')
            if validation_result["issues"]:
                print(f'⚠️ VALIDATION ISSUES: {validation_result["issues"]}')
            if validation_result["recommendations"]:
                print(f'💡 RECOMMENDATIONS: {validation_result["recommendations"]}')

            # Add professional validation to response
            result["professional_validation"] = {
                "overall_accuracy": validation_result["overall_accuracy"],
                "accuracy_percentage": validation_result.get("accuracy_metrics", {}).get("accuracy_percentage", 0),
                "validation_checks": validation_result["validation_checks"],
                "accuracy_metrics": validation_result["accuracy_metrics"],
                "issues": validation_result["issues"],
                "recommendations": validation_result["recommendations"],
                "traverse_analysis": {
                    "closure_analysis": traverse_result.get("closure_analysis", {}),
                    "error_analysis": traverse_result.get("error_analysis", {})
                } if 'traverse_result' in locals() else None
            }

            # Add surveying standards compliance
            result["surveying_standards"] = {
                "coordinate_precision_standard": "6+ decimal places",
                "traverse_closure_standard": "1:10,000 ratio",
                "bearing_accuracy_standard": "±15 arc seconds",
                "distance_accuracy_standard": "±0.01 feet",
                "datum": "WGS84"
            }

            print(f'📊 FINAL RESULT OBJECT: {result}')
            return result
            
        except Exception as e:
            logger.error(f"Georeference failed: {str(e)}")
            return {
                "success": False,
                "error": f"Georeference error: {str(e)}"
            }