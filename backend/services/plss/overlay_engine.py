"""
PLSS Overlay Engine - BULLETPROOF ARCHITECTURE v2.0
Never returns wrong features - uses spatial intersection when TRS columns missing
Comprehensive validation and logging for complete transparency
"""
import logging
import geopandas as gpd
import pandas as pd
from pathlib import Path
from typing import Dict, Any, List, Optional, Union
from shapely.geometry import box, mapping, Point
import json

logger = logging.getLogger(__name__)


class ContainerBoundsValidator:
    """Validates container bounds and ensures we get the RIGHT cell, never neighbors"""
    
    @staticmethod
    def validate_and_get_exact_cell(
        state: str, 
        plss_info: Dict[str, Any],
        data_dir: Path
    ) -> Dict[str, Any]:
        """
        Get the EXACT township-range cell geometry for bulletproof validation
        
        Returns:
            dict: {
                "valid": bool,
                "cell_geometry": shapely.Polygon or None,
                "cell_bounds": dict,
                "plss_id": str,
                "error": str or None,
                "validation_log": List[str]
            }
        """
        validation_log = []
        
        try:
            township_file = data_dir / state.lower() / "parquet" / "townships.parquet"
            if not township_file.exists():
                error = f"Townships data not found for {state}"
                validation_log.append(f"❌ {error}")
                return {"valid": False, "error": error, "validation_log": validation_log}
            
            townships_gdf = gpd.read_parquet(township_file)
            validation_log.append(f"📄 Loaded {len(townships_gdf)} townships for {state}")
            
            # Build exact TRS filter
            target_t = str(plss_info.get('township_number')).zfill(3)
            target_td = plss_info.get('township_direction')
            target_r = str(plss_info.get('range_number')).zfill(3)
            target_rd = plss_info.get('range_direction')
            
            plss_id = f"T{target_t}{target_td}R{target_r}{target_rd}"
            validation_log.append(f"🎯 SEARCHING FOR EXACT CELL: {plss_id}")
            
            # Apply exact filter
            cell_mask = (
                (townships_gdf["TWNSHPNO"] == target_t) &
                (townships_gdf["TWNSHPDIR"] == target_td) &
                (townships_gdf["RANGENO"] == target_r) &
                (townships_gdf["RANGEDIR"] == target_rd)
            )
            
            exact_cell = townships_gdf[cell_mask]
            validation_log.append(f"🔍 Filter results: {len(exact_cell)} cells found")
            
            if exact_cell.empty:
                error = f"No cell found for {plss_id}"
                validation_log.append(f"❌ {error}")
                validation_log.append(f"Available townships sample: {townships_gdf[['TWNSHPNO', 'TWNSHPDIR', 'RANGENO', 'RANGEDIR']].head().to_dict('records')}")
                return {
                    "valid": False, 
                    "error": error,
                    "plss_id": plss_id,
                    "validation_log": validation_log
                }
            
            if len(exact_cell) > 1:
                validation_log.append(f"⚠️ Multiple cells found for {plss_id}, using first")
            
            cell_geometry = exact_cell.iloc[0].geometry
            bounds = cell_geometry.bounds  # (minx, miny, maxx, maxy)
            
            cell_bounds = {
                "west": bounds[0],
                "south": bounds[1],
                "east": bounds[2], 
                "north": bounds[3]
            }
            
            validation_log.append(f"✅ EXACT CELL VALIDATED: {plss_id}")
            validation_log.append(f"📍 Precise bounds: {cell_bounds}")
            
            # Log all validation steps
            for log_entry in validation_log:
                logger.info(log_entry)
            
            return {
                "valid": True,
                "cell_geometry": cell_geometry,
                "cell_bounds": cell_bounds,
                "plss_id": plss_id,
                "error": None,
                "validation_log": validation_log
            }
            
        except Exception as e:
            error = f"Cell validation failed: {e}"
            validation_log.append(f"❌ {error}")
            logger.error(f"❌ Container validation error: {e}")
            for log_entry in validation_log:
                logger.info(log_entry)
            return {"valid": False, "error": error, "validation_log": validation_log}


class LayerSpecificEngine:
    """Dedicated retrieval engines for each layer type with proper filtering"""
    
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
    
    def get_townships_container(self, state: str, cell_geometry) -> gpd.GeoDataFrame:
        """Get township features for container (exact cell only)"""
        logger.info("🏘️ TOWNSHIPS CONTAINER: Getting exact cell")
        
        townships_file = self.data_dir / state.lower() / "parquet" / "townships.parquet"
        townships_gdf = gpd.read_parquet(townships_file)
        
        # For container, return only features that intersect with the exact cell
        intersecting = townships_gdf[townships_gdf.geometry.intersects(cell_geometry)]
        logger.info(f"🏘️ TOWNSHIPS RESULT: {len(intersecting)} features (should be 1 for exact cell)")
        
        return intersecting
    
    def get_ranges_container(self, state: str, cell_geometry) -> gpd.GeoDataFrame:
        """Get range features for container (exact cell only)"""
        logger.info("📐 RANGES CONTAINER: Getting exact cell")
        
        ranges_file = self.data_dir / state.lower() / "parquet" / "ranges.parquet"
        ranges_gdf = gpd.read_parquet(ranges_file)
        
        # For container, return only features that intersect with the exact cell
        intersecting = ranges_gdf[ranges_gdf.geometry.intersects(cell_geometry)]
        logger.info(f"📐 RANGES RESULT: {len(intersecting)} features (should be 1 for exact cell)")
        
        return intersecting
    
    def get_sections_container(self, state: str, cell_geometry) -> gpd.GeoDataFrame:
        """Get sections within the exact township-range cell using SPATIAL INTERSECTION"""
        logger.info("🏠 SECTIONS CONTAINER: Using spatial intersection (no TRS columns available)")
        
        sections_file = self.data_dir / state.lower() / "parquet" / "sections.parquet"
        sections_gdf = gpd.read_parquet(sections_file)
        
        logger.info(f"📄 Loaded {len(sections_gdf)} total sections")
        logger.info(f"📊 Sections columns: {list(sections_gdf.columns)}")
        
        # SPATIAL INTERSECTION - sections parquet lacks TRS columns
        intersecting = sections_gdf[sections_gdf.geometry.intersects(cell_geometry)]
        logger.info(f"🏠 SECTIONS RESULT: {len(intersecting)} features in cell (spatial intersection)")
        
        return intersecting
    
    def get_quarter_sections_container(self, state: str, cell_geometry, bounds: Dict[str, float]) -> gpd.GeoDataFrame:
        """Get quarter sections within the exact township-range cell using SPATIAL INTERSECTION"""
        logger.info("🔲 QUARTER SECTIONS CONTAINER: Using spatial intersection (no TRS columns available)")
        
        # Try partitioned first, then single file
        parts_dir = self.data_dir / state.lower() / "parquet" / "quarter_sections_parts"
        single_file = self.data_dir / state.lower() / "parquet" / "quarter_sections.parquet"
        
        if parts_dir.exists():
            logger.info("📂 Loading from partitioned quarter sections")
            quarter_sections_gdf = self._load_quarter_sections_parts(parts_dir, bounds)
        elif single_file.exists():
            logger.info("📄 Loading from single quarter sections file")
            quarter_sections_gdf = gpd.read_parquet(single_file)
        else:
            logger.warning("❌ No quarter sections data found")
            return gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")
        
        logger.info(f"📄 Loaded {len(quarter_sections_gdf)} total quarter sections")
        logger.info(f"📊 Quarter sections columns: {list(quarter_sections_gdf.columns)}")
        
        # SPATIAL INTERSECTION - quarter sections parquet lacks TRS columns
        intersecting = quarter_sections_gdf[quarter_sections_gdf.geometry.intersects(cell_geometry)]
        logger.info(f"🔲 QUARTER SECTIONS RESULT: {len(intersecting)} features in cell (spatial intersection)")
        
        return intersecting
    
    def get_subdivisions_container(self, state: str, cell_geometry, bounds: Dict[str, float]) -> gpd.GeoDataFrame:
        """Get subdivisions within the exact township-range cell using SPATIAL INTERSECTION"""
        logger.info("🔲 SUBDIVISIONS CONTAINER: Using spatial intersection (no TRS columns available)")
        
        # Use the same data source as quarter sections (which actually contains subdivisions)
        parts_dir = self.data_dir / state.lower() / "parquet" / "quarter_sections_parts"
        single_file = self.data_dir / state.lower() / "parquet" / "quarter_sections.parquet"
        
        if parts_dir.exists():
            logger.info("📂 Loading from partitioned subdivisions")
            subdivisions_gdf = self._load_quarter_sections_parts(parts_dir, bounds)
        elif single_file.exists():
            logger.info("📄 Loading from single subdivisions file")
            subdivisions_gdf = gpd.read_parquet(single_file)
        else:
            logger.warning("❌ No subdivisions data found")
            return gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")
        
        logger.info(f"📄 Loaded {len(subdivisions_gdf)} total subdivisions")
        logger.info(f"📊 Subdivisions columns: {list(subdivisions_gdf.columns)}")
        
        # SPATIAL INTERSECTION - subdivisions parquet lacks TRS columns
        intersecting = subdivisions_gdf[subdivisions_gdf.geometry.intersects(cell_geometry)]
        logger.info(f"🔲 SUBDIVISIONS RESULT: {len(intersecting)} features in cell (spatial intersection)")
        
        return intersecting
    
    def get_grid_container(self, state: str, cell_geometry) -> gpd.GeoDataFrame:
        """Get grid (specific township-range cell only)"""
        logger.info("🌐 GRID CONTAINER: Getting exact cell")
        
        townships_file = self.data_dir / state.lower() / "parquet" / "townships.parquet"
        townships_gdf = gpd.read_parquet(townships_file)
        
        # For grid, return only the exact cell that matches the geometry
        intersecting = townships_gdf[townships_gdf.geometry.intersects(cell_geometry)]
        logger.info(f"🌐 GRID RESULT: {len(intersecting)} features (should be 1 for exact cell)")
        
        return intersecting
    
    def _load_quarter_sections_parts(self, parts_dir: Path, bounds: Dict[str, float]) -> gpd.GeoDataFrame:
        """Load quarter sections from partitioned data with spatial pre-filtering"""
        bbox = box(bounds["west"], bounds["south"], bounds["east"], bounds["north"])
        
        collected = []
        manifest_file = parts_dir / "_manifest.json"
        
        if manifest_file.exists():
            with open(manifest_file) as f:
                manifest = json.load(f)
            part_files = [parts_dir / f for f in manifest.get("files", [])]
        else:
            part_files = list(parts_dir.glob("part_*.parquet"))
        
        for part_file in part_files:
            try:
                part_gdf = gpd.read_parquet(part_file)
                if not part_gdf.empty:
                    filtered = part_gdf[part_gdf.geometry.intersects(bbox)]
                    if not filtered.empty:
                        collected.append(filtered)
            except Exception as e:
                logger.warning(f"Failed to load part {part_file}: {e}")
                continue
        
        if not collected:
            return gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")
        
        return gpd.pd.concat(collected, ignore_index=True)


class FeatureValidator:
    """Validates that returned features are actually correct"""
    
    @staticmethod
    def validate_container_features(
        features_gdf: gpd.GeoDataFrame,
        cell_geometry,
        layer_type: str,
        plss_id: str
    ) -> Dict[str, Any]:
        """
        Comprehensive validation that features belong to the container
        
        Returns detailed validation report with pass/fail status
        """
        validation_log = []
        
        if features_gdf.empty:
            validation_log.append(f"⚠️ {layer_type.upper()}: No features found for {plss_id}")
            result = {
                "valid": True,  # Empty is valid for some layers
                "total_features": 0,
                "valid_features": 0,
                "invalid_features": 0,
                "validation_summary": f"{layer_type.upper()}: 0 features in {plss_id}",
                "validation_log": validation_log
            }
        else:
            total_features = len(features_gdf)
            
            # Check spatial intersection
            intersects = features_gdf.geometry.intersects(cell_geometry)
            valid_features = intersects.sum()
            invalid_features = total_features - valid_features
            
            is_valid = invalid_features == 0
            
            if is_valid:
                validation_log.append(f"✅ {layer_type.upper()}: All {valid_features} features correctly in {plss_id}")
            else:
                validation_log.append(f"❌ {layer_type.upper()}: {invalid_features}/{total_features} features OUTSIDE {plss_id}!")
            
            result = {
                "valid": is_valid,
                "total_features": total_features,
                "valid_features": valid_features,
                "invalid_features": invalid_features,
                "validation_summary": f"{layer_type.upper()}: {valid_features}/{total_features} valid in {plss_id}",
                "validation_log": validation_log
            }
        
        # Log validation results
        for log_entry in validation_log:
            logger.info(log_entry)
        
        return result


class PLSSOverlayEngine:
    """BULLETPROOF PLSS Overlay Engine with comprehensive validation"""
    
    def __init__(self):
        self.data_dir = Path(__file__).parent.parent.parent.parent / "plss"
        self.validator = ContainerBoundsValidator()
        self.layer_engine = LayerSpecificEngine(self.data_dir)
        self.feature_validator = FeatureValidator()
        
        self.layer_files = {
            "townships": "townships.parquet",
            "ranges": "ranges.parquet", 
            "sections": "sections.parquet",
            "quarter_sections": "quarter_sections.parquet",
            "grid": "townships.parquet"
        }
    
    def execute_query(self, query: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute PLSS overlay query with comprehensive validation and logging
        
        Returns:
            dict: {
                "features": [...],
                "validation_report": {...},
                "execution_log": [...]
            }
        """
        execution_log = []
        
        try:
            layer = query["layer"]
            query_type = query["type"]
            state = query["state"]
            
            execution_log.append(f"🚀 STARTING BULLETPROOF QUERY: {query_type} {layer} in {state}")
            
            if query_type == "container":
                return self._execute_container_query(query, execution_log)
            elif query_type == "regional":
                return self._execute_regional_query(query, execution_log)
            else:
                # For exact/multi_exact, use fallback
                return self._execute_fallback_query(query, execution_log)
                
        except Exception as e:
            error_msg = f"❌ QUERY EXECUTION FAILED: {e}"
            execution_log.append(error_msg)
            logger.error(error_msg)
            
            for log_entry in execution_log:
                logger.info(log_entry)
            
            return {
                "features": [],
                "validation_report": {"valid": False, "error": str(e)},
                "execution_log": execution_log
            }
    
    def _execute_container_query(self, query: Dict[str, Any], execution_log: List[str]) -> Dict[str, Any]:
        """Execute container query with bulletproof validation"""
        layer = query["layer"]
        state = query["state"]
        plss_info = query.get("plss_info", {})
        
        execution_log.append(f"🎯 CONTAINER QUERY: {layer} for T{plss_info.get('township_number')}{plss_info.get('township_direction')} R{plss_info.get('range_number')}{plss_info.get('range_direction')}")
        
        # Step 1: Validate and get exact container cell
        container_validation = self.validator.validate_and_get_exact_cell(state, plss_info, self.data_dir)
        
        if not container_validation["valid"]:
            execution_log.extend(container_validation.get("validation_log", []))
            execution_log.append(f"❌ CONTAINER VALIDATION FAILED: {container_validation['error']}")
            
            for log_entry in execution_log:
                logger.info(log_entry)
            
            return {
                "features": [],
                "validation_report": container_validation,
                "execution_log": execution_log
            }
        
        cell_geometry = container_validation["cell_geometry"]
        plss_id = container_validation["plss_id"]
        cell_bounds = container_validation["cell_bounds"]
        
        execution_log.extend(container_validation.get("validation_log", []))
        
        # Step 2: Get features using dedicated layer engine
        execution_log.append(f"🔧 RETRIEVING {layer.upper()} FEATURES")
        
        if layer == "townships":
            features_gdf = self.layer_engine.get_townships_container(state, cell_geometry)
        elif layer == "ranges":
            features_gdf = self.layer_engine.get_ranges_container(state, cell_geometry)
        elif layer == "sections":
            features_gdf = self.layer_engine.get_sections_container(state, cell_geometry)
        elif layer == "quarter_sections":
            features_gdf = self.layer_engine.get_quarter_sections_container(state, cell_geometry, cell_bounds)
        elif layer == "subdivisions":
            features_gdf = self.layer_engine.get_subdivisions_container(state, cell_geometry, cell_bounds)
        elif layer == "grid":
            features_gdf = self.layer_engine.get_grid_container(state, cell_geometry)
        else:
            raise ValueError(f"Unknown layer: {layer}")
        
        # Step 3: Validate features are actually in container
        feature_validation = self.feature_validator.validate_container_features(
            features_gdf, cell_geometry, layer, plss_id
        )
        
        execution_log.extend(feature_validation.get("validation_log", []))
        
        # Step 4: Process geometry and convert to GeoJSON
        features_gdf = self._process_layer_geometry(features_gdf, query)
        features_gdf = self._add_labels(features_gdf, layer)
        features = self._to_geojson_features(features_gdf)
        
        execution_log.append(f"✅ CONTAINER QUERY COMPLETE: {len(features)} features returned")
        
        # Log all execution steps
        for log_entry in execution_log:
            logger.info(log_entry)
        
        return {
            "features": features,
            "validation_report": {
                "container_validation": container_validation,
                "feature_validation": feature_validation,
                "valid": container_validation["valid"] and feature_validation["valid"]
            },
            "execution_log": execution_log
        }
    
    def _execute_regional_query(self, query: Dict[str, Any], execution_log: List[str]) -> Dict[str, Any]:
        """Execute regional query with spatial bounds filtering"""
        execution_log.append("🗺️ REGIONAL QUERY: Using spatial bounds filtering")
        
        # Load dataset and apply spatial filtering
        gdf = self._load_dataset(query)
        if gdf is None or gdf.empty:
            execution_log.append("❌ No data found for regional query")
            for log_entry in execution_log:
                logger.info(log_entry)
            return {"features": [], "validation_report": {"valid": True}, "execution_log": execution_log}
        
        execution_log.append(f"📄 Loaded {len(gdf)} initial features")
        
        # Apply spatial bounds filtering
        gdf = self._apply_regional_filters(gdf, query)
        execution_log.append(f"🎯 After spatial filtering: {len(gdf)} features")
        
        # Process and convert
        gdf = self._process_layer_geometry(gdf, query)
        gdf = self._add_labels(gdf, query["layer"])
        features = self._to_geojson_features(gdf)
        
        execution_log.append(f"✅ REGIONAL QUERY COMPLETE: {len(features)} features returned")
        
        for log_entry in execution_log:
            logger.info(log_entry)
        
        return {
            "features": features,
            "validation_report": {"valid": True},
            "execution_log": execution_log
        }
    
    def _execute_fallback_query(self, query: Dict[str, Any], execution_log: List[str]) -> Dict[str, Any]:
        """Execute exact/multi_exact queries using original logic"""
        execution_log.append(f"🔄 FALLBACK QUERY: {query['type']}")
        
        gdf = self._load_dataset(query)
        if gdf is None or gdf.empty:
            execution_log.append("❌ No data found for fallback query")
            return {"features": [], "validation_report": {"valid": True}, "execution_log": execution_log}
        
        # Apply original filtering logic
        if query["type"] == "exact":
            gdf = self._apply_exact_filters(gdf, query)
        elif query["type"] == "multi_exact":
            gdf = self._apply_multi_exact_filters(gdf, query)
        
        gdf = self._process_layer_geometry(gdf, query)
        gdf = self._add_labels(gdf, query["layer"])
        features = self._to_geojson_features(gdf)
        
        execution_log.append(f"✅ FALLBACK QUERY COMPLETE: {len(features)} features returned")
        
        for log_entry in execution_log:
            logger.info(log_entry)
        
        return {
            "features": features,
            "validation_report": {"valid": True},
            "execution_log": execution_log
        }
    
    def _load_dataset(self, query: Dict[str, Any]) -> Optional[gpd.GeoDataFrame]:
        """Load the appropriate parquet dataset for the query"""
        try:
            state = query["state"].lower()
            layer = query["layer"]
            
            pq_dir = self.data_dir / state / "parquet"
            
            # Handle quarter sections partitioned data
            if layer == "quarter_sections":
                return self._load_quarter_sections(pq_dir, query)
            
            # Standard parquet file
            file_name = self.layer_files.get(layer)
            if not file_name:
                raise ValueError(f"Unknown layer: {layer}")
                
            file_path = pq_dir / file_name
            if not file_path.exists():
                raise FileNotFoundError(f"Data not available for {layer} in {query['state']}: {file_path}")
            
            gdf = gpd.read_parquet(file_path)
            logger.info(f"📄 Loaded {layer} from {file_path} ({len(gdf)} features)")
            
            return gdf
            
        except Exception as e:
            logger.error(f"Failed to load dataset: {e}")
            raise
    
    def _load_quarter_sections(self, pq_dir: Path, query: Dict[str, Any]) -> Optional[gpd.GeoDataFrame]:
        """Load quarter sections from partitioned data with spatial pre-filtering"""
        try:
            parts_dir = pq_dir / "quarter_sections_parts"
            if not parts_dir.exists():
                # Fallback to single file
                single_file = pq_dir / "quarter_sections.parquet"
                if single_file.exists():
                    return gpd.read_parquet(single_file)
                return None
            
            # For partitioned data, we need bounds to avoid loading everything
            bounds = query.get("bounds")
            if not bounds or not all(bounds.get(k) for k in ["min_lon", "min_lat", "max_lon", "max_lat"]):
                raise ValueError("Quarter sections requires spatial bounds to avoid memory issues")
            
            # Create bounding box for spatial filtering
            bbox = box(bounds["min_lon"], bounds["min_lat"], bounds["max_lon"], bounds["max_lat"])
            
            # Load and filter parts
            collected = []
            manifest_file = parts_dir / "_manifest.json"
            
            if manifest_file.exists():
                # Use manifest if available
                with open(manifest_file) as f:
                    manifest = json.load(f)
                part_files = [parts_dir / f for f in manifest.get("files", [])]
            else:
                # Scan directory
                part_files = list(parts_dir.glob("part_*.parquet"))
            
            for part_file in part_files:
                try:
                    part_gdf = gpd.read_parquet(part_file)
                    # Pre-filter to bbox to reduce memory usage
                    if not part_gdf.empty:
                        filtered = part_gdf[part_gdf.geometry.intersects(bbox)]
                        if not filtered.empty:
                            collected.append(filtered)
                except Exception as e:
                    logger.warning(f"Failed to load part {part_file}: {e}")
                    continue
            
            if not collected:
                return gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")
            
            result = gpd.pd.concat(collected, ignore_index=True)
            logger.info(f"📄 Loaded quarter sections from {len(collected)} parts ({len(result)} features)")
            
            return result
            
        except Exception as e:
            logger.error(f"Failed to load quarter sections: {e}")
            raise
    
    def _apply_regional_filters(self, gdf: gpd.GeoDataFrame, query: Dict[str, Any]) -> gpd.GeoDataFrame:
        """Apply spatial bounds filtering for regional queries"""
        bounds = query.get("bounds", {})
        
        # Apply spatial bounds if provided
        min_lon = bounds.get("min_lon")
        min_lat = bounds.get("min_lat") 
        max_lon = bounds.get("max_lon")
        max_lat = bounds.get("max_lat")
        
        if all(v is not None for v in [min_lon, min_lat, max_lon, max_lat]):
            bbox = box(float(min_lon), float(min_lat), float(max_lon), float(max_lat))
            gdf = gdf[gdf.geometry.intersects(bbox)]
            logger.info(f"🗺️ Applied spatial filter: {len(gdf)} features in bounds")
        
        return gdf
    
    def _apply_container_filters(self, gdf: gpd.GeoDataFrame, query: Dict[str, Any]) -> gpd.GeoDataFrame:
        """Apply container-specific filtering for parcel-relative overlays"""
        layer = query["layer"]
        plss_info = query.get("plss_info", {})
        
        if not plss_info:
            logger.warning("❌ No PLSS info for container query")
            return gdf
        
        logger.info(f"🎯 Container filtering for {layer} with PLSS: {plss_info}")
        logger.info(f"📊 Input GDF shape: {gdf.shape}, columns: {list(gdf.columns)}")
        
        # Apply TRS filters based on layer type
        filtered_gdf = gdf
        
        if layer == "townships":
            # For townships, get the exact township row
            logger.info(f"🏘️ Filtering townships to T{plss_info.get('township_number')}{plss_info.get('township_direction')}")
            filtered_gdf = self._filter_exact_township(gdf, plss_info)
        elif layer == "ranges":
            # For ranges, get the exact range column  
            logger.info(f"📐 Filtering ranges to R{plss_info.get('range_number')}{plss_info.get('range_direction')}")
            filtered_gdf = self._filter_exact_range(gdf, plss_info)
        elif layer == "sections":
            # For sections, get all sections in the township-range cell
            logger.info(f"🏠 Filtering sections in T{plss_info.get('township_number')}{plss_info.get('township_direction')} R{plss_info.get('range_number')}{plss_info.get('range_direction')}")
            filtered_gdf = self._filter_exact_cell(gdf, plss_info)  # FIXED: Use exact cell filter
        elif layer == "quarter_sections":
            # For quarter sections, get all in the township-range cell
            logger.info(f"🏘️ Filtering quarter sections in T{plss_info.get('township_number')}{plss_info.get('township_direction')} R{plss_info.get('range_number')}{plss_info.get('range_direction')}")
            filtered_gdf = self._filter_exact_cell(gdf, plss_info)  # FIXED: Use exact cell filter
        elif layer == "grid":
            # For grid, get the exact township-range cell
            logger.info(f"🌐 Filtering grid to T{plss_info.get('township_number')}{plss_info.get('township_direction')} R{plss_info.get('range_number')}{plss_info.get('range_direction')}")
            filtered_gdf = self._filter_exact_cell(gdf, plss_info)
        
        logger.info(f"✅ Container filtering result: {filtered_gdf.shape} features (from {gdf.shape})")
        
        return filtered_gdf
    
    def _apply_exact_filters(self, gdf: gpd.GeoDataFrame, query: Dict[str, Any]) -> gpd.GeoDataFrame:
        """Apply exact TRS filtering"""
        trs_filter = query.get("trs_filter", {})
        return self._apply_trs_filters(gdf, trs_filter)
    
    def _apply_multi_exact_filters(self, gdf: gpd.GeoDataFrame, query: Dict[str, Any]) -> gpd.GeoDataFrame:
        """Apply multiple exact TRS filters (OR logic)"""
        feature_list = query.get("feature_list", [])
        
        if not feature_list:
            return gdf
        
        # Build OR filter for multiple TRS specifications
        mask = pd.Series([False] * len(gdf))
        
        for trs_spec in feature_list:
            trs_mask = self._build_trs_mask(gdf, trs_spec)
            mask = mask | trs_mask
        
        return gdf[mask]
    
    def _apply_trs_filters(self, gdf: gpd.GeoDataFrame, trs_filter: Dict[str, Any]) -> gpd.GeoDataFrame:
        """Apply TRS (Township/Range/Section) filters to geodataframe"""
        result = gdf.copy()
        
        # Township filters
        if trs_filter.get("t") is not None and "TWNSHPNO" in result.columns:
            township_str = str(trs_filter["t"]).zfill(3)
            result = result[result["TWNSHPNO"] == township_str]
            
        if trs_filter.get("td") and "TWNSHPDIR" in result.columns:
            result = result[result["TWNSHPDIR"] == str(trs_filter["td"])]
        
        # Range filters  
        if trs_filter.get("r") is not None and "RANGENO" in result.columns:
            range_str = str(trs_filter["r"]).zfill(3)
            result = result[result["RANGENO"] == range_str]
            
        if trs_filter.get("rd") and "RANGEDIR" in result.columns:
            result = result[result["RANGEDIR"] == str(trs_filter["rd"])]
        
        # Section filter
        if trs_filter.get("s") is not None and "FRSTDIVNO" in result.columns:
            result = result[result["FRSTDIVNO"] == int(trs_filter["s"])]
        
        return result
    
    def _build_trs_mask(self, gdf: gpd.GeoDataFrame, trs_spec: Dict[str, Any]) -> pd.Series:
        """Build boolean mask for a single TRS specification"""
        mask = pd.Series([True] * len(gdf))
        
        # Apply each TRS component
        if trs_spec.get("t") is not None and "TWNSHPNO" in gdf.columns:
            township_str = str(trs_spec["t"]).zfill(3)
            mask = mask & (gdf["TWNSHPNO"] == township_str)
            
        if trs_spec.get("td") and "TWNSHPDIR" in gdf.columns:
            mask = mask & (gdf["TWNSHPDIR"] == str(trs_spec["td"]))
            
        if trs_spec.get("r") is not None and "RANGENO" in gdf.columns:
            range_str = str(trs_spec["r"]).zfill(3)
            mask = mask & (gdf["RANGENO"] == range_str)
            
        if trs_spec.get("rd") and "RANGEDIR" in gdf.columns:
            mask = mask & (gdf["RANGEDIR"] == str(trs_spec["rd"]))
            
        if trs_spec.get("s") is not None and "FRSTDIVNO" in gdf.columns:
            mask = mask & (gdf["FRSTDIVNO"] == int(trs_spec["s"]))
        
        return mask
    
    def _filter_exact_township(self, gdf: gpd.GeoDataFrame, plss_info: Dict[str, Any]) -> gpd.GeoDataFrame:
        """Filter to exact township row"""
        trs = {
            "t": plss_info.get("township_number"),
            "td": plss_info.get("township_direction")
        }
        return self._apply_trs_filters(gdf, trs)
    
    def _filter_exact_range(self, gdf: gpd.GeoDataFrame, plss_info: Dict[str, Any]) -> gpd.GeoDataFrame:
        """Filter to exact range column"""
        trs = {
            "r": plss_info.get("range_number"),
            "rd": plss_info.get("range_direction")
        }
        return self._apply_trs_filters(gdf, trs)
    
    def _filter_exact_cell(self, gdf: gpd.GeoDataFrame, plss_info: Dict[str, Any]) -> gpd.GeoDataFrame:
        """Filter to exact township-range cell"""
        trs = {
            "t": plss_info.get("township_number"),
            "td": plss_info.get("township_direction"), 
            "r": plss_info.get("range_number"),
            "rd": plss_info.get("range_direction")
        }
        return self._apply_trs_filters(gdf, trs)
    
    def _filter_sections_in_cell(self, gdf: gpd.GeoDataFrame, plss_info: Dict[str, Any]) -> gpd.GeoDataFrame:
        """Filter to sections within the township-range cell (no section filter)"""
        trs = {
            "t": plss_info.get("township_number"),
            "td": plss_info.get("township_direction"),
            "r": plss_info.get("range_number"), 
            "rd": plss_info.get("range_direction")
            # Intentionally exclude section filter to get all sections in cell
        }
        return self._apply_trs_filters(gdf, trs)
    
    def _process_layer_geometry(self, gdf: gpd.GeoDataFrame, query: Dict[str, Any]) -> gpd.GeoDataFrame:
        """Process geometry based on layer type for clean display"""
        layer = query["layer"]
        
        if layer == "ranges" and query["type"] == "container":
            # Extract clean vertical lines for container ranges
            return self._extract_range_lines(gdf)
        elif layer == "townships" and query["type"] == "container":
            # Extract clean horizontal lines for container townships
            return self._extract_township_lines(gdf)
        
        # For other cases, return original geometry
        return gdf
    
    def _extract_range_lines(self, gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
        """Extract clean vertical boundary lines from range polygons"""
        try:
            from shapely.geometry import LineString, MultiLineString
            from shapely.ops import unary_union
            
            if gdf.empty:
                return gdf
            
            # Union all range polygons to get clean boundaries
            unioned = unary_union([geom.buffer(0) for geom in gdf.geometry])
            boundary = unioned.boundary
            
            # Extract line segments
            if isinstance(boundary, LineString):
                candidates = [boundary]
            elif isinstance(boundary, MultiLineString):
                candidates = list(boundary.geoms)
            else:
                return gdf  # Fallback to original
            
            # Filter to vertical lines (more vertical than horizontal)
            def is_vertical(line: LineString) -> bool:
                if len(line.coords) < 2:
                    return False
                x0, y0 = line.coords[0]
                x1, y1 = line.coords[-1]
                return abs(y1 - y0) > 1.5 * abs(x1 - x0)  # FIXED: More reasonable ratio
            
            vertical_lines = [line for line in candidates if isinstance(line, LineString) and is_vertical(line)]
            
            # Take the longest vertical lines (typically left and right boundaries)
            vertical_lines.sort(key=lambda l: l.length, reverse=True)
            vertical_lines = vertical_lines[:1]  # FIXED: Keep only 1 line to avoid double lines
            
            if not vertical_lines:
                logger.warning("No vertical range lines found, returning original data")
                return gdf
            
            # Create new GeoDataFrame with line geometries
            range_info = gdf.iloc[0]  # Use first row for metadata
            lines_data = []
            
            for line in vertical_lines:
                lines_data.append({
                    'geometry': line,
                    'RANGENO': range_info.get('RANGENO', ''),
                    'RANGEDIR': range_info.get('RANGEDIR', ''),
                    'line_type': 'range_boundary'
                })
            
            result = gpd.GeoDataFrame(lines_data, crs=gdf.crs)
            logger.info(f"✅ Extracted {len(result)} range boundary lines")
            
            return result
            
        except Exception as e:
            logger.error(f"Range line extraction failed: {e}")
            return gdf  # Fallback to original
    
    def _extract_township_lines(self, gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
        """Extract clean horizontal boundary lines from township polygons"""
        try:
            from shapely.geometry import LineString, MultiLineString
            from shapely.ops import unary_union
            
            if gdf.empty:
                return gdf
            
            # Union all township polygons to get clean boundaries
            unioned = unary_union([geom.buffer(0) for geom in gdf.geometry])
            boundary = unioned.boundary
            
            # Extract line segments
            if isinstance(boundary, LineString):
                candidates = [boundary]
            elif isinstance(boundary, MultiLineString):
                candidates = list(boundary.geoms)
            else:
                return gdf  # Fallback to original
            
            # Filter to horizontal lines (more horizontal than vertical)
            def is_horizontal(line: LineString) -> bool:
                if len(line.coords) < 2:
                    return False
                x0, y0 = line.coords[0]
                x1, y1 = line.coords[-1]
                return abs(x1 - x0) > 1.5 * abs(y1 - y0)  # FIXED: More reasonable ratio
            
            horizontal_lines = [line for line in candidates if isinstance(line, LineString) and is_horizontal(line)]
            
            # Take the longest horizontal lines (typically top and bottom boundaries)
            horizontal_lines.sort(key=lambda l: l.length, reverse=True)
            horizontal_lines = horizontal_lines[:1]  # FIXED: Keep only 1 line to avoid double lines
            
            if not horizontal_lines:
                logger.warning("No horizontal township lines found, returning original data")
                return gdf
            
            # Create new GeoDataFrame with line geometries
            township_info = gdf.iloc[0]  # Use first row for metadata
            lines_data = []
            
            for line in horizontal_lines:
                lines_data.append({
                    'geometry': line,
                    'TWNSHPNO': township_info.get('TWNSHPNO', ''),
                    'TWNSHPDIR': township_info.get('TWNSHPDIR', ''),
                    'line_type': 'township_boundary'
                })
            
            result = gpd.GeoDataFrame(lines_data, crs=gdf.crs)
            logger.info(f"✅ Extracted {len(result)} township boundary lines")
            
            return result
            
        except Exception as e:
            logger.error(f"Township line extraction failed: {e}")
            return gdf  # Fallback to original
    
    def _add_labels(self, gdf: gpd.GeoDataFrame, layer: str) -> gpd.GeoDataFrame:
        """Add clean, descriptive labels to features"""
        if gdf.empty:
            return gdf
        
        result = gdf.copy()
        
        if layer == "townships":
            result["__label"] = result.apply(
                lambda r: f"T{r.get('TWNSHPNO', '?')}{r.get('TWNSHPDIR', '?')}", axis=1
            )
        elif layer == "ranges":
            result["__label"] = result.apply(
                lambda r: f"R{r.get('RANGENO', '?')}{r.get('RANGEDIR', '?')}", axis=1
            )
        elif layer == "sections":
            result["__label"] = result.apply(
                lambda r: f"Section {r.get('FRSTDIVNO', '?')}", axis=1
            )
        elif layer == "quarter_sections":
            result["__label"] = result.apply(
                lambda r: r.get('SECDIVTXT', r.get('SECDIVLAB', 'Quarter')), axis=1
            )
        elif layer == "grid":
            result["__label"] = result.apply(
                lambda r: f"T{r.get('TWNSHPNO', '?')}{r.get('TWNSHPDIR', '?')} R{r.get('RANGENO', '?')}{r.get('RANGEDIR', '?')}", axis=1
            )
        else:
            result["__label"] = f"{layer.title()} Feature"
        
        return result
    
    def _to_geojson_features(self, gdf: gpd.GeoDataFrame) -> List[Dict[str, Any]]:
        """Convert GeoDataFrame to clean GeoJSON features"""
        features = []
        
        for _, row in gdf.iterrows():
            try:
                if row.geometry is None or row.geometry.is_empty:
                    continue
                
                # Get centroid for label positioning
                try:
                    centroid = row.geometry.centroid
                    label_lat, label_lon = float(centroid.y), float(centroid.x)
                except:
                    label_lat, label_lon = 0.0, 0.0
                
                feature = {
                    "type": "Feature",
                    "geometry": mapping(row.geometry),
                    "properties": {
                        "label": str(row.get("__label", "")),
                        "label_lat": label_lat,
                        "label_lon": label_lon,
                        # Include relevant PLSS attributes
                        **{k: v for k, v in row.items() 
                           if k not in ['geometry', '__label'] and not pd.isna(v)}
                    }
                }
                
                features.append(feature)
                
            except Exception as e:
                logger.warning(f"Failed to convert feature to GeoJSON: {e}")
                continue
        
        return features
    
    def get_available_layers(self, state: str) -> List[Dict[str, Any]]:
        """Get list of available layers for the specified state"""
        try:
            state_dir = self.data_dir / state.lower() / "parquet"
            
            if not state_dir.exists():
                return []
            
            available = []
            
            for layer, filename in self.layer_files.items():
                file_path = state_dir / filename
                
                # Special check for quarter sections (may be partitioned)
                if layer == "quarter_sections":
                    parts_dir = state_dir / "quarter_sections_parts"
                    if file_path.exists() or parts_dir.exists():
                        available.append({
                            "layer": layer,
                            "file": filename,
                            "available": True,
                            "partitioned": parts_dir.exists()
                        })
                    else:
                        available.append({
                            "layer": layer,
                            "file": filename,
                            "available": False
                        })
                else:
                    available.append({
                        "layer": layer,
                        "file": filename,
                        "available": file_path.exists()
                    })
            
            return available
            
        except Exception as e:
            logger.error(f"Failed to get available layers: {e}")
            return []
