"""
Provenance Schema for Dossier System
===================================

Standardized metadata schema for tracking transcription provenance.
Ensures consistent tracking of processing history, engines, models, and data integrity.

This schema is embedded in TranscriptionEntry.metadata and provides
context for reruns, consensus, and audit trails.
"""

from typing import Dict, Any, Optional, List
from datetime import datetime
import hashlib
import os


class ProvenanceSchema:
    """
    Standardized provenance schema for transcription metadata.
    Provides consistent structure for tracking processing history and data integrity.
    """

    @staticmethod
    def create_initial_provenance(
        file_path: str,
        processing_engine: str,
        model: str,
        extraction_mode: str,
        image_hash: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Create initial provenance record for a new transcription.

        Args:
            file_path: Path to the source image file
            processing_engine: Engine used (e.g., "openai", "ocr", "llm")
            model: Specific model used (e.g., "gpt-4o", "tesseract")
            extraction_mode: Extraction mode (e.g., "legal_document_json")
            image_hash: SHA256 hash of source image (auto-generated if None)
            **kwargs: Additional provenance fields

        Returns:
            Complete provenance dictionary
        """
        # Generate image hash if not provided
        if image_hash is None and os.path.exists(file_path):
            image_hash = ProvenanceSchema._calculate_file_hash(file_path)

        return {
            "version": "1.0",
            "created_at": datetime.now().isoformat(),
            "source": {
                "file_path": file_path,
                "file_hash": image_hash,
                "file_size_bytes": os.path.getsize(file_path) if os.path.exists(file_path) else None,
                "modified_time": datetime.fromtimestamp(os.path.getmtime(file_path)).isoformat() if os.path.exists(file_path) else None
            },
            "processing": {
                "engine": processing_engine,
                "model": model,
                "extraction_mode": extraction_mode,
                "processing_date": datetime.now().isoformat()
            },
        "quality": {
            "confidence_score": None,  # Will be filled by processing
            "text_length": None,
            "section_count": None,
            "estimated_accuracy": None
        },
        "enhancement": {
            "settings_applied": None,  # Enhancement parameters used
            "original_image_path": None,  # Path to saved original image
            "processed_image_path": None,  # Path to processed/enhanced image
            "enhancement_hash": None  # Hash of enhancement settings
        },
            "lineage": {
                "parent_transcription_id": None,  # For reruns of same segment
                "generation": 1,  # Increment on reruns
                "derived_from": []  # List of source transcription IDs
            },
            "metadata": kwargs  # Additional custom fields
        }

    @staticmethod
    def update_provenance_quality(
        provenance: Dict[str, Any],
        confidence_score: float,
        text_length: int,
        section_count: int
    ) -> Dict[str, Any]:
        """
        Update quality metrics in provenance record.

        Args:
            provenance: Existing provenance dictionary
            confidence_score: Processing confidence (0.0-1.0)
            text_length: Character count of extracted text
            section_count: Number of sections extracted

        Returns:
            Updated provenance dictionary
        """
        provenance_copy = provenance.copy()
        provenance_copy["quality"] = {
            "confidence_score": confidence_score,
            "text_length": text_length,
            "section_count": section_count,
            "estimated_accuracy": ProvenanceSchema._estimate_accuracy(confidence_score)
        }
        return provenance_copy

    @staticmethod
    def create_rerun_provenance(
        original_provenance: Dict[str, Any],
        new_file_path: str,
        new_processing_engine: str,
        new_model: str,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Create provenance for a rerun of an existing transcription.

        Args:
            original_provenance: Provenance from original transcription
            new_file_path: Path to new source file
            new_processing_engine: New processing engine
            new_model: New model used
            **kwargs: Additional provenance fields

        Returns:
            New provenance record for rerun
        """
        # Generate new image hash
        new_image_hash = ProvenanceSchema._calculate_file_hash(new_file_path)

        new_provenance = {
            "version": "1.0",
            "created_at": datetime.now().isoformat(),
            "source": {
                "file_path": new_file_path,
                "file_hash": new_image_hash,
                "file_size_bytes": os.path.getsize(new_file_path) if os.path.exists(new_file_path) else None,
                "modified_time": datetime.fromtimestamp(os.path.getmtime(new_file_path)).isoformat() if os.path.exists(new_file_path) else None
            },
            "processing": {
                "engine": new_processing_engine,
                "model": new_model,
                "extraction_mode": original_provenance["processing"]["extraction_mode"],
                "processing_date": datetime.now().isoformat()
            },
            "quality": {
                "confidence_score": None,
                "text_length": None,
                "section_count": None,
                "estimated_accuracy": None
            },
            "lineage": {
                "parent_transcription_id": original_provenance.get("transcription_id"),
                "generation": original_provenance["lineage"]["generation"] + 1,
                "derived_from": [original_provenance.get("transcription_id")]
            },
            "metadata": kwargs
        }

        return new_provenance

    @staticmethod
    def validate_provenance(provenance: Dict[str, Any]) -> bool:
        """
        Validate that a provenance record has required fields.

        Args:
            provenance: Provenance dictionary to validate

        Returns:
            True if valid, False otherwise
        """
        required_fields = ["version", "created_at", "source", "processing", "quality", "lineage"]

        for field in required_fields:
            if field not in provenance:
                return False

        # Check source fields
        source_required = ["file_path", "file_hash"]
        for field in source_required:
            if field not in provenance["source"]:
                return False

        # Check processing fields
        processing_required = ["engine", "model", "extraction_mode", "processing_date"]
        for field in processing_required:
            if field not in provenance["processing"]:
                return False

        return True

    @staticmethod
    def get_provenance_summary(provenance: Dict[str, Any]) -> Dict[str, Any]:
        """
        Get a human-readable summary of provenance information.

        Args:
            provenance: Provenance dictionary

        Returns:
            Summary dictionary with key information
        """
        return {
            "engine": provenance["processing"]["engine"],
            "model": provenance["processing"]["model"],
            "confidence": provenance["quality"]["confidence_score"],
            "processed_at": provenance["processing"]["processing_date"],
            "generation": provenance["lineage"]["generation"],
            "file_hash": provenance["source"]["file_hash"][:8] + "..." if provenance["source"]["file_hash"] else None
        }

    @staticmethod
    def _calculate_file_hash(file_path: str) -> str:
        """Calculate SHA256 hash of a file."""
        hash_sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_sha256.update(chunk)
        return hash_sha256.hexdigest()

    @staticmethod
    def _estimate_accuracy(confidence_score: float) -> str:
        """Estimate text accuracy based on confidence score."""
        if confidence_score >= 0.95:
            return "high"
        elif confidence_score >= 0.85:
            return "medium"
        elif confidence_score >= 0.70:
            return "low"
        else:
            return "very_low"


# Example usage and schemas
PROVENANCE_EXAMPLES = {
    "initial_transcription": {
        "version": "1.0",
        "created_at": "2024-01-15T10:30:00Z",
        "source": {
            "file_path": "/uploads/deed_page1.jpg",
            "file_hash": "a665a45920422f9d417e4867efdc4fb8a04a1f3fff1fa07e998e86f7f7a27ae3",
            "file_size_bytes": 2457600,
            "modified_time": "2024-01-15T10:25:00Z"
        },
        "processing": {
            "engine": "openai",
            "model": "gpt-4o",
            "extraction_mode": "legal_document_json",
            "processing_date": "2024-01-15T10:30:15Z"
        },
        "quality": {
            "confidence_score": 0.92,
            "text_length": 2847,
            "section_count": 4,
            "estimated_accuracy": "high"
        },
        "lineage": {
            "parent_transcription_id": None,
            "generation": 1,
            "derived_from": []
        },
        "metadata": {
            "page_number": 1,
            "page_side": "left",
            "document_type": "deed"
        }
    },

    "rerun_transcription": {
        "version": "1.0",
        "created_at": "2024-01-15T14:20:00Z",
        "source": {
            "file_path": "/uploads/deed_page1_enhanced.jpg",
            "file_hash": "b775b55930432g9e518f5978fgdc5gc9b05b2g4ggg2gb08f998f97g8g38bf4",
            "file_size_bytes": 2457600,
            "modified_time": "2024-01-15T14:15:00Z"
        },
        "processing": {
            "engine": "openai",
            "model": "o4-mini",
            "extraction_mode": "legal_document_json",
            "processing_date": "2024-01-15T14:20:25Z"
        },
        "quality": {
            "confidence_score": 0.88,
            "text_length": 2912,
            "section_count": 4,
            "estimated_accuracy": "medium"
        },
        "lineage": {
            "parent_transcription_id": "draft_1",
            "generation": 2,
            "derived_from": ["draft_1"]
        },
        "metadata": {
            "enhancement_applied": "contrast_boost",
            "rerun_reason": "improve_accuracy"
        }
    }
}


# Enhancement Methods
class ProvenanceEnhancement:
    """Methods for handling image enhancement provenance"""

    @staticmethod
    def update_provenance_enhancement(
        provenance: Dict[str, Any],
        enhancement_settings: Dict[str, Any],
        original_image_path: str = None,
        processed_image_path: str = None
    ) -> Dict[str, Any]:
        """
        Update enhancement information in provenance record.

        Args:
            provenance: Existing provenance dictionary
            enhancement_settings: Dictionary of enhancement parameters applied
            original_image_path: Path where original image is stored
            processed_image_path: Path where processed image is stored

        Returns:
            Updated provenance dictionary
        """
        provenance_copy = provenance.copy()

        # Create hash of enhancement settings for change detection
        import json
        settings_str = json.dumps(enhancement_settings, sort_keys=True)
        settings_hash = ProvenanceSchema._calculate_string_hash(settings_str)

        provenance_copy["enhancement"] = {
            "settings_applied": enhancement_settings,
            "original_image_path": original_image_path,
            "processed_image_path": processed_image_path,
            "enhancement_hash": settings_hash,
            "settings_summary": ProvenanceEnhancement._summarize_enhancement_settings(enhancement_settings)
        }

        return provenance_copy

    @staticmethod
    def _summarize_enhancement_settings(settings: Dict[str, Any]) -> str:
        """Create a human-readable summary of enhancement settings."""
        if not settings:
            return "No enhancement applied"

        parts = []
        for key, value in settings.items():
            if isinstance(value, float):
                parts.append(f"{key}={value:.1f}")
            else:
                parts.append(f"{key}={value}")

        return ", ".join(parts)

    @staticmethod
    def get_enhancement_summary(provenance: Dict[str, Any]) -> Dict[str, Any]:
        """Get enhancement information from provenance."""
        enhancement = provenance.get("enhancement", {})

        return {
            "settings_applied": enhancement.get("settings_applied", {}),
            "original_image_path": enhancement.get("original_image_path"),
            "processed_image_path": enhancement.get("processed_image_path"),
            "enhancement_hash": enhancement.get("enhancement_hash"),
            "settings_summary": enhancement.get("settings_summary", "No enhancement applied")
        }
