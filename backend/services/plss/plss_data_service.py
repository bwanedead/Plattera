"""
PLSS Data Service
Handles PLSS data management operations without breaking existing download functionality
"""
import logging
from typing import Dict, Any
from pathlib import Path

logger = logging.getLogger(__name__)

class PLSSDataService:
    """Service for PLSS data management operations"""
    
    def __init__(self):
        """Initialize the service"""
        self._data_manager = None
    
    def _get_data_manager(self):
        """Lazy load data manager to avoid import issues"""
        if self._data_manager is None:
            from pipelines.mapping.plss.data_manager import PLSSDataManager
            self._data_manager = PLSSDataManager()
        return self._data_manager
    
    async def extract_mapping_info(self, request: dict) -> dict:
        """
        Extract PLSS mapping information from schema data
        
        Args:
            request: Schema data request
            
        Returns:
            dict: Extracted mapping info with data status
        """
        try:
            # Import and use extractor
            from pipelines.mapping.plss.plss_extractor import PLSSExtractor
            from services.registry import get_registry
            
            extractor = PLSSExtractor()
            result = extractor.extract_mapping_info(request)
            
            if not result["success"]:
                return result
            
            # Check if PLSS data is available for the required state
            state = result["mapping_data"]["state"]
            registry = get_registry()
            plss_cache = registry.get_service("plss_cache")
            
            data_status = await plss_cache.check_state_data(state)
            
            return {
                "success": True,
                "plss_info": result["mapping_data"],
                "data_requirements": result["data_requirements"], 
                "data_status": data_status
            }
            
        except Exception as e:
            logger.error(f"PLSS info extraction failed: {str(e)}")
            return {
                "success": False,
                "error": f"Failed to extract PLSS info: {str(e)}"
            }
    
    def check_state_data_status(self, state: str) -> Dict[str, Any]:
        """
        Check if PLSS data exists for a state without downloading
        
        Args:
            state: State code to check
            
        Returns:
            dict: Data availability status
        """
        try:
            data_manager = self._get_data_manager()
            
            # Check if data exists locally  
            has_data = data_manager._is_data_current(state)
            
            # Also check if parquet files exist for optimal performance
            state_dir = data_manager.data_dir / state.lower()
            parquet_dir = state_dir / "parquet"
            has_parquets = parquet_dir.exists() and any(parquet_dir.glob("*.parquet"))
            
            # Data is only fully available if both FGDB and parquets exist
            fully_available = has_data and has_parquets
            
            return {
                "available": fully_available,
                "state": state,
                "message": f"PLSS data for {state} {'is fully available' if fully_available else 'needs parquet generation' if has_data else 'needs to be downloaded'}",
                "has_fgdb": has_data,
                "has_parquets": has_parquets
            }
        except Exception as e:
            logger.error(f"❌ Error checking PLSS data status for {state}: {str(e)}")
            return {"available": False, "error": str(e)}
    
    def download_state_data(self, state: str, request: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Download PLSS data for a state (explicit user action)
        
        Args:
            state: State code to download
            request: Optional request parameters
            
        Returns:
            dict: Download result
        """
        try:
            logger.info(f"📦 User requested download of PLSS data for {state}")
            data_manager = self._get_data_manager()
            
            # Perform the download (bulk FGDB for WY) - keeping existing logic intact
            result = data_manager.ensure_state_data(state)
            
            if result.get('success'):
                # Optional: prefetch sections for the hinted township/range
                # In bulk FGDB mode, no per-township prefetch is required
                logger.info(f"✅ PLSS data download completed for {state}")
                return {
                    "success": True,
                    "state": state,
                    "message": f"PLSS data for {state} downloaded successfully",
                    "features_count": result.get('features_count', 0),
                    "prefetch": result.get("prefetch_sections")
                }
            else:
                return {"success": False, "error": result.get('error', 'Unknown error')}
                
        except Exception as e:
            logger.error(f"❌ PLSS data download failed for {state}: {str(e)}")
            return {"success": False, "error": str(e)}
    
    def start_background_download(self, state: str) -> Dict[str, Any]:
        """
        Start background download for PLSS data
        
        Args:
            state: State code to download
            
        Returns:
            dict: Background download start result
        """
        try:
            data_manager = self._get_data_manager()
            return data_manager.start_bulk_install_background(state)
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def get_download_progress(self, state: str) -> Dict[str, Any]:
        """
        Get progress of background download
        
        Args:
            state: State code to check
            
        Returns:
            dict: Download progress
        """
        try:
            data_manager = self._get_data_manager()
            return data_manager.get_progress(state)
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def cancel_download(self, state: str) -> Dict[str, Any]:
        """
        Cancel background download
        
        Args:
            state: State code to cancel
            
        Returns:
            dict: Cancellation result
        """
        try:
            data_manager = self._get_data_manager()
            return data_manager.request_cancel(state)
        except Exception as e:
            return {"success": False, "error": str(e)}
