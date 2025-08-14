"""
PLSS Coordinate Resolver
Converts PLSS legal descriptions to geographic coordinates using real vector data
"""
import logging
import geopandas as gpd
import pandas as pd
from typing import Dict, Any, Optional, Tuple
import re
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

            # 0) Fast-path: SectionIndex (GeoParquet) if available
            try:
                from .section_index import SectionIndex
                idx = SectionIndex()
                fast = idx.get_centroid_bounds(state, {
                    "township_number": township,
                    "township_direction": township_direction,
                    "range_number": range_number,
                    "range_direction": range_direction,
                    "section_number": section,
                    "principal_meridian": principal_meridian,
                })
                if fast and fast.get("center"):
                    lat = float(fast["center"]["lat"])
                    lon = float(fast["center"]["lon"])
                    # Apply quarter offset if provided (small nudge from center)
                    if quarter_sections:
                        qlat, qlon = self._get_quarter_section_offset(quarter_sections)
                        lat += qlat
                        lon += qlon
                    return {
                        "success": True,
                        "coordinates": {"lat": lat, "lon": lon},
                        "method": "section_index",
                        "accuracy": "high",
                        "datum": "WGS84",
                    }
            except Exception as e:
                logger.debug(f"SectionIndex fast path skipped: {e}")

            # 1) Vector FGDB lookup (fallback)
            if vector_data and "layers" in vector_data:
                vector_result = self._resolve_from_vector_data(
                    township, township_direction, range_number, range_direction,
                    section, quarter_sections, principal_meridian, vector_data
                )
                if vector_result["success"]:
                    return vector_result

            # 2) Final: no coarse approximation to avoid misplacement
            return {
                "success": False,
                "error": "PLSS resolution failed (no index and vector lookup failed)"
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
            logger.info("🗺️ Attempting vector data lookup (FGDB)")

            layers = vector_data.get("layers", {})
            sections_fgdb = layers.get("sections_fgdb")
            sections_layer = layers.get("sections_layer")
            townships_fgdb = layers.get("townships_fgdb")
            townships_layer = layers.get("townships_layer")

            if not (sections_fgdb and sections_layer and townships_fgdb and townships_layer):
                return {"success": False, "error": "FGDB layers missing (sections or townships)"}

            # Load FGDB layers
            sec_gdf = gpd.read_file(sections_fgdb, layer=sections_layer)
            twp_gdf = gpd.read_file(townships_fgdb, layer=townships_layer)

            # Normalize CRS to EPSG:4326 when possible
            try:
                if sec_gdf.crs is not None and sec_gdf.crs.to_epsg() != 4326:
                    sec_gdf = sec_gdf.to_crs(4326)
                if twp_gdf.crs is not None and twp_gdf.crs.to_epsg() != 4326:
                    twp_gdf = twp_gdf.to_crs(4326)
            except Exception:
                pass

            # Exact field names for WY FGDB
            T_FIELD = 'TWNSHPNO'
            TD_FIELD = 'TWNSHPDIR'
            R_FIELD = 'RANGENO'
            RD_FIELD = 'RANGEDIR'
            PM_TEXT_FIELD = 'PRINMER'
            PM_CODE_FIELD = 'PRINMERCD'
            SEC_NO_FIELD = 'FRSTDIVNO'

            # Select township
            twp_mask = (
                (twp_gdf[T_FIELD].astype(int) == int(township)) &
                (twp_gdf[TD_FIELD].astype(str).str.upper().str[0] == township_direction.upper()) &
                (twp_gdf[R_FIELD].astype(int) == int(range_number)) &
                (twp_gdf[RD_FIELD].astype(str).str.upper().str[0] == range_direction.upper())
            )
            if principal_meridian:
                pm_norm = self._normalize_pm_tokens(principal_meridian)
                pm_mask = twp_gdf[PM_TEXT_FIELD].astype(str).str.contains(pm_norm['text'], case=False, na=False)
                try:
                    pm_code = int(pm_norm['code']) if pm_norm['code'] is not None else None
                except Exception:
                    pm_code = None
                if pm_code is not None and PM_CODE_FIELD in twp_gdf.columns:
                    pm_mask = pm_mask | (twp_gdf[PM_CODE_FIELD].astype('Int64') == pm_code)
                twp_mask = twp_mask & pm_mask

            twp_sel = twp_gdf[twp_mask]
            if len(twp_sel) == 0 and principal_meridian:
                # Retry without PM if that over-constrained
                twp_sel = twp_gdf[
                    (twp_gdf[T_FIELD].astype(int) == int(township)) &
                    (twp_gdf[TD_FIELD].astype(str).str.upper().str[0] == township_direction.upper()) &
                    (twp_gdf[R_FIELD].astype(int) == int(range_number)) &
                    (twp_gdf[RD_FIELD].astype(str).str.upper().str[0] == range_direction.upper())
                ]
            if len(twp_sel) == 0:
                return {"success": False, "error": "Township not found in FGDB"}

            twp_geom = twp_sel.iloc[0].geometry

            # Filter sections by section number and intersect with township
            sec_num = int(section)
            sec_pref = sec_gdf[sec_gdf[SEC_NO_FIELD].astype('Int64') == sec_num]
            if len(sec_pref) == 0:
                return {"success": False, "error": "No sections with that number in FGDB"}

            try:
                candidates = sec_pref[sec_pref.intersects(twp_geom)]
            except Exception:
                candidates = sec_pref
            if len(candidates) == 0:
                # Fallback: pick nearest to township centroid
                try:
                    cen = twp_geom.centroid
                    candidates = sec_pref.assign(_d=sec_pref.distance(cen)).sort_values('_d').head(1).drop(columns=['_d'])
                except Exception:
                    candidates = sec_pref.head(1)

            # Choose largest area
            try:
                candidates = candidates.assign(_a=candidates.geometry.area).sort_values('_a', ascending=False)
            except Exception:
                pass
            section_row = candidates.iloc[0]
            
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
            possible_township_fields = [
                'TWNSHPNO', 'TOWNSHIP', 'TWP', 'TWPNO',
                'TOWNSHIPNO', 'TOWNSHIP_NO', 'TWP_NO', 'TWP_NUM', 'TOWN_NO', 'TOWN_NUM', 'TWN', 'TWN_NO', 'TWN_NUM'
            ]
            possible_township_dir_fields = [
                'TWNSHPDIR', 'TOWNSHIP_DIR', 'TWP_DIR', 'TDIR',
                'TOWNSHIPDIRECTION', 'TOWNSHIP_DIRECTION', 'TWP_DIRECTION', 'TWN_DIR',
                'NS', 'NS_DIR', 'TWP_NS', 'TOWNSHIP_NS'
            ]
            possible_range_fields = [
                'RANGENO', 'RANGE', 'RNG', 'RNGNO',
                'RANGE_NO', 'RANGE_NUM', 'RNG_NO', 'RNG_NUM'
            ] 
            possible_range_dir_fields = [
                'RANGEDIR', 'RANGE_DIR', 'RNG_DIR', 'RDIR',
                'RANGE_DIRECTION', 'RNG_DIRECTION',
                'EW', 'EW_DIR', 'RNG_EW', 'RANGE_EW'
            ]
            possible_section_fields = [
                'SECNO', 'SECTION', 'SEC', 'SECTNO',
                'SECTION_NO', 'SECTION_NUM', 'SEC_NO', 'SEC_NUM', 'SECT_NUM',
                'SEC_NBR', 'SECTION_NBR', 'SECNUMBER', 'SEC_NUMB'
            ]
            
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
                possible_pm_fields = ['PRIN_MER', 'MERIDIAN', 'PM', 'PMCODE', 'MERIDIANCD', 'PRINCIPALMERIDIAN', 'PRINMER', 'PRIN_MERID']
                pm_field = self._find_field(gdf.columns, possible_pm_fields)
                if pm_field:
                    # Try flexible contains and numeric code matching
                    pm_tokens = self._normalize_pm_tokens(principal_meridian)
                    # Best-effort: if the column is numeric, try equality against numeric tokens; else contains()
                    try:
                        # Pandas query cannot easily mix types; defer type handling to tolerant pass below
                        conditions.append(f"{pm_field}.astype(str).str.contains(@pm_tokens['text'], case=False, na=False)")
                    except Exception:
                        pass
            
            if township_field:
                conditions.append(f"{township_field} == {plss_query['township']}")
            if township_dir_field:
                # Map NS/EW style fields to single-letter N/S
                if township_dir_field.upper() in ['NS', 'NS_DIR', 'TWP_NS', 'TOWNSHIP_NS']:
                    conditions.append(f"{township_dir_field}.astype(str).str.upper().str[0] == '{plss_query['township_direction']}'")
                else:
                    conditions.append(f"{township_dir_field} == '{plss_query['township_direction']}'")
            if range_field:
                conditions.append(f"{range_field} == {plss_query['range']}")
            if range_dir_field:
                if range_dir_field.upper() in ['EW', 'EW_DIR', 'RNG_EW', 'RANGE_EW']:
                    conditions.append(f"{range_dir_field}.astype(str).str.upper().str[0] == '{plss_query['range_direction']}'")
                else:
                    conditions.append(f"{range_dir_field} == '{plss_query['range_direction']}'")
            if section_field:
                conditions.append(f"{section_field} == {plss_query['section']}")
            
            if not conditions:
                logger.warning("No matching field names found in vector data")
                # Try composite TRS string fallback matching
                composite = self._fallback_match_trs_composite(
                    gdf,
                    plss_query['township'], plss_query['township_direction'],
                    plss_query['range'], plss_query['range_direction'],
                    plss_query['section']
                )
                return composite
            
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
                    # Principal meridian tolerant match: try numeric mapping and contains text
                    if principal_meridian:
                        pm_field = self._find_field(df.columns, possible_pm_fields)
                        if pm_field:
                            pm_norm = self._normalize_pm_tokens(principal_meridian)
                            try:
                                # Numeric code match if column convertible
                                pm_numeric = pd.to_numeric(df[pm_field], errors='coerce')
                                pm_mask = (pm_numeric == pm_norm['code']) if pm_norm['code'] is not None else pd.Series([True]*len(df))
                            except Exception:
                                pm_mask = df[pm_field].astype(str).str.contains(pm_norm['text'], case=False, na=False)
                            conds.append(pm_mask)
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

            # If still nothing, try composite TRS fallback
            if len(result) == 0:
                result = self._fallback_match_trs_composite(
                    gdf,
                    plss_query['township'], plss_query['township_direction'],
                    plss_query['range'], plss_query['range_direction'],
                    plss_query['section']
                )

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

    def _normalize_pm_tokens(self, principal_meridian: str) -> dict:
        """Normalize principal meridian into text and numeric code tokens for matching."""
        text = (principal_meridian or '').strip()
        low = text.lower()
        code = None
        # crude mapping for common meridians
        if 'sixth' in low or '6th' in low:
            code = 6
        elif 'fifth' in low or '5th' in low:
            code = 5
        elif 'fourth' in low or '4th' in low:
            code = 4
        elif 'third' in low or '3rd' in low:
            code = 3
        elif 'second' in low or '2nd' in low:
            code = 2
        elif 'first' in low or '1st' in low:
            code = 1
        return {"text": text, "code": code}

    def _fallback_match_trs_composite(
        self,
        gdf: gpd.GeoDataFrame,
        township: int, tdir: str,
        rng: int, rdir: str,
        sec: int
    ) -> gpd.GeoDataFrame:
        """Fallback matching using composite TRS text columns (e.g., 'TRS', 'TWNSHPRGSEC')."""
        try:
            df = gdf.copy()
            upper_cols = {c: c for c in df.columns}
            # Candidate string columns that might carry composite TRS values
            candidates = [
                c for c in df.columns
                if df[c].dtype == 'object' and any(tok in c.upper() for tok in ['TRS', 'TWP', 'TWN', 'RNG', 'RANGE', 'SEC'])
            ]
            if not candidates:
                return df.iloc[0:0]

            # Build tolerant patterns
            t_pat = re.escape(f"T{int(township)}{tdir.upper()}")
            r_no_pad = re.escape(f"R{int(rng)}{rdir.upper()}")
            r_pad = re.escape(f"R{int(rng):03d}{rdir.upper()}")
            sec_num = int(sec)
            sec_pat = rf"\b(SEC(TION)?\s*0*{sec_num}\b|\bS\s*0*{sec_num}\b|\b0*{sec_num}\b)"

            # Evaluate contains for each candidate; union results
            masks = []
            for col in candidates:
                s = df[col].astype(str).str.upper()
                m = (
                    s.str.contains(t_pat, regex=True, na=False) &
                    (s.str.contains(r_no_pad, regex=True, na=False) | s.str.contains(r_pad, regex=True, na=False)) &
                    s.str.contains(sec_pat, regex=True, na=False)
                )
                masks.append(m)
            if not masks:
                return df.iloc[0:0]
            mask_union = masks[0]
            for m in masks[1:]:
                mask_union = mask_union | m
            return df[mask_union]
        except Exception:
            return gdf.iloc[0:0]
    
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