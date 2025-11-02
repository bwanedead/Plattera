"""
Dossier Views API Endpoints
==========================

Endpoints for different content presentation and aggregation modes.
Provides stitched views, individual views, and export functionality.
"""

from fastapi import APIRouter, HTTPException, Query, Response
from pydantic import BaseModel
from typing import Dict, Any, Optional
import logging
import os

from services.dossier.view_service import DossierViewService
from services.dossier.image_storage_service import ImageStorageService

logger = logging.getLogger(__name__)
router = APIRouter()


# Pydantic Models
class ViewResponse(BaseModel):
    """Response model for view operations"""
    success: bool
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class ExportResponse(BaseModel):
    """Response model for export operations"""
    success: bool
    export_format: str
    content_length: Optional[int] = None
    error: Optional[str] = None


# Initialize service
view_service = DossierViewService()


@router.get("/{dossier_id}/stitched", response_model=ViewResponse)
async def get_stitched_dossier_view(dossier_id: str):
    """
    Get a stitched view of all transcriptions in a dossier.
    Combines all transcriptions into a continuous document.

    Args:
        dossier_id: The dossier to stitch

    Returns:
        ViewResponse with stitched content
    """
    logger.info(f"🧵 API: Creating stitched view for dossier {dossier_id}")

    try:
        stitched_view = view_service.get_stitched_view(dossier_id)

        if not stitched_view:
            raise HTTPException(status_code=404, detail=f"Dossier not found: {dossier_id}")

        logger.info(f"✅ API: Created stitched view with {stitched_view.get('total_sections', 0)} sections")
        return ViewResponse(
            success=True,
            data=stitched_view
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ API: Failed to create stitched view: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create stitched view: {str(e)}")


@router.get("/{dossier_id}/individual", response_model=ViewResponse)
async def get_individual_transcriptions_view(dossier_id: str):
    """
    Get individual transcription views for a dossier.
    Each transcription is presented separately.

    Args:
        dossier_id: The dossier

    Returns:
        ViewResponse with individual transcriptions
    """
    logger.info(f"📄 API: Getting individual transcriptions for dossier {dossier_id}")

    try:
        transcriptions = view_service.get_individual_transcriptions(dossier_id)

        if transcriptions is None:
            raise HTTPException(status_code=404, detail=f"Dossier not found: {dossier_id}")

        logger.info(f"✅ API: Retrieved {len(transcriptions)} individual transcriptions")
        return ViewResponse(
            success=True,
            data={
                "dossier_id": dossier_id,
                "transcriptions": transcriptions,
                "count": len(transcriptions)
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ API: Failed to get individual transcriptions: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get transcriptions: {str(e)}")


@router.get("/{dossier_id}/metadata", response_model=ViewResponse)
async def get_dossier_metadata_view(dossier_id: str):
    """
    Get comprehensive metadata about a dossier and its contents.

    Args:
        dossier_id: The dossier

    Returns:
        ViewResponse with dossier metadata
    """
    logger.info(f"📊 API: Getting metadata for dossier {dossier_id}")

    try:
        metadata = view_service.get_dossier_metadata(dossier_id)

        if not metadata:
            raise HTTPException(status_code=404, detail=f"Dossier not found: {dossier_id}")

        logger.info(f"✅ API: Retrieved metadata for dossier {dossier_id}")
        return ViewResponse(
            success=True,
            data=metadata
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ API: Failed to get dossier metadata: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get metadata: {str(e)}")


@router.get("/{dossier_id}/export/{format}", response_model=ExportResponse)
async def export_dossier(dossier_id: str, format: str):
    """
    Export a dossier in various formats.

    Args:
        dossier_id: The dossier to export
        format: Export format ("json", "text")

    Returns:
        File download response
    """
    logger.info(f"📤 API: Exporting dossier {dossier_id} as {format}")

    if format not in ["json", "text"]:
        raise HTTPException(status_code=400, detail=f"Unsupported format: {format}")

    try:
        export_data = view_service.export_dossier(dossier_id, format)

        if not export_data:
            raise HTTPException(status_code=404, detail=f"Dossier not found: {dossier_id}")

        # Set appropriate content type and filename
        if format == "json":
            content_type = "application/json"
            filename = f"dossier_{dossier_id}.json"
        else:  # text
            content_type = "text/plain"
            filename = f"dossier_{dossier_id}.txt"

        logger.info(f"✅ API: Exported dossier {dossier_id} as {format} ({len(export_data)} bytes)")
        return Response(
            content=export_data,
            media_type=content_type,
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ API: Failed to export dossier: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to export dossier: {str(e)}")


@router.get("/transcription/{transcription_id}/preview", response_model=ViewResponse)
async def get_transcription_preview(
    transcription_id: str,
    max_sections: int = Query(3, ge=1, le=10)
):
    """
    Get a preview of a transcription (first few sections).

    Args:
        transcription_id: The transcription to preview
        max_sections: Maximum sections to include (1-10)

    Returns:
        ViewResponse with preview content
    """
    logger.info(f"👀 API: Creating preview for transcription {transcription_id}")

    try:
        preview = view_service.get_transcription_preview(
            transcription_id=transcription_id,
            max_sections=max_sections
        )

        if not preview:
            raise HTTPException(status_code=404, detail=f"Transcription not found: {transcription_id}")

        logger.info(f"✅ API: Created preview with {len(preview.get('preview_sections', []))} sections")
        return ViewResponse(
            success=True,
            data=preview
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ API: Failed to create transcription preview: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create preview: {str(e)}")


@router.get("/transcription/{transcription_id}/text")
async def get_transcription_text(transcription_id: str):
    """
    Return full plain text for a transcription by concatenating section bodies.
    """
    try:
        content = view_service._load_transcription_content(transcription_id)
        if not content:
            raise HTTPException(status_code=404, detail=f"Transcription not found: {transcription_id}")
        sections = content.get('sections', [])
        parts = []
        for section in sections:
            header = section.get('header', '')
            body = section.get('body', '')
            if header:
                parts.append(f"[{header}]")
            parts.append(body or '')
            parts.append("")
        text = "\n".join(parts)
        return {"success": True, "transcription_id": transcription_id, "text": text}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ API: Failed to compose transcription text: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get transcription text: {str(e)}")


@router.get("/{dossier_id}/sections/count")
async def get_dossier_section_count(dossier_id: str):
    """
    Get section count statistics for a dossier.

    Args:
        dossier_id: The dossier

    Returns:
        Dictionary with section statistics
    """
    logger.info(f"🔢 API: Getting section count for dossier {dossier_id}")

    try:
        metadata = view_service.get_dossier_metadata(dossier_id)

        if not metadata:
            raise HTTPException(status_code=404, detail=f"Dossier not found: {dossier_id}")

        stats = {
            "dossier_id": dossier_id,
            "total_sections": metadata.get("total_sections", 0),
            "transcription_count": metadata.get("transcription_count", 0),
            "estimated_character_count": metadata.get("estimated_character_count", 0)
        }

        logger.info(f"✅ API: Retrieved section stats for dossier {dossier_id}")
        return {
            "success": True,
            "stats": stats
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ API: Failed to get section count: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get section count: {str(e)}")


@router.get("/transcription/{transcription_id}/images")
async def get_transcription_images(transcription_id: str):
    """
    Get information about images associated with a transcription.

    Args:
        transcription_id: The transcription ID

    Returns:
        Information about available images
    """
    logger.info(f"🖼️ API: Getting image info for transcription {transcription_id}")

    try:
        image_storage = ImageStorageService()
        image_info = image_storage.get_image_info(transcription_id)

        logger.info(f"✅ API: Retrieved image info for transcription {transcription_id}")
        return {
            "success": True,
            "transcription_id": transcription_id,
            "image_info": image_info
        }

    except Exception as e:
        logger.error(f"❌ API: Failed to get image info: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get image info: {str(e)}")


@router.get("/transcription/{transcription_id}/image/{image_type}")
async def get_transcription_image(transcription_id: str, image_type: str):
    """
    Retrieve an image associated with a transcription.

    Args:
        transcription_id: The transcription ID
        image_type: Type of image ("original" or "processed")

    Returns:
        Image file
    """
    logger.info(f"🖼️ API: Retrieving {image_type} image for transcription {transcription_id}")

    if image_type not in ["original", "processed"]:
        raise HTTPException(status_code=400, detail="Image type must be 'original' or 'processed'")

    try:
        image_storage = ImageStorageService()

        if image_type == "original":
            image_path = image_storage.get_original_image_path(transcription_id)
        else:  # processed
            image_path = image_storage.get_processed_image_path(transcription_id)

        if not image_path or not os.path.exists(image_path):
            raise HTTPException(status_code=404, detail=f"{image_type} image not found")

        # Determine content type based on file extension
        file_extension = os.path.splitext(image_path)[1].lower()
        content_types = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".gif": "image/gif",
            ".bmp": "image/bmp",
            ".tiff": "image/tiff"
        }
        content_type = content_types.get(file_extension, "application/octet-stream")

        # Read and return the image
        with open(image_path, "rb") as f:
            image_data = f.read()

        filename = f"{transcription_id}_{image_type}{file_extension}"
        logger.info(f"✅ API: Retrieved {image_type} image for transcription {transcription_id}")

        return Response(
            content=image_data,
            media_type=content_type,
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ API: Failed to retrieve image: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve image: {str(e)}")


@router.get("/images/stats")
async def get_image_storage_stats():
    """
    Get statistics about image storage usage.

    Returns:
        Storage statistics
    """
    logger.info("📊 API: Getting image storage statistics")

    try:
        image_storage = ImageStorageService()
        stats = image_storage.get_storage_stats()

        logger.info("✅ API: Retrieved image storage statistics")
        return {
            "success": True,
            "stats": stats
        }

    except Exception as e:
        logger.error(f"❌ API: Failed to get storage stats: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get storage stats: {str(e)}")


@router.get("/transcription/{transcription_id}/enhancement")
async def get_transcription_enhancement(transcription_id: str):
    """
    Get enhancement information for a transcription.

    Args:
        transcription_id: The transcription ID

    Returns:
        Enhancement information
    """
    logger.info(f"🔧 API: Getting enhancement info for transcription {transcription_id}")

    try:
        view_service = DossierViewService()
        enhancement_info = view_service.get_transcription_enhancement_info(transcription_id)

        if not enhancement_info:
            raise HTTPException(status_code=404, detail=f"Enhancement info not found for transcription {transcription_id}")

        logger.info(f"✅ API: Retrieved enhancement info for transcription {transcription_id}")
        return {
            "success": True,
            "enhancement_info": enhancement_info
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ API: Failed to get enhancement info: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get enhancement info: {str(e)}")


@router.get("/health")
async def dossier_views_health_check():
    """Simple health check for dossier views service"""
    return {"status": "healthy", "service": "dossier-views"}
