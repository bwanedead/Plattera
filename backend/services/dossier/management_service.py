"""
Dossier Management Service
=========================

Handles core CRUD operations for dossiers themselves.
Focused responsibility: dossier lifecycle management.
"""

import os
import json
import logging
from typing import Dict, List, Any, Optional
from pathlib import Path

from .models import Dossier, DossierSummary

logger = logging.getLogger(__name__)


class DossierManagementService:
    """
    Service for managing dossier lifecycle.
    Handles creation, retrieval, updates, and deletion of dossiers.

    Storage: JSON files in backend/dossiers/management/
    """

    def __init__(self):
        self.storage_dir = Path("backend/dossiers/management")
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        logger.info("📁 Dossier Management Service initialized")

    def create_dossier(self, title: str, description: str = None) -> str:
        """
        Create a new dossier.

        Args:
            title: Human-readable title for the dossier
            description: Optional description

        Returns:
            str: The dossier ID
        """
        logger.info(f"📝 MANAGEMENT SERVICE: Creating new dossier: '{title}'")
        logger.info(f"📝 MANAGEMENT SERVICE: Description: '{description}'")
        logger.info(f"📝 MANAGEMENT SERVICE: Storage dir: {self.storage_dir}")
        logger.info(f"📝 MANAGEMENT SERVICE: Storage dir exists: {self.storage_dir.exists()}")

        dossier = Dossier(title=title, description=description)
        self._save_dossier(dossier)

        logger.info(f"✅ Created dossier: {dossier.id}")
        return dossier.id

    def get_dossier(self, dossier_id: str) -> Optional[Dossier]:
        """
        Retrieve a dossier by ID.

        Args:
            dossier_id: The dossier identifier

        Returns:
            Dossier object or None if not found
        """
        dossier_file = self.storage_dir / f"dossier_{dossier_id}.json"

        if not dossier_file.exists():
            logger.warning(f"📂 Dossier not found: {dossier_id}")
            return None

        try:
            with open(dossier_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            dossier = Dossier.from_dict(data)
            logger.info(f"📖 Retrieved dossier: {dossier_id}")
            return dossier
        except Exception as e:
            logger.error(f"❌ Error reading dossier {dossier_id}: {e}")
            return None

    def update_dossier(self, dossier_id: str, updates: Dict[str, Any]) -> bool:
        """
        Update a dossier with new data.

        Args:
            dossier_id: The dossier to update
            updates: Dictionary of fields to update

        Returns:
            bool: Success status
        """
        logger.info(f"🔄 Updating dossier: {dossier_id}")

        dossier = self.get_dossier(dossier_id)
        if not dossier:
            logger.warning(f"⚠️ Cannot update non-existent dossier: {dossier_id}")
            return False

        # Apply updates
        if 'title' in updates:
            dossier.title = updates['title']
        if 'description' in updates:
            dossier.description = updates['description']

        dossier.updated_at = dossier.updated_at  # This will update the timestamp

        self._save_dossier(dossier)
        logger.info(f"✅ Updated dossier: {dossier_id}")
        return True

    def delete_dossier(self, dossier_id: str) -> bool:
        """
        Delete a dossier.

        Note: This only deletes the dossier metadata.
        Associated transcriptions are preserved.

        Args:
            dossier_id: The dossier to delete

        Returns:
            bool: Success status
        """
        logger.info(f"🗑️ Deleting dossier: {dossier_id}")

        dossier_file = self.storage_dir / f"dossier_{dossier_id}.json"

        if not dossier_file.exists():
            logger.warning(f"⚠️ Cannot delete non-existent dossier: {dossier_id}")
            return False

        try:
            dossier_file.unlink()
            logger.info(f"✅ Deleted dossier: {dossier_id}")
            return True
        except Exception as e:
            logger.error(f"❌ Error deleting dossier {dossier_id}: {e}")
            return False

    def list_dossiers(self, limit: int = 50, offset: int = 0) -> List[DossierSummary]:
        """
        List all dossiers with summary information.

        Args:
            limit: Maximum number of dossiers to return
            offset: Number of dossiers to skip

        Returns:
            List of DossierSummary objects
        """
        logger.info("📋 Listing dossiers")
        logger.info(f"🔍 Looking for dossiers in: {self.storage_dir}")
        logger.info(f"🔍 Storage dir exists: {self.storage_dir.exists()}")

        dossiers = []
        try:
            dossier_files = list(self.storage_dir.glob("dossier_*.json"))
            logger.info(f"📁 Found {len(dossier_files)} dossier files: {[f.name for f in dossier_files]}")

            for file_path in dossier_files:
                try:
                    logger.info(f"📖 Reading dossier file: {file_path}")
                    with open(file_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    dossier = Dossier.from_dict(data)
                    logger.info(f"✅ Loaded dossier: {dossier.id} - {dossier.title}")

                    # Get transcription count (we'll need to query the association service)
                    # For now, return basic info
                    summary = DossierSummary(
                        dossier_id=dossier.id,
                        title=dossier.title,
                        transcription_count=0,  # TODO: Get from association service
                        created_at=dossier.created_at,
                        updated_at=dossier.updated_at
                    )
                    dossiers.append(summary)

                except Exception as e:
                    logger.warning(f"⚠️ Error reading dossier file {file_path}: {e}")
                    continue

            # Sort by updated_at desc and apply pagination
            dossiers.sort(key=lambda d: d.updated_at, reverse=True)
            dossiers = dossiers[offset:offset + limit]

            logger.info(f"📊 Listed {len(dossiers)} dossiers")
            return dossiers

        except Exception as e:
            logger.error(f"❌ Error listing dossiers: {e}")
            return []

    def dossier_exists(self, dossier_id: str) -> bool:
        """
        Check if a dossier exists.

        Args:
            dossier_id: The dossier ID to check

        Returns:
            bool: True if dossier exists
        """
        dossier_file = self.storage_dir / f"dossier_{dossier_id}.json"
        return dossier_file.exists()

    def _save_dossier(self, dossier: Dossier) -> None:
        """Internal method to save dossier to disk"""
        dossier_file = self.storage_dir / f"dossier_{dossier.id}.json"

        logger.info(f"💾 MANAGEMENT SERVICE: Saving dossier to file: {dossier_file}")
        logger.info(f"💾 MANAGEMENT SERVICE: File exists before save: {dossier_file.exists()}")
        logger.info(f"💾 MANAGEMENT SERVICE: Dossier data: {dossier.to_dict()}")

        try:
            with open(dossier_file, 'w', encoding='utf-8') as f:
                json.dump(dossier.to_dict(), f, indent=2, ensure_ascii=False)
            logger.info(f"💾 MANAGEMENT SERVICE: Successfully saved dossier file: {dossier_file}")
            logger.info(f"💾 MANAGEMENT SERVICE: File exists after save: {dossier_file.exists()}")
            logger.info(f"💾 MANAGEMENT SERVICE: File size: {dossier_file.stat().st_size} bytes")
        except Exception as e:
            logger.error(f"❌ Error saving dossier {dossier.id}: {e}")
            logger.error(f"❌ Error details: {type(e).__name__}: {str(e)}")
            raise
