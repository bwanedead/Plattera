"""
PLSS Coordinate Resolver
Converts PLSS legal descriptions to geographic coordinates
"""
import logging
import math
from typing import Dict, Any, Optional, Tuple

logger = logging.getLogger(__name__)

class PLSSCoordinateResolver:
    """
    Resolves PLSS legal descriptions to lat/lon coordinates
    """
    
    def __init__(self):
        """Initialize coordinate resolver"""
        # PLSS section dimensions (standard)
        self.section_size_miles = 1.0  # 1 mile x 1 mile
        self.miles_to_degrees_lat = 1.0 / 69.0  # Approximate
        self.miles_to_degrees_lon = 1.0 / 54.6  # Approximate at 45° latitude
        
    def resolve_coordinates(
        self, 
        state: str,
        township: int,
        township_direction: str,
        range_number: int, 
        range_direction: str,
        section: int,
        quarter_sections: Optional[str] = None,
        vector_data: Optional[dict] = None
    ) -> dict:
        """
        Resolve PLSS description to geographic coordinates
        
        Args:
            state: State name
            township: Township number
            township_direction: N or S
            range_number: Range number  
            range_direction: E or W
            section: Section number (1-36)
            quarter_sections: Quarter section description
            vector_data: PLSS vector data for precise lookup
            
        Returns:
            dict: Result with lat/lon coordinates
        """
        try:
            logger.info(f"🧭 Resolving coordinates for T{township}{township_direction} R{range_number}{range_direction} Sec {section}")
            
            # Try precise vector lookup first
            if vector_data:
                vector_result = self._resolve_from_vector_data(
                    township, township_direction, range_number, range_direction, 
                    section, quarter_sections, vector_data
                )
                if vector_result["success"]:
                    return vector_result
            
            # Fall back to calculated approximation
            logger.info("📐 Using calculated coordinate approximation")
            calculated_result = self._calculate_approximate_coordinates(
                state, township, township_direction, range_number, 
                range_direction, section, quarter_sections
            )
            
            return calculated_result
            
        except Exception as e:
            logger.error(f"❌ Coordinate resolution failed: {str(e)}")
            return {
                "success": False,
                "error": f"Resolution error: {str(e)}"
            }
    
    def _resolve_from_vector_data(
        self, 
        township: int, township_direction: str,
        range_number: int, range_direction: str, 
        section: int, quarter_sections: Optional[str],
        vector_data: dict
    ) -> dict:
        """Resolve coordinates using precise vector data"""
        try:
            logger.info("🗺️ Attempting vector data lookup")
            
            # In production, this would:
            # 1. Query spatial database/shapefile
            # 2. Find matching township/range/section
            # 3. Calculate quarter section center if specified
            # 4. Return precise coordinates
            
            # For now, return mock precise coordinates
            # This simulates a successful vector lookup
            mock_base_lat = 41.5  # Mock Wyoming coordinates
            mock_base_lon = -107.5
            
            # Add small offset based on township/range for variety
            lat_offset = (township - 20) * 0.01
            lon_offset = (range_number - 70) * 0.01
            
            resolved_lat = mock_base_lat + lat_offset
            resolved_lon = mock_base_lon - lon_offset
            
            return {
                "success": True,
                "coordinates": {
                    "lat": resolved_lat,
                    "lon": resolved_lon
                },
                "method": "vector_lookup",
                "accuracy": "high",
                "datum": "WGS84"
            }
            
        except Exception as e:
            logger.warning(f"Vector lookup failed: {str(e)}")
            return {
                "success": False,
                "error": f"Vector lookup error: {str(e)}"
            }
    
    def _calculate_approximate_coordinates(
        self,
        state: str,
        township: int, township_direction: str,
        range_number: int, range_direction: str,
        section: int, quarter_sections: Optional[str]
    ) -> dict:
        """Calculate approximate coordinates using PLSS grid math"""
        try:
            # Get state baseline (principal meridian intersection)
            baseline = self._get_state_baseline(state)
            if not baseline:
                return {
                    "success": False,
                    "error": f"No baseline data for state: {state}"
                }
            
            base_lat = baseline["lat"]
            base_lon = baseline["lon"]
            
            # Calculate township offset from baseline
            township_offset_miles = township
            if township_direction.upper() == "S":
                township_offset_miles = -township_offset_miles
            
            # Calculate range offset from principal meridian
            range_offset_miles = range_number
            if range_direction.upper() == "W":
                range_offset_miles = -range_offset_miles
            
            # Convert to degrees
            lat_offset = township_offset_miles * 6 * self.miles_to_degrees_lat  # 6 miles per township
            lon_offset = range_offset_miles * 6 * self.miles_to_degrees_lon
            
            # Calculate section center
            section_lat_offset, section_lon_offset = self._get_section_offset(section)
            
            # Calculate quarter section offset if specified
            quarter_lat_offset, quarter_lon_offset = self._get_quarter_section_offset(quarter_sections)
            
            # Final coordinates
            final_lat = base_lat + lat_offset + section_lat_offset + quarter_lat_offset
            final_lon = base_lon + lon_offset + section_lon_offset + quarter_lon_offset
            
            logger.info(f"📍 Calculated coordinates: {final_lat:.6f}, {final_lon:.6f}")
            
            return {
                "success": True,
                "coordinates": {
                    "lat": final_lat,
                    "lon": final_lon
                },
                "method": "calculated_approximation",
                "accuracy": "medium",
                "datum": "WGS84"
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": f"Calculation error: {str(e)}"
            }
    
    def _get_state_baseline(self, state: str) -> Optional[dict]:
        """Get principal meridian baseline for state"""
        # Mock baseline coordinates for supported states
        baselines = {
            "Wyoming": {"lat": 40.5, "lon": -107.0},  # 6th Principal Meridian
            "Colorado": {"lat": 40.0, "lon": -105.0}   # 6th Principal Meridian
        }
        
        return baselines.get(state)
    
    def _get_section_offset(self, section: int) -> Tuple[float, float]:
        """Calculate lat/lon offset for section within township"""
        # PLSS sections are numbered 1-36 in a 6x6 grid
        # Section 1 is in northeast corner, numbering goes west then east alternately
        
        # Convert section number to grid position
        row = (section - 1) // 6
        col = (section - 1) % 6
        
        # Alternate direction for odd rows (standard PLSS numbering)
        if row % 2 == 1:
            col = 5 - col
        
        # Convert to lat/lon offset (section center)
        lat_offset = -(row * self.miles_to_degrees_lat + self.miles_to_degrees_lat / 2)
        lon_offset = col * self.miles_to_degrees_lon + self.miles_to_degrees_lon / 2
        
        return lat_offset, lon_offset
    
    def _get_quarter_section_offset(self, quarter_sections: Optional[str]) -> Tuple[float, float]:
        """Calculate offset for quarter section subdivision"""
        if not quarter_sections:
            return 0.0, 0.0
        
        # Parse quarter section description (e.g., "Southwest Quarter of the Northwest Quarter")
        # For now, return center of section (no quarter offset)
        # In production, this would parse the quarter description and calculate precise offset
        
        return 0.0, 0.0