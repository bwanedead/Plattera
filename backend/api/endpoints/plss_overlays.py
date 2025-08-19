"""
PLSS Overlay Endpoints
Clean, focused endpoints for PLSS overlay data with direct parquet access
"""
from fastapi import APIRouter, HTTPException, Query
from typing import Dict, Any, Optional, List
import logging

logger = logging.getLogger(__name__)
router = APIRouter()

# Import clean overlay services
from services.plss.overlay_engine import PLSSOverlayEngine
from services.plss.query_builder import PLSSQueryBuilder

@router.get("/overlays/regional/{layer}/{state}")
async def get_regional_overlay(
    layer: str,
    state: str,
    min_lon: Optional[float] = Query(None),
    min_lat: Optional[float] = Query(None),
    max_lon: Optional[float] = Query(None),
    max_lat: Optional[float] = Query(None),
):
    """
    Get PLSS overlay for regional (all-in-view) mode
    Returns all features within the specified bounds
    
    Supported layers: townships, ranges, sections, quarter_sections, grid
    """
    try:
        query = PLSSQueryBuilder.build_regional_query(
            layer=layer,
            state=state,
            bounds={
                "min_lon": min_lon, "min_lat": min_lat,
                "max_lon": max_lon, "max_lat": max_lat
            }
        )
        
        engine = PLSSOverlayEngine()
        result = engine.execute_query(query)
        
        return {
            "success": True,
            "layer": layer,
            "mode": "regional",
            "state": state,
            "feature_count": len(result["features"]),
            "type": "FeatureCollection",
            "features": result["features"]
        }
        
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Regional overlay error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/overlays/container/{layer}/{state}")
async def get_container_overlay(
    layer: str,
    state: str,
    request: Dict[str, Any]
):
    """
    Get PLSS overlay for container (parcel-relative) mode
    Extracts clean lines/features based on schema PLSS information
    
    For township layer: Returns horizontal lines that bound the parcel's township
    For range layer: Returns vertical lines that bound the parcel's range
    For sections layer: Returns sections within the container township-range cell
    """
    try:
        schema_data = request.get("schema_data", {})
        container_bounds = request.get("container_bounds")
        
        if not schema_data:
            raise HTTPException(status_code=400, detail="Schema data required for container mode")
            
        query = PLSSQueryBuilder.build_container_query(
            layer=layer,
            state=state,
            schema_data=schema_data,
            container_bounds=container_bounds
        )
        
        engine = PLSSOverlayEngine()
        result = engine.execute_query(query)
        
        return {
            "success": True,
            "layer": layer,
            "mode": "container",
            "state": state,
            "feature_count": len(result["features"]),
            "type": "FeatureCollection",
            "features": result["features"]
        }
        
    except Exception as e:
        logger.error(f"Container overlay error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/overlays/exact/{layer}/{state}")
async def get_exact_overlay(
    layer: str,
    state: str,
    t: Optional[int] = Query(None, description="Township number"),
    td: Optional[str] = Query(None, description="Township direction (N/S)"),
    r: Optional[int] = Query(None, description="Range number"), 
    rd: Optional[str] = Query(None, description="Range direction (E/W)"),
    s: Optional[int] = Query(None, description="Section number (1-36)"),
):
    """
    Get exact PLSS features by specific TRS coordinates
    Allows precise selection of specific townships, ranges, sections
    
    Examples:
    - Get Township 14N: t=14&td=N
    - Get Range 75W: r=75&rd=W  
    - Get Section 2 in T14N R75W: t=14&td=N&r=75&rd=W&s=2
    """
    try:
        trs_filter = {
            "t": t, "td": td, "r": r, "rd": rd, "s": s
        }
        
        query = PLSSQueryBuilder.build_exact_query(
            layer=layer,
            state=state,
            trs_filter=trs_filter
        )
        
        engine = PLSSOverlayEngine()
        result = engine.execute_query(query)
        
        return {
            "success": True,
            "layer": layer,
            "mode": "exact",
            "state": state,
            "trs_filter": {k: v for k, v in trs_filter.items() if v is not None},
            "feature_count": len(result["features"]),
            "type": "FeatureCollection", 
            "features": result["features"]
        }
        
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Exact overlay error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/overlays/multi-exact/{layer}/{state}")
async def get_multi_exact_overlay(
    layer: str,
    state: str,
    request: Dict[str, Any]
):
    """
    Get multiple exact PLSS features by list of TRS coordinates
    Allows selection of multiple specific features at once
    
    Request body:
    {
        "features": [
            {"t": 14, "td": "N", "r": 75, "rd": "W", "s": 2},
            {"t": 14, "td": "N", "r": 75, "rd": "W", "s": 3},
            {"t": 15, "td": "N", "r": 75, "rd": "W"}
        ]
    }
    """
    try:
        feature_list = request.get("features", [])
        
        if not feature_list:
            raise HTTPException(status_code=400, detail="Feature list required")
            
        query = PLSSQueryBuilder.build_multi_exact_query(
            layer=layer,
            state=state,
            feature_list=feature_list
        )
        
        engine = PLSSOverlayEngine()
        result = engine.execute_query(query)
        
        return {
            "success": True,
            "layer": layer,
            "mode": "multi_exact",
            "state": state,
            "requested_count": len(feature_list),
            "feature_count": len(result["features"]),
            "type": "FeatureCollection",
            "features": result["features"]
        }
        
    except Exception as e:
        logger.error(f"Multi-exact overlay error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/overlays/available-layers/{state}")
async def get_available_layers(state: str):
    """
    Get list of available PLSS layers for the specified state
    """
    try:
        engine = PLSSOverlayEngine()
        layers = engine.get_available_layers(state)
        
        return {
            "success": True,
            "state": state,
            "layers": layers
        }
        
    except Exception as e:
        logger.error(f"Available layers error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
