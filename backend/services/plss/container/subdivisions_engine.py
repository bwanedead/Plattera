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
from config.paths import plss_root

logger = logging.getLogger(__name__)

class ContainerSubdivisionsEngine:
    """Dedicated engine for container subdivision overlays using spatial filtering"""
    
    def __init__(self, data_dir: str = "../plss"):
        # Use caller-provided dir if overridden, otherwise centralized PLSS root
        self.data_dir = data_dir if data_dir != "../plss" else str(plss_root())
        
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
            
            # Get the specific township-range cell boundary from the subdivisions data
            cell_boundary = self._get_cell_boundary(subdivisions_gdf, plss_info)
            if cell_boundary is None:
                logger.error("❌ Could not determine cell boundary from subdivisions data")
                return self._create_error_response("Could not determine cell boundary from subdivisions data")
            
            logger.info(f"🎯 Cell boundary determined: {cell_boundary}")
            
            # Filter subdivisions using spatial intersection with the cell boundary
            filtered_gdf = self._filter_subdivisions_by_spatial_intersection(subdivisions_gdf, cell_boundary)
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
    
    def _filter_subdivisions_by_spatial_intersection(self, subdivisions_gdf: gpd.GeoDataFrame, cell_boundary: Any) -> gpd.GeoDataFrame:
        """Filter subdivisions using spatial intersection with the cell boundary"""
        logger.info(f"🎯 Filtering {len(subdivisions_gdf)} subdivisions by spatial intersection")
        
        # Find subdivisions that intersect with the cell boundary
        intersecting_mask = subdivisions_gdf.geometry.intersects(cell_boundary)
        filtered_gdf = subdivisions_gdf[intersecting_mask].copy()
        
        logger.info(f"✅ Spatial intersection filter applied: {len(filtered_gdf)} subdivisions intersect cell boundary")
        
        # Additional filtering: ensure subdivisions are actually within the cell boundary
        # Some subdivisions might just touch the boundary, we want subdivisions that are mostly inside
        if not filtered_gdf.empty:
            # Calculate intersection area ratio for each subdivision
            def calculate_intersection_ratio(row):
                try:
                    intersection = row.geometry.intersection(cell_boundary)
                    if intersection.is_empty:
                        return 0.0
                    intersection_area = intersection.area
                    subdivision_area = row.geometry.area
                    if subdivision_area == 0:
                        return 0.0
                    return intersection_area / subdivision_area
                except Exception:
                    return 0.0
            
            filtered_gdf['intersection_ratio'] = filtered_gdf.apply(calculate_intersection_ratio, axis=1)
            
            # Only keep subdivisions where at least 50% of the subdivision is within the cell
            significant_subdivisions = filtered_gdf[filtered_gdf['intersection_ratio'] >= 0.5].copy()
            
            logger.info(f"🔍 Significant subdivisions filter: {len(filtered_gdf)} → {len(significant_subdivisions)} (50%+ within cell)")
            
            # Remove the intersection_ratio column before returning
            if not significant_subdivisions.empty and 'intersection_ratio' in significant_subdivisions.columns:
                significant_subdivisions = significant_subdivisions.drop(columns=['intersection_ratio'])
            
            # Log sample of filtered features
            if not significant_subdivisions.empty:
                available_cols = [col for col in ['SECDIVTXT', 'SECDIVNO', 'GISACRE'] if col in significant_subdivisions.columns]
                if available_cols:
                    sample = significant_subdivisions[available_cols].head(5)
                    logger.info(f"📋 Sample filtered subdivisions:\n{sample}")
            else:
                logger.warning("⚠️ No subdivisions found within cell boundary")
            
            return significant_subdivisions
        
        return filtered_gdf
    
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
            
            # Create label for subdivision
            subdivision_label = f"Sub{row.get('FRSTDIVNO', '?')}" if row.get('FRSTDIVNO') else "Subdivision"
            
            feature = {
                "type": "Feature",
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [list(geom.exterior.coords)]
                },
                "properties": {
                    "subdivision_number": row.get('FRSTDIVNO'),
                    "subdivision_type": row.get('SECDIVTXT'),
                    "township_number": plss_info.get('township_number'),
                    "township_direction": plss_info.get('township_direction'),
                    "range_number": plss_info.get('range_number'),
                    "range_direction": plss_info.get('range_direction'),
                    "feature_type": "subdivision",
                    "overlay_type": "container",
                    "cell_identifier": f"T{plss_info.get('township_number')}{plss_info.get('township_direction')} R{plss_info.get('range_number')}{plss_info.get('range_direction')}",
                    "label": subdivision_label,
                    "display_label": subdivision_label
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
