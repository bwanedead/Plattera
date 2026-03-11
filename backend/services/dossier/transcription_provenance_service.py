from __future__ import annotations

import logging
import os
from typing import Any, Dict

from services.dossier.image_storage_service import ImageStorageService
from services.dossier.provenance_schema import ProvenanceEnhancement, ProvenanceSchema

logger = logging.getLogger(__name__)


def create_transcription_provenance(
    file_path: str,
    model: str,
    extraction_mode: str,
    result: Dict[str, Any],
    transcription_id: str | None = None,
    enhancement_settings: Dict[str, Any] | None = None,
    save_images: bool = True,
) -> Dict[str, Any]:
    """Create standardized provenance for a transcription result."""
    try:
        provenance = ProvenanceSchema.create_initial_provenance(
            file_path=file_path,
            processing_engine="openai",
            model=model,
            extraction_mode=extraction_mode,
        )

        if transcription_id:
            provenance["transcription_id"] = transcription_id

        original_image_path = None
        processed_image_path = None

        if save_images and os.path.exists(file_path):
            image_storage = ImageStorageService()
            original_image_path = image_storage.save_original_image(
                image_path=file_path,
                transcription_id=transcription_id,
            )
            processed_image_path = file_path

        if enhancement_settings or original_image_path or processed_image_path:
            provenance = ProvenanceEnhancement.update_provenance_enhancement(
                provenance=provenance,
                enhancement_settings=enhancement_settings or {},
                original_image_path=original_image_path,
                processed_image_path=processed_image_path,
            )

        confidence_score = result.get("confidence_score", 0.0)
        extracted_text = result.get("extracted_text", "")
        text_length = len(extracted_text) if extracted_text else 0

        section_count = 1
        if extracted_text and '"sections"' in extracted_text:
            try:
                if '"sections":' in extracted_text:
                    start = extracted_text.find('"sections":')
                    if start > 0:
                        bracket_start = extracted_text.find("[", start)
                        if bracket_start > 0:
                            bracket_end = extracted_text.find("]", bracket_start)
                            if bracket_end > bracket_start:
                                section_text = extracted_text[bracket_start:bracket_end]
                                section_count = max(1, section_text.count("},{") + 1)
            except Exception:
                pass

        provenance = ProvenanceSchema.update_provenance_quality(
            provenance=provenance,
            confidence_score=confidence_score,
            text_length=text_length,
            section_count=section_count,
        )

        return provenance

    except Exception as exc:
        logger.error("Error creating transcription provenance: %s", exc)
        return {
            "version": "1.0",
            "created_at": ProvenanceSchema.create_initial_provenance(
                file_path=file_path,
                processing_engine="unknown",
                model=model,
                extraction_mode=extraction_mode,
            )["created_at"],
            "error": str(exc),
        }
