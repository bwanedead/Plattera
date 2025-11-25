"""
Fast PLSS Coordinate Service
Ultra-fast coordinate resolution using parquet index
"""
import logging
from pathlib import Path
from typing import Dict, Any, Optional
import pandas as pd
from config.paths import plss_root

logger = logging.getLogger(__name__)

class PLSSCoordinateService:
    """
    Lightning-fast PLSS coordinate resolution
    Uses optimized parquet index for <50ms lookups
    """
    
    def __init__(self, data_dir: str = None):
        if data_dir:
            self.data_dir = Path(data_dir)
        else:
            # Use centralized PLSS root (dev: repo/plss, frozen: app data)
            self.data_dir = plss_root()

        # Verify the data directory exists
        if not self.data_dir.exists():
            logger.warning(f"PLSS data directory does not exist: {self.data_dir}")
        
        self._index_cache = {}
        
        # Quarter section offsets (approximate degrees)
        self.quarter_offsets = {
            "NE": (0.0045, 0.0045),   # ~1/4 mile north and east
            "NW": (0.0045, -0.0045),  # ~1/4 mile north and west  
            "SE": (-0.0045, 0.0045),  # ~1/4 mile south and east
            "SW": (-0.0045, -0.0045), # ~1/4 mile south and west
        }
    
    def resolve_coordinates(
        self,
        state: str,
        township: int,
        township_direction: str,
        range_number: int,
        range_direction: str,
        section: int,
        quarter_sections: Optional[str] = None,
        principal_meridian: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Resolve PLSS coordinates in <50ms
        
        Returns:
            {
                "success": bool,
                "coordinates": {"lat": float, "lon": float},
                "bounds": {...},
                "corners": {...},
                "plss_reference": str
            }
        """
        try:
            plss_ref = f"T{township}{township_direction} R{range_number}{range_direction} S{section}"
            
            # Try fast index lookup first
            result = self._fast_index_lookup(state, township, township_direction,
                                             range_number, range_direction, section, principal_meridian)
            
            if result:
                lat, lon = result["lat"], result["lon"]
                
                # Apply quarter section offset
                if quarter_sections:
                    lat_offset, lon_offset = self._get_quarter_offset(quarter_sections)
                    lat += lat_offset
                    lon += lon_offset
                
                logger.info(f"✅ Fast PLSS lookup: {lat:.6f}, {lon:.6f}")
                
                return {
                    "success": True,
                    "coordinates": {"lat": lat, "lon": lon},
                    "bounds": result.get("bounds", {}),
                    "corners": result.get("corners", {}),
                    "plss_reference": plss_ref,
                    "method": "fast_index"
                }
            
            # Fallback to parquet read (still fast)
            result = self._parquet_lookup(state, township, township_direction,
                                          range_number, range_direction, section, principal_meridian)
            
            if result:
                lat, lon = result["lat"], result["lon"]
                
                if quarter_sections:
                    lat_offset, lon_offset = self._get_quarter_offset(quarter_sections)
                    lat += lat_offset
                    lon += lon_offset
                
                logger.info(f"✅ Parquet PLSS lookup: {lat:.6f}, {lon:.6f}")
                
                return {
                    "success": True,
                    "coordinates": {"lat": lat, "lon": lon},
                    "bounds": result.get("bounds", {}),
                    "plss_reference": plss_ref,
                    "method": "parquet"
                }
            
            return {"success": False, "error": f"No data found for {plss_ref}"}
            
        except Exception as e:
            import traceback
            logger.error(f"PLSS coordinate resolution failed: {e}\n{traceback.format_exc()}")
            return {"success": False, "error": str(e) if str(e) else "Unknown error"}
    
    def _fast_index_lookup(self, state: str, township: int, township_direction: str,
                          range_number: int, range_direction: str, section: int,
                          principal_meridian: Optional[str]) -> Optional[Dict[str, Any]]:
        """Try fast index lookup using SectionIndex"""
        try:
            from .section_index import SectionIndex
            
            idx = SectionIndex(str(self.data_dir))
            
            # Log the lookup attempt
            logger.info(f"Fast index lookup for: T{township}{township_direction} R{range_number}{range_direction} S{section}")
            
            result = idx.get_centroid_bounds(state, {
                "township_number": township,
                "township_direction": township_direction,
                "range_number": range_number,
                "range_direction": range_direction,
                "section_number": section,
                "principal_meridian": principal_meridian,
            })
            
            if result and result.get("center"):
                logger.info(f"Fast index found result: {result['center']}")
                return {
                    "lat": float(result["center"]["lat"]),
                    "lon": float(result["center"]["lon"]),
                    "bounds": result.get("bounds", {}),
                    "corners": result.get("corners", {})
                }
            else:
                logger.info("Fast index lookup returned no results")
            
        except Exception as e:
            logger.info(f"Fast index lookup failed: {e}")
        
        return None
    
    def _parquet_lookup(self, state: str, township: int, township_direction: str,
                       range_number: int, range_direction: str, section: int,
                       principal_meridian: Optional[str]) -> Optional[Dict[str, Any]]:
        """Fallback parquet lookup with flexible column names"""
        try:
            sections_file = self.data_dir / state.lower() / "parquet" / "sections.parquet"
            if not sections_file.exists():
                logger.warning(f"Sections parquet file not found: {sections_file}")
                return None
            
            try:
                import geopandas as gpd
            except ImportError as e:
                logger.error(f"GeoPandas not available for parquet lookup: {e}")
                return None
            
            # Load and inspect the data
            gdf = gpd.read_parquet(sections_file)
            
            # Log what we're looking for and what columns exist
            logger.info(f"Looking for: T{township}{township_direction} R{range_number}{range_direction} S{section}")
            logger.info(f"Available columns: {list(gdf.columns)}")
            logger.info(f"Total sections in data: {len(gdf)}")
            
            # Check if the required columns exist
            required_cols = ['TWNSHPNO', 'TWNSHPDIR', 'RANGENO', 'RANGEDIR', 'FRSTDIVNO']
            missing_cols = [col for col in required_cols if col not in gdf.columns]
            
            if missing_cols:
                logger.error(f"Missing required columns in parquet: {missing_cols}")
                logger.error("The parquet file was created incorrectly - missing township/range columns")
                
                # For now, we can't lookup without these columns
                # This indicates the GeoParquet creation process needs to be fixed
                return None
            
            # If we have all columns, proceed with lookup
            mask = (
                (gdf['TWNSHPNO'] == township) &
                (gdf['TWNSHPDIR'].str.upper() == township_direction.upper()) &
                (gdf['RANGENO'] == range_number) &
                (gdf['RANGEDIR'].str.upper() == range_direction.upper()) &
                (gdf['FRSTDIVNO'] == section)
            )
            
            if principal_meridian and 'PRINMERCD' in gdf.columns:
                mask &= (gdf['PRINMERCD'].str.upper() == principal_meridian.upper())
            
            matches = gdf[mask]
            logger.info(f"Found {len(matches)} matches for the query")
            
            if len(matches) > 0:
                geom = matches.iloc[0].geometry
                centroid = geom.centroid
                bounds = geom.bounds
                
                return {
                    "lat": float(centroid.y),
                    "lon": float(centroid.x),
                    "bounds": {
                        "min_lat": float(bounds[1]), "max_lat": float(bounds[3]),
                        "min_lon": float(bounds[0]), "max_lon": float(bounds[2])
                    }
                }
                
        except Exception as e:
            import traceback
            logger.error(f"Parquet lookup failed: {e}\n{traceback.format_exc()}")
        
        return None
    
    def _get_quarter_offset(self, quarter_sections: str) -> tuple[float, float]:
        """Parse quarter section and return lat/lon offset"""
        if not quarter_sections:
            return (0.0, 0.0)
        
        # Parse quarter like "NE1/4" or "SW1/4NE1/4"
        quarters = quarter_sections.upper().replace("1/4", "").strip()
        
        # Use the last (most specific) quarter mentioned
        for direction in ["NE", "NW", "SE", "SW"]:
            if direction in quarters:
                return self.quarter_offsets.get(direction, (0.0, 0.0))
        
        return (0.0, 0.0)
