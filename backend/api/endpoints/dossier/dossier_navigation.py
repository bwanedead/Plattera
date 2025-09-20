"""
Dossier Navigation API Endpoints
===============================

Endpoints for dossier discovery, search, and navigation features.
Provides ways to find and explore dossier collections.
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Dict, Any, Optional, List
import logging

from services.dossier.navigation_service import DossierNavigationService

logger = logging.getLogger(__name__)
router = APIRouter()


# Pydantic Models
class SearchFilters(BaseModel):
    """Filters for dossier search"""
    has_transcriptions: Optional[bool] = None
    min_transcriptions: Optional[int] = None


class NavigationResponse(BaseModel):
    """Response model for navigation operations"""
    success: bool
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class SearchResponse(BaseModel):
    """Response model for search operations"""
    success: bool
    query: str
    results: List[Dict[str, Any]]
    total_results: int
    error: Optional[str] = None


class StatsResponse(BaseModel):
    """Response model for statistics"""
    success: bool
    stats: Dict[str, Any]
    error: Optional[str] = None


# Initialize service
navigation_service = DossierNavigationService()


@router.get("/recent", response_model=NavigationResponse)
async def get_recent_dossiers(limit: int = Query(10, ge=1, le=50)):
    """
    Get recently updated dossiers.

    Args:
        limit: Maximum number of dossiers to return (1-50)

    Returns:
        NavigationResponse with recent dossiers
    """
    logger.info(f"🕐 API: Getting {limit} recent dossiers")

    try:
        dossiers = navigation_service.get_recent_dossiers(limit=limit)

        dossier_dicts = [dossier.to_dict() for dossier in dossiers]

        logger.info(f"✅ API: Retrieved {len(dossiers)} recent dossiers")
        return NavigationResponse(
            success=True,
            data={
                "dossiers": dossier_dicts,
                "count": len(dossiers)
            }
        )

    except Exception as e:
        logger.error(f"❌ API: Failed to get recent dossiers: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get recent dossiers: {str(e)}")


@router.get("/search", response_model=SearchResponse)
async def search_dossiers(
    q: str = Query(..., description="Search query"),
    has_transcriptions: Optional[bool] = None,
    min_transcriptions: Optional[int] = None,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0)
):
    """
    Search dossiers by title, description, or other criteria.

    Args:
        q: Search query string
        has_transcriptions: Filter for dossiers with transcriptions
        min_transcriptions: Minimum transcription count
        limit: Maximum results to return (1-100)
        offset: Pagination offset

    Returns:
        SearchResponse with matching dossiers
    """
    logger.info(f"🔍 API: Searching dossiers with query '{q}'")

    try:
        # Build filters
        filters = {}
        if has_transcriptions is not None:
            filters["has_transcriptions"] = has_transcriptions
        if min_transcriptions is not None:
            filters["min_transcriptions"] = min_transcriptions

        results = navigation_service.search_dossiers(
            query=q,
            filters=filters,
            limit=limit,
            offset=offset
        )

        result_dicts = [result.to_dict() for result in results]

        logger.info(f"✅ API: Search returned {len(results)} dossiers")
        return SearchResponse(
            success=True,
            query=q,
            results=result_dicts,
            total_results=len(results)
        )

    except Exception as e:
        logger.error(f"❌ API: Search failed: {e}")
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")


@router.get("/{dossier_id}/summary", response_model=NavigationResponse)
async def get_dossier_summary(dossier_id: str):
    """
    Get summary information for a dossier.

    Args:
        dossier_id: The dossier to summarize

    Returns:
        NavigationResponse with dossier summary
    """
    logger.info(f"📊 API: Getting summary for dossier {dossier_id}")

    try:
        summary = navigation_service.get_dossier_summary(dossier_id)

        if not summary:
            raise HTTPException(status_code=404, detail=f"Dossier not found: {dossier_id}")

        logger.info(f"✅ API: Retrieved summary for dossier {dossier_id}")
        return NavigationResponse(
            success=True,
            data=summary.to_dict()
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ API: Failed to get dossier summary: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get summary: {str(e)}")


@router.get("/{dossier_id}/structure", response_model=NavigationResponse)
async def get_dossier_structure(dossier_id: str):
    """
    Get complete dossier structure with transcriptions.

    Args:
        dossier_id: The dossier to examine

    Returns:
        NavigationResponse with dossier structure
    """
    logger.info(f"🏗️ API: Getting structure for dossier {dossier_id}")

    try:
        structure = navigation_service.get_dossier_structure(dossier_id)

        if not structure:
            raise HTTPException(status_code=404, detail=f"Dossier not found: {dossier_id}")

        logger.info(f"✅ API: Retrieved structure for dossier {dossier_id}")
        return NavigationResponse(
            success=True,
            data=structure.to_dict()
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ API: Failed to get dossier structure: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get structure: {str(e)}")


@router.get("/{dossier_id}/hierarchy", response_model=NavigationResponse)
async def get_dossier_hierarchy(dossier_id: str):
    """
    Get navigation hierarchy for a dossier.
    Useful for UI navigation components.

    Args:
        dossier_id: The dossier

    Returns:
        NavigationResponse with navigation hierarchy
    """
    logger.info(f"🌳 API: Getting hierarchy for dossier {dossier_id}")

    try:
        hierarchy = navigation_service.get_navigation_hierarchy(dossier_id)

        if "error" in hierarchy:
            raise HTTPException(status_code=404, detail=hierarchy["error"])

        logger.info(f"✅ API: Retrieved hierarchy for dossier {dossier_id}")
        return NavigationResponse(
            success=True,
            data=hierarchy
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ API: Failed to get dossier hierarchy: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get hierarchy: {str(e)}")


@router.get("/stats", response_model=StatsResponse)
async def get_dossier_stats():
    """
    Get overall statistics about the dossier system.

    Returns:
        StatsResponse with system statistics
    """
    logger.info("📊 API: Getting dossier system statistics")

    try:
        stats = navigation_service.get_dossier_stats()

        logger.info("✅ API: Retrieved system statistics")
        return StatsResponse(
            success=True,
            stats=stats
        )

    except Exception as e:
        logger.error(f"❌ API: Failed to get statistics: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get statistics: {str(e)}")


@router.get("/{dossier_id}/similar", response_model=NavigationResponse)
async def get_similar_dossiers(dossier_id: str, limit: int = Query(5, ge=1, le=20)):
    """
    Get dossiers similar to the specified dossier.

    Args:
        dossier_id: The dossier to find similar items for
        limit: Maximum suggestions to return (1-20)

    Returns:
        NavigationResponse with similar dossiers
    """
    logger.info(f"💡 API: Finding similar dossiers to {dossier_id}")

    try:
        similar = navigation_service.suggest_similar_dossiers(
            dossier_id=dossier_id,
            limit=limit
        )

        similar_dicts = [dossier.to_dict() for dossier in similar]

        logger.info(f"✅ API: Found {len(similar)} similar dossiers")
        return NavigationResponse(
            success=True,
            data={
                "target_dossier_id": dossier_id,
                "similar_dossiers": similar_dicts,
                "count": len(similar)
            }
        )

    except Exception as e:
        logger.error(f"❌ API: Failed to find similar dossiers: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to find similar dossiers: {str(e)}")


@router.get("/health")
async def dossier_navigation_health_check():
    """Simple health check for dossier navigation service"""
    return {"status": "healthy", "service": "dossier-navigation"}
