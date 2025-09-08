"""
Dossier Navigation Service
=========================

Handles discovery, search, and navigation features for dossiers.
Provides ways to find and explore dossier collections.
"""

import logging
from typing import Dict, List, Any, Optional
from pathlib import Path

from .models import DossierSummary, DossierStructure
from .management_service import DossierManagementService
from .association_service import TranscriptionAssociationService

logger = logging.getLogger(__name__)


class DossierNavigationService:
    """
    Service for dossier discovery and navigation.
    Provides search, filtering, and structural navigation features.

    Coordinates with Management and Association services.
    """

    def __init__(self):
        self.management_service = DossierManagementService()
        self.association_service = TranscriptionAssociationService()
        logger.info("🧭 Dossier Navigation Service initialized")

    def get_recent_dossiers(self, limit: int = 10) -> List[DossierSummary]:
        """
        Get recently updated dossiers.

        Args:
            limit: Maximum number of dossiers to return

        Returns:
            List of DossierSummary objects
        """
        logger.info(f"🕐 Getting {limit} recent dossiers")

        dossiers = self.management_service.list_dossiers(limit=limit, offset=0)

        # Enhance with transcription counts
        for dossier in dossiers:
            dossier.transcription_count = self.association_service.get_transcription_count(
                dossier.dossier_id
            )

        logger.info(f"📊 Retrieved {len(dossiers)} recent dossiers")
        return dossiers

    def search_dossiers(self, query: str = None, filters: Dict[str, Any] = None,
                       limit: int = 50, offset: int = 0) -> List[DossierSummary]:
        """
        Search dossiers by title, description, or other criteria.

        Args:
            query: Search query string
            filters: Additional filters (e.g., {"has_transcriptions": True})
            limit: Maximum results to return
            offset: Pagination offset

        Returns:
            List of matching DossierSummary objects
        """
        logger.info(f"🔍 Searching dossiers with query: '{query}'")

        all_dossiers = self.management_service.list_dossiers(limit=1000, offset=0)
        filtered_dossiers = []

        for dossier in all_dossiers:
            # Text search
            if query:
                searchable_text = f"{dossier.title} {dossier.description}".lower()
                if query.lower() not in searchable_text:
                    continue

            # Apply filters
            if filters:
                if filters.get("has_transcriptions") and dossier.transcription_count == 0:
                    continue
                if filters.get("min_transcriptions"):
                    min_count = filters["min_transcriptions"]
                    if dossier.transcription_count < min_count:
                        continue

            filtered_dossiers.append(dossier)

        # Apply pagination
        filtered_dossiers = filtered_dossiers[offset:offset + limit]

        logger.info(f"📊 Search returned {len(filtered_dossiers)} dossiers")
        return filtered_dossiers

    def get_dossier_structure(self, dossier_id: str) -> Optional[DossierStructure]:
        """
        Get complete dossier structure with transcriptions.

        Args:
            dossier_id: The dossier to examine

        Returns:
            DossierStructure or None if not found
        """
        logger.info(f"🏗️ Getting structure for dossier: {dossier_id}")

        # Get dossier metadata
        dossier = self.management_service.get_dossier(dossier_id)
        if not dossier:
            logger.warning(f"⚠️ Dossier not found: {dossier_id}")
            return None

        # Get associated transcriptions
        transcriptions = self.association_service.get_dossier_transcriptions(dossier_id)

        structure = DossierStructure(dossier=dossier, transcriptions=transcriptions)

        logger.info(f"✅ Retrieved structure for dossier {dossier_id} with {len(transcriptions)} transcriptions")
        return structure

    def get_dossier_summary(self, dossier_id: str) -> Optional[DossierSummary]:
        """
        Get summary information for a dossier.

        Args:
            dossier_id: The dossier to summarize

        Returns:
            DossierSummary or None if not found
        """
        dossier = self.management_service.get_dossier(dossier_id)
        if not dossier:
            return None

        transcription_count = self.association_service.get_transcription_count(dossier_id)

        return DossierSummary(
            dossier_id=dossier.id,
            title=dossier.title,
            transcription_count=transcription_count,
            created_at=dossier.created_at,
            updated_at=dossier.updated_at
        )

    def get_navigation_hierarchy(self, dossier_id: str) -> Dict[str, Any]:
        """
        Get navigation hierarchy for a dossier.
        Useful for UI navigation components.

        Args:
            dossier_id: The dossier

        Returns:
            Dictionary representing navigation structure
        """
        logger.info(f"🌳 Building navigation hierarchy for dossier: {dossier_id}")

        structure = self.get_dossier_structure(dossier_id)
        if not structure:
            return {"error": "Dossier not found"}

        # Build hierarchy
        hierarchy = {
            "dossier": {
                "id": structure.dossier.id,
                "title": structure.dossier.title,
                "description": structure.dossier.description,
                "created_at": structure.dossier.created_at.isoformat(),
                "transcription_count": len(structure.transcriptions)
            },
            "transcriptions": []
        }

        for transcription in structure.transcriptions:
            transcription_info = {
                "id": transcription.transcription_id,
                "position": transcription.position,
                "added_at": transcription.added_at.isoformat(),
                "metadata": transcription.metadata
            }
            hierarchy["transcriptions"].append(transcription_info)

        logger.info(f"✅ Built navigation hierarchy for dossier {dossier_id}")
        return hierarchy

    def get_dossier_stats(self) -> Dict[str, Any]:
        """
        Get overall statistics about the dossier system.

        Returns:
            Dictionary with system statistics
        """
        logger.info("📊 Gathering dossier system statistics")

        all_dossiers = self.management_service.list_dossiers(limit=10000, offset=0)

        total_dossiers = len(all_dossiers)
        total_transcriptions = sum(d.transcription_count for d in all_dossiers)

        # Calculate average transcriptions per dossier
        avg_transcriptions = total_transcriptions / total_dossiers if total_dossiers > 0 else 0

        # Find most recent dossier
        most_recent = max(all_dossiers, key=lambda d: d.updated_at) if all_dossiers else None

        stats = {
            "total_dossiers": total_dossiers,
            "total_transcriptions": total_transcriptions,
            "average_transcriptions_per_dossier": round(avg_transcriptions, 2),
            "most_recent_dossier": most_recent.to_dict() if most_recent else None
        }

        logger.info(f"📈 System stats: {total_dossiers} dossiers, {total_transcriptions} transcriptions")
        return stats

    def suggest_similar_dossiers(self, dossier_id: str, limit: int = 5) -> List[DossierSummary]:
        """
        Suggest similar dossiers based on content patterns.

        Args:
            dossier_id: The dossier to find similar items for
            limit: Maximum suggestions to return

        Returns:
            List of similar DossierSummary objects
        """
        logger.info(f"💡 Finding similar dossiers to: {dossier_id}")

        # Get target dossier info
        target = self.get_dossier_summary(dossier_id)
        if not target:
            return []

        # Simple similarity based on transcription count
        all_dossiers = self.management_service.list_dossiers(limit=100, offset=0)

        # Filter out the target dossier and sort by similarity
        similar = []
        for dossier in all_dossiers:
            if dossier.dossier_id == dossier_id:
                continue

            # Simple similarity score based on transcription count difference
            count_diff = abs(dossier.transcription_count - target.transcription_count)
            similarity_score = max(0, 100 - count_diff * 10)  # Arbitrary scoring

            dossier.similarity_score = similarity_score
            similar.append(dossier)

        # Sort by similarity and return top results
        similar.sort(key=lambda d: d.similarity_score, reverse=True)
        similar = similar[:limit]

        logger.info(f"✅ Found {len(similar)} similar dossiers")
        return similar
