"""
PLSS Pipeline
Main orchestrator for PLSS coordinate resolution and data management
"""
import logging
from typing import Dict, Any, Optional, Tuple
from pathlib import Path

from .data_manager import PLSSDataManager
from .coordinate_service import PLSSCoordinateService
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
        self.coordinate_service = PLSSCoordinateService()
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
            principal_meridian = plss_description.get("principal_meridian")
            
            try:
                logger.info(
                    f"📍 Resolving: T{township}{township_dir} R{range_num}{range_dir} Sec {section} {quarter_sections}"
                )
            except Exception:
                logger.info("📍 Resolving PLSS anchor")
            if principal_meridian:
                logger.info(f"🧭 Principal Meridian: {principal_meridian}")
            
            # Ensure PLSS data is available for state
            data_result = self.data_manager.ensure_state_data(state)
            if not data_result["success"]:
                return {
                    "success": False,
                    "error": f"Failed to load PLSS data for {state}: {data_result['error']}"
                }
            # Bulk FGDB mode: use vector_data as-is
            prepared_vector = {"success": True, "vector_data": data_result.get("vector_data")}
            
            # Resolve coordinates using new coordinate service
            resolution_result = self.coordinate_service.resolve_coordinates(
                state=state,
                township=township,
                township_direction=township_dir,
                range_number=range_num,
                range_direction=range_dir,
                section=section,
                quarter_sections=quarter_sections,
                principal_meridian=principal_meridian
            )
            
            if not resolution_result["success"]:
                return {
                    "success": False,
                    "error": f"Coordinate resolution failed: {resolution_result['error']}"
                }
            
            logger.info(
                f"✅ PLSS resolution successful: {resolution_result['coordinates']} method={resolution_result.get('method')}"
            )
            
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

    def _prepare_vector_data_for_township(self, vector_data: dict, plss_description: dict) -> dict:
        """Ensure per-township sections exist and return updated vector_data with sections path.

        Keeps townships statewide file reference intact.
        """
        try:
            state = plss_description.get("state")
            t = int(plss_description.get("township_number"))
            td = (plss_description.get("township_direction") or "").upper()
            r = int(plss_description.get("range_number"))
            rd = (plss_description.get("range_direction") or "").upper()

            ensure = self.data_manager.ensure_township_sections(state, t, td, r, rd)
            if not ensure.get("success"):
                return {"success": False, "error": ensure.get("error", "Unable to ensure township sections")}

            updated = dict(vector_data)
            layers = dict(vector_data.get("layers", {}))
            layers["sections"] = ensure["output_path"]
            updated["layers"] = layers
            return {"success": True, "vector_data": updated}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
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

    def get_section_view(self, plss_description: dict) -> dict:
        """Get section information using coordinate service"""
        try:
            state = plss_description.get("state")
            township = plss_description.get("township_number")
            township_dir = plss_description.get("township_direction")
            range_num = plss_description.get("range_number")
            range_dir = plss_description.get("range_direction")
            section = plss_description.get("section_number")
            
            # Use coordinate service to get section data
            result = self.coordinate_service.resolve_coordinates(
                state=state,
                township=township,
                township_direction=township_dir,
                range_number=range_num,
                range_direction=range_dir,
                section=section
            )
            
            if result.get("success"):
                return {
                    "success": True,
                    "centroid": result.get("coordinates"),
                    "bounds": result.get("bounds")
                }
            else:
                return result
                
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_section_corner(self, plss_description: dict, corner_label: str) -> dict:
        """Get section corner using coordinate service"""
        try:
            # Use get_section_view and calculate corner offset
            section_result = self.get_section_view(plss_description)
            if not section_result.get("success"):
                return section_result
                
            # For now, return the centroid - in future could calculate actual corners
            return {
                "success": True,
                "coordinates": section_result["centroid"],
                "corner": corner_label,
                "note": "Corner calculation not yet implemented - returning section centroid"
            }
            
        except Exception as e:
            return {"success": False, "error": str(e)}