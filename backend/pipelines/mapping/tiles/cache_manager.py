"""
Tile Cache Manager
Handles local caching of map tiles for performance
"""
import logging
import os
import hashlib
import json
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class TileCacheManager:
    """
    Manages local caching of map tiles
    """
    
    def __init__(self, cache_directory: Optional[str] = None):
        """
        Initialize cache manager
        
        Args:
            cache_directory: Custom directory for tile caching
        """
        if cache_directory:
            self.cache_dir = Path(cache_directory)
        else:
            # Default to user's home directory
            self.cache_dir = Path.home() / ".plattera" / "tiles"
        
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.metadata_file = self.cache_dir / "cache_metadata.json"
        
        # Cache settings
        self.max_cache_size_mb = 500  # 500MB cache limit
        self.tile_expiry_days = 30    # Tiles expire after 30 days
        
    def get_cached_tile(self, x: int, y: int, z: int, provider: str) -> dict:
        """
        Retrieve cached tile if available and valid
        
        Args:
            x: Tile X coordinate
            y: Tile Y coordinate
            z: Zoom level
            provider: Tile provider name
            
        Returns:
            dict: Result with tile path or cache miss
        """
        try:
            tile_path = self._get_tile_path(x, y, z, provider)
            
            if not tile_path.exists():
                return {
                    "success": False,
                    "reason": "tile_not_cached"
                }
            
            # Check if tile is expired
            if self._is_tile_expired(tile_path):
                logger.info(f"🗑️ Removing expired tile: {tile_path.name}")
                tile_path.unlink()
                return {
                    "success": False,
                    "reason": "tile_expired"
                }
            
            logger.debug(f"💾 Cache hit: {x}/{y}/{z}")
            return {
                "success": True,
                "local_path": str(tile_path)
            }
            
        except Exception as e:
            logger.error(f"❌ Cache retrieval error: {str(e)}")
            return {
                "success": False,
                "reason": f"cache_error: {str(e)}"
            }
    
    def cache_tile(self, x: int, y: int, z: int, provider: str, tile_data: bytes) -> dict:
        """
        Cache a tile to local storage
        
        Args:
            x: Tile X coordinate
            y: Tile Y coordinate
            z: Zoom level
            provider: Tile provider name
            tile_data: Raw tile image data
            
        Returns:
            dict: Result with cache status
        """
        try:
            # Check cache size limit
            if not self._check_cache_space():
                self._cleanup_old_tiles()
            
            tile_path = self._get_tile_path(x, y, z, provider)
            tile_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Write tile data
            with open(tile_path, 'wb') as f:
                f.write(tile_data)
            
            # Update metadata
            self._update_tile_metadata(x, y, z, provider, len(tile_data))
            
            logger.debug(f"💾 Cached tile: {x}/{y}/{z}")
            return {
                "success": True,
                "local_path": str(tile_path),
                "size_bytes": len(tile_data)
            }
            
        except Exception as e:
            logger.error(f"❌ Cache storage error: {str(e)}")
            return {
                "success": False,
                "error": f"Cache error: {str(e)}"
            }
    
    def _get_tile_path(self, x: int, y: int, z: int, provider: str) -> Path:
        """Generate file path for tile"""
        # Use standard tile server directory structure
        return self.cache_dir / provider / str(z) / str(x) / f"{y}.png"
    
    def _is_tile_expired(self, tile_path: Path) -> bool:
        """Check if cached tile has expired"""
        try:
            stat = tile_path.stat()
            file_age = datetime.now() - datetime.fromtimestamp(stat.st_mtime)
            return file_age > timedelta(days=self.tile_expiry_days)
        except Exception:
            return True  # Consider invalid files as expired
    
    def _check_cache_space(self) -> bool:
        """Check if cache is within size limits"""
        try:
            total_size = self._calculate_cache_size()
            size_mb = total_size / (1024 * 1024)
            return size_mb < self.max_cache_size_mb
        except Exception:
            return True  # Assume OK if calculation fails
    
    def _calculate_cache_size(self) -> int:
        """Calculate total cache size in bytes"""
        total_size = 0
        for root, dirs, files in os.walk(self.cache_dir):
            for file in files:
                if file.endswith('.png'):  # Only count tile files
                    file_path = Path(root) / file
                    try:
                        total_size += file_path.stat().st_size
                    except Exception:
                        pass  # Skip inaccessible files
        return total_size
    
    def _cleanup_old_tiles(self) -> int:
        """Remove old tiles to free space"""
        logger.info("🧹 Cleaning up old tiles...")
        
        removed_count = 0
        cutoff_date = datetime.now() - timedelta(days=self.tile_expiry_days // 2)
        
        for root, dirs, files in os.walk(self.cache_dir):
            for file in files:
                if file.endswith('.png'):
                    file_path = Path(root) / file
                    try:
                        if datetime.fromtimestamp(file_path.stat().st_mtime) < cutoff_date:
                            file_path.unlink()
                            removed_count += 1
                    except Exception:
                        pass  # Skip problematic files
        
        logger.info(f"🗑️ Removed {removed_count} old tiles")
        return removed_count
    
    def _update_tile_metadata(self, x: int, y: int, z: int, provider: str, size_bytes: int):
        """Update cache metadata"""
        try:
            metadata = {}
            if self.metadata_file.exists():
                with open(self.metadata_file, 'r') as f:
                    metadata = json.load(f)
            
            # Initialize structure
            if "tiles" not in metadata:
                metadata["tiles"] = {}
            if provider not in metadata["tiles"]:
                metadata["tiles"][provider] = {}
            
            # Update tile info
            tile_key = f"{z}/{x}/{y}"
            metadata["tiles"][provider][tile_key] = {
                "cached_at": datetime.now().isoformat(),
                "size_bytes": size_bytes
            }
            
            # Update summary stats
            metadata["last_updated"] = datetime.now().isoformat()
            metadata["total_providers"] = len(metadata["tiles"])
            
            with open(self.metadata_file, 'w') as f:
                json.dump(metadata, f, indent=2)
                
        except Exception as e:
            logger.warning(f"Failed to update metadata: {str(e)}")
    
    def clear_cache(self, provider: Optional[str] = None) -> dict:
        """Clear cache for specific provider or all providers"""
        try:
            removed_files = 0
            
            if provider:
                # Clear specific provider
                provider_dir = self.cache_dir / provider
                if provider_dir.exists():
                    for file_path in provider_dir.rglob("*.png"):
                        file_path.unlink()
                        removed_files += 1
                    # Remove empty directories
                    if provider_dir.exists():
                        import shutil
                        shutil.rmtree(provider_dir)
            else:
                # Clear all cache
                for file_path in self.cache_dir.rglob("*.png"):
                    file_path.unlink()
                    removed_files += 1
            
            logger.info(f"🗑️ Cleared {removed_files} cached tiles")
            return {
                "success": True,
                "removed_files": removed_files
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": f"Cache clear error: {str(e)}"
            }
    
    def get_cache_stats(self) -> dict:
        """Get cache statistics"""
        try:
            total_size = self._calculate_cache_size()
            size_mb = total_size / (1024 * 1024)
            
            # Count tiles by provider
            provider_stats = {}
            for provider_dir in self.cache_dir.iterdir():
                if provider_dir.is_dir() and provider_dir.name != "cache_metadata.json":
                    tile_count = len(list(provider_dir.rglob("*.png")))
                    provider_stats[provider_dir.name] = tile_count
            
            return {
                "success": True,
                "cache_size_mb": round(size_mb, 2),
                "cache_size_bytes": total_size,
                "max_size_mb": self.max_cache_size_mb,
                "usage_percent": round((size_mb / self.max_cache_size_mb) * 100, 1),
                "provider_stats": provider_stats,
                "cache_directory": str(self.cache_dir)
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": f"Stats calculation error: {str(e)}"
            }