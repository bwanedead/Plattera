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

logger = logging.getLogger(__name__)

class ContainerQuarterSectionsEngine:
    """Dedicated engine for container quarter section overlays using spatial filtering"""
    
    def __init__(self, data_dir: str = "../plss"):
        self.data_dir = data_dir
        
    def get_quarter_sections_features(self, container_bounds: Dict[str, float], plss_info: Dict[str, Any]) -> Dict[str, Any]:
        logger.info("🔲 CONTAINER QUARTER SECTIONS ENGINE: Starting quarter sections feature retrieval")
        logger.info(f"📍 Container bounds: {container_bounds}")
        logger.info(f"📍 PLSS info: {plss_info}")
        
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
            
            # Validate geometry column exists
            if quarter_sections_gdf.geometry.name != 'geometry':
                logger.error("❌ No valid geometry column found in quarter sections data")
                return self._create_error_response("No valid geometry column found in quarter sections data")
            
            # Filter quarter sections using spatial intersection with the cell boundary
            filtered_gdf = self._filter_exact_quarter_sections(quarter_sections_gdf, plss_info)
            logger.info(f"🎯 Quarter sections spatial filtering result: {filtered_gdf.shape} features")
            
            # Validate spatial bounds
            spatial_validation = self._validate_spatial_bounds(filtered_gdf, container_bounds)
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
    
    def _filter_exact_quarter_sections(self, gdf: gpd.GeoDataFrame, plss_info: Dict[str, Any]) -> gpd.GeoDataFrame:
        """Filter to exact township-range cell for quarter sections"""
        township_num = plss_info.get('township_number')
        township_dir = plss_info.get('township_direction')
        range_num = plss_info.get('range_number')
        range_dir = plss_info.get('range_direction')
        
        logger.info(f"🎯 Filtering quarter sections for: T{township_num}{township_dir} R{range_num}{range_dir}")
        
        # CRITICAL FIX: Quarter sections data doesn't have township/range columns
        # We need to get the cell boundary from townships data first
        cell_boundary = self._get_cell_boundary(gdf, plss_info)
        
        if cell_boundary is None:
            logger.error(f"❌ No cell boundary found for T{township_num}{township_dir} R{range_num}{range_dir}")
            return gpd.GeoDataFrame()
        
        # Filter quarter sections to only those within the cell boundary
        try:
            # Use spatial intersection to filter quarter sections within the cell
            intersecting = gdf[gdf.geometry.intersects(cell_boundary)]
            
            logger.info(f"✅ Quarter sections filter applied: {len(intersecting)} features found in cell")
            
            # NEW: Filter to only true quarter sections (NE, NW, SE, SW), not smaller subdivisions
            true_quarter_sections = self._filter_to_true_quarter_sections(intersecting)
            
            # Log sample of filtered features
            if not true_quarter_sections.empty:
                available_cols = [col for col in ['SECDIVTXT', 'SECDIVNO'] if col in true_quarter_sections.columns]
                if available_cols:
                    sample = true_quarter_sections[available_cols].head(3)
                    logger.info(f"📋 Sample filtered quarter sections:\n{sample}")
            
            return true_quarter_sections
            
        except Exception as e:
            logger.error(f"❌ Failed to filter quarter sections: {e}")
            return gpd.GeoDataFrame()
    
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
    
    def _filter_to_true_quarter_sections(self, gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
        """Filter to only show true quarter sections, not smaller subdivisions"""
        logger.info(f"🔍 Starting quarter sections filtering with {len(gdf)} features")
        
        if 'SECDIVTXT' in gdf.columns:
            # Log some sample SECDIVTXT values to see what we're working with
            sample_texts = gdf['SECDIVTXT'].head(10).tolist()
            logger.info(f"📋 Sample SECDIVTXT values: {sample_texts}")
            
            # Also log unique values to see the variety
            unique_texts = gdf['SECDIVTXT'].unique()[:20].tolist()
            logger.info(f"🔍 Unique SECDIVTXT values (first 20): {unique_texts}")
            
            # Check if we have other columns that might help identify quarter sections
            logger.info(f"📊 Available columns: {list(gdf.columns)}")
            
            # For this data, "Aliquot Part" typically means quarter sections
            # "Government Lot" means irregular lots (not quarter sections)
            quarter_section_mask = gdf['SECDIVTXT'] == 'Aliquot Part'
            
            # Log how many features match the text pattern
            text_matches = quarter_section_mask.sum()
            logger.info(f"🎯 Aliquot Part matches: {text_matches} features")
            
            # Also exclude very small subdivisions (less than typical quarter section)
            if 'GISACRE' in gdf.columns:
                # Log acreage statistics
                acre_stats = gdf['GISACRE'].describe()
                logger.info(f"📊 GISACRE statistics: {acre_stats}")
                
                # For quarter sections, we want parcels around 40 acres (quarter-quarter sections)
                # or 160 acres (quarter sections)
                size_mask = (gdf['GISACRE'] >= 35) & (gdf['GISACRE'] <= 200)
                size_matches = size_mask.sum()
                logger.info(f"🎯 Size filter matches (35-200 acres): {size_matches} features")
                
                combined_mask = quarter_section_mask & size_mask
                combined_matches = combined_mask.sum()
                logger.info(f"🎯 Combined filter matches: {combined_matches} features")
            else:
                logger.warning("⚠️ No GISACRE column found, skipping size filtering")
                combined_mask = quarter_section_mask
                combined_matches = combined_mask.sum()
                logger.info(f"🎯 Text-only filter matches: {combined_matches} features")
                
            filtered = gdf[combined_mask].copy()
            logger.info(f"🎯 Filtered to true quarter sections: {len(filtered)} features (was {len(gdf)})")
            
            # Log some examples for debugging
            if not filtered.empty and 'SECDIVTXT' in filtered.columns:
                sample_texts = filtered['SECDIVTXT'].head(3).tolist()
                logger.info(f"📋 Sample quarter section names: {sample_texts}")
            else:
                logger.warning("⚠️ No quarter sections found after filtering!")
                
            return filtered
        else:
            logger.warning("⚠️ No SECDIVTXT column found, returning all features")
            return gdf
    
    def _validate_spatial_bounds(self, gdf: gpd.GeoDataFrame, container_bounds: Dict[str, float]) -> Dict[str, Any]:
        """Validate that features are within container bounds"""
        if gdf.empty:
            return {"status": "no_features", "message": "No features to validate"}
        
        # Create container bounding box
        bbox = box(
            container_bounds['west'], 
            container_bounds['south'],
            container_bounds['east'], 
            container_bounds['north']
        )
        
        # Check intersection
        intersecting = gdf[gdf.geometry.intersects(bbox)]
        
        validation = {
            "total_features": len(gdf),
            "intersecting_features": len(intersecting),
            "container_bounds": container_bounds,
            "status": "valid" if len(intersecting) > 0 else "warning"
        }
        
        if len(intersecting) == 0:
            validation["message"] = "WARNING: No features intersect container bounds"
        elif len(intersecting) < len(gdf):
            validation["message"] = f"Partial intersection: {len(intersecting)}/{len(gdf)} features"
        else:
            validation["message"] = "All features intersect container bounds"
        
        return validation
    
    def _to_geojson(self, gdf: gpd.GeoDataFrame, plss_info: Dict[str, Any]) -> list:
        """Convert GeoDataFrame to GeoJSON features"""
        features = []
        
        for idx, row in gdf.iterrows():
            geom = row.geometry
            
            # Handle MultiPolygon by taking the largest polygon
            if hasattr(geom, 'geom_type') and geom.geom_type == 'MultiPolygon':
                geom = max(geom.geoms, key=lambda p: p.area)
            
            # Create label for quarter section
            quarter_label = f"Q{row.get('FRSTDIVNO', '?')}" if row.get('FRSTDIVNO') else "Quarter"
            
            feature = {
                "type": "Feature",
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [list(geom.exterior.coords)]
                },
                "properties": {
                    "quarter_section_number": row.get('FRSTDIVNO'),
                    "township_number": plss_info.get('township_number'),
                    "township_direction": plss_info.get('township_direction'),
                    "range_number": plss_info.get('range_number'),
                    "range_direction": plss_info.get('range_direction'),
                    "feature_type": "quarter_section",
                    "overlay_type": "container",
                    "cell_identifier": f"T{plss_info.get('township_number')}{plss_info.get('township_direction')} R{plss_info.get('range_number')}{plss_info.get('range_direction')}",
                    "label": quarter_label,
                    "display_label": quarter_label
                }
            }
            features.append(feature)
        
        logger.info(f"✅ Converted {len(features)} features to GeoJSON")
        return features
    
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
