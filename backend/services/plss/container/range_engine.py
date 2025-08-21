"""
Container Range Engine
Dedicated engine for retrieving range features within container bounds
"""
import logging
import geopandas as gpd
import pandas as pd
from typing import Dict, Any, Optional, Tuple
from shapely.geometry import box
import os

logger = logging.getLogger(__name__)

class ContainerRangeEngine:
    """Dedicated engine for container range overlays"""
    
    def __init__(self, data_dir: str = "../plss"):
        self.data_dir = data_dir
        
    def get_range_features(self, container_bounds: Dict[str, float], plss_info: Dict[str, Any]) -> Dict[str, Any]:
        """
        Get range features for container overlay with comprehensive validation
        
        Args:
            container_bounds: Bounding box {west, south, east, north}
            plss_info: PLSS information {township_number, township_direction, range_number, range_direction}
            
        Returns:
            Dict with GeoJSON features and validation info
        """
        logger.info("📐 CONTAINER RANGE ENGINE: Starting range feature retrieval")
        logger.info(f"📍 Container bounds: {container_bounds}")
        logger.info(f"📍 PLSS info: {plss_info}")
        
        try:
            # Get state from PLSS info
            state = plss_info.get('state', 'Wyoming').lower()
            
            # Use geometry parquet files for proper shape overlays
            # The geometry files contain actual shape boundaries, not just centroids
            range_file = os.path.join(self.data_dir, state, "parquet", "ranges.parquet").replace('\\', '/')
            
            # Load range data from geometry file
            if not os.path.exists(range_file):
                logger.error(f"❌ Range parquet file not found: {range_file}")
                return self._create_error_response("Range parquet data file not found")
            
            # Read parquet file directly with geopandas to handle geometry properly
            gdf = gpd.read_parquet(range_file)
            logger.info(f"📊 Loaded range data: {gdf.shape} features, columns: {list(gdf.columns)}")
            
            # Validate geometry column exists
            if gdf.geometry.name != 'geometry':
                logger.error("❌ No valid geometry column found in range data")
                return self._create_error_response("No valid geometry column found in range data")
            
            # Validate required columns - range data should only need range columns for dissolved data
            required_cols = ['RANGENO', 'RANGEDIR', 'geometry'] 
            missing_cols = [col for col in required_cols if col not in gdf.columns]
            if missing_cols:
                logger.error(f"❌ Missing required columns in range data: {missing_cols}")
                return self._create_error_response(f"Missing columns in range data: {missing_cols}")

            # Filter to exact range
            filtered_gdf = self._filter_exact_range(gdf, plss_info)
            logger.info(f"🎯 Range filtering result: {filtered_gdf.shape} features")
            
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
                    "engine": "ContainerRangeEngine",
                    "data_source": "ranges_parquet"
                }
            }
            
        except Exception as e:
            logger.error(f"❌ Container range engine failed: {e}")
            return self._create_error_response(f"Engine error: {str(e)}")
    
    def _filter_exact_range(self, gdf: gpd.GeoDataFrame, plss_info: Dict[str, Any]) -> gpd.GeoDataFrame:
        """Filter to exact range boundary (vertical lines)"""
        range_num = plss_info.get('range_number')
        range_dir = plss_info.get('range_direction')
        
        logger.info(f"🎯 Filtering to exact range boundary: R{range_num}{range_dir}")
        
        # CRITICAL FIX: Convert range number to zero-padded string format (e.g., 75 -> '075')
        range_str = f"{range_num:03d}" if isinstance(range_num, int) else str(range_num).zfill(3)
        logger.info(f"🔧 Converting range number {range_num} to string format: '{range_str}'")
        
        # Apply range filter with corrected format
        mask = (
            (gdf['RANGENO'] == range_str) & 
            (gdf['RANGEDIR'] == range_dir)
        )
        
        filtered = gdf[mask].copy()
        logger.info(f"✅ Range boundary filter applied: {len(filtered)} features match R{range_str}{range_dir}")
        
        # Log sample of filtered features (only range columns since this is dissolved range data)
        if not filtered.empty:
            available_cols = [col for col in ['RANGENO', 'RANGEDIR'] if col in filtered.columns]
            if available_cols:
                sample = filtered[available_cols].head(3)
                logger.info(f"📋 Sample filtered range features:\n{sample}")
        
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
            feature = {
                "type": "Feature",
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [list(row.geometry.exterior.coords)]
                },
                "properties": {
                    "township_number": row.get('TWNSHPNO'),
                    "township_direction": row.get('TWNSHPDIR'),
                    "range_number": row.get('RANGENO'),
                    "range_direction": row.get('RANGEDIR'),
                    "feature_type": "range",
                    "overlay_type": "container"
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
                "engine": "ContainerRangeEngine"
            }
        }
