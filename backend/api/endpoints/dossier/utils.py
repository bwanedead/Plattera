"""
Dossier Utility Functions
========================

Helper functions for dossier endpoints.
"""

import logging
from pathlib import Path
from typing import Optional, Dict, Any

from services.dossier.provenance_schema import ProvenanceSchema, ProvenanceEnhancement
from services.dossier.image_storage_service import ImageStorageService

logger = logging.getLogger(__name__)


def extract_transcription_id_from_result(result: dict) -> Optional[str]:
    """
    Extract transcription ID from processing result.

    The transcription should have been saved to saved_drafts/ by the pipeline.
    We need to determine the transcription filename from the result.

    Args:
        result: Processing result dictionary

    Returns:
        str: Transcription ID (e.g., "draft_1") or None if not found
    """
    try:
        # Look for transcription ID in metadata
        metadata = result.get("metadata", {})

        # Check if transcription_id is already in metadata
        if "transcription_id" in metadata:
            return metadata["transcription_id"]

        # Try to extract from documentId if present
        extracted_text = result.get("extracted_text", "")
        if extracted_text and '"documentId"' in extracted_text:
            # Try to parse documentId from the JSON response
            try:
                import json
                # This is a simplified extraction - in practice you'd want more robust parsing
                if '"documentId":' in extracted_text:
                    # Extract documentId from JSON-like string
                    start = extracted_text.find('"documentId":') + len('"documentId":')
                    if start > len('"documentId":'):
                        # Find the end of the documentId value
                        end = extracted_text.find(',', start)
                        if end == -1:
                            end = extracted_text.find('}', start)
                        if end > start:
                            doc_id = extracted_text[start:end].strip().strip('"')
                            if doc_id:
                                # Convert documentId to transcription filename format
                                return f"draft_{doc_id}"
            except Exception:
                pass

        # Fallback: Look for most recent file in saved_drafts
        # This is a temporary solution until we can better track transcription IDs
        saved_drafts_dir = Path("backend/saved_drafts")
        if saved_drafts_dir.exists():
            draft_files = list(saved_drafts_dir.glob("draft_*.json"))
            if draft_files:
                # Return the most recently modified file
                most_recent = max(draft_files, key=lambda f: f.stat().st_mtime)
                return most_recent.stem  # filename without extension

        logger.warning("⚠️ Could not determine transcription ID from result")
        return None

    except Exception as e:
        logger.error(f"❌ Error extracting transcription ID: {e}")
        return None


def create_transcription_provenance(
    file_path: str,
    model: str,
    extraction_mode: str,
    result: Dict[str, Any],
    transcription_id: str = None,
    enhancement_settings: Dict[str, Any] = None,
    save_images: bool = True
) -> Dict[str, Any]:
    """
    Create standardized provenance for a transcription result.

    Args:
        file_path: Path to the processed image file
        model: Model used for processing
        extraction_mode: Extraction mode used
        result: Processing result dictionary
        transcription_id: Optional transcription ID
        enhancement_settings: Enhancement settings applied to the image
        save_images: Whether to save original and processed images

    Returns:
        Standardized provenance dictionary
    """
    try:
        # Create initial provenance
        provenance = ProvenanceSchema.create_initial_provenance(
            file_path=file_path,
            processing_engine="openai",  # Assuming OpenAI for now - could be made dynamic
            model=model,
            extraction_mode=extraction_mode
        )

        # Add transcription ID to provenance for tracking
        if transcription_id:
            provenance["transcription_id"] = transcription_id

        # Handle image storage if requested
        original_image_path = None
        processed_image_path = None

        if save_images and os.path.exists(file_path):
            image_storage = ImageStorageService()

            # Save original image
            original_image_path = image_storage.save_original_image(
                image_path=file_path,
                transcription_id=transcription_id
            )

            # Note: processed image would be saved by the image processing pipeline
            # For now, we'll just record the original path as processed path
            processed_image_path = file_path

        # Update provenance with enhancement information
        if enhancement_settings or original_image_path or processed_image_path:
            provenance = ProvenanceEnhancement.update_provenance_enhancement(
                provenance=provenance,
                enhancement_settings=enhancement_settings or {},
                original_image_path=original_image_path,
                processed_image_path=processed_image_path
            )

        # Update quality metrics from result
        confidence_score = result.get("confidence_score", 0.0)

        # Estimate text length and section count
        extracted_text = result.get("extracted_text", "")
        text_length = len(extracted_text) if extracted_text else 0

        # Try to parse section count from JSON if available
        section_count = 1  # Default
        if extracted_text and '"sections"' in extracted_text:
            try:
                import json
                # Simple parsing - could be made more robust
                if '"sections":' in extracted_text:
                    start = extracted_text.find('"sections":')
                    if start > 0:
                        # Look for array start
                        bracket_start = extracted_text.find('[', start)
                        if bracket_start > 0:
                            # Count commas in array (rough estimate)
                            bracket_end = extracted_text.find(']', bracket_start)
                            if bracket_end > bracket_start:
                                section_text = extracted_text[bracket_start:bracket_end]
                                section_count = max(1, section_text.count('},{') + 1)
            except Exception:
                pass

        # Update provenance with quality metrics
        provenance = ProvenanceSchema.update_provenance_quality(
            provenance=provenance,
            confidence_score=confidence_score,
            text_length=text_length,
            section_count=section_count
        )

        return provenance

    except Exception as e:
        logger.error(f"❌ Error creating transcription provenance: {e}")
        # Return minimal provenance on error
        return {
            "version": "1.0",
            "created_at": ProvenanceSchema.create_initial_provenance(
                file_path=file_path,
                processing_engine="unknown",
                model=model,
                extraction_mode=extraction_mode
            )["created_at"],
            "error": str(e)
        }
