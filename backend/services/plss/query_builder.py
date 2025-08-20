"""
PLSS Query Builder
Clean query specification builder for PLSS overlay operations
"""
import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

class PLSSQueryBuilder:
    """
    Builds clean, structured queries for PLSS overlay operations
    """
    
    @staticmethod
    def build_regional_query(
        layer: str,
        state: str,
        bounds: Dict[str, Optional[float]]
    ) -> Dict[str, Any]:
        """
        Build query for regional (all-in-view) overlay mode
        
        Args:
            layer: PLSS layer (townships, ranges, sections, quarter_sections, grid)
            state: State name (e.g., 'Wyoming')
            bounds: Spatial bounds {min_lon, min_lat, max_lon, max_lat}
            
        Returns:
            dict: Structured query specification
        """
        query = {
            "type": "regional",
            "layer": layer,
            "state": state,
            "bounds": bounds
        }
        
        logger.info(f"🌍 Built regional query for {layer} in {state}")
        return query
    
    @staticmethod
    def build_container_query(
        layer: str,
        state: str,
        schema_data: Dict[str, Any],
        container_bounds: Optional[Dict[str, float]] = None
    ) -> Dict[str, Any]:
        """
        Build query for container (parcel-relative) overlay mode
        
        Args:
            layer: PLSS layer type
            state: State name
            schema_data: Schema data containing PLSS information
            container_bounds: Optional spatial bounds
            
        Returns:
            dict: Structured query specification with extracted PLSS info
        """
        # Extract PLSS information from schema data
        plss_info = PLSSQueryBuilder._extract_plss_info(schema_data)
        
        if not plss_info:
            raise ValueError("No PLSS information found in schema data for container query")
        
        query = {
            "type": "container",
            "layer": layer,
            "state": state,
            "plss_info": plss_info,
            "container_bounds": container_bounds
        }
        
        logger.info(f"📦 Built container query for {layer} with PLSS: T{plss_info.get('township_number')}{plss_info.get('township_direction')} R{plss_info.get('range_number')}{plss_info.get('range_direction')}")
        
        return query
    
    @staticmethod
    def build_exact_query(
        layer: str,
        state: str,
        trs_filter: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Build query for exact TRS coordinate overlay
        
        Args:
            layer: PLSS layer type
            state: State name
            trs_filter: TRS coordinates {t, td, r, rd, s}
            
        Returns:
            dict: Structured query specification
        """
        # Filter out None values
        clean_trs = {k: v for k, v in trs_filter.items() if v is not None}
        
        if not clean_trs:
            raise ValueError("No TRS coordinates provided for exact query")
        
        query = {
            "type": "exact",
            "layer": layer,
            "state": state,
            "trs_filter": clean_trs
        }
        
        logger.info(f"🎯 Built exact query for {layer} with TRS: {clean_trs}")
        
        return query
    
    @staticmethod
    def build_multi_exact_query(
        layer: str,
        state: str,
        feature_list: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Build query for multiple exact TRS coordinates
        
        Args:
            layer: PLSS layer type
            state: State name
            feature_list: List of TRS coordinate dictionaries
            
        Returns:
            dict: Structured query specification
        """
        if not feature_list:
            raise ValueError("Empty feature list for multi-exact query")
        
        # Clean each TRS specification
        clean_features = []
        for trs_spec in feature_list:
            clean_trs = {k: v for k, v in trs_spec.items() if v is not None}
            if clean_trs:
                clean_features.append(clean_trs)
        
        if not clean_features:
            raise ValueError("No valid TRS coordinates in feature list")
        
        query = {
            "type": "multi_exact",
            "layer": layer,
            "state": state,
            "feature_list": clean_features
        }
        
        logger.info(f"🎯🎯 Built multi-exact query for {layer} with {len(clean_features)} features")
        
        return query
    
    @staticmethod
    def _extract_plss_info(schema_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Extract PLSS information from schema data
        
        Args:
            schema_data: Complete schema data from text-to-schema conversion
            
        Returns:
            dict: Extracted PLSS info or None if not found
        """
        try:
            logger.info(f"🔍 Extracting PLSS from schema: {type(schema_data)}")
            
            if not schema_data:
                logger.warning("No schema data provided")
                return None
            
            # Handle different possible schema structures
            plss_info = None
            
            if isinstance(schema_data, dict):
                # Check for direct PLSS data
                if "plss" in schema_data:
                    plss_info = schema_data["plss"]
                    logger.info(f"🎯 Found direct PLSS data: {plss_info}")
                
                # Check descriptions array
                elif "descriptions" in schema_data and schema_data["descriptions"]:
                    for i, desc in enumerate(schema_data["descriptions"]):
                        if isinstance(desc, dict) and desc.get("plss"):
                            plss_info = desc["plss"]
                            logger.info(f"🎯 Found PLSS in description {i}: {plss_info}")
                            break
                
                # Check if the schema data itself has PLSS fields
                elif any(k in schema_data for k in ['township_number', 'range_number', 'section_number']):
                    plss_info = schema_data
                    logger.info(f"🎯 Found PLSS fields at root level: {plss_info}")
                
                # Search in nested structures
                else:
                    for key, value in schema_data.items():
                        if isinstance(value, dict) and any(k in value for k in ['township_number', 'range_number', 'section_number']):
                            plss_info = value
                            logger.info(f"🎯 Found PLSS in nested key '{key}': {plss_info}")
                            break
            
            if not plss_info:
                logger.warning("No PLSS information found in schema data")
                return None
            
            # Validate and normalize PLSS info
            return PLSSQueryBuilder._normalize_plss_info(plss_info)
            
        except Exception as e:
            logger.error(f"Failed to extract PLSS from schema: {e}")
            return None
    
    @staticmethod
    def _normalize_plss_info(plss_info: Dict[str, Any]) -> Dict[str, Any]:
        """
        Normalize PLSS information to standard format
        
        Args:
            plss_info: Raw PLSS information
            
        Returns:
            dict: Normalized PLSS information
        """
        try:
            normalized = {}
            
            # Township number and direction
            if plss_info.get("township_number") is not None:
                normalized["township_number"] = int(plss_info["township_number"])
            
            if plss_info.get("township_direction"):
                td = str(plss_info["township_direction"]).upper()
                if td in ["N", "S"]:
                    normalized["township_direction"] = td
            
            # Range number and direction
            if plss_info.get("range_number") is not None:
                normalized["range_number"] = int(plss_info["range_number"])
            
            if plss_info.get("range_direction"):
                rd = str(plss_info["range_direction"]).upper()
                if rd in ["E", "W"]:
                    normalized["range_direction"] = rd
            
            # Section number
            if plss_info.get("section_number") is not None:
                section = int(plss_info["section_number"])
                if 1 <= section <= 36:
                    normalized["section_number"] = section
            
            # Other fields
            for field in ["state", "county", "principal_meridian"]:
                if plss_info.get(field):
                    normalized[field] = str(plss_info[field])
            
            logger.info(f"✅ Normalized PLSS info: {normalized}")
            
            return normalized
            
        except Exception as e:
            logger.error(f"Failed to normalize PLSS info: {e}")
            return plss_info  # Return original if normalization fails
