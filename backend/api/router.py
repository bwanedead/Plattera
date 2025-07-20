"""
Central API Router
Combines all API endpoints into a single router for main.py
"""
from fastapi import APIRouter
from api.endpoints import models, processing, system, alignment, bounding_boxes

# Create the main API router
api_router = APIRouter()

# Include all endpoint routers
api_router.include_router(models.router, prefix="/api", tags=["models"])
api_router.include_router(processing.router, prefix="/api", tags=["processing"])  
api_router.include_router(system.router, prefix="/api", tags=["system"])
api_router.include_router(alignment.router, prefix="/api/alignment", tags=["alignment"])
api_router.include_router(bounding_boxes.router, prefix="/api/bounding-boxes", tags=["bounding-boxes"])

# Quick access to pipeline-specific endpoints for backwards compatibility
api_router.include_router(models.router, prefix="/api/image-to-text", tags=["image-to-text"])
api_router.include_router(processing.router, prefix="/api/image", tags=["image-processing"])

# Add a root endpoint for API discovery
@api_router.get("/api")
async def api_root():
    """API root endpoint for discovery"""
    return {
        "message": "Plattera API v2.0",
        "documentation": "/docs",
        "endpoints": {
            "models": "/api/models - Get all available models",
            "processing": "/api/process - Process content through pipelines",
            "alignment": "/api/alignment/align-drafts - Align legal document drafts",
            "bounding_boxes": "/api/bounding-boxes/pipeline - Bounding box detection pipeline",
            "health": "/api/health - System health check",
            "services": "/api/services - Service status",
            "processing_types": "/api/process/types - Available processing types"
        },
        "backwards_compatibility": {
            "image_models": "/api/image-to-text/models",
            "image_process": "/api/image/process"
        }
    } 