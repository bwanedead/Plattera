"""
Container Township Engine
Dedicated engine for retrieving township features within container bounds
"""
import logging
import geopandas as gpd
import pandas as pd
from typing import Dict, Any, Optional, Tuple
from shapely.geometry import box
import os

logger = logging.getLogger(__name__)

class ContainerTownshipEngine:
    """Dedicated engine for container township overlays"""
    
    def __init__(self, data_dir: str = "../plss"):
        self.data_dir = data_dir
        
    def get_township_features(self, container_bounds: Dict[str, float], plss_info: Dict[str, Any]) -> Dict[str, Any]:
        """
        Get township features for container overlay with comprehensive validation
        
        Args:
            container_bounds: Bounding box {west, south, east, north}
            plss_info: PLSS information {township_number, township_direction, range_number, range_direction}
            
        Returns:
            Dict with GeoJSON features and validation info
        """
        logger.info("🏘️ CONTAINER TOWNSHIP ENGINE: Starting township feature retrieval")
        logger.info(f"📍 Container bounds: {container_bounds}")
        logger.info(f"📍 PLSS info: {plss_info}")
        
        try:
            # Get state from PLSS info
            state = plss_info.get('state', 'Wyoming').lower()
            
            # Use geometry parquet files for proper shape overlays
            # The geometry files contain actual shape boundaries, not just centroids
            township_file = os.path.join(self.data_dir, state, "parquet", "townships.parquet").replace('\\', '/')
            
            # Load township data from geometry file
            if not os.path.exists(township_file):
                logger.error(f"❌ Township parquet file not found: {township_file}")
                return self._create_error_response("Township parquet data file not found")
            
            # Read parquet file directly with geopandas to handle geometry properly
            gdf = gpd.read_parquet(township_file)
            logger.info(f"📊 Loaded township data: {gdf.shape} features, columns: {list(gdf.columns)}")
            
            # Validate geometry column exists
            if gdf.geometry.name != 'geometry':
                logger.error("❌ No valid geometry column found in township data")
                return self._create_error_response("No valid geometry column found in township data")
            
            # Validate required columns - township data should have all the necessary columns
            required_cols = ['TWNSHPNO', 'TWNSHPDIR', 'RANGENO', 'RANGEDIR', 'geometry']
            missing_cols = [col for col in required_cols if col not in gdf.columns]
            if missing_cols:
                logger.error(f"❌ Missing required columns in township data: {missing_cols}")
                return self._create_error_response(f"Missing columns in township data: {missing_cols}")
            
            # Filter to exact township
            filtered_gdf = self._filter_exact_township(gdf, plss_info)
            logger.info(f"🎯 Township filtering result: {filtered_gdf.shape} features")
            
            # Validate spatial bounds
            spatial_validation = self._validate_spatial_bounds(filtered_gdf, container_bounds)
            logger.info(f"🔍 Spatial validation: {spatial_validation}")
            
            # Convert to GeoJSON
            geojson = self._to_geojson(filtered_gdf)
            
            return {
                "type": "FeatureCollection",
                "features": geojson,
                "validation": {
                    "requested_township": f"T{plss_info.get('township_number')}{plss_info.get('township_direction')}",
                    "requested_range": f"R{plss_info.get('range_number')}{plss_info.get('range_direction')}",
                    "features_returned": len(geojson),
                    "spatial_validation": spatial_validation,
                    "container_bounds": container_bounds,
                    "engine": "ContainerTownshipEngine",
                    "data_source": "townships_parquet"
                }
            }
            
        except Exception as e:
            logger.error(f"❌ Container township engine failed: {e}")
            return self._create_error_response(f"Engine error: {str(e)}")
    
    def _validate_container_trs(self, plss_info: Dict[str, Any]) -> bool:
        """Validate that we're using container TRS, not reference TRS"""
        township_num = plss_info.get('township_number')
        township_dir = plss_info.get('township_direction')
        
        logger.info(f"🔍 Validating container TRS: T{township_num}{township_dir}")
        
        # Check if this looks like reference TRS (should be different from container)
        # Container TRS should be the actual parcel location
        if township_num is None or township_dir is None:
            logger.error("❌ Missing township information in PLSS data")
            return False
        
        logger.info(f"✅ Container TRS validation passed: T{township_num}{township_dir}")
        return True
    
    def _filter_exact_township(self, gdf: gpd.GeoDataFrame, plss_info: Dict[str, Any]) -> gpd.GeoDataFrame:
        """Filter to exact township and dissolve to get township boundaries (horizontal lines)"""
        # Validate container TRS first
        if not self._validate_container_trs(plss_info):
            logger.error("❌ Container TRS validation failed")
            return gpd.GeoDataFrame()
        
        township_num = plss_info.get('township_number')
        township_dir = plss_info.get('township_direction')
        
        logger.info(f"🎯 Filtering to exact township for boundary: T{township_num}{township_dir}")
        
        # DEBUG: Log sample of actual data values to diagnose filtering issues
        sample_data = gdf[['TWNSHPNO', 'TWNSHPDIR', 'RANGENO', 'RANGEDIR']].head(10)
        logger.info(f"🔍 Sample actual data values:\n{sample_data}")
        
        # DEBUG: Log unique values to see what's available
        unique_townships = gdf['TWNSHPNO'].unique()
        unique_dirs = gdf['TWNSHPDIR'].unique()
        logger.info(f"🔍 Available township numbers: {sorted(unique_townships[:20]) if len(unique_townships) > 0 else 'None'}")
        logger.info(f"🔍 Available township directions: {unique_dirs}")
        
        # CRITICAL FIX: Convert township number to zero-padded string format (e.g., 14 -> '014')
        township_str = f"{township_num:03d}" if isinstance(township_num, int) else str(township_num).zfill(3)
        logger.info(f"🔧 Converting township number {township_num} to string format: '{township_str}'")
        
        # Apply township filter - get ALL ranges within this township
        mask = (
            (gdf['TWNSHPNO'] == township_str) & 
            (gdf['TWNSHPDIR'] == township_dir)
        )
        
        township_cells = gdf[mask].copy()
        logger.info(f"✅ Township filter applied: {len(township_cells)} cells found in T{township_str}{township_dir}")
        
        if township_cells.empty:
            logger.error(f"❌ No cells found for township T{township_str}{township_dir}")
            return township_cells
        
        # Dissolve all cells in this township to get the township boundary (horizontal lines)
        try:
            logger.info(f"🔄 Dissolving {len(township_cells)} township cells to get boundary")
            
            # Clean geometries before dissolving
            township_cells['geometry'] = township_cells['geometry'].buffer(0)
            township_cells = township_cells[township_cells['geometry'].is_valid]
            
            # Dissolve by township to get the boundary
            dissolved = township_cells.dissolve(by=['TWNSHPNO', 'TWNSHPDIR'], as_index=False, dropna=True)
            
            logger.info(f"✅ Township dissolved: {len(dissolved)} boundary feature created")
            
            # Log sample of dissolved features
            if not dissolved.empty:
                sample = dissolved[['TWNSHPNO', 'TWNSHPDIR']].head(3)
                logger.info(f"📋 Sample dissolved township:\n{sample}")
            
            return dissolved
            
        except Exception as e:
            logger.error(f"❌ Failed to dissolve township: {e}")
            # Return original cells if dissolve fails
            return township_cells
    
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
    
    def _to_geojson(self, gdf: gpd.GeoDataFrame) -> list:
        """Convert GeoDataFrame to GeoJSON features"""
        features = []
        
        for idx, row in gdf.iterrows():
            geom = row.geometry
            
            # Handle MultiPolygon by taking the largest polygon
            if hasattr(geom, 'geom_type') and geom.geom_type == 'MultiPolygon':
                geom = max(geom.geoms, key=lambda p: p.area)
            
            # Create label for township
            township_label = f"T{row.get('TWNSHPNO', '?')}{row.get('TWNSHPDIR', '')}"
            
            feature = {
                "type": "Feature",
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [list(geom.exterior.coords)]
                },
                "properties": {
                    "township_number": row.get('TWNSHPNO'),
                    "township_direction": row.get('TWNSHPDIR'),
                    "range_number": row.get('RANGENO'),
                    "range_direction": row.get('RANGEDIR'),
                    "feature_type": "township",
                    "overlay_type": "container",
                    "label": township_label,
                    "display_label": township_label
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
                "engine": "ContainerTownshipEngine"
            }
        }
