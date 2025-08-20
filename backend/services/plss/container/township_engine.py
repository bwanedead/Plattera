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
    
    def __init__(self, data_dir: str = "plss"):
        self.data_dir = data_dir
        self.township_file = os.path.join(data_dir, "townships.parquet")
        
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
            # Load township data
            if not os.path.exists(self.township_file):
                logger.error(f"❌ Township file not found: {self.township_file}")
                return self._create_error_response("Township data file not found")
            
            gdf = gpd.read_parquet(self.township_file)
            logger.info(f"📊 Loaded township data: {gdf.shape} features, columns: {list(gdf.columns)}")
            
            # Validate required columns
            required_cols = ['TWNSHPNO', 'TWNSHPDIR', 'RANGENO', 'RANGEDIR', 'geometry']
            missing_cols = [col for col in required_cols if col not in gdf.columns]
            if missing_cols:
                logger.error(f"❌ Missing required columns: {missing_cols}")
                return self._create_error_response(f"Missing columns: {missing_cols}")
            
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
                    "engine": "ContainerTownshipEngine"
                }
            }
            
        except Exception as e:
            logger.error(f"❌ Container township engine failed: {e}")
            return self._create_error_response(f"Engine error: {str(e)}")
    
    def _filter_exact_township(self, gdf: gpd.GeoDataFrame, plss_info: Dict[str, Any]) -> gpd.GeoDataFrame:
        """Filter to exact township with comprehensive logging"""
        township_num = plss_info.get('township_number')
        township_dir = plss_info.get('township_direction')
        
        logger.info(f"🎯 Filtering to exact township: T{township_num}{township_dir}")
        
        # Apply township filter
        mask = (
            (gdf['TWNSHPNO'] == township_num) & 
            (gdf['TWNSHPDIR'] == township_dir)
        )
        
        filtered = gdf[mask].copy()
        logger.info(f"✅ Township filter applied: {len(filtered)} features match T{township_num}{township_dir}")
        
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
                    "feature_type": "township",
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
                "engine": "ContainerTownshipEngine"
            }
        }
