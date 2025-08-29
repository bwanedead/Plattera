"""
PLSS Joiner Service
Handles joining township, range, and section parquet data with direct FGDB meridian lookups.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
import pandas as pd
import geopandas as gpd
from shapely.geometry import Point
from shapely import wkb
import fiona

logger = logging.getLogger(__name__)

class PLSSJoiner:
    """
    Service for joining PLSS parquet files and querying FGDB for meridian data.
    """
    def __init__(self, plss_data_path: Optional[str] = None):
        if plss_data_path is None:
            # Navigate to project root and find plss data
            self.plss_data_path = Path(__file__).parent.parent.parent.parent.parent / "plss" / "wyoming"
        else:
            self.plss_data_path = Path(plss_data_path)
        
        self.parquet_dir = self.plss_data_path / "parquet"
        self.fgdb_dir = self.plss_data_path / "fgdb"
        
        # Cached data
        self._townships_df = None
        self._sections_df = None
        self._ranges_df = None
        self._townships_fgdb_path = None
        self._joined_cache = {}
        
        logger.info(f"🔗 PLSS Joiner initialized")
        logger.info(f"📁 Parquet path: {self.parquet_dir}")
        logger.info(f"📁 FGDB path: {self.fgdb_dir}")

    def _find_townships_fgdb(self) -> Optional[Path]:
        """Find the townships FGDB file."""
        if self._townships_fgdb_path is not None:
            return self._townships_fgdb_path
        
        for fgdb_file in self.fgdb_dir.glob("*.gdb"):
            try:
                layers = fiona.listlayers(str(fgdb_file))
                if "BLM_WY_PLSSTownship_poly" in layers:
                    self._townships_fgdb_path = fgdb_file
                    logger.info(f"🏛️ Found townships FGDB: {fgdb_file.name}")
                    return self._townships_fgdb_path
            except Exception:
                continue
        
        logger.warning("⚠️ No townships FGDB found")
        return None

    def _load_townships_data(self) -> pd.DataFrame:
        """Load townships parquet data."""
        if self._townships_df is None:
            townships_path = self.parquet_dir / "townships.parquet"
            if not townships_path.exists():
                logger.error(f"❌ Townships parquet not found: {townships_path}")
                return pd.DataFrame()
            
            self._townships_df = pd.read_parquet(townships_path)
            
            # Convert WKB geometry to Shapely objects if needed
            if 'geometry' in self._townships_df.columns:
                self._townships_df['geometry'] = self._townships_df['geometry'].apply(
                    lambda x: wkb.loads(x) if isinstance(x, bytes) else x
                )
            
            logger.info(f"📊 Loaded townships parquet: {len(self._townships_df)} rows, columns: {list(self._townships_df.columns)}")
        
        return self._townships_df

    def _load_sections_data(self) -> pd.DataFrame:
        """Load sections parquet data."""
        if self._sections_df is None:
            sections_path = self.parquet_dir / "sections.parquet"
            if not sections_path.exists():
                logger.error(f"❌ Sections parquet not found: {sections_path}")
                return pd.DataFrame()
            
            df = pd.read_parquet(sections_path)
            if 'geometry' in df.columns:
                df['geometry'] = df['geometry'].apply(lambda x: wkb.loads(x) if isinstance(x, bytes) else x)
            if 'FRSTDIVNO' in df.columns:
                def norm_sec(v):
                    try:
                        return f"{int(str(v).strip() or 0):02d}"
                    except Exception:
                        return None
                df['FRSTDIVNO'] = df['FRSTDIVNO'].apply(norm_sec)
            self._sections_df = df
            
            logger.info(f"📊 Loaded sections parquet: {len(self._sections_df)} rows, columns: {list(self._sections_df.columns)}")
        
        return self._sections_df

    def _query_meridian_from_fgdb(self, township: int, township_dir: str, range_num: int, range_dir: str) -> Optional[str]:
        """
        Query the townships FGDB directly for meridian information.
        Much simpler than creating a separate parquet!
        """
        try:
            townships_fgdb = self._find_townships_fgdb()
            if not townships_fgdb:
                return None
            
            # Convert to zero-padded strings to match FGDB format
            township_str = f"{township:03d}"
            range_str = f"{range_num:03d}"
            
            # Query the FGDB directly
            twp_gdf = gpd.read_file(
                str(townships_fgdb), 
                layer="BLM_WY_PLSSTownship_poly",
                where=f"TWNSHPNO = '{township_str}' AND TWNSHPDIR = '{township_dir}' AND RANGENO = '{range_str}' AND RANGEDIR = '{range_dir}'"
            )
            
            if twp_gdf.empty:
                logger.warning(f"⚠️ No meridian data found for T{township}{township_dir} R{range_num}{range_dir}")
                return None
            
            if len(twp_gdf) > 1:
                logger.info(f"🧭 Multiple meridian matches for T{township}{township_dir} R{range_num}{range_dir}: {list(twp_gdf['PRINMERCD'].unique())}")
            
            meridian_code = twp_gdf.iloc[0]['PRINMERCD']
            logger.info(f"🧭 Found meridian for T{township}{township_dir} R{range_num}{range_dir}: {meridian_code}")
            
            return str(meridian_code) if meridian_code else None
            
        except Exception as e:
            logger.error(f"❌ Error querying meridian from FGDB: {e}")
            return None

    def find_township_range(self, township: int, township_dir: str, range_num: int, range_dir: str, principal_meridian: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Find township/range data by TR coordinates with optional principal meridian filtering.
        """
        try:
            townships_df = self._load_townships_data()
            
            if townships_df.empty:
                logger.error("❌ No townships data available")
                return None
            
            # Convert integers to zero-padded strings to match parquet format
            township_str = f"{township:03d}"
            range_str = f"{range_num:03d}"
            
            # Filter by TR coordinates
            mask = (
                (townships_df['TWNSHPNO'] == township_str) &
                (townships_df['TWNSHPDIR'] == township_dir) &
                (townships_df['RANGENO'] == range_str) &
                (townships_df['RANGEDIR'] == range_dir)
            )
            
            matching_rows = townships_df[mask]
            
            if len(matching_rows) == 0:
                logger.warning(f"❌ No township/range found for T{township}{township_dir} R{range_num}{range_dir}")
                return None
            
            # Handle multiple matches with meridian filtering
            if len(matching_rows) > 1 and principal_meridian:
                logger.info(f"⚠️ Multiple township/range matches for T{township}{township_dir} R{range_num}{range_dir} ({len(matching_rows)} found)")
                
                # Query FGDB for actual meridian data to filter
                actual_meridian = self._query_meridian_from_fgdb(township, township_dir, range_num, range_dir)
                if actual_meridian and self._meridian_matches(actual_meridian, principal_meridian):
                    logger.info(f"✅ Meridian match confirmed: {actual_meridian} matches {principal_meridian}")
                    row = matching_rows.iloc[0]  # Use first match since meridian is correct
                else:
                    logger.warning(f"⚠️ Meridian mismatch: expected {principal_meridian}, found {actual_meridian}")
                    row = matching_rows.iloc[0]  # Use first match as fallback
            else:
                row = matching_rows.iloc[0]
            
            result = {
                'township': township,
                'township_dir': township_dir,
                'range': range_num,
                'range_dir': range_dir,
                'geometry': row.get('geometry'),
                'bounds': self._get_geometry_bounds(row.get('geometry'))
            }
            
            # Log the final selected coordinates
            if result['bounds']:
                bounds = result['bounds']
                center_lat = (bounds['miny'] + bounds['maxy']) / 2
                center_lon = (bounds['minx'] + bounds['maxx']) / 2
                logger.info(f"✅ Selected township: T{township}{township_dir} R{range_num}{range_dir} at lat={center_lat:.3f}, lon={center_lon:.3f}")
            
            return result
            
        except Exception as e:
            logger.error(f"❌ Error finding township/range T{township}{township_dir} R{range_num}{range_dir}: {e}")
            return None

    def _meridian_matches(self, actual_meridian: str, expected_meridian: str) -> bool:
        """
        Check if actual meridian code matches expected meridian name.
        """
        if not actual_meridian or not expected_meridian:
            return False
        
        # Simple matching logic - expand this as needed
        actual_upper = actual_meridian.upper()
        expected_upper = expected_meridian.upper()
        
        # Direct match
        if actual_upper == expected_upper:
            return True
        
        # Common meridian mappings
        meridian_mappings = {
            "SIXTH PRINCIPAL MERIDIAN": ["PM06", "SIXTH", "6TH", "06"],
            "WIND RIVER MERIDIAN": ["WIND", "WR", "WINDRVR"],
            "BLACK HILLS MERIDIAN": ["BH", "BLACKHLS"],
        }
        
        for name, codes in meridian_mappings.items():
            if name in expected_upper:
                return actual_upper in [c.upper() for c in codes]
        
        # Partial matching
        return actual_upper in expected_upper or expected_upper in actual_upper

    def find_section_in_township(self, section_num: int, township_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Find section by intersecting sections with the selected township; then filter FRSTDIVNO."""
        try:
            sections_df = self._load_sections_data()
            if sections_df.empty:
                logger.error("❌ No sections data available")
                return None

            # Ensure geometry is present
            t_geom = township_data.get('geometry')
            if t_geom is None:
                logger.error("❌ Township has no geometry")
                return None

            # First bbox filter, then precise intersection (fast + accurate)
            minx, miny, maxx, maxy = t_geom.bounds
            cand = sections_df[
                sections_df['geometry'].apply(lambda g: g is not None and g.bounds[2] >= minx and g.bounds[0] <= maxx and g.bounds[3] >= miny and g.bounds[1] <= maxy)
            ]

            from shapely.prepared import prep
            prep_t = prep(t_geom)
            cand = cand[cand['geometry'].apply(lambda g: g is not None and prep_t.intersects(g))]

            # Filter by section number (FRSTDIVNO is zero-padded 2-char in parquet)
            section_str = f"{section_num:02d}"
            cand = cand[cand['FRSTDIVNO'] == section_str]

            if cand.empty:
                logger.warning(f"❌ No section {section_str} inside selected township; FRSTDIVNO uniques here: {sorted(sections_df['FRSTDIVNO'].dropna().unique().tolist())[:10]} …")
                return None

            # If multiple sections found, pick the one that matches PLSS standard position
            if len(cand) > 1:
                logger.info(f"🧭 Multiple section {section_num} candidates found, selecting by PLSS position...")
                
                # PLSS section numbering: 1-6 in top row, 7-12 in second row, etc.
                # Section 2 is in the northwest corner (top row, second from left)
                # Pick the section with the highest latitude (northernmost)
                cand = cand.sort_values('geometry', key=lambda x: x.apply(lambda g: g.bounds[3] if g else 0), ascending=False)
                logger.info(f"🧭 Selected northernmost section {section_num} at lat {cand.iloc[0]['geometry'].bounds[3]:.3f}")

            row = cand.iloc[0]
            return {
                'section': section_num,
                'geometry': row.get('geometry'),
                'bounds': self._get_geometry_bounds(row.get('geometry')),
            }
        except Exception as e:
            logger.error(f"❌ Error finding section {section_num}: {e}")
            return None

    def get_section_corner_coordinates(self, township: int, township_dir: str, range_num: int, range_dir: str, section: int, corner: str, principal_meridian: Optional[str] = None) -> Optional[Tuple[float, float]]:
        """Get coordinates for a specific section corner with meridian filtering."""
        try:
            # Find township/range first (with meridian filtering if provided)
            township_data = self.find_township_range(township, township_dir, range_num, range_dir, principal_meridian)
            if township_data is None:
                return None
            
            # Find section within township
            section_data = self.find_section_in_township(section, township_data)
            if section_data is None:
                return None
            
            # Extract corner coordinates
            return self._extract_corner_from_geometry(section_data['geometry'], corner)
            
        except Exception as e:
            logger.error(f"❌ Error getting section corner: {e}")
            return None

    def _extract_corner_from_geometry(self, geometry, corner: str) -> Optional[Tuple[float, float]]:
        """Extract corner coordinates from geometry bounds."""
        try:
            if geometry is None:
                return None
            
            bounds = self._get_geometry_bounds(geometry)
            if not bounds:
                return None
            
            corner_lower = corner.lower()
            
            if 'nw' in corner_lower or 'northwest' in corner_lower:
                return (bounds['minx'], bounds['maxy'])  # (lon, lat)
            elif 'ne' in corner_lower or 'northeast' in corner_lower:
                return (bounds['maxx'], bounds['maxy'])
            elif 'sw' in corner_lower or 'southwest' in corner_lower:
                return (bounds['minx'], bounds['miny'])
            elif 'se' in corner_lower or 'southeast' in corner_lower:
                return (bounds['maxx'], bounds['miny'])
            else:
                logger.warning(f"⚠️ Unknown corner: {corner}")
                return None
                
        except Exception as e:
            logger.error(f"❌ Error extracting corner {corner}: {e}")
            return None

    def _get_geometry_bounds(self, geometry) -> Optional[Dict[str, float]]:
        """Extract bounds from geometry."""
        try:
            if geometry is None:
                return None
            
            if hasattr(geometry, 'bounds'):
                minx, miny, maxx, maxy = geometry.bounds
                return {
                    'minx': float(minx),
                    'miny': float(miny), 
                    'maxx': float(maxx),
                    'maxy': float(maxy)
                }
            else:
                logger.warning("⚠️ Geometry does not have bounds attribute")
                return None
                
        except Exception as e:
            logger.error(f"❌ Error getting geometry bounds: {e}")
            return None

    def get_plss_info(self, township: int, township_dir: str, range_num: int, range_dir: str, section: int, principal_meridian: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Get complete PLSS information for a TRS location."""
        try:
            township_data = self.find_township_range(township, township_dir, range_num, range_dir, principal_meridian)
            if not township_data:
                return None
            
            section_data = self.find_section_in_township(section, township_data)
            if not section_data:
                return None
            
            # Get actual meridian from FGDB
            actual_meridian = self._query_meridian_from_fgdb(township, township_dir, range_num, range_dir)
            
            return {
                'township_data': township_data,
                'section_data': section_data,
                'principal_meridian': actual_meridian,
                'coordinates': {
                    'township': township,
                    'township_dir': township_dir,
                    'range': range_num,
                    'range_dir': range_dir,
                    'section': section
                }
            }
            
        except Exception as e:
            logger.error(f"❌ Error getting PLSS info: {e}")
            return None
