"""
Georeference Service
Fresh implementation for converting local polygon coordinates to geographic coordinates.
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple
import logging

from .pob_resolver import POBResolver
from .pob_math import normalize_local_coordinates
from pipelines.mapping.projection.pipeline import ProjectionPipeline

logger = logging.getLogger(__name__)


class GeoreferenceService:
    """
    Main service for georeferencing deed-derived polygons.
    
    Takes local coordinates (drawn by user) and PLSS anchor information,
    and returns a geographic polygon that can be plotted on a map.
    """
    
    def __init__(self) -> None:
        """Initialize the georeference service."""
        self._pob_resolver = POBResolver()
        self._projection = ProjectionPipeline()
    
    def _feet_to_meters(self, coords: List[Tuple[float, float]]) -> List[Tuple[float, float]]:
        f2m = 0.3048
        return [(x * f2m, y * f2m) for (x, y) in coords]

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

            # 4) Project polygon via UTM anchor
            print(f'🔍 PROJECTION PROCESS:')
            print(f'📍 ANCHOR POINT: lat={pob_geo["lat"]:.6f}, lon={pob_geo["lon"]:.6f}')
            print(f'📍 LOCAL COORDINATES TO PROJECT: {local_coords_m}')
            
            proj = self._projection.project_polygon_to_geographic(
                local_coordinates=local_coords_m,
                anchor_point={"lat": float(pob_geo["lat"]), "lon": float(pob_geo["lon"])},
                options={"assume_local_units": "meters"}
            )
            if not proj.get("success"):
                return {"success": False, "error": proj.get("error", "Projection failed")}

            geo_coords = proj["geographic_coordinates"]  # [(lon,lat)]
            print(f'📍 PROJECTED GEOGRAPHIC COORDINATES: {geo_coords}')
            bounds = self._compute_bounds(geo_coords)
            print(f'📍 COMPUTED BOUNDS: {bounds}')

            # 5) Build response
            plss_ref = f"T{plss_anchor['township_number']}{plss_anchor['township_direction']} R{plss_anchor['range_number']}{plss_anchor['range_direction']} Sec {plss_anchor['section_number']}"
            resolved_coord = pob_result.get("resolved_corner_geographic") or pob_result.get("resolved_centroid_geographic") or pob_geo
            utm_zone = proj.get("metadata", {}).get("utm_zone", "unknown")

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
            
            print(f'📊 FINAL RESULT OBJECT: {result}')
            return result
            
        except Exception as e:
            logger.error(f"Georeference failed: {str(e)}")
            return {
                "success": False,
                "error": f"Georeference error: {str(e)}"
            }