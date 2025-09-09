"""
Dossier Data Models
==================

Clean, focused data models for dossier management.
Follows the same patterns as existing codebase.
"""

from typing import Dict, List, Any, Optional
from datetime import datetime
import uuid


class Dossier:
    """Core dossier entity representing a collection of transcriptions"""

    def __init__(self, title: str, description: str = None, dossier_id: str = None):
        self.id = dossier_id or str(uuid.uuid4())
        self.title = title
        self.description = description or ""
        self.created_at = datetime.now()
        self.updated_at = datetime.now()

        # Hierarchical structure for frontend
        self.segments = []  # Will be populated when dossier is loaded

        # Future consensus integration hook
        self.active_text_source = None  # Will store consensus method when implemented
        # Format: {"type": "alignment"|"llm"|"individual", "id": "consensus_123"|"transcription_456"}

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "active_text_source": self.active_text_source,
            "segments": [segment.to_dict() for segment in self.segments]
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Dossier':
        """Create from dictionary (for JSON deserialization)"""
        dossier = cls(
            title=data["title"],
            description=data.get("description", ""),
            dossier_id=data["id"]
        )
        dossier.created_at = datetime.fromisoformat(data["created_at"])
        dossier.updated_at = datetime.fromisoformat(data["updated_at"])
        dossier.active_text_source = data.get("active_text_source")

        # Load segments if present (will be populated by management service)
        dossier.segments = []
        return dossier

    def set_active_text_source(self, source_type: str, source_id: str) -> None:
        """
        Set the active text source for stitched views.

        Args:
            source_type: "alignment", "llm", "individual"
            source_id: ID of the consensus or transcription
        """
        self.active_text_source = {
            "type": source_type,
            "id": source_id,
            "set_at": datetime.now().isoformat()
        }

    def get_active_text_source(self) -> Optional[Dict[str, Any]]:
        """Get the currently active text source"""
        return self.active_text_source


class Segment:
    """Represents a logical segment of a document (page, section, etc.)"""

    def __init__(self, segment_id: str, name: str = None, description: str = None, position: int = 0):
        self.id = segment_id
        self.name = name or f"Segment {position + 1}"
        self.description = description or ""
        self.position = position
        self.runs = []  # Will be populated with Run objects

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "position": self.position,
            "runs": [run.to_dict() for run in self.runs]
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Segment':
        segment = cls(
            segment_id=data["id"],
            name=data.get("name", ""),
            description=data.get("description", ""),
            position=data.get("position", 0)
        )
        segment.runs = []
        return segment


class Run:
    """Represents a processing run (OCR attempt)"""

    def __init__(self, run_id: str, transcription_id: str, position: int = 0):
        self.id = run_id
        self.position = position
        self.transcription_id = transcription_id
        self.drafts = []  # Will be populated with Draft objects
        self.metadata = {}  # Will be populated with run metadata

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "position": self.position,
            "transcription_id": self.transcription_id,
            "metadata": self.metadata,
            "drafts": [draft.to_dict() for draft in self.drafts]
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Run':
        run = cls(
            run_id=data["id"],
            transcription_id=data.get("transcription_id", ""),
            position=data.get("position", 0)
        )
        run.metadata = data.get("metadata", {})
        run.drafts = []
        return run


class Draft:
    """Represents a transcription draft"""

    def __init__(self, draft_id: str, transcription_id: str, position: int = 0, is_best: bool = False):
        self.id = draft_id
        self.position = position
        self.transcription_id = transcription_id
        self.is_best = is_best

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "position": self.position,
            "transcription_id": self.transcription_id,
            "is_best": self.is_best
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Draft':
        return cls(
            draft_id=data["id"],
            transcription_id=data.get("transcription_id", ""),
            position=data.get("position", 0),
            is_best=data.get("is_best", False)
        )


class TranscriptionEntry:
    """Represents a transcription within a dossier"""

    def __init__(self, transcription_id: str, position: int, metadata: Dict[str, Any] = None):
        self.transcription_id = transcription_id
        self.position = position  # Neutral ordering - just sequence index
        self.added_at = datetime.now()
        self.metadata = metadata or {}

        # Ensure provenance follows standardized schema
        if "provenance" not in self.metadata:
            self.metadata["provenance"] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            "transcription_id": self.transcription_id,
            "position": self.position,
            "added_at": self.added_at.isoformat(),
            "metadata": self.metadata
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TranscriptionEntry':
        """Create from dictionary"""
        entry = cls(
            transcription_id=data["transcription_id"],
            position=data["position"],
            metadata=data.get("metadata", {})
        )
        entry.added_at = datetime.fromisoformat(data["added_at"])
        return entry

    def get_provenance(self) -> Optional[Dict[str, Any]]:
        """Get standardized provenance information"""
        return self.metadata.get("provenance")

    def update_provenance(self, provenance: Dict[str, Any]) -> None:
        """Update provenance using standardized schema"""
        self.metadata["provenance"] = provenance

    def get_quality_score(self) -> Optional[float]:
        """Get confidence score from provenance"""
        provenance = self.get_provenance()
        if provenance and "quality" in provenance:
            return provenance["quality"]["confidence_score"]
        return None


class DossierSummary:
    """Lightweight dossier summary for listings and navigation"""

    def __init__(self, dossier_id: str, title: str, transcription_count: int,
                 created_at: datetime, updated_at: datetime):
        self.dossier_id = dossier_id
        self.title = title
        self.transcription_count = transcription_count
        self.created_at = created_at
        self.updated_at = updated_at

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.dossier_id,
            "title": self.title,
            "transcription_count": self.transcription_count,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat()
        }


class DossierStructure:
    """Complete dossier structure with transcriptions"""

    def __init__(self, dossier: Dossier, transcriptions: List[TranscriptionEntry]):
        self.dossier = dossier
        self.transcriptions = sorted(transcriptions, key=lambda t: t.position)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "dossier": self.dossier.to_dict(),
            "transcriptions": [t.to_dict() for t in self.transcriptions]
        }
