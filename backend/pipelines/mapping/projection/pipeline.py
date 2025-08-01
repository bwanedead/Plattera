"""
Projection Pipeline
Main orchestrator for coordinate transformations and projections
"""
import logging
from typing import Dict, Any, List, Tuple, Optional

from .transformer import CoordinateTransformer
from .utm_manager import UTMManager

logger = logging.getLogger(__name__)

class ProjectionPipeline:
    """
    Pipeline for coordinate transformations and geographic projections
    """
    
    def __init__(self):
        """Initialize projection pipeline"""
        self.transformer = CoordinateTransformer()
        self.utm_manager = UTMManager()
    
    def project_polygon_to_geographic(
        self, 
        local_coordinates: List[Tuple[float, float]], 
        anchor_point: dict,
        options: Optional[Dict[str, Any]] = None
    ) -> dict:
        """
        Project local polygon coordinates to geographic coordinates
        
        Args:
            local_coordinates: List of (x, y) coordinate tuples in local system
            anchor_point: Geographic anchor point with lat/lon
            options: Projection options
            
        Returns:
            dict: Result with geographic coordinates and metadata
        """
        try:
            logger.info("🌍 Starting polygon projection to geographic coordinates")
            
            # Validate inputs
            validation_result = self._validate_projection_inputs(local_coordinates, anchor_point)
            if not validation_result["valid"]:
                return {
                    "success": False,
                    "error": f"Input validation failed: {validation_result['errors']}"
                }
            
            # Set projection options
            projection_options = self._get_projection_options(options)
            
            # Determine appropriate UTM zone for anchor point
            utm_zone = self.utm_manager.get_utm_zone(
                anchor_point["lat"], 
                anchor_point["lon"]
            )
            logger.info(f"📍 Using UTM zone: {utm_zone}")
            
            # Transform anchor point to UTM
            anchor_utm = self.transformer.geographic_to_utm(
                anchor_point["lat"], 
                anchor_point["lon"], 
                utm_zone
            )
            
            if not anchor_utm["success"]:
                return {
                    "success": False,
                    "error": f"Anchor transformation failed: {anchor_utm['error']}"
                }
            
            # Project local coordinates to UTM using anchor as origin
            utm_coordinates = []
            for local_x, local_y in local_coordinates:
                utm_x = anchor_utm["utm_x"] + local_x
                utm_y = anchor_utm["utm_y"] + local_y
                utm_coordinates.append((utm_x, utm_y))
            
            # Transform UTM coordinates back to geographic
            geographic_coordinates = []
            for utm_x, utm_y in utm_coordinates:
                geo_result = self.transformer.utm_to_geographic(utm_x, utm_y, utm_zone)
                if geo_result["success"]:
                    geographic_coordinates.append((geo_result["lon"], geo_result["lat"]))
                else:
                    logger.warning(f"Failed to transform UTM point ({utm_x}, {utm_y})")
            
            if len(geographic_coordinates) != len(local_coordinates):
                return {
                    "success": False,
                    "error": "Some coordinates failed to transform"
                }
            
            # Calculate polygon bounds
            bounds = self._calculate_geographic_bounds(geographic_coordinates)
            
            logger.info(f"✅ Projected {len(geographic_coordinates)} coordinates successfully")
            
            return {
                "success": True,
                "geographic_coordinates": geographic_coordinates,
                "coordinate_format": "lon_lat",  # GeoJSON standard
                "bounds": bounds,
                "metadata": {
                    "utm_zone": utm_zone,
                    "anchor_point": anchor_point,
                    "projection_method": "utm_intermediate",
                    "coordinate_count": len(geographic_coordinates),
                    "projection_options": projection_options
                }
            }
            
        except Exception as e:
            logger.error(f"❌ Projection pipeline failed: {str(e)}")
            return {
                "success": False,
                "error": f"Projection error: {str(e)}"
            }
    
    def transform_coordinates(
        self, 
        coordinates: List[Tuple[float, float]], 
        source_crs: str, 
        target_crs: str
    ) -> dict:
        """
        Transform coordinates between coordinate reference systems
        
        Args:
            coordinates: List of coordinate tuples
            source_crs: Source CRS (e.g., "EPSG:4326", "utm_13n")
            target_crs: Target CRS
            
        Returns:
            dict: Transformed coordinates
        """
        try:
            logger.info(f"🔄 Transforming coordinates from {source_crs} to {target_crs}")
            
            transformed_coords = []
            
            for coord in coordinates:
                transform_result = self.transformer.transform_point(
                    coord[0], coord[1], source_crs, target_crs
                )
                if transform_result["success"]:
                    transformed_coords.append((
                        transform_result["x"], 
                        transform_result["y"]
                    ))
                else:
                    logger.warning(f"Failed to transform point {coord}")
            
            return {
                "success": True,
                "transformed_coordinates": transformed_coords,
                "source_crs": source_crs,
                "target_crs": target_crs,
                "coordinate_count": len(transformed_coords)
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": f"Coordinate transformation error: {str(e)}"
            }
    
    def _validate_projection_inputs(self, coordinates: List[Tuple[float, float]], anchor: dict) -> dict:
        """Validate projection inputs"""
        errors = []
        
        # Validate coordinates
        if not coordinates or len(coordinates) < 3:
            errors.append("At least 3 coordinates required for polygon projection")
        
        for i, coord in enumerate(coordinates):
            if not isinstance(coord, (list, tuple)) or len(coord) != 2:
                errors.append(f"Coordinate {i} must be a 2-element tuple/list")
            else:
                try:
                    float(coord[0])
                    float(coord[1])
                except (ValueError, TypeError):
                    errors.append(f"Coordinate {i} contains non-numeric values")
        
        # Validate anchor point
        if not isinstance(anchor, dict):
            errors.append("Anchor point must be a dictionary")
        else:
            required_anchor_fields = ["lat", "lon"]
            for field in required_anchor_fields:
                if field not in anchor:
                    errors.append(f"Anchor point missing required field: {field}")
                else:
                    try:
                        value = float(anchor[field])
                        if field == "lat" and not (-90 <= value <= 90):
                            errors.append("Latitude must be between -90 and 90")
                        elif field == "lon" and not (-180 <= value <= 180):
                            errors.append("Longitude must be between -180 and 180")
                    except (ValueError, TypeError):
                        errors.append(f"Anchor {field} must be numeric")
        
        return {
            "valid": len(errors) == 0,
            "errors": errors
        }
    
    def _get_projection_options(self, options: Optional[Dict[str, Any]]) -> dict:
        """Get projection options with defaults"""
        default_options = {
            "datum": "WGS84",
            "preserve_area": True,
            "intermediate_crs": "utm",  # utm, state_plane, local
            "precision_meters": 1.0
        }
        
        if options:
            default_options.update(options)
        
        return default_options
    
    def _calculate_geographic_bounds(self, coordinates: List[Tuple[float, float]]) -> dict:
        """Calculate bounding box for geographic coordinates"""
        if not coordinates:
            return {}
        
        lons = [coord[0] for coord in coordinates]
        lats = [coord[1] for coord in coordinates]
        
        return {
            "min_lon": min(lons),
            "max_lon": max(lons),
            "min_lat": min(lats),
            "max_lat": max(lats),
            "center_lon": (min(lons) + max(lons)) / 2,
            "center_lat": (min(lats) + max(lats)) / 2
        }
    
    def get_supported_crs(self) -> dict:
        """Get list of supported coordinate reference systems"""
        return {
            "geographic": ["EPSG:4326", "EPSG:4269"],  # WGS84, NAD83
            "utm_zones": [f"utm_{zone}{'n' if north else 's'}" 
                         for zone in range(1, 61) 
                         for north in [True, False]],
            "state_plane": ["state_plane_wyoming", "state_plane_colorado"],  # Examples
            "local": ["local_feet", "local_meters"]
        }