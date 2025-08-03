"""
PLSS Information Extractor
Extracts mapping-relevant PLSS data from parcel schemas independently of polygon processing
"""
import logging
import re
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)

class PLSSExtractor:
    """
    Extracts PLSS information from parcel schema for mapping purposes
    Completely independent of polygon processing
    """
    
    def extract_mapping_info(self, parcel_schema: dict) -> dict:
        """
        Extract PLSS mapping information from parcel schema
        
        Args:
            parcel_schema: Structured parcel data from text-to-schema pipeline
            
        Returns:
            dict: Mapping information needed for PLSS data and visualization
        """
        try:
            # Extract from schema structure
            if "plss_description" in parcel_schema:
                plss_info = self._extract_from_plss_description(parcel_schema["plss_description"])
            elif "descriptions" in parcel_schema:
                # Handle multi-description format
                plss_info = self._extract_from_descriptions(parcel_schema["descriptions"])
            else:
                return {
                    "success": False,
                    "error": "No PLSS information found in schema"
                }
            
            if not plss_info["success"]:
                return plss_info
            
            return {
                "success": True,
                "mapping_data": {
                    "state": plss_info["state"],
                    "county": plss_info.get("county"),
                    "township": plss_info.get("township_parsed"),
                    "range": plss_info.get("range_parsed"), 
                    "section": plss_info.get("section_parsed"),
                    "principal_meridian": plss_info.get("principal_meridian"),
                    "raw_plss": plss_info.get("raw_plss_text"),
                    "bounding_info": {
                        "township_raw": plss_info.get("township_raw"),
                        "range_raw": plss_info.get("range_raw"),
                        "section_raw": plss_info.get("section_raw")
                    }
                },
                "data_requirements": {
                    "needs_plss_data": True,
                    "required_state": plss_info["state"],
                    "data_scope": self._determine_data_scope(plss_info)
                }
            }
            
        except Exception as e:
            logger.error(f"Failed to extract PLSS mapping info: {str(e)}")
            return {
                "success": False,
                "error": f"PLSS extraction failed: {str(e)}"
            }
    
    def _extract_from_plss_description(self, plss_desc: dict) -> dict:
        """Extract from plss_description format"""
        try:
            state = plss_desc.get("state")
            if not state:
                return {"success": False, "error": "No state found in PLSS description"}
            
            # Parse numerical values from text descriptions
            township_parsed = self._parse_township(plss_desc.get("township", ""))
            range_parsed = self._parse_range(plss_desc.get("range", ""))  
            section_parsed = self._parse_section(plss_desc.get("section", ""))
            
            return {
                "success": True,
                "state": state,
                "county": plss_desc.get("county"),
                "principal_meridian": plss_desc.get("principal_meridian"),
                "township_parsed": township_parsed,
                "range_parsed": range_parsed,
                "section_parsed": section_parsed,
                "township_raw": plss_desc.get("township"),
                "range_raw": plss_desc.get("range"),
                "section_raw": plss_desc.get("section"),
                "raw_plss_text": plss_desc.get("raw_text", "")
            }
            
        except Exception as e:
            return {"success": False, "error": f"Failed to parse PLSS description: {str(e)}"}
    
    def _extract_from_descriptions(self, descriptions: List[dict]) -> dict:
        """Extract from multi-description format"""
        try:
            # Find the first complete description with PLSS info
            for desc in descriptions:
                if desc.get("is_complete") and "plss" in desc:
                    plss_data = desc["plss"]
                    
                    # Extract state info (might be nested differently)
                    state = plss_data.get("state") or plss_data.get("location", {}).get("state")
                    if not state:
                        continue
                    
                    return {
                        "success": True,
                        "state": state,
                        "county": plss_data.get("county") or plss_data.get("location", {}).get("county"),
                        "principal_meridian": plss_data.get("principal_meridian"),
                        "township_raw": plss_data.get("township"),
                        "range_raw": plss_data.get("range"), 
                        "section_raw": plss_data.get("section"),
                        "raw_plss_text": plss_data.get("raw_text", "")
                    }
            
            return {"success": False, "error": "No complete descriptions with PLSS data found"}
            
        except Exception as e:
            return {"success": False, "error": f"Failed to parse descriptions: {str(e)}"}
    
    def _parse_township(self, township_text: str) -> Optional[dict]:
        """Parse township text like 'Township Fourteen (14) North' -> {number: 14, direction: 'N'}"""
        if not township_text:
            return None
        
        # Look for number in parentheses first
        paren_match = re.search(r'\((\d+)\)', township_text)
        if paren_match:
            number = int(paren_match.group(1))
        else:
            # Look for standalone number
            num_match = re.search(r'\b(\d+)\b', township_text)
            if num_match:
                number = int(num_match.group(1))
            else:
                return None
        
        # Determine direction
        direction = 'N' if 'north' in township_text.lower() else 'S'
        
        return {"number": number, "direction": direction}
    
    def _parse_range(self, range_text: str) -> Optional[dict]:
        """Parse range text like 'Range Seventy-four (74) West' -> {number: 74, direction: 'W'}"""
        if not range_text:
            return None
        
        # Look for number in parentheses first
        paren_match = re.search(r'\((\d+)\)', range_text)
        if paren_match:
            number = int(paren_match.group(1))
        else:
            # Look for standalone number
            num_match = re.search(r'\b(\d+)\b', range_text)
            if num_match:
                number = int(num_match.group(1))
            else:
                return None
        
        # Determine direction
        direction = 'W' if 'west' in range_text.lower() else 'E'
        
        return {"number": number, "direction": direction}
    
    def _parse_section(self, section_text: str) -> Optional[int]:
        """Parse section text like 'Section Two (2)' -> 2"""
        if not section_text:
            return None
        
        # Look for number in parentheses first
        paren_match = re.search(r'\((\d+)\)', section_text)
        if paren_match:
            return int(paren_match.group(1))
        
        # Look for standalone number
        num_match = re.search(r'\b(\d+)\b', section_text)
        if num_match:
            return int(num_match.group(1))
        
        return None
    
    def _determine_data_scope(self, plss_info: dict) -> dict:
        """Determine what PLSS data scope is needed"""
        return {
            "level": "section",  # Could be "section", "township", "county", "state"
            "priority": "high",
            "estimated_size": "medium"
        } 