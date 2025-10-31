"""
Central API Router
Combines all API endpoints into a single router for main.py
"""
from fastapi import APIRouter
from api.endpoints import models, processing, system, alignment, consensus, final_draft, text_to_schema, polygon, mapping, plss_overlays, georeference, plss_endpoints, coordinates_endpoints, llm_consensus
from api.endpoints import config as config_endpoints
from api.endpoints import image_to_text_jobs
from api.endpoints.plss import container_router
from api.endpoints.dossier import management_router, association_router, navigation_router, views_router, dossier_image_processing_router, runs_router
from api.endpoints.dossier import events as dossier_events
from api.endpoints.dossier import edits as dossier_edits, versions as dossier_versions
from api.endpoints.dossier import final_selection as dossier_final_selection, finalize as dossier_finalize
from api.endpoints.dossier import finals as dossier_finals
from api.endpoints.dossier import finalized_list as dossier_finalized_list

# Create the main API router
api_router = APIRouter()

# Include all endpoint routers
api_router.include_router(models.router, prefix="/api", tags=["models"])
api_router.include_router(processing.router, prefix="/api", tags=["processing"])  
api_router.include_router(system.router, prefix="/api", tags=["system"])
api_router.include_router(alignment.router, prefix="/api/alignment", tags=["alignment"])
api_router.include_router(consensus.router, prefix="/api/consensus", tags=["consensus"])
api_router.include_router(llm_consensus.router, prefix="/api/llm-consensus", tags=["llm-consensus"])
api_router.include_router(final_draft.router, prefix="/api/final-draft", tags=["final-draft"])
api_router.include_router(text_to_schema.router, prefix="/api/text-to-schema", tags=["text-to-schema"])
api_router.include_router(polygon.router, prefix="/api/polygon", tags=["polygon"])
api_router.include_router(mapping.router, prefix="/api/mapping", tags=["mapping"])
api_router.include_router(coordinates_endpoints.router, prefix="/api/mapping", tags=["coordinates"])
api_router.include_router(georeference.router, prefix="/api/mapping", tags=["georeference"])
api_router.include_router(plss_overlays.router, prefix="/api/plss", tags=["plss-overlays"])
api_router.include_router(container_router, prefix="/api/plss", tags=["plss-container"])
api_router.include_router(plss_endpoints.router, prefix="/api/plss", tags=["plss-nearest"])

# Dossier system endpoints - independent modular services
api_router.include_router(management_router, prefix="/api/dossier-management", tags=["dossier-management"])
api_router.include_router(association_router, prefix="/api/transcription-association", tags=["transcription-association"])
api_router.include_router(navigation_router, prefix="/api/dossier-navigation", tags=["dossier-navigation"])
api_router.include_router(views_router, prefix="/api/dossier-views", tags=["dossier-views"])
api_router.include_router(dossier_image_processing_router, prefix="/api/dossier", tags=["dossier-image-processing"])
api_router.include_router(runs_router, prefix="/api/dossier-runs", tags=["dossier-runs"])
api_router.include_router(dossier_events.router, prefix="/api/dossier", tags=["dossier-events"])
api_router.include_router(dossier_edits.router, prefix="/api/dossier/edits", tags=["dossier-edits"])
api_router.include_router(dossier_versions.router, prefix="/api/dossier/versions", tags=["dossier-versions"])
api_router.include_router(dossier_final_selection.router, prefix="/api/dossier/final-selection", tags=["dossier-final-selection"])
api_router.include_router(dossier_finalize.router, prefix="/api/dossier", tags=["dossier-finalize"])
api_router.include_router(dossier_finals.router, prefix="/api", tags=["dossier-finals"])
api_router.include_router(dossier_finalized_list.router, prefix="/api/dossier", tags=["dossier-finalized"])

# Quick access to pipeline-specific endpoints for backwards compatibility
api_router.include_router(models.router, prefix="/api/image-to-text", tags=["image-to-text"])
api_router.include_router(processing.router, prefix="/api/image", tags=["image-processing"])

# New batch queue endpoints for Image-to-Text
api_router.include_router(image_to_text_jobs.router, prefix="/api", tags=["image-to-text-jobs"])

# Config endpoints (no additional prefix; router has /config)
api_router.include_router(config_endpoints.router)

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
            "mapping": "/api/mapping/project-polygon - Project polygons to geographic coordinates",
            "plss_overlays": "/api/plss/overlays - PLSS overlay data for mapping visualization",
            "plss_container": "/api/plss/container - Dedicated container PLSS overlay endpoints",
            "dossier-management": "/api/dossier-management - CRUD operations for dossiers",
            "dossier-image-processing": "/api/dossier/process - Process images with dossier association and progressive saving",
            "transcription-association": "/api/transcription-association - Manage transcription relationships",
            "dossier-navigation": "/api/dossier-navigation - Discovery and navigation features",
            "dossier-views": "/api/dossier-views - Content presentation modes",
            "dossier-runs": "/api/dossier-runs - Run skeleton initialization for immediate UI feedback",
            "health": "/api/health - System health check",
            "services": "/api/services - Service status",
            "processing_types": "/api/process/types - Available processing types"
        },
        "backwards_compatibility": {
            "image_models": "/api/image-to-text/models",
            "image_process": "/api/image/process"
        }
    } 