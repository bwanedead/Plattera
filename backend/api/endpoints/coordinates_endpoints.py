"""
Unified Coordinates API Endpoints
Routes to appropriate calculator based on method selection
"""
import logging
import math
from typing import Dict, Any
from fastapi import APIRouter, HTTPException

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/coordinates", tags=["coordinates"])

# Import calculator modules from mapping pipeline
from pipelines.mapping.calculators.haversine_calculator import HaversineCalculator
from pipelines.mapping.calculators.utm_calculator import UTMCalculator
from pipelines.mapping.calculators.geodesic_calculator import GeodesicCalculator

# Initialize calculator instances
haversine_calc = HaversineCalculator()
utm_calc = UTMCalculator()
geodesic_calc = GeodesicCalculator()

# Default method for polygon projection (most accurate)
DEFAULT_PROJECTION_METHOD = "geodesic"

@router.post("/calculate-endpoint")
async def calculate_coordinate_endpoint(request: Dict[str, Any]) -> Dict[str, Any]:
    """
    Calculate end point using selected calculation method
    Routes to appropriate calculator based on method parameter
    """
    try:
        start_lat = request.get("start_lat")
        start_lng = request.get("start_lng")
        bearing_degrees = request.get("bearing_degrees")
        distance_feet = request.get("distance_feet")
        method = request.get("method", "geodesic")  # Default to most accurate

        # Validate required parameters
        if None in [start_lat, start_lng, bearing_degrees, distance_feet]:
            return {
                "success": False,
                "error": "Missing required parameters: start_lat, start_lng, bearing_degrees, distance_feet"
            }

        # Convert feet to meters for calculations
        distance_meters = distance_feet * 0.3048

        logger.info(f"🧮 Calculating endpoint using {method} method")

        # Route to appropriate calculator
        if method == "haversine":
            # Validate inputs for Haversine
            validation = haversine_calc.validate_inputs(
                start_lat, start_lng, bearing_degrees, distance_meters
            )
            if not validation["valid"]:
                return {
                    "success": False,
                    "error": f"Input validation failed: {', '.join(validation['issues'])}",
                    "method": "haversine_validation_error"
                }

            result = haversine_calc.calculate_endpoint(
                start_lat, start_lng, bearing_degrees, distance_meters
            )

        elif method == "utm":
            # Validate inputs for UTM
            validation = utm_calc.validate_inputs(
                start_lat, start_lng, bearing_degrees, distance_meters
            )
            if not validation["valid"]:
                return {
                    "success": False,
                    "error": f"Input validation failed: {', '.join(validation['issues'])}",
                    "method": "utm_validation_error"
                }

            result = utm_calc.calculate_endpoint(
                start_lat, start_lng, bearing_degrees, distance_meters
            )

        elif method == "geodesic":
            # Validate inputs for Geodesic
            validation = geodesic_calc.validate_inputs(
                start_lat, start_lng, bearing_degrees, distance_meters
            )
            if not validation["valid"]:
                return {
                    "success": False,
                    "error": f"Input validation failed: {', '.join(validation['issues'])}",
                    "method": "geodesic_validation_error"
                }

            result = geodesic_calc.calculate_endpoint(
                start_lat, start_lng, bearing_degrees, distance_meters
            )

        else:
            return {
                "success": False,
                "error": f"Unknown calculation method: {method}",
                "available_methods": ["haversine", "utm", "geodesic"]
            }

        if not result["success"]:
            return result

        # Add method metadata to result
        result["selected_method"] = method
        result["input_distance_feet"] = distance_feet
        result["input_distance_meters"] = distance_meters

        logger.info(f"✅ Endpoint calculation successful using {method} method")

        return result

    except Exception as e:
        logger.error(f"🚨 Coordinate calculation error: {str(e)}")
        return {
            "success": False,
            "error": f"Coordinate calculation failed: {str(e)}"
        }

@router.post("/calculate-endpoint-batch")
async def calculate_coordinate_endpoints_batch(request: Dict[str, Any]) -> Dict[str, Any]:
    """
    Calculate multiple endpoints in a single request
    Useful for polygon calculations or measurement chains
    """
    try:
        calculations = request.get("calculations", [])
        method = request.get("method", "geodesic")

        if not calculations:
            return {
                "success": False,
                "error": "No calculations provided"
            }

        results = []
        errors = []

        for i, calc in enumerate(calculations):
            try:
                calc_request = {
                    "start_lat": calc["start_lat"],
                    "start_lng": calc["start_lng"],
                    "bearing_degrees": calc["bearing_degrees"],
                    "distance_feet": calc["distance_feet"],
                    "method": method
                }

                result = await calculate_coordinate_endpoint(calc_request)
                results.append({
                    "index": i,
                    "input": calc,
                    "result": result
                })

            except Exception as e:
                errors.append({
                    "index": i,
                    "input": calc,
                    "error": str(e)
                })

        return {
            "success": True,
            "method": method,
            "total_calculations": len(calculations),
            "successful_calculations": len(results),
            "failed_calculations": len(errors),
            "results": results,
            "errors": errors
        }

    except Exception as e:
        logger.error(f"🚨 Batch calculation error: {str(e)}")
        return {
            "success": False,
            "error": f"Batch calculation failed: {str(e)}"
        }

@router.post("/compare-methods")
async def compare_calculation_methods(request: Dict[str, Any]) -> Dict[str, Any]:
    """
    Compare all three calculation methods for the same inputs
    Returns accuracy analysis and recommendations
    """
    try:
        start_lat = request.get("start_lat", 41.219354)
        start_lng = request.get("start_lng", -105.789304)
        bearing_degrees = request.get("bearing_degrees", 176.0)
        distance_feet = request.get("distance_feet", 1638.0)

        distance_meters = distance_feet * 0.3048

        logger.info("🧮 Comparing all calculation methods")

        results = {}

        # Calculate using all three methods
        try:
            haversine_result = haversine_calc.calculate_endpoint(
                start_lat, start_lng, bearing_degrees, distance_meters
            )
            results["haversine"] = haversine_result
        except Exception as e:
            results["haversine"] = {"success": False, "error": str(e)}

        try:
            utm_result = utm_calc.calculate_endpoint(
                start_lat, start_lng, bearing_degrees, distance_meters
            )
            results["utm"] = utm_result
        except Exception as e:
            results["utm"] = {"success": False, "error": str(e)}

        try:
            geodesic_result = geodesic_calc.calculate_endpoint(
                start_lat, start_lng, bearing_degrees, distance_meters
            )
            results["geodesic"] = geodesic_result
        except Exception as e:
            results["geodesic"] = {"success": False, "error": str(e)}

        # Analyze differences if all methods succeeded
        analysis = {}
        if all(r.get("success", False) for r in results.values()):
            haversine_coords = (results["haversine"]["end_lat"], results["haversine"]["end_lng"])
            utm_coords = (results["utm"]["end_lat"], results["utm"]["end_lng"])
            geodesic_coords = (results["geodesic"]["end_lat"], results["geodesic"]["end_lng"])

            # Calculate differences from geodesic (most accurate)
            analysis = {
                "haversine_vs_geodesic": {
                    "lat_diff_deg": haversine_coords[0] - geodesic_coords[0],
                    "lng_diff_deg": haversine_coords[1] - geodesic_coords[1],
                    "linear_distance_m": _calculate_linear_distance(haversine_coords, geodesic_coords)
                },
                "utm_vs_geodesic": {
                    "lat_diff_deg": utm_coords[0] - geodesic_coords[0],
                    "lng_diff_deg": utm_coords[1] - geodesic_coords[1],
                    "linear_distance_m": _calculate_linear_distance(utm_coords, geodesic_coords)
                },
                "recommendations": {
                    "best_for_accuracy": "geodesic",
                    "best_for_speed": "haversine",
                    "best_for_surveying": "geodesic",
                    "default_method": "geodesic"
                }
            }

        return {
            "success": True,
            "input": {
                "start_lat": start_lat,
                "start_lng": start_lng,
                "bearing_degrees": bearing_degrees,
                "distance_feet": distance_feet,
                "distance_meters": distance_meters
            },
            "results": results,
            "analysis": analysis,
            "method_comparison": True
        }

    except Exception as e:
        logger.error(f"🚨 Method comparison error: {str(e)}")
        return {
            "success": False,
            "error": f"Method comparison failed: {str(e)}"
        }

@router.get("/methods")
async def get_available_methods() -> Dict[str, Any]:
    """
    Get information about available calculation methods
    """
    return {
        "success": True,
        "methods": {
            "haversine": {
                "name": "Haversine (Spherical)",
                "description": "Fast spherical calculations using Haversine formula",
                "accuracy": "~50-200m for distances under 50km",
                "speed": "Fastest",
                "best_for": "Quick measurements, rough estimates",
                "limitations": "Less accurate for surveying, spherical Earth model"
            },
            "utm": {
                "name": "UTM Planar (Corrected)",
                "description": "UTM coordinate system with meridian convergence correction",
                "accuracy": "~1-10cm for distances under 500km",
                "speed": "Medium",
                "best_for": "Surveying applications, professional mapping",
                "limitations": "Requires UTM zone determination"
            },
            "geodesic": {
                "name": "GeographicLib (Ellipsoidal)",
                "description": "Professional ellipsoidal geodesics using Karney's algorithm",
                "accuracy": "~1mm globally",
                "speed": "Medium-Fast",
                "best_for": "Surveying, precision applications, polygon projection",
                "limitations": "Requires GeographicLib dependency"
            }
        },
        "default_method": DEFAULT_PROJECTION_METHOD,
        "recommendations": {
            "polygon_projection": "geodesic",
            "surveying_measurements": "geodesic",
            "quick_measurements": "haversine",
            "professional_mapping": "utm"
        }
    }

@router.post("/calculate-geodesic")
async def calculate_geodesic_endpoint(request: Dict[str, Any]) -> Dict[str, Any]:
    """
    Calculate end point using GeographicLib (most accurate method)
    Dedicated endpoint for geodesic calculations
    """
    try:
        start_lat = request.get("start_lat")
        start_lng = request.get("start_lng")
        bearing_degrees = request.get("bearing_degrees")
        distance_feet = request.get("distance_feet")

        # Validate required parameters
        if None in [start_lat, start_lng, bearing_degrees, distance_feet]:
            return {
                "success": False,
                "error": "Missing required parameters: start_lat, start_lng, bearing_degrees, distance_feet"
            }

        # Convert feet to meters
        distance_meters = distance_feet * 0.3048

        logger.info(f"🧮 Calculating geodesic endpoint")

        # Validate inputs
        validation = geodesic_calc.validate_inputs(
            start_lat, start_lng, bearing_degrees, distance_meters
        )
        if not validation["valid"]:
            return {
                "success": False,
                "error": f"Input validation failed: {', '.join(validation['issues'])}"
            }

        result = geodesic_calc.calculate_endpoint(
            start_lat, start_lng, bearing_degrees, distance_meters
        )

        if not result["success"]:
            return result

        # Add method metadata
        result["selected_method"] = "geodesic"
        result["input_distance_feet"] = distance_feet
        result["input_distance_meters"] = distance_meters

        logger.info(f"✅ Geodesic endpoint calculation successful")

        return result

    except Exception as e:
        logger.error(f"🚨 Geodesic calculation error: {str(e)}")
        return {
            "success": False,
            "error": f"Geodesic calculation failed: {str(e)}"
        }

@router.post("/calculate-utm")
async def calculate_utm_endpoint(request: Dict[str, Any]) -> Dict[str, Any]:
    """
    Calculate end point using UTM planar method with meridian convergence correction
    Dedicated endpoint for UTM calculations
    """
    try:
        start_lat = request.get("start_lat")
        start_lng = request.get("start_lng")
        bearing_degrees = request.get("bearing_degrees")
        distance_feet = request.get("distance_feet")

        # Validate required parameters
        if None in [start_lat, start_lng, bearing_degrees, distance_feet]:
            return {
                "success": False,
                "error": "Missing required parameters: start_lat, start_lng, bearing_degrees, distance_feet"
            }

        # Convert feet to meters
        distance_meters = distance_feet * 0.3048

        logger.info(f"🧮 Calculating UTM endpoint")

        # Validate inputs
        validation = utm_calc.validate_inputs(
            start_lat, start_lng, bearing_degrees, distance_meters
        )
        if not validation["valid"]:
            return {
                "success": False,
                "error": f"Input validation failed: {', '.join(validation['issues'])}"
            }

        result = utm_calc.calculate_endpoint(
            start_lat, start_lng, bearing_degrees, distance_meters
        )

        if not result["success"]:
            return result

        # Add method metadata
        result["selected_method"] = "utm"
        result["input_distance_feet"] = distance_feet
        result["input_distance_meters"] = distance_meters

        logger.info(f"✅ UTM endpoint calculation successful")

        return result

    except Exception as e:
        logger.error(f"🚨 UTM calculation error: {str(e)}")
        return {
            "success": False,
            "error": f"UTM calculation failed: {str(e)}"
        }

@router.post("/calculate-haversine")
async def calculate_haversine_endpoint(request: Dict[str, Any]) -> Dict[str, Any]:
    """
    Calculate end point using Haversine spherical method (fastest)
    Dedicated endpoint for Haversine calculations
    """
    try:
        start_lat = request.get("start_lat")
        start_lng = request.get("start_lng")
        bearing_degrees = request.get("bearing_degrees")
        distance_feet = request.get("distance_feet")

        # Validate required parameters
        if None in [start_lat, start_lng, bearing_degrees, distance_feet]:
            return {
                "success": False,
                "error": "Missing required parameters: start_lat, start_lng, bearing_degrees, distance_feet"
            }

        # Convert feet to meters
        distance_meters = distance_feet * 0.3048

        logger.info(f"🧮 Calculating Haversine endpoint")

        # Validate inputs
        validation = haversine_calc.validate_inputs(
            start_lat, start_lng, bearing_degrees, distance_meters
        )
        if not validation["valid"]:
            return {
                "success": False,
                "error": f"Input validation failed: {', '.join(validation['issues'])}"
            }

        result = haversine_calc.calculate_endpoint(
            start_lat, start_lng, bearing_degrees, distance_meters
        )

        if not result["success"]:
            return result

        # Add method metadata
        result["selected_method"] = "haversine"
        result["input_distance_feet"] = distance_feet
        result["input_distance_meters"] = distance_meters

        logger.info(f"✅ Haversine endpoint calculation successful")

        return result

    except Exception as e:
        logger.error(f"🚨 Haversine calculation error: {str(e)}")
        return {
            "success": False,
            "error": f"Haversine calculation failed: {str(e)}"
        }

@router.post("/clear-caches")
async def clear_coordinate_caches() -> Dict[str, Any]:
    """
    Clear all coordinate calculation caches
    This only affects coordinate calculation caches, NOT PLSS data
    """
    try:
        logger.info("🧹 Clearing coordinate calculation caches")

        # Clear caches from all calculators
        utm_calc.clear_cache()
        geodesic_calc.clear_cache()

        # Haversine doesn't have a cache, but we can log it
        logger.info("🧹 Haversine calculator (no cache to clear)")

        return {
            "success": True,
            "message": "Coordinate calculation caches cleared successfully",
            "caches_cleared": ["utm_transformers", "geodesic_calculations"],
            "note": "This only affects coordinate calculation caches, PLSS data remains untouched"
        }

    except Exception as e:
        logger.error(f"🧹 Cache cleanup error: {str(e)}")
        return {
            "success": False,
            "error": f"Cache cleanup failed: {str(e)}"
        }

def _calculate_linear_distance(coord1: tuple, coord2: tuple) -> float:
    """
    Calculate approximate linear distance between two coordinate pairs
    Used for comparison analysis
    """
    try:
        lat1, lng1 = coord1
        lat2, lng2 = coord2

        # Approximate conversion: 1 degree ≈ 111,320 meters
        lat_diff_m = (lat2 - lat1) * 111320
        lng_diff_m = (lng2 - lng1) * 111320 * math.cos(math.radians((lat1 + lat2) / 2))

        return math.sqrt(lat_diff_m**2 + lng_diff_m**2)

    except Exception:
        return 0.0
