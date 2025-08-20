"""
Container PLSS Endpoints
Dedicated endpoints for container-based PLSS overlays
"""
from fastapi import APIRouter, HTTPException, Query
from typing import Dict, Any, Optional, List
import logging

logger = logging.getLogger(__name__)
router = APIRouter()

# Import container engines
from services.plss.container.township_engine import ContainerTownshipEngine
from services.plss.container.range_engine import ContainerRangeEngine
from services.plss.container.grid_engine import ContainerGridEngine
from services.plss.container.sections_engine import ContainerSectionsEngine
from services.plss.container.quarter_sections_engine import ContainerQuarterSectionsEngine

# Import query builder for PLSS info extraction
from services.plss.query_builder import PLSSQueryBuilder

@router.post("/container/township/{state}")
async def get_container_township_overlay(
    state: str,
    request: Dict[str, Any]
):
    """
    Get township features for container overlay
    """
    logger.info(f"🏘️ CONTAINER TOWNSHIP ENDPOINT: Processing request for {state}")
    
    try:
        # Extract PLSS info and container bounds
        plss_info = PLSSQueryBuilder._extract_plss_info(request.get('schema_data', {}))
        container_bounds = request.get('container_bounds', {})
        
        if not plss_info:
            logger.error("❌ No PLSS info found in request")
            raise HTTPException(status_code=400, detail="No PLSS information provided")
        
        if not container_bounds:
            logger.error("❌ No container bounds found in request")
            raise HTTPException(status_code=400, detail="No container bounds provided")
        
        # Initialize engine and get features
        engine = ContainerTownshipEngine()
        result = engine.get_township_features(container_bounds, plss_info)
        
        logger.info(f"✅ Container township endpoint completed: {result['validation']['features_returned']} features")
        return result
        
    except Exception as e:
        logger.error(f"❌ Container township endpoint failed: {e}")
        raise HTTPException(status_code=500, detail=f"Container township overlay failed: {str(e)}")

@router.post("/container/range/{state}")
async def get_container_range_overlay(
    state: str,
    request: Dict[str, Any]
):
    """
    Get range features for container overlay
    """
    logger.info(f"📐 CONTAINER RANGE ENDPOINT: Processing request for {state}")
    
    try:
        # Extract PLSS info and container bounds
        plss_info = PLSSQueryBuilder._extract_plss_info(request.get('schema_data', {}))
        container_bounds = request.get('container_bounds', {})
        
        if not plss_info:
            logger.error("❌ No PLSS info found in request")
            raise HTTPException(status_code=400, detail="No PLSS information provided")
        
        if not container_bounds:
            logger.error("❌ No container bounds found in request")
            raise HTTPException(status_code=400, detail="No container bounds provided")
        
        # Initialize engine and get features
        engine = ContainerRangeEngine()
        result = engine.get_range_features(container_bounds, plss_info)
        
        logger.info(f"✅ Container range endpoint completed: {result['validation']['features_returned']} features")
        return result
        
    except Exception as e:
        logger.error(f"❌ Container range endpoint failed: {e}")
        raise HTTPException(status_code=500, detail=f"Container range overlay failed: {str(e)}")

@router.post("/container/grid/{state}")
async def get_container_grid_overlay(
    state: str,
    request: Dict[str, Any]
):
    """
    Get grid features (specific township-range cell) for container overlay
    """
    logger.info(f"🌐 CONTAINER GRID ENDPOINT: Processing request for {state}")
    
    try:
        # Extract PLSS info and container bounds
        plss_info = PLSSQueryBuilder._extract_plss_info(request.get('schema_data', {}))
        container_bounds = request.get('container_bounds', {})
        
        if not plss_info:
            logger.error("❌ No PLSS info found in request")
            raise HTTPException(status_code=400, detail="No PLSS information provided")
        
        if not container_bounds:
            logger.error("❌ No container bounds found in request")
            raise HTTPException(status_code=400, detail="No container bounds provided")
        
        # Initialize engine and get features
        engine = ContainerGridEngine()
        result = engine.get_grid_features(container_bounds, plss_info)
        
        logger.info(f"✅ Container grid endpoint completed: {result['validation']['features_returned']} features")
        return result
        
    except Exception as e:
        logger.error(f"❌ Container grid endpoint failed: {e}")
        raise HTTPException(status_code=500, detail=f"Container grid overlay failed: {str(e)}")

@router.post("/container/sections/{state}")
async def get_container_sections_overlay(
    state: str,
    request: Dict[str, Any]
):
    """
    Get section features for container overlay using spatial intersection
    """
    logger.info(f"🏠 CONTAINER SECTIONS ENDPOINT: Processing request for {state}")
    
    try:
        # Extract PLSS info and container bounds
        plss_info = PLSSQueryBuilder._extract_plss_info(request.get('schema_data', {}))
        container_bounds = request.get('container_bounds', {})
        
        if not plss_info:
            logger.error("❌ No PLSS info found in request")
            raise HTTPException(status_code=400, detail="No PLSS information provided")
        
        if not container_bounds:
            logger.error("❌ No container bounds found in request")
            raise HTTPException(status_code=400, detail="No container bounds provided")
        
        # Initialize engine and get features
        engine = ContainerSectionsEngine()
        result = engine.get_sections_features(container_bounds, plss_info)
        
        logger.info(f"✅ Container sections endpoint completed: {result['validation']['features_returned']} features")
        return result
        
    except Exception as e:
        logger.error(f"❌ Container sections endpoint failed: {e}")
        raise HTTPException(status_code=500, detail=f"Container sections overlay failed: {str(e)}")

@router.post("/container/quarter-sections/{state}")
async def get_container_quarter_sections_overlay(
    state: str,
    request: Dict[str, Any]
):
    """
    Get quarter section features for container overlay using spatial intersection
    """
    logger.info(f"🏘️ CONTAINER QUARTER SECTIONS ENDPOINT: Processing request for {state}")
    
    try:
        # Extract PLSS info and container bounds
        plss_info = PLSSQueryBuilder._extract_plss_info(request.get('schema_data', {}))
        container_bounds = request.get('container_bounds', {})
        
        if not plss_info:
            logger.error("❌ No PLSS info found in request")
            raise HTTPException(status_code=400, detail="No PLSS information provided")
        
        if not container_bounds:
            logger.error("❌ No container bounds found in request")
            raise HTTPException(status_code=400, detail="No container bounds provided")
        
        # Initialize engine and get features
        engine = ContainerQuarterSectionsEngine()
        result = engine.get_quarter_sections_features(container_bounds, plss_info)
        
        logger.info(f"✅ Container quarter sections endpoint completed: {result['validation']['features_returned']} features")
        return result
        
    except Exception as e:
        logger.error(f"❌ Container quarter sections endpoint failed: {e}")
        raise HTTPException(status_code=500, detail=f"Container quarter sections overlay failed: {str(e)}")
