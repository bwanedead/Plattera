"""
Persistent Vector Store Adapter
================================

Combines HnswVectorStore (vectors) and VectorMetadataStore (metadata) to provide
a persistent vector index with chunk_id as the public API.

Key responsibilities:
- Hide internal HNSW labels from external API (use chunk_id)
- Upsert vectors with automatic label assignment
- Query vectors and return chunk_id hits
- Support tombstone/deletion via metadata store
- Persist both vector index and metadata to disk
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

from .hnsw_store import HnswVectorStore, create_hnsw_store, load_hnsw_store
from .metadata_store import ChunkMetadata, VectorMetadataStore


@dataclass
class PersistentVectorStore:
    """
    Persistent vector store combining HNSW index and metadata store.

    Public API uses chunk_id (string) instead of internal labels (int).
    """

    hnsw_store: HnswVectorStore
    metadata_store: VectorMetadataStore
    pool_identifier: str

    def upsert(
        self,
        chunk_id: str,
        vector: List[float],
        dossier_id: Optional[str],
        entry_id: str,
        selector_json: str,
        preview: Optional[str] = None,
        segment_id: Optional[str] = None,
        draft_id: Optional[str] = None,
    ) -> None:
        """
        Insert or update a chunk's vector.

        If chunk_id already exists, updates the vector (deterministic behavior).

        Args:
            chunk_id: External chunk identifier
            vector: Embedding vector
            dossier_id: Dossier this chunk belongs to (for replace-slice)
            entry_id: Corpus entry identifier
            selector_json: JSON-serialized ChunkSelector
            preview: Short deterministic excerpt for triage (max ~200 chars)
            segment_id: Segment identifier (for FINAL_SEGMENTS CorpusEntryRef)
            draft_id: Draft identifier (for FINAL_SEGMENTS CorpusEntryRef)
        """
        # Check if chunk_id already exists
        existing_meta = self.metadata_store.lookup_by_chunk_id(chunk_id)

        if existing_meta is not None:
            # Update existing: allocate NEW label, tombstone old (safe-by-design)
            old_label = existing_meta.label
            new_label = self.metadata_store.get_next_label()

            # Tombstone old label in HNSW (never reuse deleted labels)
            self.hnsw_store.mark_deleted(old_label)

            # Add new vector with NEW label
            self.hnsw_store.add_vector(label=new_label, vector=vector)

            # Update metadata to point chunk_id to new label
            metadata = ChunkMetadata(
                chunk_id=chunk_id,
                label=new_label,
                dossier_id=dossier_id,
                pool_identifier=self.pool_identifier,
                entry_id=entry_id,
                selector_json=selector_json,
                preview=preview,
                segment_id=segment_id,
                draft_id=draft_id,
                is_deleted=False,
            )
            self.metadata_store.upsert_chunk(metadata)
        else:
            # New chunk: assign new label
            label = self.metadata_store.get_next_label()

            # Add to HNSW index
            self.hnsw_store.add_vector(label=label, vector=vector)

            # Add metadata
            metadata = ChunkMetadata(
                chunk_id=chunk_id,
                label=label,
                dossier_id=dossier_id,
                pool_identifier=self.pool_identifier,
                entry_id=entry_id,
                selector_json=selector_json,
                preview=preview,
                segment_id=segment_id,
                draft_id=draft_id,
                is_deleted=False,
            )
            self.metadata_store.upsert_chunk(metadata)

    def query(
        self, vector: List[float], k: int = 10
    ) -> List[Tuple[str, float]]:
        """
        Query for k nearest neighbor chunks.

        Args:
            vector: Query vector
            k: Number of results to return

        Returns:
            List of (chunk_id, distance) tuples sorted by distance
        """
        # Query HNSW index (returns labels)
        label_results = self.hnsw_store.knn_query(vector=vector, k=k)

        # Convert labels to chunk_ids
        chunk_results = []
        for label, distance in label_results:
            # Lookup metadata by label
            metadata = self.metadata_store.lookup_by_label(label)

            if metadata is None:
                # Missing metadata (shouldn't happen, but handle safely)
                continue

            if metadata.is_deleted:
                # Skip tombstoned chunks
                continue

            chunk_results.append((metadata.chunk_id, distance))

        return chunk_results

    def delete_slice(self, dossier_id: str) -> int:
        """
        Delete all chunks for a dossier/pool slice (tombstone).

        Args:
            dossier_id: Dossier identifier

        Returns:
            Number of labels tombstoned
        """
        # Get all labels for this slice
        labels = self.metadata_store.list_labels_for_slice(
            dossier_id=dossier_id, pool_identifier=self.pool_identifier
        )

        if not labels:
            return 0

        # Mark as deleted in HNSW
        self.hnsw_store.mark_deleted_batch(labels)

        # Mark as deleted in metadata
        self.metadata_store.mark_deleted(labels)

        return len(labels)

    def save(self, hnsw_path: Path, metadata_path: Path) -> None:
        """
        Save both HNSW index and metadata to disk.

        Args:
            hnsw_path: Path for HNSW index file
            metadata_path: Path for metadata database
        """
        self.hnsw_store.save(hnsw_path)
        # Metadata store is already persisted to SQLite (no explicit save needed)

    def should_compact(self, threshold: float = 0.3) -> bool:
        """
        Check if compaction is recommended based on tombstone ratio.

        Compaction Strategy:
        -------------------
        Compaction rebuilds the HNSW index without tombstoned vectors, reclaiming
        memory and improving query performance. Compaction is recommended when the
        tombstone ratio exceeds a threshold (default 30%). Tombstones are measured
        at the vector level (HNSW entries that are no longer active chunk_ids).

        When to compact:
        - tombstone_ratio > threshold (default 30%)
        - After many updates or deletions
        - During off-peak hours or maintenance windows

        Why compact:
        - Reclaim memory from deleted vectors
        - Improve query performance (fewer vectors to filter)
        - Reset HNSW graph structure for better cache locality

        Operational impact:
        - Compaction is a blocking operation (no queries during compaction)
        - Duration scales with number of active chunks (not tombstones)
        - Index remains functional during compaction (old index replaced atomically)
        - No data loss (all active chunks preserved with vectors)

        Args:
            threshold: Tombstone ratio threshold (0.0-1.0). Default 0.3 (30%)

        Returns:
            True if tombstone_ratio > threshold, False otherwise

        Example:
            >>> if store.should_compact(threshold=0.3):
            >>>     stats = store.compact()
            >>>     print(f"Compacted: removed {stats['tombstones_removed']} tombstones")
        """
        stats = self.get_stats()
        return stats["tombstone_ratio"] > threshold

    def compact(self) -> dict:
        """
        Compact the vector store by rebuilding without tombstones.

        This operation:
        1. Retrieves all active chunks and their vectors
        2. Creates a new HNSW index with sequential labels (0, 1, 2, ...)
        3. Updates metadata to map chunk_ids to new labels
        4. Replaces old HNSW index with compacted one

        Returns:
            Dict with compaction statistics:
            - chunks_retained: Number of active chunks kept
            - tombstones_removed: Number of tombstoned chunks discarded
            - old_total_vectors: Total vectors before compaction
            - new_total_vectors: Total vectors after compaction

        Note: This is a destructive operation that modifies the index in-place.
        """
        # Get all active chunks from metadata
        active_chunks = self.metadata_store.list_all_active_chunks()

        # Get old stats for reporting
        old_stats = self.get_stats()
        old_total = old_stats["total_vectors"]
        tombstones_removed = old_stats["tombstoned_vectors"]

        # Create new HNSW index with preserved capacity
        from .hnsw_store import HnswVectorStore

        new_capacity = max(self.hnsw_store.max_elements, len(active_chunks))
        new_hnsw = HnswVectorStore(
            embedding_dim=self.hnsw_store.embedding_dim,
            max_elements=new_capacity,
            ef_construction=self.hnsw_store.ef_construction,
            M=self.hnsw_store.M,
        )

        # Retrieve and re-add vectors for all active chunks
        old_labels = [chunk.label for chunk in active_chunks]
        vectors = self.hnsw_store.get_vectors(old_labels)
        new_labels = list(range(len(active_chunks)))
        if new_labels:
            new_hnsw.add_vectors(new_labels, vectors)

        # Rebuild metadata in a new SQLite DB to avoid label collisions
        metadata_db_path = self.metadata_store.db_path
        temp_db_path = metadata_db_path.with_name(
            f"{metadata_db_path.stem}.compact{metadata_db_path.suffix}"
        )
        if temp_db_path.exists():
            temp_db_path.unlink()

        temp_metadata_store = VectorMetadataStore(db_path=temp_db_path)
        for chunk, new_label in zip(active_chunks, new_labels):
            updated_chunk = ChunkMetadata(
                chunk_id=chunk.chunk_id,
                label=new_label,
                dossier_id=chunk.dossier_id,
                pool_identifier=chunk.pool_identifier,
                entry_id=chunk.entry_id,
                selector_json=chunk.selector_json,
                preview=chunk.preview,
                segment_id=chunk.segment_id,
                draft_id=chunk.draft_id,
                is_deleted=False,
            )
            temp_metadata_store.upsert_chunk(updated_chunk)

        # Swap compacted metadata DB into place
        temp_db_path.replace(metadata_db_path)
        self.metadata_store = VectorMetadataStore(db_path=metadata_db_path)

        # Replace old HNSW store with new one
        self.hnsw_store = new_hnsw

        return {
            "chunks_retained": len(active_chunks),
            "tombstones_removed": tombstones_removed,
            "old_total_vectors": old_total,
            "new_total_vectors": new_hnsw.get_current_count(),
        }

    def get_stats(self) -> dict:
        """
        Get statistics about the vector store.

        Returns:
            Dict with:
            - active_chunks: Number of active (non-deleted) chunks
            - total_vectors: Total vectors in HNSW index (active + tombstoned)
            - tombstoned_vectors: Number of vectors not mapped to active chunks
            - tombstone_ratio: Ratio of tombstoned vectors to total (0.0-1.0)
            - deleted_chunks: Number of deleted chunk rows in metadata
            - pool_identifier: Pool this store belongs to
        """
        active_chunks = self.metadata_store.count_active_chunks()
        deleted_chunks = self.metadata_store.count_deleted_chunks()
        total_vectors = self.hnsw_store.get_current_count()
        tombstoned_vectors = max(total_vectors - active_chunks, 0)
        tombstone_ratio = (
            tombstoned_vectors / total_vectors if total_vectors > 0 else 0.0
        )

        return {
            "active_chunks": active_chunks,
            "total_vectors": total_vectors,
            "tombstoned_vectors": tombstoned_vectors,
            "tombstoned_count": tombstoned_vectors,
            "tombstone_ratio": tombstone_ratio,
            "deleted_chunks": deleted_chunks,
            "pool_identifier": self.pool_identifier,
        }


def create_persistent_store(
    pool_identifier: str,
    embedding_dim: int,
    metadata_db_path: Path,
    max_elements: int = 10000,
    M: int = 32,
    ef_construction: int = 200,
) -> PersistentVectorStore:
    """
    Create a new persistent vector store.

    Args:
        pool_identifier: Pool/view identifier (e.g., "FINAL_SEGMENTS")
        embedding_dim: Vector dimensionality
        metadata_db_path: Path to SQLite metadata database
        max_elements: Maximum number of vectors
        M: HNSW M parameter (higher = better recall, more memory)
        ef_construction: HNSW construction parameter (higher = better recall, slower build)

    Returns:
        Initialized PersistentVectorStore
    """
    hnsw_store = create_hnsw_store(
        embedding_dim=embedding_dim,
        max_elements=max_elements,
        M=M,
        ef_construction=ef_construction,
    )

    metadata_store = VectorMetadataStore(db_path=metadata_db_path)

    return PersistentVectorStore(
        hnsw_store=hnsw_store,
        metadata_store=metadata_store,
        pool_identifier=pool_identifier,
    )


def load_persistent_store(
    pool_identifier: str,
    embedding_dim: int,
    hnsw_path: Path,
    metadata_db_path: Path,
    max_elements: int = 10000,
) -> PersistentVectorStore:
    """
    Load a persistent vector store from disk.

    Args:
        pool_identifier: Pool/view identifier
        embedding_dim: Vector dimensionality
        hnsw_path: Path to HNSW index file
        metadata_db_path: Path to SQLite metadata database
        max_elements: Maximum number of vectors

    Returns:
        Loaded PersistentVectorStore
    """
    hnsw_store = load_hnsw_store(
        path=hnsw_path,
        embedding_dim=embedding_dim,
        max_elements=max_elements,
    )

    metadata_store = VectorMetadataStore(db_path=metadata_db_path)

    return PersistentVectorStore(
        hnsw_store=hnsw_store,
        metadata_store=metadata_store,
        pool_identifier=pool_identifier,
    )
