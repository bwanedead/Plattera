"""
Central API Router
Combines all API endpoints into a single router for main.py
"""
from fastapi import APIRouter
from api.endpoints import models, processing, system, alignment, consensus, final_draft, text_to_schema, polygon

# Create the main API router
api_router = APIRouter()

# Include all endpoint routers
api_router.include_router(models.router, prefix="/api", tags=["models"])
api_router.include_router(processing.router, prefix="/api", tags=["processing"])  
api_router.include_router(system.router, prefix="/api", tags=["system"])
api_router.include_router(alignment.router, prefix="/api/alignment", tags=["alignment"])
api_router.include_router(consensus.router, prefix="/api/consensus", tags=["consensus"])
api_router.include_router(final_draft.router, prefix="/api/final-draft", tags=["final-draft"])
api_router.include_router(text_to_schema.router, prefix="/api/text-to-schema", tags=["text-to-schema"])
api_router.include_router(polygon.router, prefix="/api/polygon", tags=["polygon"])

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
            "consensus": "/api/consensus/generate-consensus - Generate consensus drafts from alignment results",
            "final_draft": "/api/final-draft/select-final-draft - Select final draft output",
            "text_to_schema": "/api/text-to-schema/convert - Convert text to structured parcel data",
            "polygon": "/api/polygon/draw - Generate polygon from structured data",
            "health": "/api/health - System health check",
            "services": "/api/services - Service status",
            "processing_types": "/api/process/types - Available processing types"
        },
        "backwards_compatibility": {
            "image_models": "/api/image-to-text/models",
            "image_process": "/api/image/process"
        }
    } 