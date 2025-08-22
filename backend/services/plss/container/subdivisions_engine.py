"""
Container Subdivisions Engine
Dedicated engine for retrieving subdivision features within container bounds using spatial intersection
"""
import logging
import geopandas as gpd
import pandas as pd
from typing import Dict, Any, Optional, Tuple
from shapely.geometry import box
import os

logger = logging.getLogger(__name__)

class ContainerSubdivisionsEngine:
    """Dedicated engine for container subdivision overlays using spatial filtering"""
    
    def __init__(self, data_dir: str = "../plss"):
        self.data_dir = data_dir
        
    def get_subdivisions_features(self, container_bounds: Dict[str, float], plss_info: Dict[str, Any]) -> Dict[str, Any]:
        logger.info("🔲 CONTAINER SUBDIVISIONS ENGINE: Starting subdivisions feature retrieval")
        logger.info(f"📍 Container bounds: {container_bounds}")
        logger.info(f"📍 PLSS info: {plss_info}")
        
        try:
            # Get state from PLSS info
            state = plss_info.get('state', 'Wyoming').lower()
            
            # Use the same data source as current quarter sections (which actually contains subdivisions)
            subdivisions_file = os.path.join(self.data_dir, state, "parquet", "quarter_sections_parts").replace('\\', '/')
            
            # Load subdivisions data from geometry directory
            if not os.path.exists(subdivisions_file):
                logger.error(f"❌ Subdivisions parquet directory not found: {subdivisions_file}")
                return self._create_error_response("Subdivisions parquet directory not found")
            
            # Read parquet file directly with geopandas to handle geometry properly
            subdivisions_gdf = gpd.read_parquet(subdivisions_file)
            logger.info(f"📊 Loaded subdivisions data: {subdivisions_gdf.shape} features, columns: {list(subdivisions_gdf.columns)}")
            
            # Validate geometry column exists
            if subdivisions_gdf.geometry.name != 'geometry':
                logger.error("❌ No valid geometry column found in subdivisions data")
                return self._create_error_response("No valid geometry column found in subdivisions data")
            
            # Filter subdivisions using spatial intersection with the cell boundary
            filtered_gdf = self._filter_exact_subdivisions(subdivisions_gdf, plss_info)
            logger.info(f"🎯 Subdivisions spatial filtering result: {filtered_gdf.shape} features")
            
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
                    "engine": "ContainerSubdivisionsEngine",
                    "filtering_method": "spatial_intersection",
                    "data_source": "subdivisions_parquet"
                }
            }
            
        except Exception as e:
            logger.error(f"❌ Container subdivisions engine failed: {e}")
            return self._create_error_response(f"Engine error: {str(e)}")
    
    def _filter_exact_subdivisions(self, gdf: gpd.GeoDataFrame, plss_info: Dict[str, Any]) -> gpd.GeoDataFrame:
        """Filter to exact township-range cell for subdivisions"""
        township_num = plss_info.get('township_number')
        township_dir = plss_info.get('township_direction')
        range_num = plss_info.get('range_number')
        range_dir = plss_info.get('range_direction')
        
        logger.info(f"🎯 Filtering subdivisions for: T{township_num}{township_dir} R{range_num}{range_dir}")
        
        # Get the cell boundary from townships data first
        cell_boundary = self._get_cell_boundary(gdf, plss_info)
        
        if cell_boundary is None:
            logger.error(f"❌ No cell boundary found for T{township_num}{township_dir} R{range_num}{range_dir}")
            return gpd.GeoDataFrame()
        
        # Filter subdivisions to only those within the cell boundary
        try:
            # Use spatial intersection to filter subdivisions within the cell
            intersecting = gdf[gdf.geometry.intersects(cell_boundary)]
            
            logger.info(f"✅ Subdivisions filter applied: {len(intersecting)} features found in cell")
            
            # Log sample of filtered features
            if not intersecting.empty:
                available_cols = [col for col in ['SECDIVTXT', 'SECDIVNO', 'GISACRE'] if col in intersecting.columns]
                if available_cols:
                    sample = intersecting[available_cols].head(3)
                    logger.info(f"📋 Sample filtered subdivisions:\n{sample}")
            
            return intersecting
            
        except Exception as e:
            logger.error(f"❌ Failed to filter subdivisions: {e}")
            return gpd.GeoDataFrame()
    
    def _get_cell_boundary(self, subdivisions_gdf: gpd.GeoDataFrame, plss_info: Dict[str, Any]) -> Optional[Any]:
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
            
            feature = {
                "type": "Feature",
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [list(geom.exterior.coords)]
                },
                "properties": {
                    "subdivision_type": row.get('SECDIVTXT'),
                    "subdivision_number": row.get('SECDIVNO'),
                    "acres": row.get('GISACRE'),
                    "feature_type": "subdivision",
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
                "engine": "ContainerSubdivisionsEngine"
            }
        }
