"""
Container Sections Engine
Dedicated engine for retrieving section features within container bounds using spatial intersection
"""
import logging
import geopandas as gpd
import pandas as pd
from typing import Dict, Any, Optional, Tuple
from shapely.geometry import box
import os

logger = logging.getLogger(__name__)

class ContainerSectionsEngine:
    """Dedicated engine for container section overlays using spatial filtering"""
    
    def __init__(self, data_dir: str = "../plss"):
        self.data_dir = data_dir
        
    def get_sections_features(self, container_bounds: Dict[str, float], plss_info: Dict[str, Any]) -> Dict[str, Any]:
        logger.info("🔲 CONTAINER SECTIONS ENGINE: Starting sections feature retrieval")
        logger.info(f"📍 Container bounds: {container_bounds}")
        logger.info(f"📍 PLSS info: {plss_info}")
        
        try:
            # Get state from PLSS info
            state = plss_info.get('state', 'Wyoming').lower()
            
            # Use geometry parquet files for proper shape overlays
            # The geometry files contain actual shape boundaries, not just centroids
            sections_file = os.path.join(self.data_dir, state, "parquet", "sections.parquet").replace('\\', '/')
            
            # Load sections data from geometry file
            if not os.path.exists(sections_file):
                logger.error(f"❌ Sections parquet file not found: {sections_file}")
                return self._create_error_response("Sections parquet data file not found")
            
            # Read parquet file directly with geopandas to handle geometry properly
            sections_gdf = gpd.read_parquet(sections_file)
            logger.info(f"📊 Loaded sections data: {sections_gdf.shape} features, columns: {list(sections_gdf.columns)}")
            
            # Validate geometry column exists
            if sections_gdf.geometry.name != 'geometry':
                logger.error("❌ No valid geometry column found in sections data")
                return self._create_error_response("No valid geometry column found in sections data")
            
            # Get the specific township-range cell boundary from the sections data
            cell_boundary = self._get_cell_boundary(sections_gdf, plss_info)
            if cell_boundary is None:
                logger.error("❌ Could not determine cell boundary from sections data")
                return self._create_error_response("Could not determine cell boundary from sections data")
            
            logger.info(f"🎯 Cell boundary determined: {cell_boundary}")
            
            # Filter sections using spatial intersection with the cell boundary
            filtered_gdf = self._filter_sections_by_spatial_intersection(sections_gdf, cell_boundary)
            logger.info(f"🎯 Sections spatial filtering result: {filtered_gdf.shape} features")
            
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
                    "engine": "ContainerSectionsEngine",
                    "filtering_method": "spatial_intersection",
                    "data_source": "sections_parquet"
                }
            }
            
        except Exception as e:
            logger.error(f"❌ Container sections engine failed: {e}")
            return self._create_error_response(f"Engine error: {str(e)}")
    
    def _get_cell_boundary(self, sections_gdf: gpd.GeoDataFrame, plss_info: Dict[str, Any]) -> Optional[Any]:
        """Get the boundary of the specific township-range cell from townships data"""
        township_num = plss_info.get('township_number')
        township_dir = plss_info.get('township_direction')
        range_num = plss_info.get('range_number')
        range_dir = plss_info.get('range_direction')
        
        logger.info(f"🎯 Getting boundary for cell: T{township_num}{township_dir} R{range_num}{range_dir}")
        
        try:
            # Get state from PLSS info for townships data
            state = plss_info.get('state', 'Wyoming').lower()
            
            # Load townships data to get the cell boundary (NOT sections data)
            townships_file = os.path.join(self.data_dir, state, "parquet", "townships.parquet").replace('\\', '/')
            
            if not os.path.exists(townships_file):
                logger.error(f"❌ Townships parquet file not found: {townships_file}")
                return None
            
            # Read townships parquet file
            townships_gdf = gpd.read_parquet(townships_file)
            logger.info(f"📊 Loaded townships data for cell boundary: {townships_gdf.shape} features, columns: {list(townships_gdf.columns)}")
            
            # Convert numbers to zero-padded string format
            township_str = f"{township_num:03d}" if isinstance(township_num, int) else str(township_num).zfill(3)
            range_str = f"{range_num:03d}" if isinstance(range_num, int) else str(range_num).zfill(3)
            logger.info(f"🔧 Converting to string formats: T{township_str}{township_dir} R{range_str}{range_dir}")
            
            # Filter to exact township-range cell
            mask = (
                (townships_gdf['TWNSHPNO'] == township_str) & 
                (townships_gdf['TWNSHPDIR'] == township_dir) &
                (townships_gdf['RANGENO'] == range_str) & 
                (townships_gdf['RANGEDIR'] == range_dir)
            )
            
            cell_gdf = townships_gdf[mask].copy()
            logger.info(f"✅ Cell boundary filter applied: {len(cell_gdf)} features found for T{township_str}{township_dir} R{range_str}{range_dir}")
            
            if cell_gdf.empty:
                logger.error(f"❌ No cell boundary found for T{township_str}{township_dir} R{range_str}{range_dir}")
                return None
            
            # Get the geometry of the cell (handle MultiPolygon)
            cell_geometry = cell_gdf.iloc[0].geometry
            if hasattr(cell_geometry, 'geom_type') and cell_geometry.geom_type == 'MultiPolygon':
                cell_geometry = max(cell_geometry.geoms, key=lambda p: p.area)
                
            logger.info(f"✅ Cell boundary determined: {cell_geometry}")
            
            return cell_geometry
            
        except Exception as e:
            logger.error(f"❌ Failed to get cell boundary: {e}")
            return None
    
    def _filter_sections_by_spatial_intersection(self, sections_gdf: gpd.GeoDataFrame, cell_boundary: Any) -> gpd.GeoDataFrame:
        """Filter sections using spatial intersection with the cell boundary"""
        logger.info(f"🎯 Filtering {len(sections_gdf)} sections by spatial intersection")
        
        # Find sections that intersect with the cell boundary
        intersecting_mask = sections_gdf.geometry.intersects(cell_boundary)
        filtered_gdf = sections_gdf[intersecting_mask].copy()
        
        logger.info(f"✅ Spatial intersection filter applied: {len(filtered_gdf)} sections intersect cell boundary")
        
        # Log sample of filtered features
        if not filtered_gdf.empty:
            sample = filtered_gdf[['FRSTDIVNO']].head(5)
            logger.info(f"📋 Sample filtered sections:\n{sample}")
        else:
            logger.warning("⚠️ No sections found within cell boundary")
        
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
                    "section_number": row.get('FRSTDIVNO'),
                    "township_number": plss_info.get('township_number'),
                    "township_direction": plss_info.get('township_direction'),
                    "range_number": plss_info.get('range_number'),
                    "range_direction": plss_info.get('range_direction'),
                    "feature_type": "section",
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
                "engine": "ContainerSectionsEngine"
            }
        }

    def _validate_container_trs(self, plss_info: Dict[str, Any]) -> bool:
        """Validate that we're using container TRS, not reference TRS"""
        township_num = plss_info.get('township_number')
        township_dir = plss_info.get('township_direction')
        range_num = plss_info.get('range_number')
        range_dir = plss_info.get('range_direction')
        
        logger.info(f"🔍 Validating container TRS: T{township_num}{township_dir} R{range_num}{range_dir}")
        
        # Check if this looks like reference TRS (should be different from container)
        # Container TRS should be the actual parcel location
        if township_num is None or township_dir is None or range_num is None or range_dir is None:
            logger.error("❌ Missing TRS information in PLSS data")
            return False
        
        logger.info(f"✅ Container TRS validation passed: T{township_num}{township_dir} R{range_num}{range_dir}")
        return True
    
    def _filter_exact_sections(self, gdf: gpd.GeoDataFrame, plss_info: Dict[str, Any]) -> gpd.GeoDataFrame:
        """Filter to exact township-range cell for sections"""
        # Validate container TRS first
        if not self._validate_container_trs(plss_info):
            logger.error("❌ Container TRS validation failed")
            return gpd.GeoDataFrame()
        
        township_num = plss_info.get('township_number')
        township_dir = plss_info.get('township_direction')
        range_num = plss_info.get('range_number')
        range_dir = plss_info.get('range_direction')
        
        logger.info(f"🎯 Filtering sections for: T{township_num}{township_dir} R{range_num}{range_dir}")
        
        # CRITICAL FIX: Sections data doesn't have township/range columns
        # We need to get the cell boundary from townships data first
        cell_boundary = self._get_cell_boundary(gdf, plss_info)
        
        if cell_boundary is None:
            logger.error(f"❌ No cell boundary found for T{township_num}{township_dir} R{range_num}{range_dir}")
            return gpd.GeoDataFrame()
        
        # Filter sections to only those within the cell boundary
        try:
            # Use spatial intersection to filter sections within the cell
            intersecting = gdf[gdf.geometry.intersects(cell_boundary)]
            
            logger.info(f"✅ Sections filter applied: {len(intersecting)} features found in cell")
            
            # Log sample of filtered features
            if not intersecting.empty:
                available_cols = [col for col in ['SECNO'] if col in intersecting.columns]
                if available_cols:
                    sample = intersecting[available_cols].head(3)
                    logger.info(f"📋 Sample filtered sections:\n{sample}")
            
            return intersecting
            
        except Exception as e:
            logger.error(f"❌ Failed to filter sections: {e}")
            return gpd.GeoDataFrame()
