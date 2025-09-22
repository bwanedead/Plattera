"""
Transcription Association Service
================================

Handles relationships between transcriptions and dossiers.
Manages adding, removing, and reordering transcriptions within dossiers.
"""

import json
import logging
from typing import Dict, List, Any, Optional
from pathlib import Path

from .models import TranscriptionEntry

logger = logging.getLogger(__name__)


class TranscriptionAssociationService:
    """
    Service for managing transcription-to-dossier associations.
    Handles the relationship metadata between transcriptions and dossiers.

    Storage: JSON files in backend/dossiers/associations/
    """

    def __init__(self):
        BACKEND_DIR = Path(__file__).resolve().parents[2]
        self.storage_dir = BACKEND_DIR / "dossiers_data/associations"
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        # Reduce log noise: initialization can happen frequently during refreshes
        logger.debug("TranscriptionAssociationService initialized")

    def add_transcription(self, dossier_id: str, transcription_id: str,
                         position: int = None, metadata: Dict[str, Any] = None) -> bool:
        """
        Add a transcription to a dossier.

        Args:
            dossier_id: The dossier to add to
            transcription_id: The transcription to add
            position: Position in the dossier (auto-assigned if None)
            metadata: Additional metadata about the association

        Returns:
            bool: Success status
        """
        logger.info(f"ASSOC_ADD dossier={dossier_id} transcription={transcription_id} pos={position}")

        # Check if transcription already exists in dossier
        if self.transcription_exists_in_dossier(dossier_id, transcription_id):
            logger.warning(f"⚠️ Transcription {transcription_id} already in dossier {dossier_id}")
            return False

        # Get current associations
        associations = self._load_associations(dossier_id)

        # Auto-assign position if not provided
        if position is None:
            position = len(associations) + 1

        # Create new association
        entry = TranscriptionEntry(
            transcription_id=transcription_id,
            position=position,
            metadata=metadata or {}
        )

        associations.append(entry)

        # Save updated associations
        self._save_associations(dossier_id, associations)

        logger.info(f"ASSOC_ADDED dossier={dossier_id} transcription={transcription_id}")
        return True

    def remove_transcription(self, dossier_id: str, transcription_id: str) -> bool:
        """
        Remove a transcription from a dossier.

        Args:
            dossier_id: The dossier to remove from
            transcription_id: The transcription to remove

        Returns:
            bool: Success status
        """
        logger.info(f"➖ Removing transcription {transcription_id} from dossier {dossier_id}")

        associations = self._load_associations(dossier_id)

        # Find and remove the transcription
        original_length = len(associations)
        associations = [a for a in associations if a.transcription_id != transcription_id]

        if len(associations) == original_length:
            logger.warning(f"⚠️ Transcription {transcription_id} not found in dossier {dossier_id}")
            return False

        # Save updated associations
        self._save_associations(dossier_id, associations)

        logger.info(f"✅ Removed transcription {transcription_id} from dossier {dossier_id}")
        return True

    def reorder_transcriptions(self, dossier_id: str, transcription_ids: List[str]) -> bool:
        """
        Reorder transcriptions within a dossier.

        Args:
            dossier_id: The dossier to reorder
            transcription_ids: New order of transcription IDs

        Returns:
            bool: Success status
        """
        logger.info(f"🔄 Reordering transcriptions in dossier {dossier_id}")

        associations = self._load_associations(dossier_id)

        # Validate that all provided transcription IDs exist in the dossier
        existing_ids = {a.transcription_id for a in associations}
        provided_ids = set(transcription_ids)

        if provided_ids != existing_ids:
            missing = existing_ids - provided_ids
            extra = provided_ids - existing_ids
            logger.error(f"❌ Reorder validation failed. Missing: {missing}, Extra: {extra}")
            return False

        # Create new associations with updated positions
        new_associations = []
        for position, transcription_id in enumerate(transcription_ids, 1):
            # Find existing association
            existing = next(a for a in associations if a.transcription_id == transcription_id)
            # Create new entry with updated position
            new_entry = TranscriptionEntry(
                transcription_id=transcription_id,
                position=position,
                metadata=existing.metadata
            )
            new_entry.added_at = existing.added_at
            new_associations.append(new_entry)

        # Save reordered associations
        self._save_associations(dossier_id, new_associations)

        logger.info(f"✅ Reordered transcriptions in dossier {dossier_id}")
        return True

    def get_dossier_transcriptions(self, dossier_id: str) -> List[TranscriptionEntry]:
        """
        Get all transcriptions in a dossier, ordered by position.

        Args:
            dossier_id: The dossier to query

        Returns:
            List of TranscriptionEntry objects, ordered by position
        """
        associations = self._load_associations(dossier_id)
        return sorted(associations, key=lambda a: a.position)

    def get_transcription_position(self, dossier_id: str, transcription_id: str) -> Optional[int]:
        """
        Get the position of a transcription within a dossier.

        Args:
            dossier_id: The dossier
            transcription_id: The transcription

        Returns:
            Position number or None if not found
        """
        associations = self._load_associations(dossier_id)
        for association in associations:
            if association.transcription_id == transcription_id:
                return association.position
        return None

    def transcription_exists_in_dossier(self, dossier_id: str, transcription_id: str) -> bool:
        """
        Check if a transcription exists in a dossier.

        Args:
            dossier_id: The dossier
            transcription_id: The transcription

        Returns:
            bool: True if transcription exists in dossier
        """
        associations = self._load_associations(dossier_id)
        return any(a.transcription_id == transcription_id for a in associations)

    def get_transcription_count(self, dossier_id: str) -> int:
        """
        Get the number of transcriptions in a dossier.

        Args:
            dossier_id: The dossier

        Returns:
            int: Number of transcriptions
        """
        associations = self._load_associations(dossier_id)
        return len(associations)

    def update_transcription_metadata(self, dossier_id: str, transcription_id: str,
                                    metadata: Dict[str, Any]) -> bool:
        """
        Update metadata for a transcription association.

        Args:
            dossier_id: The dossier
            transcription_id: The transcription
            metadata: New metadata to merge

        Returns:
            bool: Success status
        """
        logger.info(f"🔄 Updating metadata for {transcription_id} in dossier {dossier_id}")

        associations = self._load_associations(dossier_id)

        # Find and update the transcription
        for association in associations:
            if association.transcription_id == transcription_id:
                association.metadata.update(metadata)
                break
        else:
            logger.warning(f"⚠️ Transcription {transcription_id} not found in dossier {dossier_id}")
            return False

        # Save updated associations
        self._save_associations(dossier_id, associations)

        logger.info(f"✅ Updated metadata for {transcription_id} in dossier {dossier_id}")
        return True

    def _load_associations(self, dossier_id: str) -> List[TranscriptionEntry]:
        """Load associations for a dossier from disk"""
        associations_file = self.storage_dir / f"assoc_{dossier_id}.json"

        if not associations_file.exists():
            return []

        try:
            with open(associations_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            associations = []
            for item in data.get('associations', []):
                associations.append(TranscriptionEntry.from_dict(item))

            return associations

        except Exception as e:
            logger.error(f"❌ Error loading associations for {dossier_id}: {e}")
            return []

    def _save_associations(self, dossier_id: str, associations: List[TranscriptionEntry]) -> None:
        """Save associations for a dossier to disk"""
        associations_file = self.storage_dir / f"assoc_{dossier_id}.json"

        try:
            data = {
                'dossier_id': dossier_id,
                'associations': [a.to_dict() for a in associations]
            }

            with open(associations_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

            logger.debug(f"💾 Saved associations for dossier: {dossier_id}")

        except Exception as e:
            logger.error(f"❌ Error saving associations for {dossier_id}: {e}")
            raise
