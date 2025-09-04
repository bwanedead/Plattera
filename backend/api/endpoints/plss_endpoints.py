"""
PLSS Endpoints
Dedicated endpoints for PLSS (Public Land Survey System) operations
"""
from fastapi import APIRouter, HTTPException, status, Body
from typing import Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)
router = APIRouter()

@router.post("/find-nearest-plss")
async def find_nearest_plss_coordinates(request: Dict[str, Any]) -> Dict[str, Any]:
    """
    Find the nearest PLSS section coordinates to a given latitude/longitude

    Uses the PLSS Nearest Snap Engine to query parquet/index data efficiently

    Args:
        request: JSON with latitude, longitude, state, and search_radius_miles (optional)

    Returns:
        dict: Nearest PLSS section coordinates and metadata
    """
    try:
        latitude = request.get("latitude")
        longitude = request.get("longitude")
        state = request.get("state", "Wyoming")
        search_radius_miles = request.get("search_radius_miles", 1.0)

        if latitude is None or longitude is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Missing latitude or longitude in request"
            )

        logger.info(".6f")

        # Import and use the PLSS Nearest Snap Engine
        logger.info("🔧 Importing PLSS Nearest Snap Engine...")
        from pipelines.mapping.plss.nearest_snap_engine import PLSSNearestSnapEngine

        # Create engine instance and find nearest PLSS feature
        logger.info("🏗️ Creating PLSS Nearest Snap Engine instance...")
        snap_engine = PLSSNearestSnapEngine()
        logger.info("🔍 Calling find_nearest_plss method...")
        result = snap_engine.find_nearest_plss(
            latitude=latitude,
            longitude=longitude,
            state=state,
            search_radius_miles=search_radius_miles
        )
        logger.info(".6f")

        if result["success"]:
            logger.info(".6f")
            return result
        else:
            logger.warning(f"PLSS snap engine failed: {result.get('error', 'Unknown error')}")
            return {
                "success": False,
                "error": result.get("error", "Failed to find nearest PLSS feature"),
                "fallback": True,
                "search_location": {
                    "latitude": latitude,
                    "longitude": longitude,
                    "state": state,
                    "search_radius_miles": search_radius_miles
                }
            }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Find nearest PLSS failed: {str(e)}")
        import traceback
        logger.error(f"Full traceback: {traceback.format_exc()}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Find nearest PLSS failed: {str(e)}"
        )
