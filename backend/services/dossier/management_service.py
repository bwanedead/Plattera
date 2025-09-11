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
from datetime import datetime

from .models import Dossier, DossierSummary

logger = logging.getLogger(__name__)


class DossierManagementService:
    """
    Service for managing dossier lifecycle.
    Handles creation, retrieval, updates, and deletion of dossiers.

    Storage: JSON files in backend/dossiers/management/
    """

    def __init__(self):
        BACKEND_DIR = Path(__file__).resolve().parents[2]
        self.storage_dir = BACKEND_DIR / "dossiers/management"
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
        Retrieve a dossier by ID with populated segments/runs/drafts.

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

            # Populate segments, runs, and drafts from associations
            self._populate_dossier_hierarchy(dossier)

            logger.info(f"📖 Retrieved dossier: {dossier_id} with {len(dossier.segments)} segments")
            return dossier
        except Exception as e:
            logger.error(f"❌ Error reading dossier {dossier_id}: {e}")
            return None

    def _populate_dossier_hierarchy(self, dossier: Dossier) -> None:
        """
        Populate the dossier's segments, runs, and drafts from transcription associations.
        Applies overrides to auto segments and preserves manual segments.

        Args:
            dossier: The dossier to populate
        """
        from .association_service import TranscriptionAssociationService
        from .models import Segment, Run, Draft

        association_service = TranscriptionAssociationService()
        transcriptions = association_service.get_dossier_transcriptions(dossier.id)

        if not transcriptions:
            logger.debug(f"📄 No transcriptions found for dossier {dossier.id}")
            return

        # Start with manual segments already loaded in dossier.segments

        # Group transcriptions by segment (for now, each transcription = one segment)
        for transcription in transcriptions:
            # Create stable segment ID based on transcription_id
            segment_id = f"segment_auto_{transcription.transcription_id}"
            segment = Segment(
                segment_id=segment_id,
                name=f"Segment {len(dossier.segments) + 1}",
                description=f"Auto-generated segment for transcription {transcription.transcription_id}",
                position=len(dossier.segments)
            )

            # Apply override if exists
            if segment_id in dossier.segment_name_overrides:
                segment.name = dossier.segment_name_overrides[segment_id]

            # Create run
            run_id = f"run_{transcription.transcription_id}"
            run = Run(
                run_id=run_id,
                transcription_id=transcription.transcription_id,
                position=0
            )
            # Add metadata for frontend compatibility
            run.metadata = {
                'createdAt': transcription.added_at.isoformat(),
                'totalSizeBytes': 0,  # TODO: Calculate from drafts
                'lastActivity': transcription.added_at.isoformat()
            }

            # Determine how many drafts were produced for this run
            processing_params = (transcription.metadata or {}).get('processing_params', {})
            try:
                redundancy_count = int(processing_params.get('redundancy_count') or 1)
            except Exception:
                redundancy_count = 1

            # Build drafts list: Draft 1..N (first marked as best for now)
            run.drafts = []
            for i in range(max(1, redundancy_count)):
                draft_id = f"{transcription.transcription_id}_v{i+1}"
                draft = Draft(
                    draft_id=draft_id,
                    transcription_id=transcription.transcription_id,
                    position=i,
                    is_best=(i == 0)
                )
                # Minimal metadata placeholders; can be enriched later from provenance
                draft.metadata = {
                    'sizeBytes': 0,
                    'quality': 'unknown',
                    'confidence': 0
                }
                run.drafts.append(draft)

            # Build hierarchy
            segment.runs.append(run)
            dossier.segments.append(segment)

        logger.debug(f"🏗️ Populated dossier {dossier.id} with {len(dossier.segments)} segments")

    # -----------------------------
    # Segment management operations
    # -----------------------------

    def add_segment(self, dossier_id: str, name: str) -> Optional[Dict[str, Any]]:
        """Create a new manual segment in a dossier and persist it."""
        dossier = self.get_dossier(dossier_id)
        if not dossier:
            logger.warning(f"⚠️ Cannot add segment; dossier not found: {dossier_id}")
            return None

        # Generate a stable manual segment id
        segment_index = len(dossier.manual_segments) + len(dossier.segment_name_overrides)
        segment_id = f"segment_manual_{segment_index}_{dossier_id[:8]}"

        from .models import Segment
        segment = Segment(segment_id=segment_id, name=name or f"Manual Segment {segment_index + 1}", position=segment_index)

        # Add to manual segments and persist
        dossier.manual_segments.append(segment.to_dict())
        dossier.segments.append(segment)  # Also add to runtime segments

        # Persist by saving dossier back to disk
        self._save_dossier(dossier)
        logger.info(f"✅ Added manual segment '{segment.name}' to dossier {dossier_id}")
        return segment.to_dict()

    def update_segment_by_id(self, segment_id: str, name: str) -> bool:
        """Update a segment's name by scanning dossiers for the segment id."""
        try:
            dossier_files = list(self.storage_dir.glob("dossier_*.json"))
            for file_path in dossier_files:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                # Check manual segments first
                manual_segments = data.get('manual_segments', [])
                updated = False
                for seg in manual_segments:
                    if seg.get('id') == segment_id:
                        seg['name'] = name
                        updated = True
                        break

                # If not in manual segments, check if it's an auto segment and use overrides
                if not updated and segment_id.startswith('segment_auto_'):
                    segment_name_overrides = data.get('segment_name_overrides', {})
                    segment_name_overrides[segment_id] = name
                    data['segment_name_overrides'] = segment_name_overrides
                    updated = True

                if updated:
                    # Save file and return
                    with open(file_path, 'w', encoding='utf-8') as f:
                        json.dump(data, f, indent=2, ensure_ascii=False)
                    logger.info(f"✅ Updated segment {segment_id} name to '{name}' in {file_path.name}")
                    return True

            logger.warning(f"⚠️ Segment id not found for update: {segment_id}")
            return False
        except Exception as e:
            logger.error(f"❌ Failed to update segment {segment_id}: {e}")
            return False

    def update_dossier(self, dossier_id: str, updates: Dict[str, Any]) -> Optional[Dossier]:
        """
        Update a dossier with new data.

        Args:
            dossier_id: The dossier to update
            updates: Dictionary of fields to update

        Returns:
            Dossier: Updated dossier object or None if not found
        """
        logger.info(f"🔄 Updating dossier: {dossier_id}")

        dossier = self.get_dossier(dossier_id)
        if not dossier:
            logger.warning(f"⚠️ Cannot update non-existent dossier: {dossier_id}")
            return None

        # Apply updates
        if 'title' in updates:
            dossier.title = updates['title']
            logger.info(f"🔄 Applied title update: '{dossier.title}'")
        if 'description' in updates:
            dossier.description = updates['description']
            logger.info(f"🔄 Applied description update: '{dossier.description}'")

        dossier.updated_at = datetime.now()  # Update timestamp explicitly
        logger.info(f"🔄 Updated timestamp to: {dossier.updated_at}")

        self._save_dossier(dossier)
        logger.info(f"✅ Updated dossier: {dossier_id}")
        return dossier

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

    def list_dossiers(self, limit: int = 50, offset: int = 0) -> List[Dossier]:
        """
        List all dossiers with populated hierarchy.

        Args:
            limit: Maximum number of dossiers to return
            offset: Number of dossiers to skip

        Returns:
            List of full Dossier objects with populated segments/runs/drafts
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

                    # Populate segments, runs, and drafts from associations
                    self._populate_dossier_hierarchy(dossier)

                    logger.info(f"✅ Loaded dossier: {dossier.id} - {dossier.title} with {len(dossier.segments)} segments")
                    dossiers.append(dossier)

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
