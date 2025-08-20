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
    
    def __init__(self, data_dir: str = "plss"):
        self.data_dir = data_dir
        self.quarter_sections_file = os.path.join(data_dir, "quarter_sections.parquet")
        self.township_file = os.path.join(data_dir, "townships.parquet")
        
    def get_quarter_sections_features(self, container_bounds: Dict[str, float], plss_info: Dict[str, Any]) -> Dict[str, Any]:
        """
        Get quarter section features for container overlay using spatial intersection
        
        Args:
            container_bounds: Bounding box {west, south, east, north}
            plss_info: PLSS information {township_number, township_direction, range_number, range_direction}
            
        Returns:
            Dict with GeoJSON features and validation info
        """
        logger.info("🏘️ CONTAINER QUARTER SECTIONS ENGINE: Starting quarter section feature retrieval")
        logger.info(f"📍 Container bounds: {container_bounds}")
        logger.info(f"📍 PLSS info: {plss_info}")
        
        try:
            # Load quarter sections data
            if not os.path.exists(self.quarter_sections_file):
                logger.error(f"❌ Quarter sections file not found: {self.quarter_sections_file}")
                return self._create_error_response("Quarter sections data file not found")
            
            quarter_sections_gdf = gpd.read_parquet(self.quarter_sections_file)
            logger.info(f"📊 Loaded quarter sections data: {quarter_sections_gdf.shape} features, columns: {list(quarter_sections_gdf.columns)}")
            
            # Load township data to get the specific cell boundary
            if not os.path.exists(self.township_file):
                logger.error(f"❌ Township file not found: {self.township_file}")
                return self._create_error_response("Township data file not found")
            
            township_gdf = gpd.read_parquet(self.township_file)
            logger.info(f"📊 Loaded township data: {township_gdf.shape} features, columns: {list(township_gdf.columns)}")
            
            # Get the specific township-range cell boundary
            cell_boundary = self._get_cell_boundary(township_gdf, plss_info)
            if cell_boundary is None:
                logger.error("❌ Could not determine cell boundary")
                return self._create_error_response("Could not determine cell boundary")
            
            logger.info(f"🎯 Cell boundary determined: {cell_boundary}")
            
            # Filter quarter sections using spatial intersection with the cell boundary
            filtered_gdf = self._filter_quarter_sections_by_spatial_intersection(quarter_sections_gdf, cell_boundary)
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
                    "filtering_method": "spatial_intersection"
                }
            }
            
        except Exception as e:
            logger.error(f"❌ Container quarter sections engine failed: {e}")
            return self._create_error_response(f"Engine error: {str(e)}")
    
    def _get_cell_boundary(self, township_gdf: gpd.GeoDataFrame, plss_info: Dict[str, Any]) -> Optional[Any]:
        """Get the boundary of the specific township-range cell"""
        township_num = plss_info.get('township_number')
        township_dir = plss_info.get('township_direction')
        range_num = plss_info.get('range_number')
        range_dir = plss_info.get('range_direction')
        
        logger.info(f"🎯 Getting boundary for cell: T{township_num}{township_dir} R{range_num}{range_dir}")
        
        # Filter to exact township-range cell
        mask = (
            (township_gdf['TWNSHPNO'] == township_num) & 
            (township_gdf['TWNSHPDIR'] == township_dir) &
            (township_gdf['RANGENO'] == range_num) & 
            (township_gdf['RANGEDIR'] == range_dir)
        )
        
        cell_gdf = township_gdf[mask].copy()
        
        if cell_gdf.empty:
            logger.error(f"❌ No cell found for T{township_num}{township_dir} R{range_num}{range_dir}")
            return None
        
        # Get the geometry of the cell
        cell_geometry = cell_gdf.iloc[0].geometry
        logger.info(f"✅ Cell boundary determined: {cell_geometry}")
        
        return cell_geometry
    
    def _filter_quarter_sections_by_spatial_intersection(self, quarter_sections_gdf: gpd.GeoDataFrame, cell_boundary: Any) -> gpd.GeoDataFrame:
        """Filter quarter sections using spatial intersection with the cell boundary"""
        logger.info(f"🎯 Filtering {len(quarter_sections_gdf)} quarter sections by spatial intersection")
        
        # Find quarter sections that intersect with the cell boundary
        intersecting_mask = quarter_sections_gdf.geometry.intersects(cell_boundary)
        filtered_gdf = quarter_sections_gdf[intersecting_mask].copy()
        
        logger.info(f"✅ Spatial intersection filter applied: {len(filtered_gdf)} quarter sections intersect cell boundary")
        
        # Log sample of filtered features
        if not filtered_gdf.empty:
            sample = filtered_gdf[['FRSTDIVNO']].head(5)
            logger.info(f"📋 Sample filtered quarter sections:\n{sample}")
        else:
            logger.warning("⚠️ No quarter sections found within cell boundary")
        
        return filtered_gdf
    
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
            feature = {
                "type": "Feature",
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [list(row.geometry.exterior.coords)]
                },
                "properties": {
                    "quarter_section_number": row.get('FRSTDIVNO'),
                    "township_number": plss_info.get('township_number'),
                    "township_direction": plss_info.get('township_direction'),
                    "range_number": plss_info.get('range_number'),
                    "range_direction": plss_info.get('range_direction'),
                    "feature_type": "quarter_section",
                    "overlay_type": "container",
                    "cell_identifier": f"T{plss_info.get('township_number')}{plss_info.get('township_direction')} R{plss_info.get('range_number')}{plss_info.get('range_direction')}"
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
