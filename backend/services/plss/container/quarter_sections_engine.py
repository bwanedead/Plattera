"""
Container Quarter Sections Engine
Dedicated engine for retrieving quarter section features within container bounds using spatial intersection
"""
import logging
import geopandas as gpd
import pandas as pd
from typing import Dict, Any, Optional, Tuple
from shapely.geometry import box
import os
from config.paths import plss_root

logger = logging.getLogger(__name__)

class ContainerQuarterSectionsEngine:
    """Dedicated engine for container quarter section overlays using spatial filtering"""
    
    def __init__(self, data_dir: str = "../plss"):
        # Use caller-provided dir if overridden, otherwise centralized PLSS root
        self.data_dir = data_dir if data_dir != "../plss" else str(plss_root())
        
    def get_quarter_sections_features(self, container_bounds: Dict[str, float], plss_info: Dict[str, Any]) -> Dict[str, Any]:
        logger.info("🔲 CONTAINER QUARTER SECTIONS ENGINE: Starting quarter sections feature retrieval")
        logger.info(f"📍 Container bounds: {container_bounds}")
        logger.info(f"📍 PLSS info: {plss_info}")

        self.plss_info = plss_info
        
        # Build TRS key for cell-scoped operations
        self.trs_key = (f"T{str(plss_info['township_number']).zfill(3)}{plss_info['township_direction']}"
                       f"R{str(plss_info['range_number']).zfill(3)}{plss_info['range_direction']}")
        logger.info(f"🔑 TRS key: {self.trs_key}")
        
        try:
            # Get state from PLSS info
            state = plss_info.get('state', 'Wyoming').lower()
            
            # Use geometry parquet files for proper shape overlays
            # The geometry files contain actual shape boundaries, not just centroids
            quarter_sections_file = os.path.join(self.data_dir, state, "parquet", "quarter_sections_parts").replace('\\', '/')
            
            # Load quarter sections data from geometry directory
            if not os.path.exists(quarter_sections_file):
                logger.error(f"❌ Quarter sections parquet directory not found: {quarter_sections_file}")
                return self._create_error_response("Quarter sections parquet directory not found")
            
            # Read parquet file directly with geopandas to handle geometry properly
            quarter_sections_gdf = gpd.read_parquet(quarter_sections_file)
            logger.info(f"📊 Loaded quarter sections data: {quarter_sections_gdf.shape} features, columns: {list(quarter_sections_gdf.columns)}")
            
            # COORDINATE DEBUGGING: Analyze loaded data
            self._debug_coordinates(quarter_sections_gdf, "LOADED QUARTER SECTIONS", container_bounds)
            
            # Validate geometry column exists
            if quarter_sections_gdf.geometry.name != 'geometry':
                logger.error("❌ No valid geometry column found in quarter sections data")
                return self._create_error_response("No valid geometry column found in quarter sections data")
            
            # Get the specific township-range cell boundary from the sections data
            cell_boundary = self._get_cell_boundary(quarter_sections_gdf, plss_info)
            if cell_boundary is None:
                logger.error("❌ Could not determine cell boundary from quarter sections data")
                return self._create_error_response("Could not determine cell boundary from quarter sections data")
            
            logger.info(f"🎯 Cell boundary determined: {cell_boundary}")
            
            # COORDINATE DEBUGGING: Analyze cell boundary vs container bounds
            if cell_boundary:
                # Create a simple GeoDataFrame with just the cell boundary for analysis
                cell_gdf = gpd.GeoDataFrame([1], geometry=[cell_boundary], crs=quarter_sections_gdf.crs)
                self._debug_coordinates(cell_gdf, "CELL BOUNDARY", container_bounds, cell_boundary)
            
            # Filter quarter sections using spatial intersection with the cell boundary
            filtered_gdf = self._filter_quarter_sections_by_spatial_intersection(quarter_sections_gdf, cell_boundary)
            logger.info(f"🎯 Quarter sections spatial filtering result: {filtered_gdf.shape} features")
            
            # COORDINATE DEBUGGING: Analyze filtered data
            self._debug_coordinates(filtered_gdf, "FILTERED QUARTER SECTIONS", container_bounds, cell_boundary)
            
            # Validate spatial bounds using cell boundary for consistency
            spatial_validation = self._validate_spatial_bounds(filtered_gdf, container_bounds, cell_boundary)
            logger.info(f"🔍 Spatial validation: {spatial_validation}")
            
            # Convert to GeoJSON
            geojson = self._to_geojson(filtered_gdf, plss_info)
            
            return {
                "type": "FeatureCollection",
                "features": geojson,
                "validation": {
                    "requested_township": f"T{plss_info.get('township_number')}{plss_info.get('township_direction')}",
                    "requested_range": f"R{plss_info.get('range_number')}{plss_info.get('range_direction')}",
                    "cell_identifier": f"T{plss_info.get('township_number')}{plss_info.get('township_direction')} R{plss_info.get('range_number')}{plss_info.get('range_direction')}",
                    "features_returned": len(geojson),
                    "spatial_validation": spatial_validation,
                    "container_bounds": container_bounds,
                    "engine": "ContainerQuarterSectionsEngine",
                    "filtering_method": "spatial_intersection",
                    "data_source": "quarter_sections_parquet"
                }
            }
            
        except Exception as e:
            logger.error(f"❌ Container quarter sections engine failed: {e}")
            return self._create_error_response(f"Engine error: {str(e)}")
    
    def _filter_quarter_sections_by_spatial_intersection(self, quarter_sections_gdf: gpd.GeoDataFrame, cell_boundary: Any) -> gpd.GeoDataFrame:
        """Filter quarter sections using spatial intersection with the cell boundary"""
        logger.info(f"🎯 Filtering {len(quarter_sections_gdf)} quarter sections by spatial intersection")
        
        # Find quarter sections that intersect with the cell boundary
        intersecting_mask = quarter_sections_gdf.geometry.intersects(cell_boundary)
        filtered_gdf = quarter_sections_gdf[intersecting_mask].copy()
        
        logger.info(f"✅ Spatial intersection filter applied: {len(filtered_gdf)} quarter sections intersect cell boundary")
        
        # Additional filtering: ensure quarter sections are actually within the cell boundary
        # Some quarter sections might just touch the boundary, we want quarter sections that are mostly inside
        if not filtered_gdf.empty:
            # Calculate intersection area ratio for each quarter section
            def calculate_intersection_ratio(row):
                try:
                    intersection = row.geometry.intersection(cell_boundary)
                    if intersection.is_empty:
                        return 0.0
                    intersection_area = intersection.area
                    quarter_section_area = row.geometry.area
                    if quarter_section_area == 0:
                        return 0.0
                    return intersection_area / quarter_section_area
                except Exception:
                    return 0.0
            
            filtered_gdf['intersection_ratio'] = filtered_gdf.apply(calculate_intersection_ratio, axis=1)
            
            # Only keep quarter sections where at least 50% of the quarter section is within the cell
            significant_quarter_sections = filtered_gdf[filtered_gdf['intersection_ratio'] >= 0.5].copy()
            
            logger.info(f"🔍 Significant quarter sections filter: {len(filtered_gdf)} → {len(significant_quarter_sections)} (50%+ within cell)")
            
            # FILTER TO QUARTER-QUARTER SECTIONS (~40 acres), THEN DISSOLVE TO QUARTER SECTIONS (~160 acres)
            logger.info(f"🔍 FILTERING: Converting quarter-quarters to quarter sections")
            
            # Step 1: Filter to true quarter-quarter sections (~40 acres)
            qq = self._filter_to_true_quarter_quarters(significant_quarter_sections)
            logger.info(f"🔍 Quarter-quarters filtered: {len(significant_quarter_sections)} → {len(qq)} features")
            
            # NEW: everything we filtered OUT are potential Government Lots / non-aliquot parts
            fillers = significant_quarter_sections.loc[~significant_quarter_sections.index.isin(qq.index)].copy()
            if not fillers.empty:
                logger.info(f"🧩 Non-aliquot fillers to absorb: {len(fillers)}")
            
            # Step 2: Dissolve quarter-quarters to quarter sections (~160 acres) with fillers
            quarters = self._dissolve_to_quarter_sections(qq, fillers=fillers)
            logger.info(f"🔍 Quarter sections dissolved: {len(qq)} → {len(quarters)} features")
            
            # Log sample of dissolved features for validation
            if not quarters.empty:
                sample_cols = [col for col in ['section_number', 'parent_quarter', 'section_quarter_key'] if col in quarters.columns]
                if sample_cols:
                    sample = quarters[sample_cols].head(5)
                    logger.info(f"📋 Sample dissolved quarter sections:\n{sample}")
            else:
                logger.warning("⚠️ No quarter sections found after dissolution")
            
            return quarters
        
        return filtered_gdf
    
    def _spatial_join_with_sections(self, gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
        """Perform spatial join with sections to get proper section numbers for quarter sections"""
        logger.info(f"🔗 Performing spatial join with sections for {len(gdf)} quarter sections")

        # Attribute-first section assignment (fallback to spatial)
        if 'FRSTDIVNO' in gdf.columns and gdf['FRSTDIVNO'].notna().any():
            logger.info("🔗 Using attribute-based section assignment")
            gdf = gdf.copy()
            gdf['section_number'] = gdf['FRSTDIVNO'].astype(str).str.zfill(2)
            return gdf
        else:
            logger.info("🔗 Using spatial join for section assignment")
            
            # Use the new cell sections method to get the correct 36 sections
            sections = self._get_cell_sections()
            if sections.empty:
                logger.error("❌ No cell sections available for spatial join")
                return gdf
            
            # Ensure CRS consistency
            if sections.crs != gdf.crs:
                sections = sections.to_crs(gdf.crs)

            # Spatial join; keep left index so we can dedupe PER QQ
            joined = gpd.sjoin(gdf, sections, how='left', predicate='intersects')
            joined = joined.reset_index(names='src_idx')  # src_idx = original QQ row id

            # pick the section with the largest overlap for each QQ
            def int_area(row):
                try:
                    if pd.isna(row.get('index_right')): 
                        return 0.0
                    return row.geometry.intersection(sections.loc[row['index_right'], 'geometry']).area
                except Exception:
                    return 0.0

            joined['_int_area'] = joined.apply(int_area, axis=1)
            before = len(joined)
            joined = joined.sort_values('_int_area', ascending=False).drop_duplicates(subset=['src_idx'], keep='first')
            logger.info(f"🧹 Join rows: {before} → {len(joined)} after per-QQ dedupe")

            # canonical section number column
            if 'FRSTDIVNO_right' in joined.columns:
                joined['section_number'] = joined['FRSTDIVNO_right']
            elif 'FRSTDIVNO' in joined.columns:  # very rare fallback
                joined['section_number'] = joined['FRSTDIVNO']
            else:
                joined['section_number'] = pd.NA

            return joined.drop(columns=['_int_area'], errors='ignore')
    
    def _dissolve_quarter_sections_by_section(self, gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
        """Dissolve quarter sections by section to get actual quarter section boundaries"""
        logger.info(f"🔄 Dissolving {len(gdf)} quarter section parcels by section")
        
        if gdf.empty:
            return gdf
        
        # We need to extract the section number from the quarter section data
        # The SECDIVNO field contains quarter section identifiers like "SENW", "NESW", etc.
        # We need to find the parent section number
        
        # First, let's see what columns we have and what the data looks like
        logger.info(f"📊 Available columns: {list(gdf.columns)}")
        
        # Try to extract section number from various possible sources
        if 'SECDIVNO' in gdf.columns:
            # Log some sample SECDIVNO values to understand the pattern
            sample_divnos = gdf['SECDIVNO'].head(10).tolist()
            logger.info(f"📋 Sample SECDIVNO values: {sample_divnos}")
            
            # We need to extract both section number and quarter type
            # The SECDIVNO format seems to be like "SENW", "NESW", etc.
            # We need to find the parent section number from the geometry or other properties
            
            # Extract quarter types from SECDIVNO
            quarter_types = []
            for divno in gdf['SECDIVNO']:
                if isinstance(divno, str):
                    if len(divno) >= 2:
                        quarter_type = divno[-2:] if divno.endswith(('NE', 'NW', 'SE', 'SW')) else divno[-4:]
                    else:
                        quarter_type = divno
                else:
                    quarter_type = str(divno)
                quarter_types.append(quarter_type)
            
            gdf = gdf.copy()
            gdf['quarter_type'] = quarter_types
            
            # Use section numbers from spatial join if available
            if 'section_number' in gdf.columns:
                logger.info(f"✅ Using section numbers from spatial join")
            else:
                logger.warning("⚠️ No section numbers found, using fallback")
                gdf['section_number'] = 1
            
            gdf['section_quarter_key'] = gdf['section_number'].astype(str) + '_' + gdf['quarter_type']
            
            logger.info(f"🔍 Section numbers found: {list(set(gdf['section_number']))}")
            logger.info(f"🔍 Quarter types found: {list(set(quarter_types))}")
            logger.info(f"🔍 Unique section-quarter combinations: {len(set(gdf['section_quarter_key']))}")
            
            # Group by section + quarter type and dissolve
            try:
                dissolved = gdf.dissolve(by='section_quarter_key', as_index=False)
                logger.info(f"✅ Dissolved quarter sections: {len(gdf)} parcels → {len(dissolved)} quarter sections")
                
                # Log the dissolved features
                if not dissolved.empty:
                    sample = dissolved[['section_quarter_key', 'SECDIVTXT']].head(10)
                    logger.info(f"📋 Sample dissolved quarter sections:\n{sample}")
                
                return dissolved
                
            except Exception as e:
                logger.error(f"❌ Failed to dissolve quarter sections: {e}")
                return gdf
        else:
            logger.warning("⚠️ No SECDIVNO column found, cannot dissolve quarter sections")
            return gdf
    
    def _get_cell_boundary(self, quarter_sections_gdf: gpd.GeoDataFrame, plss_info: Dict[str, Any]) -> Optional[Any]:
        """Get the boundary of the specific township-range cell from townships data"""
        township_num = plss_info.get('township_number')
        township_dir = plss_info.get('township_direction')
        range_num = plss_info.get('range_number')
        range_dir = plss_info.get('range_direction')
        
        logger.info(f"🔍 Getting cell boundary for T{township_num}{township_dir} R{range_num}{range_dir}")
        
        try:
            # Load townships data to get the cell boundary
            townships_path = os.path.join(self.data_dir, plss_info.get('state', 'Wyoming').lower(), "parquet", "townships.parquet").replace('\\', '/')
            if not os.path.exists(townships_path):
                logger.error(f"❌ Townships data not found: {townships_path}")
                return None
            
            townships_gdf = gpd.read_parquet(townships_path)
            
            # Convert to string format for filtering
            township_str = f"{township_num:03d}" if isinstance(township_num, int) else str(township_num).zfill(3)
            range_str = f"{range_num:03d}" if isinstance(range_num, int) else str(range_num).zfill(3)
            
            # Filter to exact cell
            mask = (
                (townships_gdf['TWNSHPNO'] == township_str) & 
                (townships_gdf['TWNSHPDIR'] == township_dir) &
                (townships_gdf['RANGENO'] == range_str) & 
                (townships_gdf['RANGEDIR'] == range_dir)
            )
            
            cell = townships_gdf[mask]
            
            if cell.empty:
                logger.error(f"❌ No cell found for T{township_str}{township_dir} R{range_str}{range_dir}")
                return None
            
            # Return the geometry of the cell
            cell_geometry = cell.iloc[0].geometry
            logger.info(f"✅ Found cell boundary for T{township_str}{township_dir} R{range_str}{range_dir}")
            
            return cell_geometry
            
        except Exception as e:
            logger.error(f"❌ Failed to get cell boundary: {e}")
            return None
    
    def _filter_to_true_quarter_quarters(self, gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
        """Filter to only show true quarter-quarter sections (~40 acres), not smaller subdivisions"""
        logger.info(f"🔍 Filtering to quarter-quarter sections with {len(gdf)} features")
        
        # QQ codes are 4 letters and each 2-letter chunk ∈ {NE,NW,SE,SW}
        def is_qq(code: str) -> bool:
            if not isinstance(code, str) or len(code) != 4:
                return False
            return code[:2] in {"NE","NW","SE","SW"} and code[2:] in {"NE","NW","SE","SW"}
        
        # Primary filter: "Aliquot Part" with proper 4-letter QQ codes
        aliquot = gdf['SECDIVTXT'].eq('Aliquot Part') if 'SECDIVTXT' in gdf.columns else True
        code_filter = gdf['SECDIVNO'].map(is_qq) if 'SECDIVNO' in gdf.columns else True
        
        # Secondary filter: acreage sanity check (32-55 acres)
        size = gdf['GISACRE'].between(32, 55) if 'GISACRE' in gdf.columns else True
        
        filtered = gdf[aliquot & code_filter & size].copy()
        logger.info(f"🔍 Quarter-quarters filtered: {len(gdf)} → {len(filtered)} features")
        
        # Log filtering results
        if 'SECDIVTXT' in gdf.columns:
            aliquot_count = aliquot.sum()
            logger.info(f"🎯 Aliquot Part matches: {aliquot_count} features")
        
        if 'SECDIVNO' in gdf.columns:
            code_count = code_filter.sum()
            logger.info(f"🎯 QQ code filter matches: {code_count} features")
        
        if 'GISACRE' in gdf.columns:
            size_count = size.sum()
            logger.info(f"🎯 Size filter matches (32-55 acres): {size_count} features")
            
            # Log acreage statistics for filtered data
            if not filtered.empty:
                acre_stats = filtered['GISACRE'].describe()
                logger.info(f"📊 Filtered GISACRE statistics: {acre_stats}")
        
        return filtered
    
    def _parent_quarter_from_secdivno(self, s: str):
        """Extract parent quarter from SECDIVNO (last two letters must be NE, NW, SE, SW)"""
        if isinstance(s, str) and len(s) >= 2:
            q = s[-2:].upper()
            return q if q in {"NE", "NW", "SE", "SW"} else None
        return None
    
    def _dissolve_to_quarter_sections(self, qq: gpd.GeoDataFrame, fillers: gpd.GeoDataFrame = None) -> gpd.GeoDataFrame:
        """Dissolve quarter-quarter sections to quarter sections by section number and parent quarter"""
        logger.info(f"🔄 Dissolving {len(qq)} quarter-quarters to quarter sections")
        if qq.empty:
            return qq

        qq = self._spatial_join_with_sections(qq)

        # normalize codes (handles stray spaces / case)
        qq['SECDIVNO'] = qq['SECDIVNO'].astype(str).str.strip().str.upper()
        qq['parent_quarter'] = qq['SECDIVNO'].str[-2:]  # Direct extraction: last 2 letters
        qq = qq[qq['parent_quarter'].isin(['NE','NW','SE','SW'])].copy()  # Filter valid quarters

        # Use the normalized column produced by the join; if missing, fall back gracefully
        if 'section_number' not in qq.columns or qq['section_number'].isna().all():
            logger.warning("⚠️ No section_number after join; falling back to FRSTDIVNO/FRSTDIVNO_right")
            qq['section_number'] = (
                qq.get('FRSTDIVNO') if 'FRSTDIVNO' in qq.columns
                else qq.get('FRSTDIVNO_right')
            )

        qq = qq.dropna(subset=['parent_quarter', 'section_number']).copy()
        # zfill to avoid '1' vs '01' grouping splits
        qq['section_number'] = qq['section_number'].astype(str).str.zfill(2)

        # De-duplicate using src_idx (original QQ row id) instead of FRSTDIVID
        if 'src_idx' in qq.columns:
            qq = qq.drop_duplicates(subset=['src_idx'])

        # Carry the TRS into the join & dissolve
        qq['trs_key'] = self.trs_key
        qq['section_number'] = qq['section_number'].astype(str).str.zfill(2)
        qq['section_quarter_key'] = qq['trs_key'] + "_S" + qq['section_number'] + "_" + qq['parent_quarter']

        # Geometry cleaning before dissolve
        try:
            # Try precision cleaning if available
            qq['geometry'] = qq.geometry.set_precision(1e-8).buffer(0)
        except AttributeError:
            # Fallback: topology fix
            qq['geometry'] = qq.geometry.buffer(0)

        # Dissolve QQs to Quarters
        dissolved = qq.dissolve(by='section_quarter_key', as_index=False, aggfunc='first')

        # Keep helpful columns
        dissolved['parent_quarter'] = dissolved['parent_quarter']
        dissolved['section_number'] = dissolved['section_number']

        logger.info(f"✅ QQ→Q: {len(qq)} → {len(dissolved)}; "
                    f"quarters per section: {dissolved['section_number'].value_counts().to_dict()}")

        # ---------- NEW: absorb non-aliquot "fillers" (Gov Lots, etc.) ----------
        if fillers is not None and not fillers.empty:
            fillers = self._spatial_join_with_sections(fillers)
            if 'section_number' not in fillers.columns:
                logger.warning("⚠️ No section_number on fillers; skipping absorption")
            else:
                # ensure zfill and CRS
                fillers['section_number'] = fillers['section_number'].astype(str).str.zfill(2)
                if dissolved.crs != fillers.crs:
                    fillers = fillers.to_crs(dissolved.crs)

                absorbed = 0
                for i, lot in fillers.iterrows():
                    sec = lot['section_number']
                    cand = dissolved[dissolved['section_number'] == sec]
                    if cand.empty:
                        continue

                    # pick quarter with largest overlap; require ≥50% of lot area overlap
                    inter = cand.geometry.intersection(lot.geometry)
                    areas = inter.area
                    if areas.max() <= 0:
                        continue
                    target_idx = areas.idxmax()
                    overlap_ratio = float(areas.max() / max(lot.geometry.area, 1e-12))
                    if overlap_ratio >= 0.50:
                        dissolved.at[target_idx, 'geometry'] = dissolved.at[target_idx, 'geometry'].union(lot.geometry)
                        absorbed += 1

                logger.info(f"🧩 Absorbed {absorbed}/{len(fillers)} filler parts into quarters")

        # CRITICAL: Clip each quarter back to its section polygon
        dissolved = self._clip_quarters_to_sections(dissolved)
        
        # Area budget check to confirm there's no big hole left
        try:
            sec_area = self._get_cell_sections().set_index('FRSTDIVNO')['geometry'].area.sum()
            q_area = dissolved.geometry.area.sum()
            coverage_pct = 100.0 * q_area / max(sec_area, 1e-12)
            logger.info(f"📏 Coverage check (quarters/sections): {q_area:.3f} / {sec_area:.3f} sq units "
                       f"({coverage_pct:.2f}%)")
        except Exception as e:
            logger.warning(f"⚠️ Could not calculate coverage check: {e}")

        # Final geometry clean-up
        dissolved['geometry'] = dissolved['geometry'].buffer(0)
        
        # 🔴 REMOVE the "keep largest component" step — it causes the island/band
        # def simplify_geometry(geom):
        #     if geom.geom_type == 'MultiPolygon':
        #         return max(geom.geoms, key=lambda p: p.area)
        #     return geom
        # dissolved['geometry'] = dissolved['geometry'].apply(simplify_geometry)
        
        # Remove empty/invalid geometries
        dissolved = dissolved[~dissolved['geometry'].is_empty]
        
        # Bonus sanity logs
        counts = dissolved.groupby('section_number')['parent_quarter'].nunique()
        logger.info(f"🔢 unique quarters per section (sample): {counts.sort_index().head(12).to_dict()}")
        logger.info(f"📦 total quarters: {len(dissolved)} (expected ≤ 144)")
        
        # Log any sections with fewer than 4 quarters
        incomplete_sections = counts[counts < 4]
        if not incomplete_sections.empty:
            logger.warning(f"⚠️ Sections with <4 quarters after absorption: {incomplete_sections.to_dict()}")
        
        return dissolved
    
    def _clip_quarters_to_sections(self, quarters: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
        """Clip each quarter back to its section polygon to ensure perfect alignment"""
        logger.info(f"✂️ Clipping {len(quarters)} quarters to section boundaries")
        
        try:
            # Use the new cell sections method to get the correct 36 sections
            sections = self._get_cell_sections()
            if sections.empty:
                logger.warning("⚠️ No cell sections available for clipping, returning unclipped quarters")
                return quarters
            
            # Ensure CRS consistency
            if sections.crs != quarters.crs:
                sections = sections.to_crs(quarters.crs)
            
            # Build section index using the normalized section numbers
            sections['section_number'] = sections['FRSTDIVNO'].astype(str).str.zfill(2)
            sec_index = {row.section_number: row.geometry for _, row in sections.iterrows()}
            
            # Clip each quarter to its section
            def clip_to_section(row):
                section_geom = sec_index.get(row['section_number'])
                if section_geom is None:
                    logger.warning(f"⚠️ No section geometry found for section {row['section_number']}")
                    return row.geometry
                
                try:
                    clipped = row.geometry.intersection(section_geom)
                    return clipped if not clipped.is_empty else row.geometry
                except Exception as e:
                    logger.warning(f"⚠️ Failed to clip quarter {row['section_number']}_{row['parent_quarter']}: {e}")
                    return row.geometry
            
            quarters['geometry'] = quarters.apply(clip_to_section, axis=1)
            
            logger.info(f"✅ Clipped quarters to cell section boundaries")
            return quarters
            
        except Exception as e:
            logger.error(f"❌ Failed to clip quarters to sections: {e}")
            return quarters
    
    def _validate_spatial_bounds(self, gdf: gpd.GeoDataFrame, container_bounds: Dict[str, float], cell_boundary=None) -> Dict[str, Any]:
        """Validate that features are within container bounds using cell boundary for consistency"""
        if gdf.empty:
            return {"status": "no_features", "message": "No features to validate"}
        
        # Check intersection with cell boundary
        cell_ok = 0
        if cell_boundary is not None:
            cell_ok = gdf.geometry.intersects(cell_boundary).sum()
        
        # Check intersection with container bounds bbox
        bbox = box(
            container_bounds['west'], 
            container_bounds['south'],
            container_bounds['east'], 
            container_bounds['north']
        )
        box_ok = gdf.geometry.intersects(bbox).sum()
        
        validation = {
            "total_features": len(gdf),
            "within_cell": int(cell_ok),
            "within_container_bbox": int(box_ok),
            "container_bounds": container_bounds,
            "status": "valid" if box_ok == len(gdf) else "warning"
        }
        
        if box_ok == 0:
            validation["message"] = "WARNING: No features intersect container bounds"
        elif box_ok < len(gdf):
            validation["message"] = f"Partial intersection: {box_ok}/{len(gdf)} features within container bounds"
        else:
            validation["message"] = "All features intersect container bounds"
        
        # Add cell boundary info if available
        if cell_boundary is not None:
            if cell_ok == 0:
                validation["message"] += f" | WARNING: No features intersect cell boundary"
            elif cell_ok < len(gdf):
                validation["message"] += f" | Partial cell intersection: {cell_ok}/{len(gdf)} features"
            else:
                validation["message"] += f" | All features intersect cell boundary"
        
        return validation
    
    def _to_geojson(self, gdf: gpd.GeoDataFrame, plss_info: Dict[str, Any]) -> list:
        """Convert GeoDataFrame to GeoJSON features with faithful polygon serialization"""
        features = []
        
        def poly_coords(poly):
            """Extract coordinates from polygon including interior rings"""
            return [list(poly.exterior.coords)] + [list(r.coords) for r in poly.interiors]
        
        for idx, row in gdf.iterrows():
            geom = row.geometry
            
            # Handle different geometry types faithfully
            if geom.geom_type == 'Polygon':
                geometry = {"type": "Polygon", "coordinates": poly_coords(geom)}
            elif geom.geom_type == 'MultiPolygon':
                geometry = {"type": "MultiPolygon", "coordinates": [poly_coords(p) for p in geom.geoms]}
            else:
                # Try to clean and convert other geometry types
                try:
                    cleaned = geom.buffer(0)
                    if cleaned.geom_type == 'Polygon':
                        geometry = {"type": "Polygon", "coordinates": poly_coords(cleaned)}
                    elif cleaned.geom_type == 'MultiPolygon':
                        geometry = {"type": "MultiPolygon", "coordinates": [poly_coords(p) for p in cleaned.geoms]}
                    else:
                        logger.warning(f"⚠️ Skipping unsupported geometry type: {geom.geom_type}")
                        continue
                except Exception as e:
                    logger.warning(f"⚠️ Failed to clean geometry: {e}")
                    continue
            
            # Create properties with enhanced quarter section information
            quarter_label = f"Q{row.get('parent_quarter', '?')}" if row.get('parent_quarter') else "Quarter"
            section_num = row.get('section_number') or row.get('FRSTDIVNO')
            
            props = {
                "feature_type": "quarter_section",
                "overlay_type": "container",
                    "township_number": plss_info.get('township_number'),
                    "township_direction": plss_info.get('township_direction'),
                    "range_number": plss_info.get('range_number'),
                    "range_direction": plss_info.get('range_direction'),
                "section_number": section_num,
                "quarter": row.get('parent_quarter'),
                    "cell_identifier": f"T{plss_info.get('township_number')}{plss_info.get('township_direction')} R{plss_info.get('range_number')}{plss_info.get('range_direction')}",
                    "label": quarter_label,
                "display_label": f"Sec {section_num} {quarter_label}" if section_num else quarter_label
                }
            
            feature = {
                "type": "Feature",
                "geometry": geometry,
                "properties": props
            }
            features.append(feature)
        
        logger.info(f"✅ Converted {len(features)} features to GeoJSON")
        
        # COORDINATE DEBUGGING: Log sample coordinates from GeoJSON
        if features:
            logger.info(f"🔍 GEOJSON SAMPLE COORDINATES:")
            for i, feature in enumerate(features[:3]):  # First 3 features
                geom = feature.get('geometry', {})
                if geom.get('type') == 'Polygon' and geom.get('coordinates'):
                    coords = geom['coordinates'][0]  # Exterior ring
                    if coords:
                        # Log first and last coordinate of each polygon
                        first_coord = coords[0]
                        last_coord = coords[-1]
                        logger.info(f"   📋 Feature {i+1}: First coord = {first_coord}, Last coord = {last_coord}")
        
        return features
    
    def _debug_coordinates(self, gdf: gpd.GeoDataFrame, name: str, container_bounds: Dict[str, float] = None, cell_boundary = None):
        """Debug coordinate mismatches by logging bounds and sample coordinates"""
        if gdf.empty:
            logger.warning(f"🔍 {name}: No features to analyze")
            return
        
        # Get data bounds
        bounds = gdf.total_bounds  # [minx, miny, maxx, maxy]
        data_bounds = {'west': bounds[0], 'south': bounds[1], 'east': bounds[2], 'north': bounds[3]}
        
        logger.info(f"🔍 {name} COORDINATE ANALYSIS:")
        logger.info(f"   📊 Feature count: {len(gdf)}")
        logger.info(f"   📍 Data bounds: {data_bounds}")
        
        if container_bounds:
            logger.info(f"   📦 Container bounds: {container_bounds}")
            
            # Calculate coordinate differences
            lon_diff = abs(data_bounds['west'] - container_bounds['west'])
            lat_diff = abs(data_bounds['south'] - container_bounds['south'])
            
            logger.info(f"   ⚠️  COORDINATE MISMATCH: Longitude diff = {lon_diff:.6f}°, Latitude diff = {lat_diff:.6f}°")
            
            if lon_diff > 0.1 or lat_diff > 0.1:
                logger.error(f"   🚨 MAJOR COORDINATE MISMATCH DETECTED!")
        
        if cell_boundary:
            cell_bounds = cell_boundary.bounds
            cell_dict = {'west': cell_bounds[0], 'south': cell_bounds[1], 'east': cell_bounds[2], 'north': cell_bounds[3]}
            logger.info(f"   🏠 Cell bounds: {cell_dict}")
        
        # Log sample coordinates from first few features
        sample_coords = []
        for i, (idx, row) in enumerate(gdf.head(3).iterrows()):
            geom = row.geometry
            if hasattr(geom, 'centroid'):
                center = geom.centroid
                sample_coords.append((center.x, center.y))
        
        logger.info(f"   📋 Sample coordinates: {sample_coords}")
    
    def _get_cell_sections(self) -> gpd.GeoDataFrame:
        """Get the correct 36 section polygons for the cell using representative point filtering"""
        logger.info(f"🎯 Getting cell sections for TRS: {self.trs_key}")
        
        # Get state from PLSS info
        state = self.plss_info.get('state', 'Wyoming').lower()
        sections_path = os.path.join(self.data_dir, state, "parquet", "sections.parquet").replace('\\', '/')
        
        if not os.path.exists(sections_path):
            logger.error(f"❌ Sections parquet file not found: {sections_path}")
            return gpd.GeoDataFrame(columns=["FRSTDIVNO", "geometry"], geometry="geometry")
        
        # Load sections data
        sections = gpd.read_parquet(sections_path)
        logger.info(f"📊 Loaded sections data: {sections.shape} features")
        
        # Get shapely cell geometry (no CRS attached)
        cell_geom = self._get_cell_boundary(sections, self.plss_info)
        if cell_geom is None:
            logger.error("❌ Could not determine cell boundary")
            return gpd.GeoDataFrame(columns=["FRSTDIVNO", "geometry"], geometry="geometry")
        
        # Ensure sections has a CRS (assume WGS84 if missing)
        if sections.crs is None:
            sections = sections.set_crs("EPSG:4326")
        
        # Wrap the shapely geometry in a GeoSeries with the SAME CRS as sections
        cell = gpd.GeoSeries([cell_geom], crs=sections.crs).iloc[0]
        
        # Robust selection: representative point must be inside the cell (avoids edge-touchers)
        logger.info(f"🔍 Filtering sections by representative point within cell")
        inside = sections.representative_point().within(cell)
        cand = sections[inside].copy()
        
        logger.info(f"🔍 Representative point filter: {len(sections)} → {len(cand)} sections")
        
        # If we don't have exactly 36 sections, use intersects fallback
        if len(cand) != 36:
            logger.warning(f"⚠️ Expected 36 sections, got {len(cand)}; using intersects fallback")
            
            # Use intersects but dedupe by max overlap per FRSTDIVNO
            touch = sections[sections.geometry.intersects(cell)].copy()
            logger.info(f"🔍 Intersects filter: {len(sections)} → {len(touch)} sections")
            
            # Calculate overlap area for each section
            touch['_overlap'] = touch.geometry.intersection(cell).area
            
            # Dedupe by keeping the section with largest overlap per FRSTDIVNO
            touch['FRSTDIVNO'] = touch['FRSTDIVNO'].astype(str).str.zfill(2)
            cand = (touch.sort_values('_overlap', ascending=False)
                         .drop_duplicates(subset=['FRSTDIVNO'], keep='first'))
            
            logger.info(f"🔍 Overlap deduplication: {len(touch)} → {len(cand)} sections")
        
        # Keep only sections 01..36
        cand['FRSTDIVNO'] = cand['FRSTDIVNO'].astype(str).str.zfill(2)
        valid = {f"{i:02d}" for i in range(1, 37)}
        cand = cand[cand['FRSTDIVNO'].isin(valid)].copy()
        
        logger.info(f"🔍 Section number filter: {len(cand)} sections (expected 36)")
        
        # Sanity check and logging
        nums = sorted(cand['FRSTDIVNO'].unique())
        logger.info(f"📋 Cell sections {len(nums)}: {nums}")
        
        if len(cand) != 36:
            missing = sorted(list(valid - set(nums)))
            logger.warning(f"⚠️ Still not 36 sections (found {len(cand)}); missing: {missing}")
        
        # Return only the essential columns
        result = cand[['FRSTDIVNO', 'geometry']].copy()
        logger.info(f"✅ Cell sections ready: {len(result)} sections")
        
        return result
    
    def _create_error_response(self, message: str) -> Dict[str, Any]:
        """Create standardized error response"""
        return {
            "type": "FeatureCollection",
            "features": [],
            "validation": {
                "status": "error",
                "message": message,
                "features_returned": 0,
                "engine": "ContainerQuarterSectionsEngine"
            }
        }
