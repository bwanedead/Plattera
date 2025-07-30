"""
Polygon Drawing API Endpoints
"""
from fastapi import APIRouter, HTTPException, status
from typing import Optional, Dict, Any
import logging

from pipelines.polygon.pipeline import PolygonPipeline

logger = logging.getLogger(__name__)
router = APIRouter()

@router.post("/draw")
async def draw_polygon(request: Dict[str, Any]) -> Dict[str, Any]:
    """
    Generate polygon coordinates from structured parcel data
    """
    try:
        parcel_data = request.get("parcel_data")
        options = request.get("options", {})
        
        if not parcel_data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Missing parcel_data in request"
            )
        
        # Initialize pipeline
        pipeline = PolygonPipeline()
        
        # Process the data
        result = pipeline.process(parcel_data, options)
        
        return result
        
    except Exception as e:
        logger.error(f"Polygon drawing failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Polygon drawing failed: {str(e)}"
        )

@router.get("/options")
async def get_polygon_options() -> Dict[str, Any]:
    """
    Get available polygon drawing options
    """
    try:
        pipeline = PolygonPipeline()
        options = pipeline.get_available_options()
        
        return {
            "status": "success",
            "options": options
        }
        
    except Exception as e:
        logger.error(f"Failed to get polygon options: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get options: {str(e)}"
        ) 