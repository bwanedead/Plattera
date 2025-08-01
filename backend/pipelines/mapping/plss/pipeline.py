"""
PLSS Pipeline
Main orchestrator for PLSS coordinate resolution and data management
"""
import logging
from typing import Dict, Any, Optional, Tuple
from pathlib import Path

from .data_manager import PLSSDataManager
from .coordinate_resolver import PLSSCoordinateResolver
from .vector_processor import PLSSVectorProcessor

logger = logging.getLogger(__name__)

class PLSSPipeline:
    """
    Pipeline for resolving PLSS descriptions to geographic coordinates
    """
    
    def __init__(self, data_directory: Optional[str] = None):
        """
        Initialize PLSS pipeline
        
        Args:
            data_directory: Optional custom directory for PLSS data storage
        """
        self.data_manager = PLSSDataManager(data_directory)
        self.coordinate_resolver = PLSSCoordinateResolver()
        self.vector_processor = PLSSVectorProcessor()
        
    def resolve_starting_point(self, plss_description: dict) -> dict:
        """
        Convert PLSS description to lat/lon coordinates
        
        Args:
            plss_description: PLSS data from schema (state, township, range, section, etc.)
            
        Returns:
            dict: Result with lat/lon coordinates and metadata
        """
        try:
            logger.info("🗺️ Starting PLSS coordinate resolution")
            
            # Validate PLSS description
            validation_result = self._validate_plss_description(plss_description)
            if not validation_result["valid"]:
                return {
                    "success": False,
                    "error": f"Invalid PLSS description: {validation_result['errors']}"
                }
            
            # Extract required components
            state = plss_description.get("state")
            township = plss_description.get("township_number")
            township_dir = plss_description.get("township_direction")
            range_num = plss_description.get("range_number") 
            range_dir = plss_description.get("range_direction")
            section = plss_description.get("section_number")
            quarter_sections = plss_description.get("quarter_sections")
            
            logger.info(f"📍 Resolving: T{township}{township_dir} R{range_num}{range_dir} Sec {section} {quarter_sections}")
            
            # Ensure PLSS data is available for state
            data_result = self.data_manager.ensure_state_data(state)
            if not data_result["success"]:
                return {
                    "success": False,
                    "error": f"Failed to load PLSS data for {state}: {data_result['error']}"
                }
            
            # Resolve coordinates using vector data
            resolution_result = self.coordinate_resolver.resolve_coordinates(
                state=state,
                township=township,
                township_direction=township_dir,
                range_number=range_num,
                range_direction=range_dir,
                section=section,
                quarter_sections=quarter_sections,
                vector_data=data_result["vector_data"]
            )
            
            if not resolution_result["success"]:
                return {
                    "success": False,
                    "error": f"Coordinate resolution failed: {resolution_result['error']}"
                }
            
            logger.info(f"✅ PLSS resolution successful: {resolution_result['coordinates']}")
            
            return {
                "success": True,
                "coordinates": resolution_result["coordinates"],
                "anchor_point": {
                    "lat": resolution_result["coordinates"]["lat"],
                    "lon": resolution_result["coordinates"]["lon"],
                    "datum": resolution_result.get("datum", "WGS84"),
                    "accuracy": resolution_result.get("accuracy", "unknown")
                },
                "metadata": {
                    "plss_reference": f"T{township}{township_dir} R{range_num}{range_dir} Sec {section}",
                    "quarter_sections": quarter_sections,
                    "state": state,
                    "data_source": data_result.get("source"),
                    "resolution_method": resolution_result.get("method")
                }
            }
            
        except Exception as e:
            logger.error(f"❌ PLSS pipeline failed: {str(e)}")
            return {
                "success": False,
                "error": f"PLSS pipeline error: {str(e)}"
            }
    
    def _validate_plss_description(self, plss_description: dict) -> dict:
        """Validate PLSS description has required fields"""
        errors = []
        
        required_fields = [
            "state", "township_number", "township_direction",
            "range_number", "range_direction", "section_number"
        ]
        
        for field in required_fields:
            if field not in plss_description or plss_description[field] is None:
                errors.append(f"Missing required field: {field}")
        
        # Validate ranges
        if "township_number" in plss_description:
            township = plss_description["township_number"]
            if not isinstance(township, int) or township < 1 or township > 50:
                errors.append("Township number must be between 1 and 50")
        
        if "range_number" in plss_description:
            range_num = plss_description["range_number"]
            if not isinstance(range_num, int) or range_num < 1 or range_num > 100:
                errors.append("Range number must be between 1 and 100")
        
        if "section_number" in plss_description:
            section = plss_description["section_number"]
            if not isinstance(section, int) or section < 1 or section > 36:
                errors.append("Section number must be between 1 and 36")
        
        return {
            "valid": len(errors) == 0,
            "errors": errors
        }
    
    def get_available_states(self) -> dict:
        """Get list of states with available PLSS data"""
        return self.data_manager.get_available_states()
    
    def get_state_coverage(self, state: str) -> dict:
        """Get coverage information for a specific state"""
        return self.data_manager.get_state_coverage(state)