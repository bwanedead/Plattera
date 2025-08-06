"""
Mapping API Endpoints
Geographic mapping functionality for converting polygons to real-world coordinates
"""
from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse
from typing import Optional, Dict, Any, List
import logging
from pathlib import Path

logger = logging.getLogger(__name__)
router = APIRouter()

# Fix: Import the get_registry function
from services.registry import get_registry

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
        
        # Fix: Use get_registry() function
        registry = get_registry()
        projection_pipeline = registry.get_pipeline("projection")
        
        # Process projection
        result = await projection_pipeline.process({
            "local_coordinates": local_coordinates,
            "plss_anchor": plss_anchor,
            "options": options
        })
        
        if not result.get("success"):
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Projection failed: {result.get('error', 'Unknown error')}"
            )
        
        return {
            "success": True,
            "projected_coordinates": result["projected_coordinates"],
            "coordinate_system": result.get("coordinate_system"),
            "metadata": result.get("metadata", {})
        }
        
    except Exception as e:
        logger.error(f"Error in polygon projection: {str(e)}")
        if isinstance(e, HTTPException):
            raise
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(e)}"
        )

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
        
        # Validate zoom level against provider limits
        if z < provider_config.get("min_zoom", 0) or z > provider_config.get("max_zoom", 19):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Zoom level {z} outside valid range for {provider} ({provider_config.get('min_zoom', 0)}-{provider_config.get('max_zoom', 19)})"
            )
        
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
        # Fix: Use absolute import
        from pipelines.mapping.plss.plss_extractor import PLSSExtractor
        
        extractor = PLSSExtractor()
        result = extractor.extract_mapping_info(request)
        
        if not result["success"]:
            return result
        
        # Check if PLSS data is available for the required state
        state = result["mapping_data"]["state"]
        # Fix: Use get_registry() function
        registry = get_registry()
        plss_cache = registry.get_service("plss_cache")
        
        data_status = await plss_cache.check_state_data(state)
        
        return {
            "success": True,
            "plss_info": result["mapping_data"],
            "data_requirements": result["data_requirements"], 
            "data_status": data_status
        }
        
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
        # Import and create data manager directly
        from pipelines.mapping.plss.data_manager import PLSSDataManager
        data_manager = PLSSDataManager()
        
        # Check if data exists locally  
        has_data = data_manager._is_data_current(state)
        
        return {
            "available": has_data,
            "state": state,
            "message": f"PLSS data for {state} {'is available' if has_data else 'needs to be downloaded'}"
        }
    except Exception as e:
        logger.error(f"❌ Error checking PLSS data status for {state}: {str(e)}")
        return {"available": False, "error": str(e)}

@router.post("/download-plss/{state}")
@router.post("/download-plss/{state}/")
async def download_plss_data(state: str) -> Dict[str, Any]:
    """Download PLSS data for a state (explicit user action)"""
    try:
        logger.info(f"📦 User requested download of PLSS data for {state}")
        # Import and create data manager directly
        from pipelines.mapping.plss.data_manager import PLSSDataManager
        data_manager = PLSSDataManager()
        
        # Perform the download
        result = data_manager.ensure_state_data(state)
        
        if result.get('success'):
            logger.info(f"✅ PLSS data download completed for {state}")
            return {
                "success": True,
                "state": state,
                "message": f"PLSS data for {state} downloaded successfully",
                "features_count": result.get('features_count', 0)
            }
        else:
            return {"success": False, "error": result.get('error', 'Unknown error')}
            
    except Exception as e:
        logger.error(f"❌ PLSS data download failed for {state}: {str(e)}")
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