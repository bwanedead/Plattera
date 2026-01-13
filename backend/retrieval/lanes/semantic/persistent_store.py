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
            # Update existing: reuse label
            label = existing_meta.label

            # Mark old label as deleted (tombstone)
            self.hnsw_store.mark_deleted(label)

            # Add new vector with same label
            self.hnsw_store.add_vector(label=label, vector=vector)

            # Update metadata (unmark deleted)
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

    def get_stats(self) -> dict:
        """
        Get statistics about the vector store.

        Returns:
            Dict with count statistics
        """
        return {
            "total_vectors": self.hnsw_store.get_current_count(),
            "active_chunks": self.metadata_store.count_active_chunks(),
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
