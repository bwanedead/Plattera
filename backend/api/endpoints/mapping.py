"""
Mapping API Endpoints
Geographic mapping functionality for converting polygons to real-world coordinates
"""
from fastapi import APIRouter, HTTPException, status
from typing import Optional, Dict, Any, List
import logging

logger = logging.getLogger(__name__)
router = APIRouter()

@router.post("/project-polygon")
async def project_polygon_to_map(request: Dict[str, Any]) -> Dict[str, Any]:
    """
    Project local polygon coordinates to geographic map coordinates
    
    Args:
        request: JSON with local_coordinates, plss_anchor, and options
        
    Returns:
        dict: Geographic polygon data for map overlay
    """
    try:
        # Extract request components
        local_coordinates = request.get("local_coordinates")
        plss_anchor = request.get("plss_anchor")
        options = request.get("options", {})
        
        if not local_coordinates:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Missing local_coordinates in request"
            )
        
        if not plss_anchor:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Missing plss_anchor in request"
            )
        
        logger.info("🗺️ Starting polygon projection to geographic coordinates")
        
        # Import pipelines
        from pipelines.mapping.plss.pipeline import PLSSPipeline
        from pipelines.mapping.projection.pipeline import ProjectionPipeline
        
        # Resolve PLSS anchor to geographic coordinates
        plss_pipeline = PLSSPipeline()
        anchor_result = plss_pipeline.resolve_starting_point(plss_anchor)
        
        if not anchor_result["success"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"PLSS anchor resolution failed: {anchor_result['error']}"
            )
        
        # Project local coordinates to geographic
        projection_pipeline = ProjectionPipeline()
        projection_result = projection_pipeline.project_polygon_to_geographic(
            local_coordinates,
            anchor_result["anchor_point"],
            options
        )
        
        if not projection_result["success"]:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Polygon projection failed: {projection_result['error']}"
            )
        
        logger.info("✅ Polygon projection completed successfully")
        
        return {
            "success": True,
            "geographic_polygon": {
                "type": "Polygon",
                "coordinates": [projection_result["geographic_coordinates"]],  # GeoJSON format
                "bounds": projection_result["bounds"]
            },
            "anchor_info": {
                "plss_reference": anchor_result["metadata"]["plss_reference"],
                "resolved_coordinates": anchor_result["anchor_point"]
            },
            "projection_metadata": projection_result["metadata"]
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Polygon projection failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Polygon projection failed: {str(e)}"
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