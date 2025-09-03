"""
PLSS Overlay Generator Service
Handles PLSS overlay generation for visualization
"""
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

class PLSSOverlayGeneratorService:
    """Service for PLSS overlay generation"""
    
    def __init__(self):
        """Initialize the service"""
        pass
    
    def generate_section_overlay(self, plss_description: dict) -> Dict[str, Any]:
        """
        Generate PLSS overlay geometry for visualization
        
        Args:
            plss_description: PLSS description data
            
        Returns:
            dict: Overlay geometry with section, township, and bounds
        """
        try:
            if not plss_description:
                return {
                    "success": False,
                    "error": "Missing plss_description"
                }
            
            from pipelines.mapping.plss.pipeline import PLSSPipeline
            
            plss = PLSSPipeline()
            state = plss_description.get("state")

            # READ-ONLY CHECK: Never trigger data rebuilds during overlay generation
            if not plss.data_manager._is_data_current(state):
                logger.warning(f"🔍 PLSS overlay skipped: Data not available for {state}")
                return {
                    "success": False,
                    "error": f"PLSS data not available for {state}. Please download data first."
                }
            
            # Use new coordinate service for simplified section bounds
            section_result = plss.get_section_view(plss_description)
            if not section_result.get("success"):
                return {
                    "success": False,
                    "error": section_result.get("error")
                }
            
            # Calculate section geometry and bounds
            centroid = section_result["centroid"]
            section_geometry = self.build_section_geometry(centroid)
            bounds = self.calculate_section_bounds(centroid)
            
            return {
                "success": True,
                "section": section_geometry,
                "township": None,  # Simplified - no township overlay for now
                "splits": [],      # Simplified - no quarter splits for now
                "bounds": bounds,
            }
            
        except Exception as e:
            logger.error(f"plss_overlay error: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def build_section_geometry(self, centroid: dict) -> dict:
        """
        Build section geometry from centroid
        
        Args:
            centroid: Section centroid with lat/lon
            
        Returns:
            dict: GeoJSON polygon geometry
        """
        try:
            lat, lon = centroid["lat"], centroid["lon"]
            bounds_size = 0.007  # Half a section in degrees (approximate)
            
            return {
                "type": "Polygon",
                "coordinates": [[[lon - bounds_size, lat - bounds_size],
                               [lon + bounds_size, lat - bounds_size],
                               [lon + bounds_size, lat + bounds_size],
                               [lon - bounds_size, lat + bounds_size],
                               [lon - bounds_size, lat - bounds_size]]]
            }
        except Exception as e:
            logger.error(f"Error building section geometry: {str(e)}")
            raise e
    
    def calculate_section_bounds(self, centroid: dict) -> dict:
        """
        Calculate section bounds from centroid
        
        Args:
            centroid: Section centroid with lat/lon
            
        Returns:
            dict: Bounds with min/max lat/lon
        """
        try:
            lat, lon = centroid["lat"], centroid["lon"]
            bounds_size = 0.007  # Half a section in degrees (approximate)
            
            return {
                "min_lon": lon - bounds_size, 
                "min_lat": lat - bounds_size,
                "max_lon": lon + bounds_size, 
                "max_lat": lat + bounds_size
            }
        except Exception as e:
            logger.error(f"Error calculating section bounds: {str(e)}")
            raise e


