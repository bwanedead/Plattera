"""
Dossier Utility Functions
========================

Helper functions for dossier endpoints.
"""

import logging
from pathlib import Path
from typing import Optional, Dict, Any

from services.dossier.provenance_schema import ProvenanceSchema
from services.dossier.transcription_provenance_service import create_transcription_provenance
from config.paths import dossiers_views_root

logger = logging.getLogger(__name__)

# Compatibility re-export for endpoint modules that still import from dossier_utils.
__all__ = ["extract_transcription_id_from_result", "create_transcription_provenance"]


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
        logger.info(f"🔍 Extracting transcription ID from result: {type(result)}")
        logger.info(f"🔍 Result keys: {list(result.keys()) if isinstance(result, dict) else 'Not a dict'}")
        
        # Look for transcription ID in metadata
        metadata = result.get("metadata", {})
        logger.info(f"🔍 Result metadata: {metadata}")

        # Check if transcription_id is already in metadata
        if "transcription_id" in metadata:
            transcription_id = metadata["transcription_id"]
            logger.info(f"✅ Found transcription_id in metadata: {transcription_id}")
            return transcription_id

        # Try to extract from documentId if present
        extracted_text = result.get("extracted_text", "")
        logger.info(f"🔍 Extracted text length: {len(extracted_text) if extracted_text else 0}")
        
        if extracted_text and '"documentId"' in extracted_text:
            # Try to parse documentId from the JSON response
            try:
                import json
                logger.info("🔍 Attempting to parse documentId from extracted_text")
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
                                logger.info(f"✅ Extracted documentId: {doc_id}")
                                return f"draft_{doc_id}"
            except Exception as parse_error:
                logger.warning(f"⚠️ Failed to parse documentId: {parse_error}")

        # Fallback: Look in dossiers_data/views/transcriptions for most recent draft
        BACKEND_DIR = Path(__file__).resolve().parents[3]
        primary_dir = dossiers_views_root()
        legacy_dir = BACKEND_DIR / "saved_drafts"
        for probe in [primary_dir, legacy_dir]:
            logger.info(f"🔍 Checking drafts directory: {probe}")
            if probe.exists():
                draft_files = list(probe.glob("*.json"))
                logger.info(f"🔍 Found {len(draft_files)} draft files: {[f.name for f in draft_files]}")
                if draft_files:
                    most_recent = max(draft_files, key=lambda f: f.stat().st_mtime)
                    return most_recent.stem

        logger.warning("⚠️ Could not determine transcription ID from result")
        return None

    except Exception as e:
        logger.error(f"❌ Error extracting transcription ID: {e}")
        logger.error(f"❌ Exception type: {type(e).__name__}")
        import traceback
        logger.error(f"❌ Traceback: {traceback.format_exc()}")
        return None


