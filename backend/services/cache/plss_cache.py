"""
PLSS Cache Service
High-level caching interface for PLSS data
"""
import logging
from typing import Dict, Any, Optional
from pathlib import Path

logger = logging.getLogger(__name__)

class PLSSCache:
    """
    High-level caching service for PLSS data
    Provides abstraction over the PLSS data manager
    """
    
    def __init__(self, cache_directory: Optional[str] = None):
        """
        Initialize PLSS cache service
        
        Args:
            cache_directory: Optional custom cache directory
        """
        # Import here to avoid circular imports
        from pipelines.mapping.plss.data_manager import PLSSDataManager
        
        self.data_manager = PLSSDataManager(cache_directory)
        self.cache_stats = {
            "hits": 0,
            "misses": 0,
            "states_cached": 0
        }
    
    def get_state_data(self, state: str) -> dict:
        """
        Get PLSS data for state (cached or download)
        
        Args:
            state: State name
            
        Returns:
            dict: PLSS data result
        """
        try:
            logger.info(f"🗺️ Getting PLSS data for {state}")
            
            # Check if already cached
            if self._is_state_cached(state):
                self.cache_stats["hits"] += 1
                logger.info(f"💾 Cache hit for {state}")
                return self.data_manager._load_cached_data(state)
            
            # Cache miss - ensure data is downloaded
            self.cache_stats["misses"] += 1
            logger.info(f"📥 Cache miss for {state} - ensuring data availability")
            
            result = self.data_manager.ensure_state_data(state)
            if result["success"]:
                self.cache_stats["states_cached"] += 1
            
            return result
            
        except Exception as e:
            logger.error(f"❌ PLSS cache error for {state}: {str(e)}")
            return {
                "success": False,
                "error": f"Cache error: {str(e)}"
            }
    
    def _is_state_cached(self, state: str) -> bool:
        """Check if state data is already cached"""
        try:
            state_dir = self.data_manager.data_dir / state.lower()
            processed_file = state_dir / "processed_plss.json"
            return processed_file.exists()
        except Exception:
            return False
    
    def preload_states(self, states: list) -> dict:
        """
        Preload PLSS data for multiple states
        
        Args:
            states: List of state names
            
        Returns:
            dict: Preload results
        """
        results = {
            "successful": [],
            "failed": [],
            "already_cached": []
        }
        
        for state in states:
            try:
                if self._is_state_cached(state):
                    results["already_cached"].append(state)
                    continue
                
                result = self.get_state_data(state)
                if result["success"]:
                    results["successful"].append(state)
                else:
                    results["failed"].append({
                        "state": state,
                        "error": result.get("error", "Unknown error")
                    })
                    
            except Exception as e:
                results["failed"].append({
                    "state": state,
                    "error": str(e)
                })
        
        logger.info(f"✅ Preload complete: {len(results['successful'])} successful, {len(results['failed'])} failed")
        return {
            "success": True,
            "results": results,
            "summary": {
                "total_requested": len(states),
                "successful": len(results["successful"]),
                "failed": len(results["failed"]),
                "already_cached": len(results["already_cached"])
            }
        }
    
    def clear_state_cache(self, state: str) -> dict:
        """Clear in-memory cache for specific state (NOT data files)"""
        try:
            # FIXED: Only clear in-memory caches, NOT data files
            
            # If the data manager has state-specific cache clearing, call that
            if hasattr(self.data_manager, 'clear_state_memory_cache'):
                self.data_manager.clear_state_memory_cache(state)
                
            logger.info(f"🧹 Cleared in-memory cache for {state} (data files preserved)")
            return {"success": True, "message": f"In-memory cache cleared for {state} (data files preserved)"}
            
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to clear cache for {state}: {str(e)}"
            }
    
    def get_cache_info(self) -> dict:
        """Get cache information and statistics"""
        try:
            # Get available states
            available_states = self.data_manager.get_available_states()
            
            # Check which states are cached
            cached_states = []
            cache_size_mb = 0
            
            for state in available_states["available_states"]:
                if self._is_state_cached(state):
                    cached_states.append(state)
                    # Calculate size (simplified)
                    state_dir = self.data_manager.data_dir / state.lower()
                    try:
                        import os
                        for root, dirs, files in os.walk(state_dir):
                            for file in files:
                                file_path = os.path.join(root, file)
                                cache_size_mb += os.path.getsize(file_path) / (1024 * 1024)
                    except Exception:
                        pass
            
            return {
                "success": True,
                "cache_directory": str(self.data_manager.data_dir),
                "cached_states": cached_states,
                "cache_size_mb": round(cache_size_mb, 2),
                "statistics": self.cache_stats,
                "available_states": available_states["available_states"]
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to get cache info: {str(e)}"
            }
    
    def clear_all_cache(self) -> dict:
        """Clear all PLSS in-memory cache (NOT data files)"""
        try:
            # FIXED: Only clear in-memory caches, NOT data files
            # The data_manager should handle its own in-memory caches
            
            # Reset our own stats
            self.cache_stats = {"hits": 0, "misses": 0, "states_cached": 0}
            
            # If the data manager has cache clearing methods, call those
            if hasattr(self.data_manager, 'clear_memory_cache'):
                self.data_manager.clear_memory_cache()
            
            logger.info("🧹 Cleared PLSS in-memory cache (data files preserved)")
            return {"success": True, "message": "PLSS in-memory cache cleared (data files preserved)"}
            
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to clear PLSS cache: {str(e)}"
            }