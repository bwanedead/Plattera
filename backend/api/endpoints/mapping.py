"""
Mapping API Endpoints
Geographic mapping functionality for converting polygons to real-world coordinates
"""
from fastapi import APIRouter, HTTPException, status, Body, Query
from fastapi.responses import FileResponse
from typing import Optional, Dict, Any, List
import logging
from pathlib import Path
import json

logger = logging.getLogger(__name__)
router = APIRouter()

# Fix: Import the get_registry function
from services.registry import get_registry

# Import PLSS services (only what's needed for mapping functionality)
from services.plss.plss_data_service import PLSSDataService
from services.plss.plss_lookup_service import PLSSLookupService
from services.plss.plss_section_view_service import PLSSSectionViewService
from services.plss.plss_overlay_generator_service import PLSSOverlayGeneratorService

@router.get("/test")
async def test_mapping_endpoint():
    """Simple test to verify mapping router is working"""
    logger.info("🧪 TEST: Mapping router is working!")
    return {"message": "Mapping router is working", "success": True}

@router.post("/project-polygon")
async def project_polygon_to_map(request: Dict[str, Any]) -> Dict[str, Any]:
    """
    Project local polygon coordinates to geographic map coordinates
    
    Args:
        request: JSON with local_coordinates, plss_anchor, and options
    
    Returns:
        dict: Projected coordinates and metadata
    """
    try:
        logger.info("Received polygon projection request")
        logger.info(f"Request keys: {list(request.keys())}")
        if request.get("plss_anchor"):
            logger.info(f"PLSS state: {request['plss_anchor'].get('state')}")
        
        # Extract request data
        local_coordinates = request.get("local_coordinates", [])
        plss_anchor = request.get("plss_anchor", {})
        options = request.get("options", {})
        
        if not local_coordinates:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="local_coordinates are required"
            )
        
        if not plss_anchor:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="plss_anchor information is required"
            )
        
        # Use new fresh GeoreferenceService
        from pipelines.mapping.georeference.georeference_service import GeoreferenceService

        georeference_service = GeoreferenceService()
        result = georeference_service.georeference_polygon({
            "local_coordinates": local_coordinates,
            "plss_anchor": plss_anchor,
            "starting_point": request.get("starting_point", {}),
            "options": options,
        })

        # Log the actual error from georeference service
        if not result.get("success"):
            error_msg = result.get('error', 'Unknown error')
            logger.error(f"Georeference service failed: {error_msg}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Georeference failed: {error_msg}"
            )
        
        # Log successful georeference
        if result.get("success"):
            try:
                anchor = result.get("anchor_info", {})
                coords = anchor.get("resolved_coordinates", {})
                method = result.get("projection_metadata", {}).get("method", "unknown")
                lat_val = coords.get("lat", 0.0)
                lon_val = coords.get("lon", 0.0)
                lat = float(lat_val) if lat_val is not None else 0.0
                lon = float(lon_val) if lon_val is not None else 0.0
                logger.info(f"✅ Georeference complete using {method} method at {lat:.6f}, {lon:.6f}")
            except Exception as log_err:
                logger.warning(f"Georeference succeeded but logging failed: {log_err}")

        return result
        
    except Exception as e:
        # Include traceback for better diagnostics and ensure a helpful error message
        import traceback
        tb = traceback.format_exc()
        msg = str(e) if str(e) else "Unknown error (see server logs)"
        logger.error(f"Error in polygon georeference: {msg}\n{tb}")
        if isinstance(e, HTTPException):
            raise
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {msg}"
        )

# ------------------- Dedicated Georeference Endpoints -------------------

@router.post("/georeference/project")
async def georeference_project(request: Dict[str, Any]) -> Dict[str, Any]:
    """
    Dedicated endpoint to georeference a local polygon to geographic coordinates.
    Body: { local_coordinates: [{x,y}], plss_anchor: {...}, starting_point?: { tie_to_corner?: {...} }, options?: {...} }
    """
    try:
        from pipelines.mapping.georeference.georeference_service import GeoreferenceService

        georeference_service = GeoreferenceService()
        result = georeference_service.georeference_polygon({
            "local_coordinates": request.get("local_coordinates", []),
            "plss_anchor": request.get("plss_anchor", {}),
            "starting_point": request.get("starting_point", {}),
            "options": request.get("options", {}),
        })

        if not result.get("success"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=result.get("error", "Georeference failed")
            )

        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ georeference_project error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/georeference/resolve-pob")
async def georeference_resolve_pob(request: Dict[str, Any]) -> Dict[str, Any]:
    """
    Dedicated endpoint to resolve the Point of Beginning (POB) from PLSS and optional tie.
    Body: { plss_anchor: {...}, starting_point?: { tie_to_corner?: {...} } }
    """
    try:
        from pipelines.mapping.georeference.pob_resolver import POBResolver

        plss_anchor = request.get("plss_anchor", {})
        starting_point = request.get("starting_point", {})
        tie_to_corner = (starting_point or {}).get("tie_to_corner")

        resolver = POBResolver()
        result = resolver.resolve_pob(plss_anchor, tie_to_corner)
        if not result.get("success"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=result.get("error", "POB resolution failed")
            )
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ georeference_resolve_pob error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/tile-cache/stats")
async def get_tile_cache_stats():
    """Get tile cache statistics"""
    try:
        from pipelines.mapping.tiles.smart_cache import SmartTileCache
        cache = SmartTileCache()
        return cache.get_stats()
    except Exception as e:
        logger.error(f"Cache stats error: {e}")
        return {"error": str(e)}

@router.post("/get-map-tiles")
async def get_map_tiles(request: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get map tiles for specified bounding box and zoom level
    
    Args:
        request: JSON with bbox, zoom_level, and provider
        
    Returns:
        dict: Map tiles information
    """
    try:
        bbox = request.get("bbox")
        zoom_level = request.get("zoom_level")
        provider = request.get("provider", "usgs_topo")
        
        if not bbox:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Missing bbox in request"
            )
        
        if zoom_level is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Missing zoom_level in request"
            )
        
        logger.info(f"🗺️ Getting map tiles for bbox: {bbox} at zoom {zoom_level}")
        
        # Import tile pipeline
        from pipelines.mapping.tiles.pipeline import TilePipeline
        
        # Get tiles
        tile_pipeline = TilePipeline()
        tiles_result = tile_pipeline.get_tiles_for_extent(bbox, zoom_level, provider)
        
        if not tiles_result["success"]:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Tile fetching failed: {tiles_result['error']}"
            )
        
        logger.info(f"✅ Retrieved {len(tiles_result['tiles'])} tiles successfully")
        
        return tiles_result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Map tiles request failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Map tiles request failed: {str(e)}"
        )

@router.post("/resolve-plss")
async def resolve_plss_coordinates(request: Dict[str, Any]) -> Dict[str, Any]:
    """
    Resolve PLSS description to geographic coordinates
    
    Args:
        request: JSON with PLSS description data
        
    Returns:
        dict: Geographic coordinates and metadata
    """
    try:
        plss_description = request.get("plss_description")
        
        if not plss_description:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Missing plss_description in request"
            )
        
        logger.info("📍 Resolving PLSS coordinates")
        
        # Import PLSS pipeline
        from pipelines.mapping.plss.pipeline import PLSSPipeline
        
        # Resolve coordinates
        plss_pipeline = PLSSPipeline()
        result = plss_pipeline.resolve_starting_point(plss_description)
        
        if not result["success"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"PLSS resolution failed: {result['error']}"
            )
        
        logger.info("✅ PLSS coordinates resolved successfully")
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ PLSS resolution failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"PLSS resolution failed: {str(e)}"
        )

@router.post("/plss/overlay")
async def plss_overlay(request: Dict[str, Any]) -> Dict[str, Any]:
    """
    Return PLSS overlay geometry for visualization (section, optional township, quarter splits).
    Body: { "plss_description": { ... } }
    """
    try:
        plss_description = request.get("plss_description")
        if not plss_description:
            raise HTTPException(status_code=400, detail="Missing plss_description")

        overlay_generator = PLSSOverlayGeneratorService()
        result = overlay_generator.generate_section_overlay(plss_description)
        
        if not result.get("success"):
            raise HTTPException(status_code=400, detail=result.get("error"))
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"plss_overlay error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/tile-providers")
async def get_tile_providers() -> Dict[str, Any]:
    """Get available tile providers"""
    try:
        from pipelines.mapping.tiles.providers import TileProviders
        
        providers = TileProviders()
        return providers.get_all_providers_info()
        
    except Exception as e:
        logger.error(f"❌ Failed to get tile providers: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get tile providers: {str(e)}"
        )

@router.post("/plss/section-view")
async def plss_section_view(request: Dict[str, Any]) -> Dict[str, Any]:
    """
    Given a PLSS description, return section centroid and bounds in EPSG:4326 for map centering and tile retrieval.
    Body: { "plss_description": { state, township_number, township_direction, range_number, range_direction, section_number, principal_meridian?, quarter_sections? }, "padding": 0.1? }
    """
    try:
        plss_description = request.get("plss_description")
        padding = float(request.get("padding", 0.1))
        if not plss_description:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing plss_description")

        section_view_service = PLSSSectionViewService()
        result = section_view_service.get_section_view(plss_description, padding)
        
        if not result.get("success"):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=result.get("error"))
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"plss_section_view error: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

@router.get("/plss-states")
async def get_plss_states() -> Dict[str, Any]:
    """Get available PLSS states"""
    try:
        from pipelines.mapping.plss.pipeline import PLSSPipeline
        
        plss_pipeline = PLSSPipeline()
        return plss_pipeline.get_available_states()
        
    except Exception as e:
        logger.error(f"❌ Failed to get PLSS states: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get PLSS states: {str(e)}"
        )

@router.post("/validate-georef")
async def validate_georef(request: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validate a georeferenced polygon against PLSS.
    Body: { "plss_description": {...}, "geographic_polygon": {GeoJSON Polygon} }
    """
    try:
        plss_desc = request.get("plss_description")
        polygon = request.get("geographic_polygon")
        if not plss_desc or not polygon:
            raise HTTPException(status_code=400, detail="Missing plss_description or geographic_polygon")

        from pipelines.mapping.georeference.validator import validate_polygon_against_plss
        res = validate_polygon_against_plss(plss_desc, polygon)
        return res
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"validate_georef error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/cache/clear")
async def clear_mapping_cache(request: Dict[str, Any]) -> Dict[str, Any]:
    """
    Clear mapping cache (PLSS data, tiles, or both)
    
    Args:
        request: JSON with cache_type ("plss", "tiles", or "all")
    """
    try:
        cache_type = request.get("cache_type", "all")
        
        results = {}
        
        if cache_type in ["plss", "all"]:
            from services.cache.plss_cache import PLSSCache
            plss_cache = PLSSCache()
            results["plss"] = plss_cache.clear_all_cache()
        
        if cache_type in ["tiles", "all"]:
            from services.cache.tile_cache import TileCache
            tile_cache = TileCache()
            results["tiles"] = tile_cache.clear_all_cache()
        
        logger.info(f"✅ Cache cleared: {cache_type}")
        
        return {
            "success": True,
            "cache_type": cache_type,
            "results": results
        }
        
    except Exception as e:
        logger.error(f"❌ Cache clear failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Cache clear failed: {str(e)}"
        )

@router.get("/cache/stats")
async def get_cache_stats() -> Dict[str, Any]:
    """Get cache statistics for mapping data"""
    try:
        from services.cache.plss_cache import PLSSCache
        from services.cache.tile_cache import TileCache
        
        plss_cache = PLSSCache()
        tile_cache = TileCache()
        
        plss_stats = plss_cache.get_cache_info()
        tile_stats = tile_cache.get_cache_stats()
        
        return {
            "success": True,
            "plss_cache": plss_stats,
            "tile_cache": tile_stats
        }
        
    except Exception as e:
        logger.error(f"❌ Failed to get cache stats: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get cache stats: {str(e)}"
        )

# FIX THE ENSURE-PLSS ENDPOINT - ADD BOTH VERSIONS
@router.get("/ensure-plss/{state}")
@router.get("/ensure-plss/{state}/")
async def ensure_plss_data(state: str) -> Dict[str, Any]:
    """
    Ensure PLSS data is available for the specified state
    Downloads from BLM CadNSDI if not already cached
    
    Args:
        state: State name (e.g., "Wyoming", "Colorado")
        
    Returns:
        dict: Result with data availability status
    """
    try:
        logger.info(f"📦 Ensuring PLSS data availability for {state}")
        
        # Import PLSS data manager
        from pipelines.mapping.plss.data_manager import PLSSDataManager
        
        # Ensure data is available
        data_manager = PLSSDataManager()
        result = data_manager.ensure_state_data(state)
        
        if not result["success"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to ensure PLSS data for {state}: {result['error']}"
            )
        
        logger.info(f"✅ PLSS data ready for {state}")
        return {
            "success": True,
            "state": state,
            "data_status": "ready",
            "data_source": result.get("source", "unknown"),
            "vector_data_info": result.get("vector_data", {})
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ PLSS data ensuring failed for {state}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"PLSS data operation failed: {str(e)}"
        )

@router.get("/tile/{provider}/{z}/{x}/{y}")
async def serve_tile(provider: str, z: int, x: int, y: int):
    """
    Serve a specific map tile with high-performance streaming and caching
    
    Args:
        provider: Tile provider name (e.g., "usgs_topo", "osm_standard")
        z: Zoom level
        x: Tile X coordinate  
        y: Tile Y coordinate
        
    Returns:
        FileResponse: PNG tile with optimal caching headers
    """
    try:
        logger.debug(f"🗺️ Serving tile {provider}/{z}/{x}/{y}")
        
        # Import tile components
        from pipelines.mapping.tiles.providers import TileProviders
        from pipelines.mapping.tiles.cache_manager import TileCacheManager
        from pipelines.mapping.tiles.tile_server import TileServer
        from pipelines.mapping.tiles.config import tile_config
        
        # Validate provider
        providers = TileProviders()
        provider_result = providers.get_provider_config(provider)
        
        if not provider_result["success"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unknown tile provider: {provider}"
            )
        
        provider_config = provider_result["config"]
        
        # Validate and clamp zoom level against provider limits to avoid hard failures
        provider_min_zoom = provider_config.get("min_zoom", 0)
        provider_max_zoom = provider_config.get("max_zoom", 19)
        if z < provider_min_zoom:
            z = provider_min_zoom
        elif z > provider_max_zoom:
            z = provider_max_zoom
        
        # Check if tile proxy is enabled
        if not tile_config.tiles_proxy_enabled:
            # Return redirect to direct provider URL for high-traffic scenarios
            direct_url = provider_config["url_template"].format(z=z, x=x, y=y)
            return {"redirect": direct_url, "cors_enabled": provider_config.get("cors_enabled", False)}
        
        # Check cache first
        cache_manager = TileCacheManager()
        cache_result = cache_manager.get_cached_tile(x, y, z, provider)
        
        if cache_result["success"]:
            tile_path = Path(cache_result["local_path"])
            if tile_path.exists():
                logger.debug(f"💾 Cache hit for tile {x}/{y}/{z}")
                return FileResponse(
                    path=str(tile_path),
                    media_type="image/png",
                    headers={
                        "Cache-Control": "public, max-age=31536000",  # 1 year cache
                        "X-Tile-Source": "cache",
                        "X-Tile-Provider": provider
                    }
                )
        
        # Fetch from remote server with rate limiting
        tile_server = TileServer()
        fetch_result = tile_server.fetch_tile(x, y, z, provider_config)
        
        if not fetch_result["success"]:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Tile not available: {fetch_result.get('error', 'Unknown error')}"
            )
        
        # Cache the fetched tile
        cache_result = cache_manager.cache_tile(
            x, y, z, provider, fetch_result["tile_data"]
        )
        
        if cache_result["success"]:
            tile_path = Path(cache_result["local_path"])
            logger.debug(f"🆕 Cached and serving tile {x}/{y}/{z}")
            return FileResponse(
                path=str(tile_path),
                media_type="image/png",
                headers={
                    "Cache-Control": "public, max-age=31536000",  # 1 year cache
                    "X-Tile-Source": "remote",
                    "X-Tile-Provider": provider
                }
            )
        else:
            # Fallback: serve directly from fetch result if caching failed
            temp_path = fetch_result.get("local_path")
            if temp_path and Path(temp_path).exists():
                return FileResponse(
                    path=temp_path,
                    media_type="image/png",
                    headers={
                        "Cache-Control": "no-cache",
                        "X-Tile-Source": "temporary",
                        "X-Tile-Provider": provider
                    }
                )
            else:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to serve tile"
                )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Tile serving failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Tile serving failed: {str(e)}"
        )

@router.post("/extract-plss-info")
async def extract_plss_info(request: dict) -> dict:
    """
    Extract PLSS mapping information from schema data
    Independent of polygon processing
    """
    try:
        plss_data_service = PLSSDataService()
        return await plss_data_service.extract_mapping_info(request)
        
    except Exception as e:
        logger.error(f"PLSS info extraction failed: {str(e)}")
        return {
            "success": False,
            "error": f"Failed to extract PLSS info: {str(e)}"
        }

@router.get("/check-plss/{state}")
@router.get("/check-plss/{state}/")
async def check_plss_data_status(state: str) -> Dict[str, Any]:
    """Check if PLSS data exists for a state without downloading"""
    try:
        plss_data_service = PLSSDataService()
        return plss_data_service.check_state_data_status(state)
    except Exception as e:
        logger.error(f"❌ Error checking PLSS data status for {state}: {str(e)}")
        return {"available": False, "error": str(e)}

@router.post("/download-plss/{state}")
@router.post("/download-plss/{state}/")
async def download_plss_data(state: str, request: Dict[str, Any] | None = Body(default=None)) -> Dict[str, Any]:
    """Download PLSS data for a state (explicit user action)"""
    try:
        plss_data_service = PLSSDataService()
        return plss_data_service.download_state_data(state, request)
            
    except Exception as e:
        logger.error(f"❌ PLSS data download failed for {state}: {str(e)}")
        return {"success": False, "error": str(e)}

@router.post("/download-plss/{state}/start")
async def start_download_plss_background(state: str) -> Dict[str, Any]:
    try:
        plss_data_service = PLSSDataService()
        return plss_data_service.start_background_download(state)
    except Exception as e:
        return {"success": False, "error": str(e)}

@router.get("/download-plss/{state}/progress")
async def get_download_progress(state: str) -> Dict[str, Any]:
    try:
        plss_data_service = PLSSDataService()
        return plss_data_service.get_download_progress(state)
    except Exception as e:
        return {"success": False, "error": str(e)}

@router.post("/download-plss/{state}/cancel")
async def cancel_download(state: str) -> Dict[str, Any]:
    try:
        plss_data_service = PLSSDataService()
        return plss_data_service.cancel_download(state)
    except Exception as e:
        return {"success": False, "error": str(e)}

@router.get("/test-plss-debug")
async def test_plss_debug() -> Dict[str, Any]:
    """Debug endpoint to isolate the List error"""
    try:
        logger.info("🔍 Testing PLSSDataManager import...")
        
        # Test step 1: Basic import
        from pipelines.mapping.plss.data_manager import PLSSDataManager
        logger.info("✅ PLSSDataManager imported successfully")
        
        # Test step 2: Create instance
        data_manager = PLSSDataManager()
        logger.info("✅ PLSSDataManager instance created successfully")
        
        # Test step 3: Call the method
        result = data_manager._is_data_current("Wyoming")
        logger.info(f"✅ _is_data_current returned: {result}")
        
        return {"success": True, "result": result}
        
    except Exception as e:
        logger.error(f"❌ Test failed at: {str(e)}")
        import traceback
        logger.error(f"❌ Full traceback: {traceback.format_exc()}")
        return {"success": False, "error": str(e)}

# -------- PLSS overlay endpoints moved to dedicated plss_overlays.py --------
# See /api/plss/overlays endpoints for clean PLSS overlay functionality

@router.post("/plss-lookup")
async def get_plss_coordinates(request: Dict[str, Any]):
    """
    Get PLSS coordinates from TRS string
    
    Args:
        request: Dict with 'trs_string' (e.g., 'T14N R74W S2') and 'state'
        
    Returns:
        dict: Latitude and longitude coordinates
    """
    try:
        trs_string = request.get("trs_string")
        state = request.get("state", "Wyoming")
        
        plss_lookup_service = PLSSLookupService()
        result = plss_lookup_service.lookup_trs_coordinates(trs_string, state)
        
        if not result.get("success"):
            if "not found" in result.get("error", "").lower():
                raise HTTPException(status_code=404, detail=result.get("error"))
            else:
                raise HTTPException(status_code=400, detail=result.get("error"))
        
        return {
            "latitude": result["latitude"],
            "longitude": result["longitude"],
            "trs_string": result["trs_string"],
            "state": result["state"]
        }
        
    except Exception as e:
        logger.error(f"❌ PLSS lookup failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/download-plss/{state}/status")
async def get_download_status(state: str) -> Dict[str, Any]:
    """
    Check if download/parquet building process is active for a state
    Returns whether the process is active, not the detailed progress
    """
    try:
        plss_data_service = PLSSDataService()
        
        # Check if state is in active processing
        from pipelines.mapping.plss.data_manager import PLSSDataManager
        data_manager = PLSSDataManager()
        
        # Check if currently in processing states
        is_processing = state in data_manager._processing_states
        
        # Check progress file for active stages
        progress_path = data_manager._progress_path(state)
        active_stage = None
        if progress_path.exists():
            try:
                with open(progress_path, 'r') as f:
                    progress_data = json.load(f)
                stage = progress_data.get("stage", "")
                if stage in ["initializing", "downloading", "processing:prepare", 
                           "building:parquet", "building:index", "writing:manifest"]:
                    active_stage = stage
            except Exception:
                pass
        
        is_active = is_processing or (active_stage is not None)
        
        return {
            "success": True,
            "state": state,
            "download_active": is_active,
            "current_stage": active_stage,
            "message": f"Download process {'active' if is_active else 'inactive'} for {state}"
        }
        
    except Exception as e:
        logger.error(f"❌ Error checking download status for {state}: {str(e)}")
        return {
            "success": False,
            "error": str(e),
            "download_active": False  # Default to false on error
        }