"""
Dossier View Service
===================

Handles different content presentation and aggregation modes.
Provides stitched views, individual views, and export functionality.
"""

import json
import logging
from typing import Dict, List, Any, Optional
from pathlib import Path

from config.paths import dossiers_root, dossiers_views_root
from corpus.adapters.dossiers_fs import DossiersFSAdapter
from .models import DossierStructure
from .navigation_service import DossierNavigationService
from .provenance_schema import ProvenanceEnhancement

logger = logging.getLogger(__name__)


class DossierViewService:
    """
    Service for dossier content presentation.
    Handles stitched views, individual transcription views, and exports.

    Coordinates with Navigation service for data access.
    """

    def __init__(self):
        self.navigation_service = DossierNavigationService()
        self._dossiers_adapter = DossiersFSAdapter()
        logger.info("👁️ Dossier View Service initialized")

    def get_stitched_view(self, dossier_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a stitched view of all transcriptions in a dossier.
        Combines all transcriptions into a continuous document.

        Args:
            dossier_id: The dossier to stitch

        Returns:
            Dictionary with stitched content or None if not found
        """
        logger.info(f"🧵 Creating stitched view for dossier: {dossier_id}")

        structure = self.navigation_service.get_dossier_structure(dossier_id)
        if not structure:
            logger.warning(f"⚠️ Cannot create stitched view for non-existent dossier: {dossier_id}")
            return None

        stitched_sections = []
        transcription_count = len(structure.transcriptions)

        for transcription_entry in structure.transcriptions:
            transcription_id = transcription_entry.transcription_id

            # Load the actual transcription content
            transcription_content = self._load_transcription_content(transcription_id)
            if transcription_content:
                sections = transcription_content.get('sections', [])

                # Add position metadata to each section
                for section in sections:
                    section['transcription_id'] = transcription_id
                    section['dossier_position'] = transcription_entry.position

                stitched_sections.extend(sections)
            else:
                logger.warning(f"⚠️ Could not load transcription: {transcription_id}")

        stitched_view = {
            "dossier_id": dossier_id,
            "dossier_title": structure.dossier.title,
            "total_sections": len(stitched_sections),
            "transcription_count": transcription_count,
            "stitched_sections": stitched_sections,
            "generated_at": structure.dossier.updated_at.isoformat()
        }

        logger.info(f"✅ Created stitched view with {len(stitched_sections)} sections")
        return stitched_view

    def get_individual_transcriptions(self, dossier_id: str) -> Optional[List[Dict[str, Any]]]:
        """
        Get individual transcription views for a dossier.
        Each transcription is presented separately.

        Args:
            dossier_id: The dossier

        Returns:
            List of transcription dictionaries or None if dossier not found
        """
        logger.info(f"📄 Getting individual transcriptions for dossier: {dossier_id}")

        structure = self.navigation_service.get_dossier_structure(dossier_id)
        if not structure:
            return None

        transcriptions = []

        for transcription_entry in structure.transcriptions:
            transcription_id = transcription_entry.transcription_id

            # Load transcription content
            content = self._load_transcription_content(transcription_id)
            if content:
                # Add dossier metadata
                content['dossier_position'] = transcription_entry.position
                content['added_to_dossier_at'] = transcription_entry.added_at.isoformat()
                content['dossier_metadata'] = transcription_entry.metadata

                transcriptions.append(content)
            else:
                logger.warning(f"⚠️ Could not load transcription: {transcription_id}")

        logger.info(f"✅ Retrieved {len(transcriptions)} individual transcriptions")
        return transcriptions

    def get_dossier_metadata(self, dossier_id: str) -> Optional[Dict[str, Any]]:
        """
        Get comprehensive metadata about a dossier and its contents.

        Args:
            dossier_id: The dossier

        Returns:
            Dictionary with dossier metadata or None if not found
        """
        logger.info(f"📊 Getting metadata for dossier: {dossier_id}")

        structure = self.navigation_service.get_dossier_structure(dossier_id)
        if not structure:
            return None

        # Calculate various statistics
        transcription_count = len(structure.transcriptions)
        total_sections = 0
        total_characters = 0

        for transcription_entry in structure.transcriptions:
            content = self._load_transcription_content(transcription_entry.transcription_id)
            if content:
                sections = content.get('sections', [])
                total_sections += len(sections)

                # Estimate character count
                for section in sections:
                    body_text = section.get('body', '')
                    total_characters += len(body_text)

        metadata = {
            "dossier_id": structure.dossier.id,
            "title": structure.dossier.title,
            "description": structure.dossier.description,
            "created_at": structure.dossier.created_at.isoformat(),
            "updated_at": structure.dossier.updated_at.isoformat(),
            "transcription_count": transcription_count,
            "total_sections": total_sections,
            "estimated_character_count": total_characters,
            "transcriptions": [
                {
                    "id": t.transcription_id,
                    "position": t.position,
                    "added_at": t.added_at.isoformat(),
                    "metadata": t.metadata
                }
                for t in structure.transcriptions
            ]
        }

        logger.info(f"✅ Retrieved metadata for dossier {dossier_id}")
        return metadata

    def export_dossier(self, dossier_id: str, format_type: str = "json") -> Optional[bytes]:
        """
        Export a dossier in various formats.

        Args:
            dossier_id: The dossier to export
            format_type: Export format ("json", "text", etc.)

        Returns:
            Bytes of exported content or None if failed
        """
        logger.info(f"📤 Exporting dossier {dossier_id} as {format_type}")

        if format_type == "json":
            return self._export_as_json(dossier_id)
        elif format_type == "text":
            return self._export_as_text(dossier_id)
        else:
            logger.error(f"❌ Unsupported export format: {format_type}")
            return None

    def get_transcription_preview(self, transcription_id: str, max_sections: int = 3) -> Optional[Dict[str, Any]]:
        """
        Get a preview of a transcription (first few sections).

        Args:
            transcription_id: The transcription to preview
            max_sections: Maximum sections to include

        Returns:
            Dictionary with preview content or None if not found
        """
        logger.info(f"👀 Creating preview for transcription: {transcription_id}")

        content = self._load_transcription_content(transcription_id)
        if not content:
            return None

        sections = content.get('sections', [])[:max_sections]

        preview = {
            "transcription_id": transcription_id,
            "document_id": content.get('documentId'),
            "total_sections": len(content.get('sections', [])),
            "preview_sections": sections,
            "has_more_sections": len(content.get('sections', [])) > max_sections
        }

        logger.info(f"✅ Created preview with {len(sections)} sections")
        return preview

    def get_transcription_enhancement_info(self, transcription_id: str) -> Optional[Dict[str, Any]]:
        """
        Get enhancement information for a transcription.

        Args:
            transcription_id: The transcription ID

        Returns:
            Enhancement information or None if not found
        """
        logger.info(f"🔧 Getting enhancement info for transcription: {transcription_id}")

        # Load transcription content
        content = self._load_transcription_content(transcription_id)
        if not content:
            return None

        # Look for provenance in the transcription entry metadata
        # We need to check the association service to find the transcription entry
        try:
            from .association_service import TranscriptionAssociationService
            association_service = TranscriptionAssociationService()

            # This is a simplified approach - in a real implementation,
            # we'd need to search through all dossiers or maintain an index
            # For now, we'll return a placeholder structure

            return {
                "transcription_id": transcription_id,
                "enhancement_info": {
                    "settings_available": False,
                    "message": "Enhancement info stored in transcription metadata"
                }
            }

        except Exception as e:
            logger.error(f"❌ Error getting enhancement info: {e}")
            return None

    def _export_as_json(self, dossier_id: str) -> Optional[bytes]:
        """Export dossier as JSON"""
        stitched_view = self.get_stitched_view(dossier_id)
        if not stitched_view:
            return None

        try:
            json_str = json.dumps(stitched_view, indent=2, ensure_ascii=False)
            return json_str.encode('utf-8')
        except Exception as e:
            logger.error(f"❌ JSON export failed: {e}")
            return None

    def _export_as_text(self, dossier_id: str) -> Optional[bytes]:
        """Export dossier as plain text"""
        stitched_view = self.get_stitched_view(dossier_id)
        if not stitched_view:
            return None

        try:
            text_parts = []
            for section in stitched_view.get('stitched_sections', []):
                header = section.get('header', '')
                body = section.get('body', '')

                if header:
                    text_parts.append(f"[{header}]")
                text_parts.append(body)
                text_parts.append("")  # Empty line between sections

            text_content = "\n".join(text_parts)
            return text_content.encode('utf-8')
        except Exception as e:
            logger.error(f"❌ Text export failed: {e}")
            return None

    def _load_transcription_content(self, transcription_id: str) -> Optional[Dict[str, Any]]:
        """
        Load transcription content from canonical dossiers views directory,
        with fallbacks for legacy flat layouts and saved_drafts.
        """
        # New canonical layout: dossiers_data/views/transcriptions/<dossier_id>/<transcription_id>/{raw|consensus}/<file>.json
        # Because we don't always have dossier_id here, search recursively by filename
        transcriptions_root = dossiers_views_root()
        candidates: List[Path] = []

        # Support special consensus draft IDs
        try:
            if transcription_id.endswith("_consensus_llm"):
                base_id = transcription_id[:-len("_consensus_llm")]
                candidates = list(
                    transcriptions_root.rglob(
                        f"**/{base_id}/consensus/llm_{base_id}.json"
                    )
                )
            elif transcription_id.endswith("_consensus_alignment"):
                base_id = transcription_id[:-len("_consensus_alignment")]
                candidates = list(
                    transcriptions_root.rglob(
                        f"**/{base_id}/consensus/alignment_{base_id}.json"
                    )
                )
            elif transcription_id.endswith("_agent_edit"):
                base_id = transcription_id[:-len("_agent_edit")]
                candidates = list(
                    transcriptions_root.rglob(
                        f"**/{base_id}/consensus/agent_edit_{base_id}.json"
                    )
                )
        except Exception:
            candidates = []

        # Standard raw/base file lookup
        if not candidates:
            candidates = list(
                transcriptions_root.rglob(f"**/raw/{transcription_id}.json")
            )
        if not candidates and ("_v" in transcription_id):
            base_id = transcription_id.rsplit("_v", 1)[0]
            candidates = list(transcriptions_root.rglob(f"**/raw/{base_id}.json"))

        transcription_file = candidates[0] if candidates else None

        # Backward-compatible fallbacks (flat and legacy)
        if not transcription_file:
            flat_primary = transcriptions_root / f"{transcription_id}.json"
            if flat_primary.exists():
                transcription_file = flat_primary
        if not transcription_file:
            # Legacy flat layout under backend/dossiers_data/views
            flat_alt = dossiers_root() / "views" / f"{transcription_id}.json"
            if flat_alt.exists():
                transcription_file = flat_alt
        if not transcription_file:
            # Very old saved_drafts compatibility
            backend_dir = Path(__file__).resolve().parents[2]
            legacy_path = backend_dir / "saved_drafts" / f"{transcription_id}.json"
            if legacy_path.exists():
                transcription_file = legacy_path

        if not transcription_file:
            logger.warning(f"📂 Transcription file not found: {transcription_id}")
            return None

        try:
            with open(transcription_file, "r", encoding="utf-8") as f:
                content = json.load(f)
            logger.info(
                f"📄 Loaded transcription (global): id={transcription_id} path={transcription_file}"
            )
            return content
        except Exception as e:
            logger.error(f"❌ Error loading transcription {transcription_id}: {e}")
            return None

    def _load_transcription_content_scoped(self, transcription_id: str, dossier_id: Optional[str]) -> Optional[Dict[str, Any]]:
        """
        Load transcription content, preferring paths within the provided dossier_id.

        This avoids cross-dossier collisions when identical transcription IDs exist across dossiers.

        Delegates path resolution to DossiersFSAdapter.resolve_draft_path() for DRY
        consistency with corpus hydration layer.
        """
        if not dossier_id:
            return self._load_transcription_content(transcription_id)

        try:
            # Use the shared adapter for draft path resolution (DRY with corpus layer)
            resolved_path = self._dossiers_adapter.resolve_draft_path(
                dossier_id,
                transcription_id,
                use_rglob_fallback=False,  # Avoid expensive fallback in hot path
            )

            if resolved_path and resolved_path.exists():
                with open(resolved_path, 'r', encoding='utf-8') as f:
                    content = json.load(f)
                logger.info(
                    f"📄 Loaded transcription (scoped via adapter): "
                    f"dossier={dossier_id} id={transcription_id} path={resolved_path}"
                )
                return content

            logger.info(
                f"ℹ️ Scoped lookup missed, falling back to global search: "
                f"dossier={dossier_id} id={transcription_id}"
            )

        except Exception as e:
            logger.error(f"❌ Scoped load failed for {transcription_id} in dossier {dossier_id}: {e}")

        # Fallback to global search
        return self._load_transcription_content(transcription_id)
