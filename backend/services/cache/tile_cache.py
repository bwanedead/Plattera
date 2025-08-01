"""
Tile Cache Service
High-level caching interface for map tiles
"""
import logging
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)

class TileCache:
    """
    High-level caching service for map tiles
    Provides abstraction over the tile cache manager
    """
    
    def __init__(self, cache_directory: Optional[str] = None):
        """
        Initialize tile cache service
        
        Args:
            cache_directory: Optional custom cache directory
        """
        # Import here to avoid circular imports
        from pipelines.mapping.tiles.cache_manager import TileCacheManager
        
        self.cache_manager = TileCacheManager(cache_directory)
        self.cache_stats = {
            "requests": 0,
            "hits": 0,
            "misses": 0,
            "providers_used": set()
        }
    
    def get_tile(self, x: int, y: int, z: int, provider: str) -> dict:
        """
        Get a single tile (from cache or mark for fetch)
        
        Args:
            x: Tile X coordinate
            y: Tile Y coordinate
            z: Zoom level
            provider: Tile provider name
            
        Returns:
            dict: Tile information
        """
        try:
            self.cache_stats["requests"] += 1
            self.cache_stats["providers_used"].add(provider)
            
            # Check cache
            cache_result = self.cache_manager.get_cached_tile(x, y, z, provider)
            
            if cache_result["success"]:
                self.cache_stats["hits"] += 1
                return {
                    "success": True,
                    "tile_path": cache_result["local_path"],
                    "source": "cache",
                    "coordinates": {"x": x, "y": y, "z": z},
                    "provider": provider
                }
            else:
                self.cache_stats["misses"] += 1
                return {
                    "success": False,
                    "reason": cache_result.get("reason", "cache_miss"),
                    "coordinates": {"x": x, "y": y, "z": z},
                    "provider": provider,
                    "needs_fetch": True
                }
                
        except Exception as e:
            logger.error(f"❌ Tile cache error: {str(e)}")
            return {
                "success": False,
                "error": f"Cache error: {str(e)}"
            }
    
    def cache_tile(self, x: int, y: int, z: int, provider: str, tile_data: bytes) -> dict:
        """
        Cache a tile that was fetched from remote
        
        Args:
            x: Tile X coordinate
            y: Tile Y coordinate 
            z: Zoom level
            provider: Tile provider name
            tile_data: Raw tile image data
            
        Returns:
            dict: Cache result
        """
        try:
            return self.cache_manager.cache_tile(x, y, z, provider, tile_data)
        except Exception as e:
            logger.error(f"❌ Tile caching error: {str(e)}")
            return {
                "success": False,
                "error": f"Caching error: {str(e)}"
            }
    
    def get_tiles_for_bounds(
        self, 
        min_lat: float, max_lat: float, 
        min_lon: float, max_lon: float,
        zoom_level: int, 
        provider: str
    ) -> dict:
        """
        Get all tiles needed for geographic bounds
        
        Args:
            min_lat, max_lat, min_lon, max_lon: Bounding box
            zoom_level: Map zoom level
            provider: Tile provider name
            
        Returns:
            dict: Tiles information with cache status
        """
        try:
            # Calculate tile grid
            tile_grid = self._calculate_tile_grid(
                min_lat, max_lat, min_lon, max_lon, zoom_level
            )
            
            tiles_info = {
                "cached": [],
                "needs_fetch": [],
                "total_tiles": len(tile_grid)
            }
            
            for tile_coord in tile_grid:
                tile_result = self.get_tile(
                    tile_coord["x"], 
                    tile_coord["y"], 
                    tile_coord["z"], 
                    provider
                )
                
                if tile_result["success"]:
                    tiles_info["cached"].append(tile_result)
                else:
                    tiles_info["needs_fetch"].append(tile_coord)
            
            return {
                "success": True,
                "bounds": {
                    "min_lat": min_lat, "max_lat": max_lat,
                    "min_lon": min_lon, "max_lon": max_lon
                },
                "zoom_level": zoom_level,
                "provider": provider,
                "tiles": tiles_info,
                "cache_efficiency": len(tiles_info["cached"]) / len(tile_grid) if tile_grid else 0
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": f"Bounds tiles error: {str(e)}"
            }
    
    def _calculate_tile_grid(
        self, 
        min_lat: float, max_lat: float, 
        min_lon: float, max_lon: float, 
        zoom_level: int
    ) -> List[dict]:
        """Calculate tile coordinates for bounding box"""
        import math
        
        def deg2num(lat_deg: float, lon_deg: float, zoom: int):
            lat_rad = math.radians(lat_deg)
            n = 2.0 ** zoom
            x = int((lon_deg + 180.0) / 360.0 * n)
            y = int((1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n)
            return (x, y)
        
        x_min, y_max = deg2num(min_lat, min_lon, zoom_level)
        x_max, y_min = deg2num(max_lat, max_lon, zoom_level)
        
        tile_grid = []
        for x in range(x_min, x_max + 1):
            for y in range(y_min, y_max + 1):
                tile_grid.append({"x": x, "y": y, "z": zoom_level})
        
        return tile_grid
    
    def clear_provider_cache(self, provider: str) -> dict:
        """Clear cache for specific provider"""
        try:
            return self.cache_manager.clear_cache(provider)
        except Exception as e:
            return {
                "success": False,
                "error": f"Provider cache clear error: {str(e)}"
            }
    
    def clear_all_cache(self) -> dict:
        """Clear all tile cache"""
        try:
            result = self.cache_manager.clear_cache(None)
            if result["success"]:
                # Reset stats
                self.cache_stats = {
                    "requests": 0,
                    "hits": 0,
                    "misses": 0,
                    "providers_used": set()
                }
            return result
        except Exception as e:
            return {
                "success": False,
                "error": f"All cache clear error: {str(e)}"
            }
    
    def get_cache_stats(self) -> dict:
        """Get cache statistics"""
        try:
            # Get underlying cache stats
            manager_stats = self.cache_manager.get_cache_stats()
            
            # Combine with our stats
            combined_stats = {
                "service_stats": {
                    **self.cache_stats,
                    "providers_used": list(self.cache_stats["providers_used"]),
                    "hit_rate": (self.cache_stats["hits"] / self.cache_stats["requests"]) 
                               if self.cache_stats["requests"] > 0 else 0
                }
            }
            
            if manager_stats["success"]:
                combined_stats["cache_stats"] = manager_stats
            
            return {
                "success": True,
                **combined_stats
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": f"Stats calculation error: {str(e)}"
            }
    
    def optimize_cache(self) -> dict:
        """Optimize cache by removing old/unused tiles"""
        try:
            # This would implement cache optimization logic
            # For now, just cleanup old tiles
            removed = self.cache_manager._cleanup_old_tiles()
            
            return {
                "success": True,
                "optimization_result": {
                    "removed_tiles": removed,
                    "action": "cleanup_old_tiles"
                }
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": f"Cache optimization error: {str(e)}"
            }