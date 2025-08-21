"""
Container Grid Engine
Dedicated engine for retrieving the specific township-range cell (grid) within container bounds
"""
import logging
import geopandas as gpd
import pandas as pd
from typing import Dict, Any, Optional, Tuple
from shapely.geometry import box
import os

logger = logging.getLogger(__name__)

class ContainerGridEngine:
    """Dedicated engine for container grid overlays (specific township-range cell)"""
    
    def __init__(self, data_dir: str = "../plss"):
        self.data_dir = data_dir
        
    def get_grid_features(self, container_bounds: Dict[str, float], plss_info: Dict[str, Any]) -> Dict[str, Any]:
        """
        Get grid features (specific township-range cell) for container overlay with comprehensive validation
        
        Args:
            container_bounds: Bounding box {west, south, east, north}
            plss_info: PLSS information {township_number, township_direction, range_number, range_direction}
            
        Returns:
            Dict with GeoJSON features and validation info
        """
        logger.info("🌐 CONTAINER GRID ENGINE: Starting grid (specific cell) feature retrieval")
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
            
            # Filter to exact township-range cell
            filtered_gdf = self._filter_exact_cell(gdf, plss_info)
            logger.info(f"🎯 Grid cell filtering result: {filtered_gdf.shape} features")
            
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
                    "cell_identifier": f"T{plss_info.get('township_number')}{plss_info.get('township_direction')} R{plss_info.get('range_number')}{plss_info.get('range_direction')}",
                    "features_returned": len(geojson),
                    "spatial_validation": spatial_validation,
                    "container_bounds": container_bounds,
                    "engine": "ContainerGridEngine",
                    "data_source": "townships_parquet"
                }
            }
            
        except Exception as e:
            logger.error(f"❌ Container grid engine failed: {e}")
            return self._create_error_response(f"Engine error: {str(e)}")
    
    def _filter_exact_cell(self, gdf: gpd.GeoDataFrame, plss_info: Dict[str, Any]) -> gpd.GeoDataFrame:
        """Filter to exact township-range cell with comprehensive logging"""
        township_num = plss_info.get('township_number')
        township_dir = plss_info.get('township_direction')
        range_num = plss_info.get('range_number')
        range_dir = plss_info.get('range_direction')
        
        logger.info(f"🎯 Filtering to exact cell: T{township_num}{township_dir} R{range_num}{range_dir}")
        
        # CRITICAL FIX: Convert numbers to zero-padded string format
        township_str = f"{township_num:03d}" if isinstance(township_num, int) else str(township_num).zfill(3)
        range_str = f"{range_num:03d}" if isinstance(range_num, int) else str(range_num).zfill(3)
        logger.info(f"🔧 Converting to string formats: T{township_str}{township_dir} R{range_str}{range_dir}")
        
        # Apply both township and range filters to get the specific cell
        mask = (
            (gdf['TWNSHPNO'] == township_str) & 
            (gdf['TWNSHPDIR'] == township_dir) &
            (gdf['RANGENO'] == range_str) & 
            (gdf['RANGEDIR'] == range_dir)
        )
        
        filtered = gdf[mask].copy()
        logger.info(f"✅ Grid cell filter applied: {len(filtered)} features match T{township_str}{township_dir} R{range_str}{range_dir}")
        
        if filtered.empty:
            logger.warning(f"⚠️ No features found for cell T{township_str}{township_dir} R{range_str}{range_dir}")
        
        # Log sample of filtered features
        if not filtered.empty:
            sample = filtered[['TWNSHPNO', 'TWNSHPDIR', 'RANGENO', 'RANGEDIR']].head(3)
            logger.info(f"📋 Sample filtered features:\n{sample}")
        
        return filtered
    
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
                    "feature_type": "grid_cell",
                    "overlay_type": "container",
                    "cell_identifier": f"T{row.get('TWNSHPNO')}{row.get('TWNSHPDIR')} R{row.get('RANGENO')}{row.get('RANGEDIR')}"
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
                "engine": "ContainerGridEngine"
            }
        }
