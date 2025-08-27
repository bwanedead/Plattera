"""
Georeference API Endpoints
Dedicated endpoints for georeferencing polygons and resolving POB
"""
from fastapi import APIRouter, HTTPException, status, Body
from typing import Dict, Any
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/georeference")

@router.post("/project")
async def project_polygon_to_map(request: Dict[str, Any]) -> Dict[str, Any]:
    """
    Project local polygon coordinates to geographic map coordinates
    
    Args:
        request: JSON with local_coordinates, plss_anchor, starting_point, and options
    
    Returns:
        dict: Projected coordinates and metadata
    """
    try:
        logger.info("🗺️ Georeference project endpoint called")
        logger.info(f"Request keys: {list(request.keys())}")
        if request.get("plss_anchor"):
            logger.info(f"PLSS state: {request['plss_anchor'].get('state')}")
        
        # Extract request data
        local_coordinates = request.get("local_coordinates", [])
        plss_anchor = request.get("plss_anchor", {})
        starting_point = request.get("starting_point", {})
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
        
        # Use GeoreferenceService
        from pipelines.mapping.georeference.georeference_service import GeoreferenceService

        georeference_service = GeoreferenceService()
        result = georeference_service.georeference_polygon({
            "local_coordinates": local_coordinates,
            "plss_anchor": plss_anchor,
            "starting_point": starting_point,
            "options": options,
        })

        # Log the actual error from georeference service
        if not result.get("success"):
            error_msg = result.get('error', 'Unknown error')
            logger.error(f"❌ Georeference service failed: {error_msg}")
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
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Georeference project endpoint failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Georeference project failed: {str(e)}"
        )

@router.post("/resolve-pob")
async def resolve_pob_endpoint(request: Dict[str, Any]) -> Dict[str, Any]:
    """
    Resolve Point of Beginning (POB) from PLSS anchor information
    
    Args:
        request: JSON with plss_anchor and optional tie_to_corner
    
    Returns:
        dict: POB coordinates and metadata
    """
    try:
        logger.info("📍 POB resolution endpoint called")
        
        plss_anchor = request.get("plss_anchor")
        tie_to_corner = request.get("tie_to_corner")
        
        if not plss_anchor:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="plss_anchor is required"
            )

        from pipelines.mapping.georeference.pob_resolver import POBResolver
        pob_resolver = POBResolver()
        result = pob_resolver.resolve_pob(plss_anchor, tie_to_corner)

        if not result.get("success"):
            error_msg = result.get("error", "POB resolution failed")
            logger.error(f"❌ POB resolution failed: {error_msg}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=error_msg
            )
        
        logger.info(f"✅ POB resolved successfully using {result.get('method', 'unknown')} method")
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ POB resolution endpoint failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"POB resolution failed: {str(e)}"
        )
