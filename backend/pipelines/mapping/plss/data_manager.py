"""
PLSS Data Manager
Handles downloading, caching, and management of PLSS vector data
"""
import logging
import os
from pathlib import Path
from typing import Dict, Any, Optional
import urllib.request
import zipfile
import json

logger = logging.getLogger(__name__)

class PLSSDataManager:
    """
    Manages PLSS vector data downloads and local caching
    """
    
    def __init__(self, data_directory: Optional[str] = None):
        """
        Initialize data manager
        
        Args:
            data_directory: Custom directory for PLSS data storage
        """
        if data_directory:
            self.data_dir = Path(data_directory)
        else:
            # Default to user's home directory
            self.data_dir = Path.home() / ".plattera" / "plss"
        
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.metadata_file = self.data_dir / "metadata.json"
        
        # PLSS data sources (URLs would be real BLM/USGS endpoints)
        self.data_sources = {
            "Wyoming": {
                "url": "https://example-blm-data.gov/wyoming/plss.zip", 
                "format": "shapefile",
                "crs": "EPSG:4326"
            },
            "Colorado": {
                "url": "https://example-blm-data.gov/colorado/plss.zip",
                "format": "shapefile", 
                "crs": "EPSG:4326"
            }
            # Add more states as needed
        }
        
    def ensure_state_data(self, state: str) -> dict:
        """
        Ensure PLSS data is available for the specified state
        
        Args:
            state: State name (e.g., "Wyoming", "Colorado")
            
        Returns:
            dict: Result with vector data path and metadata
        """
        try:
            logger.info(f"📦 Ensuring PLSS data for {state}")
            
            if state not in self.data_sources:
                return {
                    "success": False,
                    "error": f"PLSS data not available for state: {state}"
                }
            
            state_dir = self.data_dir / state.lower()
            state_dir.mkdir(exist_ok=True)
            
            # Check if data already exists and is current
            if self._is_data_current(state):
                logger.info(f"✅ Using cached PLSS data for {state}")
                return self._load_cached_data(state)
            
            # Download and cache data
            logger.info(f"⬇️ Downloading PLSS data for {state}")
            download_result = self._download_state_data(state)
            if not download_result["success"]:
                return download_result
            
            # Process and validate data
            processing_result = self._process_state_data(state)
            if not processing_result["success"]:
                return processing_result
            
            # Update metadata
            self._update_metadata(state)
            
            logger.info(f"✅ PLSS data ready for {state}")
            return self._load_cached_data(state)
            
        except Exception as e:
            logger.error(f"❌ Failed to ensure PLSS data for {state}: {str(e)}")
            return {
                "success": False,
                "error": f"Data management error: {str(e)}"
            }
    
    def _is_data_current(self, state: str) -> bool:
        """Check if cached data exists and is current"""
        try:
            if not self.metadata_file.exists():
                return False
            
            with open(self.metadata_file, 'r') as f:
                metadata = json.load(f)
            
            state_data = metadata.get("states", {}).get(state)
            if not state_data:
                return False
            
            # Check if files exist
            state_dir = self.data_dir / state.lower()
            data_file = state_dir / "plss_sections.shp"
            
            return data_file.exists()
            
        except Exception as e:
            logger.warning(f"Error checking data currency: {str(e)}")
            return False
    
    def _download_state_data(self, state: str) -> dict:
        """Download PLSS data for state"""
        try:
            source_info = self.data_sources[state]
            state_dir = self.data_dir / state.lower()
            zip_path = state_dir / "plss_data.zip"
            
            # For now, create mock data structure
            # In production, this would download from actual BLM/USGS servers
            logger.info(f"🔧 Creating mock PLSS data structure for {state}")
            
            # Create mock shapefile structure
            mock_files = [
                "plss_sections.shp", "plss_sections.shx", 
                "plss_sections.dbf", "plss_sections.prj"
            ]
            
            for mock_file in mock_files:
                mock_path = state_dir / mock_file
                mock_path.touch()
            
            return {
                "success": True,
                "download_path": str(zip_path),
                "source_url": source_info["url"]
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": f"Download failed: {str(e)}"
            }
    
    def _process_state_data(self, state: str) -> dict:
        """Process downloaded data into usable format"""
        try:
            logger.info(f"⚙️ Processing PLSS data for {state}")
            
            # In production, this would:
            # 1. Extract shapefiles from zip
            # 2. Validate CRS and geometry
            # 3. Create spatial indexes
            # 4. Generate lookup tables
            
            # For now, create mock processing result
            state_dir = self.data_dir / state.lower()
            processed_file = state_dir / "processed_plss.json"
            
            mock_processed_data = {
                "format": "processed_plss",
                "crs": "EPSG:4326",
                "feature_count": 1000,  # Mock feature count
                "extent": {
                    "min_lat": 41.0, "max_lat": 45.0,
                    "min_lon": -111.0, "max_lon": -104.0
                }
            }
            
            with open(processed_file, 'w') as f:
                json.dump(mock_processed_data, f, indent=2)
            
            return {
                "success": True,
                "processed_file": str(processed_file)
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": f"Processing failed: {str(e)}"
            }
    
    def _load_cached_data(self, state: str) -> dict:
        """Load cached PLSS data for state"""
        try:
            state_dir = self.data_dir / state.lower()
            processed_file = state_dir / "processed_plss.json"
            
            if not processed_file.exists():
                return {
                    "success": False,
                    "error": "Processed data file not found"
                }
            
            with open(processed_file, 'r') as f:
                vector_data = json.load(f)
            
            return {
                "success": True,
                "vector_data": vector_data,
                "data_path": str(state_dir),
                "source": "cached"
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to load cached data: {str(e)}"
            }
    
    def _update_metadata(self, state: str):
        """Update metadata file with state information"""
        try:
            metadata = {}
            if self.metadata_file.exists():
                with open(self.metadata_file, 'r') as f:
                    metadata = json.load(f)
            
            if "states" not in metadata:
                metadata["states"] = {}
            
            from datetime import datetime
            metadata["states"][state] = {
                "downloaded": datetime.now().isoformat(),
                "status": "ready",
                "source": self.data_sources[state]["url"]
            }
            
            with open(self.metadata_file, 'w') as f:
                json.dump(metadata, f, indent=2)
                
        except Exception as e:
            logger.warning(f"Failed to update metadata: {str(e)}")
    
    def get_available_states(self) -> dict:
        """Get list of states with available PLSS data"""
        return {
            "available_states": list(self.data_sources.keys()),
            "data_directory": str(self.data_dir)
        }
    
    def get_state_coverage(self, state: str) -> dict:
        """Get coverage information for specific state"""
        if state not in self.data_sources:
            return {
                "success": False,
                "error": f"No data source configured for {state}"
            }
        
        state_dir = self.data_dir / state.lower()
        is_downloaded = (state_dir / "processed_plss.json").exists()
        
        return {
            "success": True,
            "state": state,
            "is_downloaded": is_downloaded,
            "data_source": self.data_sources[state],
            "storage_path": str(state_dir)
        }