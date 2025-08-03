"""
PLSS Data Manager
Handles downloading, caching, and management of PLSS vector data using BLM CadNSDI REST API
"""
import logging
import os
import requests
import geopandas as gpd
from pathlib import Path
from typing import Dict, Any, Optional
import json
import zipfile
import io
from datetime import datetime

logger = logging.getLogger(__name__)

class PLSSDataManager:
    """
    Manages PLSS vector data downloads from BLM CadNSDI and local caching
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
            # Use project directory instead of hidden home directory
            # Navigate up from backend/pipelines/mapping/plss/ to project root
            project_root = Path(__file__).parent.parent.parent.parent.parent
            self.data_dir = project_root / "plss"
        
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.metadata_file = self.data_dir / "metadata.json"
        
        # BLM CadNSDI REST API configuration
        self.blm_mapserver_base = "https://gis.blm.gov/arcgis/rest/services/Cadastral/BLM_Natl_PLSS_CadNSDI/MapServer"
        
        # Layer definitions from BLM CadNSDI
        self.blm_layers = {
            "township": 0,      # Township/Range polygons  
            "section": 1,       # Section (1st div) polygons & centroids
            "special": 3        # Special surveys/lots
        }
        
        # State abbreviations mapping  
        self.state_abbrevs = {
            "Wyoming": "WY", "Colorado": "CO", "Utah": "UT", "Montana": "MT",
            "New Mexico": "NM", "Idaho": "ID", "Nevada": "NV", "Arizona": "AZ",
            "California": "CA", "Oregon": "OR", "Washington": "WA", "Alaska": "AK",
            "North Dakota": "ND", "South Dakota": "SD", "Nebraska": "NE", "Kansas": "KS",
            "Oklahoma": "OK", "Arkansas": "AR", "Louisiana": "LA", "Mississippi": "MS",
            "Alabama": "AL", "Florida": "FL", "Wisconsin": "WI", "Minnesota": "MN",
            "Iowa": "IA", "Missouri": "MO", "Illinois": "IL", "Indiana": "IN",
            "Michigan": "MI", "Ohio": "OH"
        }
        
    def ensure_state_data(self, state: str) -> dict:
        """
        Ensure PLSS data is available for the specified state using BLM CadNSDI API
        
        Args:
            state: State name (e.g., "Wyoming", "Colorado")
            
        Returns:
            dict: Result with vector data path and metadata
        """
        try:
            logger.info(f"📦 Ensuring PLSS data for {state}")
            
            if state not in self.state_abbrevs:
                return {
                    "success": False,
                    "error": f"PLSS data not available for state: {state}"
                }
            
            state_abbr = self.state_abbrevs[state]
            state_dir = self.data_dir / state.lower()
            state_dir.mkdir(exist_ok=True)
            
            # Check if data already exists and is current
            if self._is_data_current(state):
                logger.info(f"✅ Using cached PLSS data for {state}")
                return self._load_cached_data(state)
            
            # Download and cache data from BLM CadNSDI
            logger.info(f"⬇️ Downloading PLSS data for {state} from BLM CadNSDI")
            download_result = self._download_state_data_from_blm(state, state_abbr)
            if not download_result["success"]:
                return download_result
            
            # Process and validate data
            processing_result = self._process_state_data(state)
            if not processing_result["success"]:
                return processing_result
            
            # Update metadata
            self._update_metadata(state, state_abbr)
            
            logger.info(f"✅ PLSS data ready for {state}")
            return self._load_cached_data(state)
            
        except Exception as e:
            logger.error(f"❌ Failed to ensure PLSS data for {state}: {str(e)}")
            return {
                "success": False,
                "error": f"Data management error: {str(e)}"
            }
    
    def _download_state_data_from_blm(self, state: str, state_abbr: str) -> dict:
        """Download PLSS data for state from BLM CadNSDI REST API"""
        try:
            state_dir = self.data_dir / state.lower()
            
            # Download sections (most commonly used layer)
            sections_result = self._download_layer_data(
                state_abbr, 
                self.blm_layers["section"], 
                state_dir / "sections.geojson"
            )
            if not sections_result["success"]:
                return sections_result
            
            # Download townships for broader context
            townships_result = self._download_layer_data(
                state_abbr,
                self.blm_layers["township"],
                state_dir / "townships.geojson"
            )
            if not townships_result["success"]:
                logger.warning(f"Township download failed: {townships_result['error']}")
                # Continue without townships - sections are sufficient
            
            return {
                "success": True,
                "downloaded_layers": ["sections", "townships"],
                "source": "BLM_CadNSDI"
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": f"BLM download failed: {str(e)}"
            }
    
    def _download_layer_data(self, state_abbr: str, layer_id: int, output_path: Path) -> dict:
        """Download specific layer data from BLM CadNSDI"""
        try:
            # Build query URL for BLM CadNSDI
            query_url = f"{self.blm_mapserver_base}/{layer_id}/query"
            
            params = {
                'where': f"STATEABBR='{state_abbr}'",
                'outFields': '*',
                'returnGeometry': 'true', 
                'outSR': '4326',  # WGS84
                'f': 'geojson'
            }
            
            logger.info(f"🌐 Querying BLM CadNSDI layer {layer_id} for {state_abbr}")
            
            # Make request with proper headers
            headers = {
                'User-Agent': 'Plattera/1.0 (PLSS Data Manager)',
                'Accept': 'application/json'
            }
            
            response = requests.get(query_url, params=params, headers=headers, timeout=60)
            response.raise_for_status()
            
            # Validate GeoJSON response
            geojson_data = response.json()
            if 'features' not in geojson_data:
                return {
                    "success": False,
                    "error": f"Invalid GeoJSON response for layer {layer_id}"
                }
            
            feature_count = len(geojson_data['features'])
            logger.info(f"📊 Downloaded {feature_count} features for layer {layer_id}")
            
            # Save to file
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, 'w') as f:
                json.dump(geojson_data, f)
            
            return {
                "success": True,
                "feature_count": feature_count,
                "output_path": str(output_path)
            }
            
        except requests.exceptions.RequestException as e:
            return {
                "success": False,
                "error": f"HTTP request failed: {str(e)}"
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Layer download error: {str(e)}"
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
            sections_file = state_dir / "sections.geojson"
            processed_file = state_dir / "processed_plss.json"
            
            return sections_file.exists() and processed_file.exists()
            
        except Exception as e:
            logger.warning(f"Error checking data currency: {str(e)}")
            return False
    
    def _process_state_data(self, state: str) -> dict:
        """Process downloaded GeoJSON data into usable format"""
        try:
            logger.info(f"⚙️ Processing PLSS data for {state}")
            
            state_dir = self.data_dir / state.lower()
            sections_file = state_dir / "sections.geojson"
            
            if not sections_file.exists():
                return {
                    "success": False,
                    "error": "Sections data file not found"
                }
            
            # Load and process GeoJSON with GeoPandas
            gdf = gpd.read_file(sections_file)
            
            # Calculate bounds and summary statistics
            bounds = gdf.total_bounds  # [minx, miny, maxx, maxy]
            feature_count = len(gdf)
            
            # Create processed summary
            processed_data = {
                "format": "processed_plss",
                "crs": "EPSG:4326",
                "feature_count": feature_count,
                "extent": {
                    "min_lat": float(bounds[1]), "max_lat": float(bounds[3]),
                    "min_lon": float(bounds[0]), "max_lon": float(bounds[2])
                },
                "data_source": "BLM_CadNSDI",
                "layers": {
                    "sections": str(sections_file),
                    "townships": str(state_dir / "townships.geojson") if (state_dir / "townships.geojson").exists() else None
                }
            }
            
            # Save processed metadata
            processed_file = state_dir / "processed_plss.json"
            with open(processed_file, 'w') as f:
                json.dump(processed_data, f, indent=2)
            
            logger.info(f"✅ Processed {feature_count} PLSS features for {state}")
            
            return {
                "success": True,
                "processed_file": str(processed_file),
                "feature_count": feature_count
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
    
    def _update_metadata(self, state: str, state_abbr: str):
        """Update metadata file with state information"""
        try:
            metadata = {}
            if self.metadata_file.exists():
                with open(self.metadata_file, 'r') as f:
                    metadata = json.load(f)
            
            if "states" not in metadata:
                metadata["states"] = {}
            
            metadata["states"][state] = {
                "downloaded": datetime.now().isoformat(),
                "status": "ready",
                "state_abbreviation": state_abbr,
                "source": "BLM_CadNSDI",
                "mapserver_url": self.blm_mapserver_base
            }
            
            with open(self.metadata_file, 'w') as f:
                json.dump(metadata, f, indent=2)
                
        except Exception as e:
            logger.warning(f"Failed to update metadata: {str(e)}")
    
    def get_available_states(self) -> dict:
        """Get list of states with available PLSS data"""
        return {
            "available_states": list(self.state_abbrevs.keys()),
            "data_directory": str(self.data_dir),
            "source": "BLM_CadNSDI"
        }
    
    def get_state_coverage(self, state: str) -> dict:
        """Get coverage information for specific state"""
        if state not in self.state_abbrevs:
            return {
                "success": False,
                "error": f"No data source configured for {state}"
            }
        
        state_dir = self.data_dir / state.lower()
        is_downloaded = (state_dir / "processed_plss.json").exists()
        
        return {
            "success": True,
            "state": state,
            "state_abbreviation": self.state_abbrevs[state],
            "is_downloaded": is_downloaded,
            "data_source": "BLM_CadNSDI",
            "storage_path": str(state_dir)
        }