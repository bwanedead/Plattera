"""
Tile Pipeline
Main orchestrator for map tile management and serving
"""
import logging
from typing import Dict, Any, Optional, List, Tuple
from pathlib import Path

from .cache_manager import TileCacheManager
from .tile_server import TileServer
from .providers import TileProviders

logger = logging.getLogger(__name__)

class TilePipeline:
    """
    Pipeline for managing map tile fetching, caching, and serving
    """
    
    def __init__(self, cache_directory: Optional[str] = None):
        """
        Initialize tile pipeline
        
        Args:
            cache_directory: Optional custom directory for tile caching
        """
        self.cache_manager = TileCacheManager(cache_directory)
        self.tile_server = TileServer()
        self.providers = TileProviders()
        
    def get_tiles_for_extent(
        self, 
        bbox: dict, 
        zoom_level: int, 
        provider: str = "usgs_topo"
    ) -> dict:
        """
        Get map tiles for specified bounding box and zoom level
        
        Args:
            bbox: Bounding box with min_lat, max_lat, min_lon, max_lon
            zoom_level: Map zoom level (1-18)
            provider: Tile provider name
            
        Returns:
            dict: Result with tile URLs and metadata
        """
        try:
            logger.info(f"🗺️ Getting tiles for bbox: {bbox} at zoom {zoom_level}")
            
            # Validate inputs
            validation_result = self._validate_tile_request(bbox, zoom_level, provider)
            if not validation_result["valid"]:
                return {
                    "success": False,
                    "error": f"Invalid tile request: {validation_result['errors']}"
                }
            
            # Get provider configuration
            provider_config = self.providers.get_provider_config(provider)
            if not provider_config["success"]:
                return {
                    "success": False,
                    "error": f"Provider configuration error: {provider_config['error']}"
                }
            
            # Calculate required tiles
            tile_grid = self._calculate_tile_grid(bbox, zoom_level)
            logger.info(f"📊 Calculated tile grid: {len(tile_grid)} tiles needed")
            
            # Fetch tiles (from cache or remote)
            tile_results = []
            cache_hits = 0
            cache_misses = 0
            
            for tile_coord in tile_grid:
                tile_result = self._get_single_tile(
                    tile_coord["x"], 
                    tile_coord["y"], 
                    zoom_level, 
                    provider_config["config"]
                )
                
                if tile_result["success"]:
                    tile_results.append(tile_result["tile_info"])
                    if tile_result["source"] == "cache":
                        cache_hits += 1
                    else:
                        cache_misses += 1
                else:
                    logger.warning(f"Failed to get tile {tile_coord}: {tile_result['error']}")
            
            logger.info(f"✅ Tile fetching complete: {cache_hits} cache hits, {cache_misses} cache misses")
            
            return {
                "success": True,
                "tiles": tile_results,
                "metadata": {
                    "bbox": bbox,
                    "zoom_level": zoom_level,
                    "provider": provider,
                    "total_tiles": len(tile_results),
                    "cache_hits": cache_hits,
                    "cache_misses": cache_misses,
                    "tile_size": provider_config["config"]["tile_size"]
                }
            }
            
        except Exception as e:
            logger.error(f"❌ Tile pipeline failed: {str(e)}")
            return {
                "success": False,
                "error": f"Tile pipeline error: {str(e)}"
            }
    
    def _validate_tile_request(self, bbox: dict, zoom_level: int, provider: str) -> dict:
        """Validate tile request parameters"""
        errors = []
        
        # Validate bounding box
        required_bbox_fields = ["min_lat", "max_lat", "min_lon", "max_lon"]
        for field in required_bbox_fields:
            if field not in bbox:
                errors.append(f"Missing bbox field: {field}")
        
        if len(errors) == 0:
            if bbox["min_lat"] >= bbox["max_lat"]:
                errors.append("min_lat must be less than max_lat")
            if bbox["min_lon"] >= bbox["max_lon"]:
                errors.append("min_lon must be less than max_lon")
            if not (-90 <= bbox["min_lat"] <= 90) or not (-90 <= bbox["max_lat"] <= 90):
                errors.append("Latitude values must be between -90 and 90")
            if not (-180 <= bbox["min_lon"] <= 180) or not (-180 <= bbox["max_lon"] <= 180):
                errors.append("Longitude values must be between -180 and 180")
        
        # Validate zoom level
        if not isinstance(zoom_level, int) or zoom_level < 1 or zoom_level > 18:
            errors.append("Zoom level must be an integer between 1 and 18")
        
        # Validate provider
        available_providers = self.providers.get_available_providers()
        if provider not in available_providers:
            errors.append(f"Unknown provider: {provider}. Available: {available_providers}")
        
        return {
            "valid": len(errors) == 0,
            "errors": errors
        }
    
    def _calculate_tile_grid(self, bbox: dict, zoom_level: int) -> List[dict]:
        """Calculate tile coordinates needed for bounding box"""
        # Web Mercator tile calculation
        import math
        
        def deg2num(lat_deg: float, lon_deg: float, zoom: int) -> Tuple[int, int]:
            lat_rad = math.radians(lat_deg)
            n = 2.0 ** zoom
            x = int((lon_deg + 180.0) / 360.0 * n)
            y = int((1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n)
            return (x, y)
        
        # Calculate tile boundaries
        x_min, y_max = deg2num(bbox["min_lat"], bbox["min_lon"], zoom_level)
        x_max, y_min = deg2num(bbox["max_lat"], bbox["max_lon"], zoom_level)
        
        # Generate tile grid
        tile_grid = []
        for x in range(x_min, x_max + 1):
            for y in range(y_min, y_max + 1):
                tile_grid.append({"x": x, "y": y, "z": zoom_level})
        
        return tile_grid
    
    def _get_single_tile(self, x: int, y: int, z: int, provider_config: dict) -> dict:
        """Get a single tile from cache or remote server"""
        try:
            # Check cache first
            cache_result = self.cache_manager.get_cached_tile(x, y, z, provider_config["name"])
            if cache_result["success"]:
                return {
                    "success": True,
                    "tile_info": {
                        "x": x, "y": y, "z": z,
                        "url": cache_result["local_path"],
                        "size": provider_config["tile_size"]
                    },
                    "source": "cache"
                }
            
            # Fetch from remote server
            fetch_result = self.tile_server.fetch_tile(x, y, z, provider_config)
            if not fetch_result["success"]:
                return fetch_result
            
            # Cache the fetched tile
            cache_result = self.cache_manager.cache_tile(
                x, y, z, 
                provider_config["name"],
                fetch_result["tile_data"]
            )
            
            tile_url = cache_result["local_path"] if cache_result["success"] else fetch_result["remote_url"]
            
            return {
                "success": True,
                "tile_info": {
                    "x": x, "y": y, "z": z,
                    "url": tile_url,
                    "size": provider_config["tile_size"]
                },
                "source": "remote"
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": f"Single tile fetch error: {str(e)}"
            }
    
    def get_tile_providers(self) -> dict:
        """Get available tile providers"""
        return self.providers.get_available_providers()
    
    def clear_cache(self, provider: Optional[str] = None) -> dict:
        """Clear tile cache for specific provider or all providers"""
        return self.cache_manager.clear_cache(provider)
    
    def get_cache_stats(self) -> dict:
        """Get tile cache statistics"""
        return self.cache_manager.get_cache_stats()