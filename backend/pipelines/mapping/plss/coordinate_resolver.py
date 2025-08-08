"""
PLSS Coordinate Resolver
Converts PLSS legal descriptions to geographic coordinates using real vector data
"""
import logging
import geopandas as gpd
import pandas as pd
from typing import Dict, Any, Optional, Tuple
from pathlib import Path

logger = logging.getLogger(__name__)

class PLSSCoordinateResolver:
    """
    Resolves PLSS legal descriptions to lat/lon coordinates using real vector data
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
        principal_meridian: Optional[str] = None,
        vector_data: Optional[dict] = None
    ) -> dict:
        """
        Resolve PLSS description to geographic coordinates using real vector data
        
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
            logger.info(
                f"🧭 Resolving coordinates for T{township}{township_direction} R{range_number}{range_direction} Sec {section}"
            )
            if principal_meridian:
                logger.info(f"🧭 Principal Meridian (hint): {principal_meridian}")
            
            # Try precise vector lookup first
            if vector_data and "layers" in vector_data:
                vector_result = self._resolve_from_vector_data(
                    township, township_direction, range_number, range_direction, 
                    section, quarter_sections, principal_meridian, vector_data
                )
                if vector_result["success"]:
                    return vector_result
            
            # Do NOT fall back to coarse approximation to avoid wrong placement
            return {
                "success": False,
                "error": "Vector lookup failed; coarse approximation disabled to prevent misplacement"
            }
            
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
        principal_meridian: Optional[str],
        vector_data: dict
    ) -> dict:
        """Resolve coordinates using real BLM CadNSDI vector data"""
        try:
            logger.info("🗺️ Attempting vector data lookup")
            
            sections_file = vector_data["layers"].get("sections")
            if not sections_file or not Path(sections_file).exists():
                return {
                    "success": False,
                    "error": "Sections vector data not available"
                }
            
            # Load sections GeoDataFrame
            gdf = gpd.read_file(sections_file)
            logger.debug(f"Vector data columns: {list(gdf.columns)}")
            
            # Build PLSS query to match section
            plss_query = self._build_plss_query(township, township_direction, range_number, range_direction, section)
            
            # Query the geodataframe for matching section
            matching_sections = self._query_sections(gdf, plss_query, principal_meridian)
            logger.debug(f"Vector PLSS query: {plss_query} with principal_meridian={principal_meridian}")
            logger.debug(f"Match count: {len(matching_sections)}")
            
            if len(matching_sections) == 0:
                logger.warning(f"No matching sections found for {plss_query}")
                return {
                    "success": False,
                    "error": f"No sections found matching: {plss_query}"
                }
            
            if len(matching_sections) > 1:
                logger.warning(f"Multiple sections found for {plss_query}, using first match")
            
            # Get the best match
            section_row = matching_sections.iloc[0]
            
            # Calculate centroid or use existing centroid fields
            if hasattr(section_row.geometry, 'centroid'):
                centroid = section_row.geometry.centroid
                resolved_lat = centroid.y
                resolved_lon = centroid.x
            else:
                # Fallback to bounds center
                bounds = section_row.geometry.bounds
                resolved_lat = (bounds[1] + bounds[3]) / 2  # (miny + maxy) / 2
                resolved_lon = (bounds[0] + bounds[2]) / 2  # (minx + maxx) / 2
            
            # Apply quarter section offset if specified
            if quarter_sections:
                quarter_lat_offset, quarter_lon_offset = self._get_quarter_section_offset(quarter_sections)
                resolved_lat += quarter_lat_offset
                resolved_lon += quarter_lon_offset
            
            logger.info(f"✅ Vector lookup successful: {resolved_lat:.6f}, {resolved_lon:.6f}")
            
            return {
                "success": True,
                "coordinates": {
                    "lat": resolved_lat,
                    "lon": resolved_lon
                },
                "method": "vector_lookup",
                "accuracy": "high",
                "datum": "WGS84",
                "matched_attributes": {
                    k: v for k, v in section_row.items() 
                    if k not in ['geometry'] and pd.notna(v)
                }
            }
            
        except Exception as e:
            logger.warning(f"Vector lookup failed: {str(e)}")
            return {
                "success": False,
                "error": f"Vector lookup error: {str(e)}"
            }
    
    def _build_plss_query(self, township: int, township_direction: str, range_number: int, range_direction: str, section: int) -> dict:
        """Build standardized PLSS query parameters"""
        return {
            "township": township,
            "township_direction": township_direction.upper(),
            "range": range_number,
            "range_direction": range_direction.upper(),
            "section": section
        }
    
    def _query_sections(self, gdf: gpd.GeoDataFrame, plss_query: dict, principal_meridian: Optional[str] = None) -> gpd.GeoDataFrame:
        """Query sections GeoDataFrame for matching PLSS description"""
        try:
            # Common BLM CadNSDI field mappings (may vary by dataset)
            possible_township_fields = ['TWNSHPNO', 'TOWNSHIP', 'TWP', 'TWPNO']
            possible_township_dir_fields = ['TWNSHPDIR', 'TOWNSHIP_DIR', 'TWP_DIR', 'TDIR']
            possible_range_fields = ['RANGENO', 'RANGE', 'RNG', 'RNGNO'] 
            possible_range_dir_fields = ['RANGEDIR', 'RANGE_DIR', 'RNG_DIR', 'RDIR']
            possible_section_fields = ['SECNO', 'SECTION', 'SEC', 'SECTNO']
            
            # Find actual field names in the dataset
            township_field = self._find_field(gdf.columns, possible_township_fields)
            township_dir_field = self._find_field(gdf.columns, possible_township_dir_fields)
            range_field = self._find_field(gdf.columns, possible_range_fields)
            range_dir_field = self._find_field(gdf.columns, possible_range_dir_fields)
            section_field = self._find_field(gdf.columns, possible_section_fields)
            
            # Build filter conditions
            conditions = []
            # Some datasets include a principal meridian or meridian code; try to match if provided
            if principal_meridian:
                possible_pm_fields = ['PRIN_MER', 'MERIDIAN', 'PM', 'PMCODE', 'MERIDIANCD']
                pm_field = self._find_field(gdf.columns, possible_pm_fields)
                if pm_field:
                    # Try a flexible contains match to tolerate naming differences
                    conditions.append(f"{pm_field}.str.contains(@principal_meridian, case=False, na=False)")
            
            if township_field:
                conditions.append(f"{township_field} == {plss_query['township']}")
            if township_dir_field:
                conditions.append(f"{township_dir_field} == '{plss_query['township_direction']}'")
            if range_field:
                conditions.append(f"{range_field} == {plss_query['range']}")
            if range_dir_field:
                conditions.append(f"{range_dir_field} == '{plss_query['range_direction']}'")
            if section_field:
                conditions.append(f"{section_field} == {plss_query['section']}")
            
            if not conditions:
                logger.warning("No matching field names found in vector data")
                return gpd.GeoDataFrame()
            
            # Apply filters
            query_string = " & ".join(conditions)
            logger.debug(f"Vector query: {query_string}")
            try:
                result = gdf.query(query_string)
            except Exception as e:
                logger.debug(f"Primary query failed, attempting fallback: {e}")
                result = gdf.iloc[0:0]

            # Fallback: try tolerant comparisons if no matches
            if len(result) == 0:
                try:
                    df = gdf.copy()
                    if township_field and df[township_field].dtype != 'int64':
                        df[township_field] = pd.to_numeric(df[township_field], errors='coerce').astype('Int64')
                    if range_field and df[range_field].dtype != 'int64':
                        df[range_field] = pd.to_numeric(df[range_field], errors='coerce').astype('Int64')
                    if section_field and df[section_field].dtype != 'int64':
                        df[section_field] = pd.to_numeric(df[section_field], errors='coerce').astype('Int64')

                    conds = []
                    if township_field:
                        conds.append(df[township_field] == int(plss_query['township']))
                    if township_dir_field:
                        conds.append(df[township_dir_field].astype(str).str.upper() == plss_query['township_direction'])
                    if range_field:
                        conds.append(df[range_field] == int(plss_query['range']))
                    if range_dir_field:
                        conds.append(df[range_dir_field].astype(str).str.upper() == plss_query['range_direction'])
                    if section_field:
                        conds.append(df[section_field] == int(plss_query['section']))

                    if conds:
                        mask = conds[0]
                        for c in conds[1:]:
                            mask = mask & c
                        result = df[mask]
                except Exception as e2:
                    logger.debug(f"Fallback tolerant filter failed: {e2}")

            return result
            
        except Exception as e:
            logger.error(f"Section query failed: {str(e)}")
            return gpd.GeoDataFrame()
    
    def _find_field(self, columns, possible_names) -> Optional[str]:
        """Find the first matching field name from possibilities"""
        for col in columns:
            if col.upper() in [name.upper() for name in possible_names]:
                return col
        return None
    
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
        # Principal meridian baselines for PLSS states
        baselines = {
            "Wyoming": {"lat": 40.5, "lon": -107.0},  # 6th Principal Meridian
            "Colorado": {"lat": 40.0, "lon": -105.0}, # 6th Principal Meridian  
            "Utah": {"lat": 40.5, "lon": -111.5},     # Salt Lake Meridian
            "Montana": {"lat": 45.0, "lon": -110.0},  # Principal Meridian Montana
            "New Mexico": {"lat": 34.25, "lon": -106.5}, # New Mexico Principal Meridian
            "Idaho": {"lat": 43.5, "lon": -114.0},    # Boise Meridian
            "Nevada": {"lat": 39.5, "lon": -116.0},   # Mount Diablo Meridian
            "Arizona": {"lat": 33.5, "lon": -112.25}, # Gila and Salt River Meridian
            "California": {"lat": 37.8, "lon": -122.25}, # Mount Diablo Meridian
            "Oregon": {"lat": 45.5, "lon": -122.75},  # Willamette Meridian
            "Washington": {"lat": 47.0, "lon": -120.5} # Willamette Meridian
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
        
        # Basic quarter section parsing - expand this for more complex descriptions
        quarter_offset = self.miles_to_degrees_lat / 4  # Quarter of a mile
        
        if "northwest" in quarter_sections.lower() or "nw" in quarter_sections.lower():
            return quarter_offset, -quarter_offset
        elif "northeast" in quarter_sections.lower() or "ne" in quarter_sections.lower():
            return quarter_offset, quarter_offset
        elif "southwest" in quarter_sections.lower() or "sw" in quarter_sections.lower():
            return -quarter_offset, -quarter_offset
        elif "southeast" in quarter_sections.lower() or "se" in quarter_sections.lower():
            return -quarter_offset, quarter_offset
        
        # Default to center if quarter description not recognized
        return 0.0, 0.0