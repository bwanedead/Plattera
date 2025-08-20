"""
PLSS Lookup Service
Handles PLSS coordinate lookup operations
"""
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class PLSSLookupService:
    """Service for PLSS coordinate lookup operations"""
    
    def __init__(self):
        """Initialize the service"""
        pass
    
    def lookup_trs_coordinates(self, trs_string: str, state: str = "Wyoming") -> Dict[str, Any]:
        """
        Get PLSS coordinates from TRS string
        
        Args:
            trs_string: TRS string (e.g., 'T14N R74W S2')
            state: State name (default: Wyoming)
            
        Returns:
            dict: Latitude and longitude coordinates
        """
        try:
            if not trs_string:
                return {
                    "success": False,
                    "error": "TRS string required"
                }
            
            logger.info(f"🔍 PLSS lookup request: {trs_string} in {state}")
            
            # Use the existing fast index lookup logic from the projection service
            from pipelines.mapping.georeference.georeference_service import GeoreferenceService
            
            georeference_service = GeoreferenceService()
            result = georeference_service.lookup_plss_fast_index(trs_string, state)
            
            if not result:
                return {
                    "success": False,
                    "error": f"PLSS coordinates not found for {trs_string}"
                }
            
            logger.info(f"✅ PLSS lookup successful: {result}")
            
            return {
                "success": True,
                "latitude": result["lat"],
                "longitude": result["lon"],
                "trs_string": trs_string,
                "state": state
            }
            
        except Exception as e:
            logger.error(f"❌ PLSS lookup failed: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def validate_trs_string(self, trs_string: str) -> Dict[str, Any]:
        """
        Validate TRS string format
        
        Args:
            trs_string: TRS string to validate
            
        Returns:
            dict: Validation result
        """
        try:
            if not trs_string or not isinstance(trs_string, str):
                return {
                    "valid": False,
                    "error": "TRS string must be a non-empty string"
                }
            
            # Basic format validation (this could be expanded)
            trs_upper = trs_string.upper().strip()
            
            # Check for basic TRS pattern
            if not any(char in trs_upper for char in ['T', 'R', 'S']):
                return {
                    "valid": False,
                    "error": "TRS string should contain T (Township), R (Range), and S (Section)"
                }
            
            return {
                "valid": True,
                "normalized": trs_upper
            }
            
        except Exception as e:
            return {
                "valid": False,
                "error": f"Validation error: {str(e)}"
            }


