"""
System Management Endpoints
==========================

Endpoints for system health monitoring, cleanup, and maintenance.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Dict, Any, List
import logging

from services.alignment_service import AlignmentService

logger = logging.getLogger(__name__)
router = APIRouter()


class HealthResponse(BaseModel):
    """Response model for health check endpoints"""
    status: str
    memory_usage_mb: float
    cpu_percent: float
    uptime_seconds: float
    overall_status: str
    recommendations: List[str] = []
    errors: List[str] = []


class CleanupResponse(BaseModel):
    """Response model for cleanup endpoints"""
    status: str
    actions_performed: List[str]
    memory_before_mb: float
    memory_after_mb: float
    memory_freed_mb: float
    errors: List[str] = []


@router.get("/health", response_model=HealthResponse)
async def check_system_health():
    """
    Check system health status including memory usage, CPU, and file system health.
    """
    try:
        logger.info("🏥 SYSTEM HEALTH CHECK REQUEST")
        
        alignment_service = AlignmentService()
        health_status = alignment_service.get_health_status()
        
        # Calculate memory freed
        memory_freed = health_status.get('memory_before_mb', 0) - health_status.get('memory_after_mb', 0)
        
        response = HealthResponse(
            status="success",
            memory_usage_mb=health_status.get('memory_usage_mb', 0),
            cpu_percent=health_status.get('cpu_percent', 0),
            uptime_seconds=health_status.get('uptime_seconds', 0),
            overall_status=health_status.get('overall_status', 'unknown'),
            recommendations=health_status.get('recommendations', []),
            errors=health_status.get('errors', [])
        )
        
        logger.info(f"✅ HEALTH CHECK COMPLETE ► Status: {response.overall_status}")
        return response
        
    except Exception as e:
        logger.error(f"❌ Health check failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Health check failed: {str(e)}"
        )


@router.post("/cleanup", response_model=CleanupResponse)
async def perform_system_cleanup():
    """
    Perform system cleanup including memory cleanup, garbage collection, and file system cleanup.
    """
    try:
        logger.info("🧹 SYSTEM CLEANUP REQUEST")
        
        alignment_service = AlignmentService()
        cleanup_results = alignment_service.force_cleanup()
        
        # Calculate memory freed
        memory_freed = cleanup_results.get('memory_before_mb', 0) - cleanup_results.get('memory_after_mb', 0)
        
        response = CleanupResponse(
            status=cleanup_results.get('status', 'unknown'),
            actions_performed=cleanup_results.get('actions_performed', []),
            memory_before_mb=cleanup_results.get('memory_before_mb', 0),
            memory_after_mb=cleanup_results.get('memory_after_mb', 0),
            memory_freed_mb=round(memory_freed, 1),
            errors=cleanup_results.get('errors', [])
        )
        
        logger.info(f"✅ CLEANUP COMPLETE ► Status: {response.status}, Memory freed: {response.memory_freed_mb}MB")
        return response
        
    except Exception as e:
        logger.error(f"❌ Cleanup failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Cleanup failed: {str(e)}"
        )


@router.get("/services")
async def get_services_status():
    """
    Get status of all backend services.
    """
    try:
        logger.info("🔍 SERVICES STATUS REQUEST")
        
        alignment_service = AlignmentService()
        
        # Check dependencies
        from alignment.alignment_utils import check_dependencies
        dependencies_available, missing_packages = check_dependencies()
        
        # Get engine info
        engine_info = alignment_service.alignment_engine.get_engine_info()
        
        # Get health status
        health_status = alignment_service.get_health_status()
        
        services_status = {
            'alignment_service': {
                'status': 'healthy' if health_status['overall_status'] == 'healthy' else 'warning',
                'health_status': health_status['overall_status'],
                'memory_usage_mb': health_status.get('memory_usage_mb', 0)
            },
            'dependencies': {
                'available': dependencies_available,
                'missing': missing_packages
            },
            'biopython_engine': {
                'status': 'available',
                'info': engine_info
            },
            'section_normalizer': {
                'status': 'available'
            }
        }
        
        logger.info("✅ SERVICES STATUS COMPLETE")
        return services_status
        
    except Exception as e:
        logger.error(f"❌ Services status check failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Services status check failed: {str(e)}"
        )


@router.get("/processing_types")
async def get_processing_types():
    """
    Get available processing types and their status.
    """
    try:
        logger.info("📋 PROCESSING TYPES REQUEST")
        
        processing_types = {
            "image-to-text": {
                "description": "Extract text from images using OCR and LLM processing",
                "models": ["gpt-4o", "gpt-4o-mini"],
                "extraction_modes": ["legal_document_json", "simple_text", "structured_text"],
                "status": "available"
            },
            "text-to-schema": {
                "description": "Convert text to structured schema format",
                "models": ["gpt-4o"],
                "status": "available"
            },
            "alignment": {
                "description": "Align multiple legal document drafts for comparison",
                "consensus_strategies": ["highest_confidence", "majority", "sequential"],
                "status": "available"
            }
        }
        
        logger.info("✅ PROCESSING TYPES COMPLETE")
        return processing_types
        
    except Exception as e:
        logger.error(f"❌ Processing types check failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Processing types check failed: {str(e)}"
        ) 