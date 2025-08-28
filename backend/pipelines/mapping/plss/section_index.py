"""
Section Index (GeoParquet-backed)

Provides fast lookup of PLSS section centroid, bounds, and canonical corners
without reading entire FGDB layers at request time.

Artifacts per state (created during ensure_state_data processing):
- plss/<state>/parquet/sections.parquet (full sections geometry in EPSG:4326)
- plss/<state>/parquet/townships.parquet (optional)
- plss/<state>/index/sections_index.parquet (compact TRS index with centroid/bounds/corners)
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, Any, Optional, Tuple
import logging

import geopandas as gpd
import pandas as pd
from shapely.geometry import Polygon
import fiona
import shutil

logger = logging.getLogger(__name__)


TRSKey = Tuple[int, str, int, str, int, Optional[str]]


class SectionIndex:
    """Process-level helper for fast TRS lookups."""

    _state_to_index_df: Dict[str, pd.DataFrame] = {}

    def __init__(self, data_root: Optional[str] = None) -> None:
        # Discover project root -> plss dir if not provided
        if data_root:
            self.base_dir = Path(data_root)
        else:
            # backend/pipelines/mapping/plss/ -> project root / plss
            self.base_dir = Path(__file__).parent.parent.parent.parent.parent / "plss"

    def _index_path(self, state: str) -> Path:
        return (self.base_dir / state.lower() / "index" / "sections_index.parquet").resolve()

    def _sections_parquet_path(self, state: str) -> Path:
        return (self.base_dir / state.lower() / "parquet" / "sections.parquet").resolve()

    def _townships_parquet_path(self, state: str) -> Path:
        return (self.base_dir / state.lower() / "parquet" / "townships.parquet").resolve()

    def has_index(self, state: str) -> bool:
        return self._index_path(state).exists()

    def load_index(self, state: str) -> Optional[pd.DataFrame]:
        if state in self._state_to_index_df:
            return self._state_to_index_df[state]
        p = self._index_path(state)
        if not p.exists():
            return None
        try:
            df = pd.read_parquet(p)
            # Normalize string columns for directions
            for col in ["td", "rd", "pm"]:
                if col in df.columns:
                    df[col] = df[col].astype(str).str.upper().str.strip()
            self._state_to_index_df[state] = df
            return df
        except Exception as e:
            logger.warning(f"Failed to load section index for {state}: {e}")
            return None

    def build_index_from_fgdb(self, state: str, sections_fgdb: str, sections_layer: str, 
                         townships_fgdb: Optional[str] = None, townships_layer: Optional[str] = None,
                         subdivisions_fgdb: Optional[str] = None, subdivisions_layer: Optional[str] = None,
                         progress_callback: Optional[callable] = None) -> Dict[str, Any]:
        """Create sections GeoParquet and a compact TRS index.

        The index columns:
          t, td, r, rd, s, pm?, centroid_lat, centroid_lon, min_lat, min_lon, max_lat, max_lon,
          nw_lat, nw_lon, ne_lat, ne_lon, se_lat, se_lon, sw_lat, sw_lon
        """
        try:
            state_dir = (self.base_dir / state.lower()).resolve()
            pq_dir = state_dir / "parquet"
            idx_dir = state_dir / "index"
            pq_dir.mkdir(parents=True, exist_ok=True)
            idx_dir.mkdir(parents=True, exist_ok=True)

            # 1) Load sections once from FGDB, normalize to EPSG:4326
            sec_gdf = gpd.read_file(sections_fgdb, layer=sections_layer)
            try:
                if sec_gdf.crs is not None and sec_gdf.crs.to_epsg() != 4326:
                    sec_gdf = sec_gdf.to_crs(4326)
            except Exception:
                pass

            # Discover and map actual column names from FGDB
            logger.info(f"FGDB columns available: {list(sec_gdf.columns)}")
            
            # Map actual column names to expected names (flexible matching)
            column_mapping = {}
            
            # Find township number column
            for col in sec_gdf.columns:
                col_upper = col.upper()
                if ('TWNSHP' in col_upper or 'TOWNSHIP' in col_upper) and ('NO' in col_upper or 'NUM' in col_upper):
                    column_mapping['TWNSHPNO'] = col
                    break
            
            # Find township direction column  
            for col in sec_gdf.columns:
                col_upper = col.upper()
                if ('TWNSHP' in col_upper or 'TOWNSHIP' in col_upper) and 'DIR' in col_upper:
                    column_mapping['TWNSHPDIR'] = col
                    break
                    
            # Find range number column
            for col in sec_gdf.columns:
                col_upper = col.upper()
                if 'RANGE' in col_upper and ('NO' in col_upper or 'NUM' in col_upper):
                    column_mapping['RANGENO'] = col
                    break
                    
            # Find range direction column
            for col in sec_gdf.columns:
                col_upper = col.upper()
                if 'RANGE' in col_upper and 'DIR' in col_upper:
                    column_mapping['RANGEDIR'] = col
                    break
                    
            # Find section/first division column
            for col in sec_gdf.columns:
                col_upper = col.upper()
                if ('FRSTDIV' in col_upper or 'FIRSTDIV' in col_upper or 'SECTION' in col_upper) and ('NO' in col_upper or 'NUM' in col_upper):
                    column_mapping['FRSTDIVNO'] = col
                    break
                    
            # Find principal meridian column
            for col in sec_gdf.columns:
                col_upper = col.upper()
                if ('PRINMER' in col_upper or 'MERIDIAN' in col_upper):
                    column_mapping['PRINMERCD'] = col
                    break
            
            logger.info(f"Column mapping discovered: {column_mapping}")
            
            # Rename columns to standard names
            if column_mapping:
                sec_gdf = sec_gdf.rename(columns=column_mapping)
            
            # Keep all available mapped columns plus geometry
            keep_cols = ['TWNSHPNO', 'TWNSHPDIR', 'RANGENO', 'RANGEDIR', 'FRSTDIVNO', 'PRINMERCD', 'geometry']
            present = [c for c in keep_cols if c in sec_gdf.columns]
            sec_gdf = sec_gdf[present]
            
            logger.info(f"Final columns for parquet: {list(sec_gdf.columns)}")

            # 2) Write full sections as GeoParquet for optional overlays
            sections_parquet = pq_dir / "sections.parquet"
            sec_gdf.to_parquet(sections_parquet, compression="zstd", index=False)

            # Initialize townships parquet path
            townships_parquet_path: Optional[Path] = None
            # 2.5) Load townships to get TRS info and join with sections
            if townships_fgdb and townships_layer:
                try:
                    logger.info("Loading townships for spatial join...")
                    twp_gdf = gpd.read_file(townships_fgdb, layer=townships_layer)
                    
                    # Normalize townships to EPSG:4326
                    try:
                        if twp_gdf.crs is not None and twp_gdf.crs.to_epsg() != 4326:
                            twp_gdf = twp_gdf.to_crs(4326)
                    except Exception:
                        pass
                    
                    logger.info(f"Townships columns available: {list(twp_gdf.columns)}")
                    
                    # Map township column names
                    twp_column_mapping = {}
                    
                    # Find township columns in townships layer
                    for col in twp_gdf.columns:
                        col_upper = col.upper()
                        if ('TWNSHP' in col_upper or 'TOWNSHIP' in col_upper) and ('NO' in col_upper or 'NUM' in col_upper):
                            twp_column_mapping['TWNSHPNO'] = col
                        elif ('TWNSHP' in col_upper or 'TOWNSHIP' in col_upper) and 'DIR' in col_upper:
                            twp_column_mapping['TWNSHPDIR'] = col
                        elif 'RANGE' in col_upper and ('NO' in col_upper or 'NUM' in col_upper):
                            twp_column_mapping['RANGENO'] = col
                        elif 'RANGE' in col_upper and 'DIR' in col_upper:
                            twp_column_mapping['RANGEDIR'] = col
                        elif ('PRINMER' in col_upper or 'MERIDIAN' in col_upper):
                            twp_column_mapping['PRINMERCD'] = col
                    
                    logger.info(f"Township column mapping: {twp_column_mapping}")
                    
                    # Rename township columns
                    if twp_column_mapping:
                        twp_gdf = twp_gdf.rename(columns=twp_column_mapping)
                    
                    # Keep only needed township columns
                    twp_keep_cols = ['TWNSHPNO', 'TWNSHPDIR', 'RANGENO', 'RANGEDIR', 'PRINMERCD', 'geometry']
                    twp_present = [c for c in twp_keep_cols if c in twp_gdf.columns]
                    twp_gdf = twp_gdf[twp_present]
                    
                    # Perform spatial join: sections to townships
                    logger.info("Performing spatial join of sections to townships...")
                    sec_gdf_joined = gpd.sjoin(sec_gdf, twp_gdf, how='left', predicate='within')
                    
                    # Use the joined data for index creation
                    sec_gdf = sec_gdf_joined
                    
                    logger.info(f"After spatial join, sections columns: {list(sec_gdf.columns)}")
                    logger.info(f"Sections with TRS data: {len(sec_gdf[sec_gdf['TWNSHPNO'].notna()])} / {len(sec_gdf)}")
                    
                except Exception as e:
                    logger.warning(f"Spatial join failed, proceeding with sections only: {e}")

            # 2b) Optional: write townships parquet if FGDB layer provided
            ranges_parquet_path: Optional[Path] = None
            if townships_fgdb and townships_layer:
                try:
                    townships_parquet = pq_dir / "townships.parquet"
                    if 'twp_gdf' in locals():
                        # Use the already loaded townships data
                        twp_gdf.to_parquet(townships_parquet, compression="zstd", index=False)
                        townships_parquet_path = townships_parquet
                    else:
                        # Load townships separately if spatial join failed
                        twp_gdf = gpd.read_file(townships_fgdb, layer=townships_layer)
                        try:
                            if twp_gdf.crs is not None and twp_gdf.crs.to_epsg() != 4326:
                                twp_gdf = twp_gdf.to_crs(4326)
                        except Exception:
                            pass
                        twp_gdf.to_parquet(townships_parquet, compression="zstd", index=False)
                        townships_parquet_path = townships_parquet
                    
                    # 2b.1) Build ranges parquet by dissolving townships by range
                    if {'RANGENO', 'RANGEDIR'}.issubset(set(twp_gdf.columns)):
                        # Clean invalid geometries before dissolving
                        logger.info("Cleaning township geometries before dissolving...")
                        twp_gdf['geometry'] = twp_gdf['geometry'].buffer(0)  # Fix invalid geometries
                        twp_gdf = twp_gdf[twp_gdf['geometry'].is_valid]  # Remove still-invalid ones

                        dissolved = twp_gdf.dissolve(by=['RANGENO', 'RANGEDIR'], as_index=False, dropna=True)
                        # Optional light simplify to reduce size
                        try:
                            dissolved['geometry'] = dissolved['geometry'].buffer(0.0001).simplify(0.0001)
                        except Exception:
                            pass
                        
                        # Keep minimal columns for overlays
                        keep_cols = ['RANGENO', 'RANGEDIR', 'geometry']
                        present = [c for c in keep_cols if c in dissolved.columns]
                        dissolved = dissolved[present]
                        
                        ranges_parquet = pq_dir / "ranges.parquet"
                        dissolved.to_parquet(ranges_parquet, compression="zstd", index=False)
                        ranges_parquet_path = ranges_parquet
                        logger.info(f"✅ Built ranges parquet: {len(dissolved)} ranges")
                    else:
                        logger.info("Skipping ranges parquet (missing RANGENO/RANGEDIR in townships)")
                except Exception as e:
                    logger.warning(f"Townships parquet build skipped: {e}")

            # 2c) Optional: write quarter sections parquet if FGDB layer provided  
            subdivisions_parquet_path: Optional[Path] = None
            if subdivisions_fgdb and subdivisions_layer:
                try:
                    if progress_callback:
                        progress_callback("Building quarter sections parquet... (Est. 12-15 min)")
                    logger.info("Building quarter sections parquet (chunked)...")

                    # Prepare parts directory for chunked GeoParquet
                    parts_dir = pq_dir / "quarter_sections_parts"
                    if parts_dir.exists():
                        # Clear existing parts
                        try:
                            shutil.rmtree(parts_dir)
                        except Exception:
                            pass
                    parts_dir.mkdir(parents=True, exist_ok=True)

                    # Discover total features via fiona without loading into memory
                    with fiona.open(subdivisions_fgdb, layer=subdivisions_layer) as src:
                        total_features = len(src)
                        logger.info(f"Quarter sections total features: {total_features:,}")

                    # Read in chunks and write individual parquet part files
                    chunk_size = 10000
                    written = 0
                    keep_cols = ['FRSTDIVID', 'SECDIVTYP', 'SECDIVTXT', 'SECDIVNO', 'SECDIVLAB', 'GISACRE', 'geometry']

                    start = 0
                    part_index = 0
                    while start < total_features:
                        end = min(start + chunk_size, total_features)
                        # Calculate progress percentage for frontend
                        percent_complete = int((start / total_features) * 100)

                        if progress_callback:
                            progress_callback({
                                "status": f"Processing quarter sections: {start:,}-{end-1:,} of {total_features:,}",
                                "overall": {
                                    "downloaded": start,
                                    "total": total_features,
                                    "percent": percent_complete
                                },
                                "estimated_time": "12-15 minutes",
                                "phase": "quarter_sections_chunked"
                            })
                        logger.info(f"Quarter sections: reading rows slice({start}, {end})")

                        # Use GeoPandas slice read to limit memory
                        sub_chunk = gpd.read_file(
                            subdivisions_fgdb,
                            layer=subdivisions_layer,
                            rows=slice(start, end)
                        )

                        # Normalize CRS
                        try:
                            if sub_chunk.crs is not None and sub_chunk.crs.to_epsg() != 4326:
                                sub_chunk = sub_chunk.to_crs(4326)
                        except Exception:
                            pass

                        # Keep essential columns
                        present = [c for c in keep_cols if c in sub_chunk.columns]
                        sub_chunk = sub_chunk[present]

                        # Write part file
                        part_path = parts_dir / f"part_{part_index:05d}.parquet"
                        sub_chunk.to_parquet(part_path, compression="zstd", index=False)

                        written += len(sub_chunk)
                        part_index += 1
                        start = end

                    # Write a simple manifest for the parts
                    manifest_path = parts_dir / "_manifest.json"
                    try:
                        import json
                        manifest = {
                            "success": True,
                            "total_features": written,
                            "chunk_size": chunk_size,
                            "parts": part_index
                        }
                        with open(manifest_path, 'w') as mf:
                            json.dump(manifest, mf)
                    except Exception:
                        pass
                    
                    subdivisions_parquet_path = parts_dir
                    logger.info(f"✅ Built quarter sections parquet parts: {written:,} features in {part_index} files")
                    if progress_callback:
                        progress_callback("Quarter sections parquet complete")
                    
                except Exception as e:
                    logger.warning(f"Quarter sections parquet build skipped: {e}")
                    if progress_callback:
                        progress_callback(f"Quarter sections build failed: {e}")

            # 3) Build compact index
            records = []
            for _, row in sec_gdf.iterrows():
                try:
                    geom = row.geometry
                    if geom is None:
                        continue
                    if getattr(geom, "geom_type", "") == "MultiPolygon":
                        # choose largest
                        geom = max(list(geom.geoms), key=lambda p: p.area)
                    centroid = geom.centroid
                    minx, miny, maxx, maxy = geom.bounds

                    # Derive canonical corners using exterior coords and azimuth selection
                    def pick_corner(target_deg: float) -> Tuple[float, float]:
                        import math
                        cx, cy = float(centroid.x), float(centroid.y)
                        best = None
                        best_d = 1e9
                        for x, y in list(geom.exterior.coords):
                            dx, dy = x - cx, y - cy
                            # azimuth clockwise from north
                            ang = math.degrees(math.atan2(dx, dy))
                            if ang < 0:
                                ang += 360.0
                            diff = abs((ang - target_deg + 180) % 360 - 180)
                            if diff < best_d:
                                best_d = diff
                                best = (float(x), float(y))
                        if best is None:
                            return float(cx), float(cy)
                        return best

                    ne_lon, ne_lat = pick_corner(45.0)
                    se_lon, se_lat = pick_corner(135.0)
                    sw_lon, sw_lat = pick_corner(225.0)
                    nw_lon, nw_lat = pick_corner(315.0)

                    rec = {
                        "t": int(row.get('TWNSHPNO')) if pd.notnull(row.get('TWNSHPNO')) else None,
                        "td": str(row.get('TWNSHPDIR')).upper().strip() if pd.notnull(row.get('TWNSHPDIR')) else None,
                        "r": int(row.get('RANGENO')) if pd.notnull(row.get('RANGENO')) else None,
                        "rd": str(row.get('RANGEDIR')).upper().strip() if pd.notnull(row.get('RANGEDIR')) else None,
                        "s": int(row.get('FRSTDIVNO')) if pd.notnull(row.get('FRSTDIVNO')) else None,
                        "pm": str(row.get('PRINMERCD')).upper().strip() if 'PRINMERCD' in sec_gdf.columns and pd.notnull(row.get('PRINMERCD')) else None,
                        "centroid_lat": float(centroid.y),
                        "centroid_lon": float(centroid.x),
                        "min_lat": float(miny),
                        "min_lon": float(minx),
                        "max_lat": float(maxy),
                        "max_lon": float(maxx),
                        "nw_lat": float(nw_lat), "nw_lon": float(nw_lon),
                        "ne_lat": float(ne_lat), "ne_lon": float(ne_lon),
                        "se_lat": float(se_lat), "se_lon": float(se_lon),
                        "sw_lat": float(sw_lat), "sw_lon": float(sw_lon),
                    }
                    records.append(rec)
                except Exception as e:
                    logger.debug(f"Index build skipped a feature: {e}")
                    continue

            if not records:
                return {"success": False, "error": "No records for index"}

            df = pd.DataFrame.from_records(records)
            index_path = self._index_path(state)
            df.to_parquet(index_path, compression="zstd", index=False)
            # Warm in-process cache
            self._state_to_index_df[state] = df

            result = {
                "success": True,
                "sections_parquet": str(sections_parquet),
                "sections_index": str(index_path),
                "rows": int(len(df)),
            }
            if townships_parquet_path:
                result["townships_parquet"] = str(townships_parquet_path)
            if ranges_parquet_path:
                result["ranges_parquet"] = str(ranges_parquet_path)
            if subdivisions_parquet_path:
                result["quarter_sections_parquet"] = str(subdivisions_parquet_path)
            return result
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _match_row(self, df: pd.DataFrame, key: Dict[str, Any]) -> Optional[pd.Series]:
        t = int(key.get("township_number"))
        td = str(key.get("township_direction")).upper().strip()[0:1]
        r = int(key.get("range_number"))
        rd = str(key.get("range_direction")).upper().strip()[0:1]
        s = int(key.get("section_number"))
        cand = df[(df["t"] == t) & (df["td"].str[0] == td) & (df["r"] == r) & (df["rd"].str[0] == rd) & (df["s"] == s)]
        if len(cand) == 0:
            return None
        return cand.iloc[0]

    def get_centroid_bounds(self, state: str, plss: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        df = self.load_index(state)
        if df is None:
            return None
        row = self._match_row(df, plss)
        if row is None:
            return None
        return {
            "center": {"lat": float(row["centroid_lat"]), "lon": float(row["centroid_lon"])},
            "bounds": {
                "min_lat": float(row["min_lat"]), "min_lon": float(row["min_lon"]),
                "max_lat": float(row["max_lat"]), "max_lon": float(row["max_lon"]),
            }
        }

    def get_corner(self, state: str, plss: Dict[str, Any], label: str) -> Optional[Dict[str, float]]:
        df = self.load_index(state)
        if df is None:
            return None
        row = self._match_row(df, plss)
        if row is None:
            return None
        lab = (label or "").lower()
        if "ne" in lab or ("north" in lab and "east" in lab):
            return {"lat": float(row["ne_lat"]), "lon": float(row["ne_lon"])}
        if "se" in lab or ("south" in lab and "east" in lab):
            return {"lat": float(row["se_lat"]), "lon": float(row["se_lon"])}
        if "sw" in lab or ("south" in lab and "west" in lab):
            return {"lat": float(row["sw_lat"]), "lon": float(row["sw_lon"])}
        # default NW
        return {"lat": float(row["nw_lat"]), "lon": float(row["nw_lon"])}