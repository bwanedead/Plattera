"""
Professional Georeference Validator
Civil engineering-grade validation for surveying accuracy and quality assurance.
"""
from __future__ import annotations

from typing import Dict, Any, List, Optional
from shapely.geometry import Polygon, shape, Point
import math
import logging

from pipelines.mapping.plss.pipeline import PLSSPipeline
from .survey_math import SurveyingMathematics

logger = logging.getLogger(__name__)


def _quarter_label(pt: Point, section_centroid: Point) -> str:
    ns = "N" if pt.y >= section_centroid.y else "S"
    ew = "E" if pt.x >= section_centroid.x else "W"
    return f"{ns}{ew}"


def _quarter_quarter_label(pt: Point, section_geom) -> Optional[str]:
    c = section_geom.centroid
    q_label = _quarter_label(pt, c)

    # Determine label relative to quarter centroid (approximation)
    # This intentionally avoids heavy polygon splitting.
    if q_label == "NW":
        qc = section_geom.envelope.centroid  # fallback
    elif q_label == "NE":
        qc = section_geom.envelope.centroid
    elif q_label == "SW":
        qc = section_geom.envelope.centroid
    else:
        qc = section_geom.envelope.centroid

    sub = _quarter_label(pt, qc)
    return f"{sub} of {q_label}"


class ProfessionalGeoreferenceValidator:
    """
    Professional surveying validation for civil engineering accuracy.

    Implements comprehensive validation including:
    - Traverse closure analysis
    - Coordinate precision validation
    - Bearing accuracy verification
    - Error propagation analysis
    - PLSS boundary compliance

    ⚠️  CRITICAL SAFETY CONSTRAINTS:
    - VALIDATION IS READ-ONLY: Never trigger data downloads or rebuilds
    - Use _is_data_current() for availability checks, NOT ensure_state_data()
    - If data is unavailable, skip validation gracefully rather than triggering rebuilds
    - This prevents expensive operations during normal georeferencing workflow
    """

    def __init__(self):
        """Initialize professional validator"""
        self.survey_math = SurveyingMathematics()
        self.plss_pipeline = PLSSPipeline()

    def validate_georeferenced_polygon(self, plss_desc: Dict[str, Any], geographic_polygon: Dict[str, Any],
                                     traverse_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Comprehensive professional validation of georeferenced polygon.

        Args:
            plss_desc: PLSS description (township, range, section, etc.)
            geographic_polygon: GeoJSON polygon
            traverse_data: Optional traverse calculation results for enhanced validation

        Returns:
            dict: Professional validation results with accuracy metrics
        """
        try:
            validation_results = {
                "success": True,
                "overall_accuracy": "unknown",
                "validation_checks": {},
                "accuracy_metrics": {},
                "issues": [],
                "recommendations": []
            }

            # 1. PLSS Boundary Validation
            plss_validation = self._validate_plss_boundary_compliance(plss_desc, geographic_polygon)
            validation_results["validation_checks"].update(plss_validation["checks"])

            if not plss_validation["success"]:
                validation_results["issues"].extend(plss_validation["issues"])

            # 2. Coordinate Precision Validation
            precision_validation = self._validate_coordinate_precision(geographic_polygon)
            validation_results["validation_checks"].update(precision_validation["checks"])

            if not precision_validation["success"]:
                validation_results["issues"].extend(precision_validation["issues"])

            # 3. Traverse Analysis (if available)
            if traverse_data:
                traverse_validation = self._validate_traverse_quality(traverse_data)
                validation_results["validation_checks"].update(traverse_validation["checks"])
                validation_results["accuracy_metrics"].update(traverse_validation["metrics"])

                if not traverse_validation["success"]:
                    validation_results["issues"].extend(traverse_validation["issues"])

            # 4. Overall Accuracy Assessment
            overall_assessment = self._assess_overall_accuracy(validation_results)
            validation_results["overall_accuracy"] = overall_assessment["grade"]
            validation_results["accuracy_metrics"].update(overall_assessment["metrics"])
            validation_results["recommendations"].extend(overall_assessment["recommendations"])

            # Update success status
            validation_results["success"] = len(validation_results["issues"]) == 0

            return validation_results

        except Exception as e:
            return {
                "success": False,
                "error": f"Professional validation failed: {str(e)}",
                "overall_accuracy": "error"
            }

    def _validate_plss_boundary_compliance(self, plss_desc: Dict[str, Any], geographic_polygon: Dict[str, Any]) -> Dict[str, Any]:
        """Validate polygon compliance with PLSS boundaries"""
        try:
            state = plss_desc.get("state")

            # READ-ONLY CHECK: Never trigger data rebuilds during validation
            if not self.plss_pipeline.data_manager._is_data_current(state):
                logger.warning(f"🔍 PLSS validation skipped: Data not available for {state}")
                return {
                    "success": True,
                    "issues": [],
                    "checks": {"plss_boundary_compliance": "skipped - data unavailable"}
                }

            section_result = self.plss_pipeline.get_section_view(plss_desc)
            if not section_result.get("success"):
                logger.warning(f"🔍 PLSS validation skipped: Section data unavailable for {plss_desc}")
                return {
                    "success": True,
                    "issues": [],
                    "checks": {"plss_boundary_compliance": "skipped - section data unavailable"}
                }

            section_centroid = section_result["centroid"]
            poly = shape(geographic_polygon)
            poly_centroid = poly.centroid

            # Calculate distance from polygon centroid to section centroid
            from geopy.distance import geodesic
            distance_km = geodesic(
                (poly_centroid.y, poly_centroid.x),
                (section_centroid["lat"], section_centroid["lon"])
            ).kilometers

            # Professional surveying standards: polygon should be within section bounds
            section_size_km = 1.6  # Approximate section size (1.6km x 1.6km)
            tolerance_km = section_size_km * 0.5  # 50% tolerance

            centroid_within_tolerance = distance_km <= tolerance_km

            # Calculate polygon area overlap with section (simplified)
            section_bounds = section_result.get("bounds", {})
            if section_bounds:
                # Check if polygon vertices are within reasonable distance of section
                vertex_check = self._check_polygon_vertices_near_section(poly, section_centroid, tolerance_km)
            else:
                vertex_check = {"within_bounds": True, "vertex_count": len(poly.exterior.coords)}

            return {
                "success": centroid_within_tolerance,
                "checks": {
                    "centroid_within_section_tolerance": centroid_within_tolerance,
                    "distance_from_section_center_km": round(distance_km, 3),
                    "section_tolerance_km": tolerance_km,
                    "vertices_near_section": vertex_check["within_bounds"],
                    "vertex_count": vertex_check["vertex_count"]
                },
                "issues": [] if centroid_within_tolerance else [
                    f"Polygon centroid {distance_km:.1f}km from section center (tolerance: {tolerance_km:.1f}km)"
                ]
            }

        except Exception as e:
            return {"success": False, "issues": [f"PLSS validation error: {str(e)}"], "checks": {}}

    def _validate_coordinate_precision(self, geographic_polygon: Dict[str, Any]) -> Dict[str, Any]:
        """Validate coordinate precision meets surveying standards"""
        try:
            poly = shape(geographic_polygon)
            coords = list(poly.exterior.coords)

            precision_issues = []
            precision_checks = {
                "latitude_precision_ok": True,
                "longitude_precision_ok": True,
                "coordinate_count": len(coords),
                "min_precision_decimals": 8
            }

            for lon, lat in coords:
                # Check latitude precision (should have at least 6 decimal places for surveying)
                lat_str = str(lat)
                lat_decimals = len(lat_str.split('.')[-1]) if '.' in lat_str else 0
                if lat_decimals < 6:
                    precision_checks["latitude_precision_ok"] = False
                    precision_issues.append(f"Latitude precision insufficient: {lat_decimals} decimals")

                # Check longitude precision
                lon_str = str(lon)
                lon_decimals = len(lon_str.split('.')[-1]) if '.' in lon_str else 0
                if lon_decimals < 6:
                    precision_checks["longitude_precision_ok"] = False
                    precision_issues.append(f"Longitude precision insufficient: {lon_decimals} decimals")

            return {
                "success": len(precision_issues) == 0,
                "checks": precision_checks,
                "issues": precision_issues
            }

        except Exception as e:
            return {"success": False, "issues": [f"Precision validation error: {str(e)}"], "checks": {}}

    def _validate_traverse_quality(self, traverse_data: Dict[str, Any]) -> Dict[str, Any]:
        """Validate traverse calculation quality and closure"""
        try:
            validation_checks = {}
            issues = []
            metrics = {}

            # Check closure analysis if available
            if "closure_analysis" in traverse_data:
                closure = traverse_data["closure_analysis"]
                validation_checks["closure_ratio_acceptable"] = closure.get("acceptable", False)
                validation_checks["closure_ratio"] = closure.get("closure_ratio", 0)
                metrics["traverse_closure_ratio"] = closure.get("closure_ratio_string", "unknown")

                if not closure.get("acceptable", True):
                    issues.append(f"Traverse closure exceeds 1:10,000 standard: {closure.get('closure_ratio_string', 'unknown')}")

            # Check error analysis if available
            if "error_analysis" in traverse_data:
                error = traverse_data["error_analysis"]
                validation_checks["distance_error_mm"] = error.get("total_distance_error_mm", 0)
                validation_checks["bearing_error_arcsec"] = error.get("total_bearing_error_arcsec", 0)
                metrics["distance_error_mm"] = error.get("total_distance_error_mm", 0)
                metrics["bearing_error_arcsec"] = error.get("total_bearing_error_arcsec", 0)

                # Professional standards
                if error.get("total_distance_error_mm", 0) > 50:  # 50mm tolerance
                    issues.append(f"Distance measurement error too high: {error.get('total_distance_error_mm', 0)}mm")

                if error.get("total_bearing_error_arcsec", 0) > 30:  # 30" tolerance
                    issues.append(f"Bearing measurement error too high: {error.get('total_bearing_error_arcsec', 0)}\"")

            return {
                "success": len(issues) == 0,
                "checks": validation_checks,
                "metrics": metrics,
                "issues": issues
            }

        except Exception as e:
            return {"success": False, "issues": [f"Traverse validation error: {str(e)}"], "checks": {}, "metrics": {}}

    def _assess_overall_accuracy(self, validation_results: Dict[str, Any]) -> Dict[str, Any]:
        """Assess overall accuracy grade based on all validation checks"""
        try:
            checks = validation_results.get("validation_checks", {})
            issues = validation_results.get("issues", [])

            # Count passed checks
            total_checks = len(checks)
            passed_checks = sum(1 for check in checks.values() if check is True)

            # Calculate accuracy percentage
            accuracy_percentage = (passed_checks / total_checks * 100) if total_checks > 0 else 0

            # Determine grade based on professional surveying standards
            if accuracy_percentage >= 95 and len(issues) == 0:
                grade = "excellent"
                recommendations = ["Accuracy meets professional surveying standards"]
            elif accuracy_percentage >= 90 and len(issues) <= 2:
                grade = "good"
                recommendations = ["Minor improvements recommended for optimal accuracy"]
            elif accuracy_percentage >= 80:
                grade = "acceptable"
                recommendations = ["Review coordinate precision and traverse closure"]
            else:
                grade = "needs_improvement"
                recommendations = ["Significant accuracy issues detected - professional review recommended"]

            return {
                "grade": grade,
                "accuracy_percentage": round(accuracy_percentage, 1),
                "recommendations": recommendations,
                "metrics": {
                    "total_checks": total_checks,
                    "passed_checks": passed_checks,
                    "failed_checks": total_checks - passed_checks,
                    "critical_issues": len(issues)
                }
            }

        except Exception as e:
            return {
                "grade": "error",
                "accuracy_percentage": 0,
                "recommendations": [f"Accuracy assessment error: {str(e)}"],
                "metrics": {}
            }

    def _check_polygon_vertices_near_section(self, poly: Polygon, section_centroid: Dict[str, Any], tolerance_km: float) -> Dict[str, Any]:
        """Check if polygon vertices are within tolerance of section centroid"""
        try:
            from geopy.distance import geodesic

            vertices_within_bounds = 0
            total_vertices = len(poly.exterior.coords)

            for coord in poly.exterior.coords:
                distance = geodesic(
                    (coord[1], coord[0]),  # lat, lon
                    (section_centroid["lat"], section_centroid["lon"])
                ).kilometers

                if distance <= tolerance_km:
                    vertices_within_bounds += 1

            return {
                "within_bounds": vertices_within_bounds == total_vertices,
                "vertices_within_bounds": vertices_within_bounds,
                "vertex_count": total_vertices,
                "percentage_within_bounds": round((vertices_within_bounds / total_vertices * 100), 1)
            }

        except Exception:
            return {
                "within_bounds": False,
                "vertices_within_bounds": 0,
                "vertex_count": len(poly.exterior.coords),
                "percentage_within_bounds": 0
            }


# Legacy function for backward compatibility
def validate_polygon_against_plss(plss_desc: Dict[str, Any], geographic_polygon: Dict[str, Any]) -> Dict[str, Any]:
    """
    Legacy validation function - use ProfessionalGeoreferenceValidator for new implementations
    """
    validator = ProfessionalGeoreferenceValidator()
    return validator.validate_georeferenced_polygon(plss_desc, geographic_polygon)


