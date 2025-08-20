"""
PLSS Section View Service
Handles PLSS section view operations and bounds calculation
"""
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

class PLSSSectionViewService:
    """Service for PLSS section view operations"""
    
    def __init__(self):
        """Initialize the service"""
        pass
    
    def get_section_view(self, plss_description: dict, padding: float = 0.1) -> Dict[str, Any]:
        """
        Get section view with center and padded bounds
        
        Args:
            plss_description: PLSS description data
            padding: Padding factor for bounds (default: 0.1)
            
        Returns:
            dict: Section view with center and bounds
        """
        try:
            if not plss_description:
                return {
                    "success": False,
                    "error": "Missing plss_description"
                }
            
            from pipelines.mapping.plss.pipeline import PLSSPipeline
            
            plss = PLSSPipeline()
            res = plss.get_section_view(plss_description)
            
            if not res.get("success"):
                return {
                    "success": False,
                    "error": res.get("error", "PLSS section lookup failed")
                }
            
            center = res["center"]
            bounds = res["bounds"]
            
            # Calculate padded bounds
            padded_bounds = self.calculate_padded_bounds(bounds, padding)
            
            return {
                "success": True,
                "center": center,
                "bounds": padded_bounds
            }
            
        except Exception as e:
            logger.error(f"❌ Section view lookup failed: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def calculate_padded_bounds(self, bounds: dict, padding: float) -> dict:
        """
        Calculate padded bounds for a section
        
        Args:
            bounds: Original bounds dict with min/max lat/lon
            padding: Padding factor (e.g., 0.1 for 10% padding)
            
        Returns:
            dict: Padded bounds
        """
        try:
            lat_pad = (bounds["max_lat"] - bounds["min_lat"]) * padding
            lon_pad = (bounds["max_lon"] - bounds["min_lon"]) * padding
            
            return {
                "min_lat": bounds["min_lat"] - lat_pad,
                "max_lat": bounds["max_lat"] + lat_pad,
                "min_lon": bounds["min_lon"] - lon_pad,
                "max_lon": bounds["max_lon"] + lon_pad,
            }
        except Exception as e:
            logger.error(f"Error calculating padded bounds: {str(e)}")
            # Return original bounds if padding calculation fails
            return bounds
    
    def validate_plss_description(self, plss_description: dict) -> Dict[str, Any]:
        """
        Validate PLSS description format
        
        Args:
            plss_description: PLSS description to validate
            
        Returns:
            dict: Validation result
        """
        try:
            required_fields = ["state", "township_number", "township_direction", 
                             "range_number", "range_direction", "section_number"]
            
            missing_fields = []
            for field in required_fields:
                if field not in plss_description:
                    missing_fields.append(field)
            
            if missing_fields:
                return {
                    "valid": False,
                    "error": f"Missing required fields: {', '.join(missing_fields)}"
                }
            
            return {
                "valid": True
            }
            
        except Exception as e:
            return {
                "valid": False,
                "error": f"Validation error: {str(e)}"
            }


