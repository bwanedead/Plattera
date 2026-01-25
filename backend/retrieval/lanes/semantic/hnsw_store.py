"""
HNSW Vector Store Wrapper
==========================

Wraps hnswlib for persistent vector indexing with HNSW algorithm.

Key responsibilities:
- Create/load/save HNSW indexes
- Add vectors with integer labels
- KNN query (top-k nearest neighbors)
- Mark vectors as deleted (tombstone support)
- Normalize vectors for cosine-equivalent similarity
"""

from __future__ import annotations

import numpy as np
from pathlib import Path
from typing import List, Optional, Tuple

try:
    import hnswlib
except ImportError:
    hnswlib = None  # type: ignore


class HnswVectorStore:
    """
    HNSW-backed vector store for semantic search.

    Uses hnswlib for fast approximate nearest neighbor search.
    Supports cosine similarity via normalization + inner product.
    """

    def __init__(
        self,
        embedding_dim: int,
        max_elements: int = 10000,
        ef_construction: int = 200,
        M: int = 16,
        init: bool = True,
    ):
        """
        Initialize HNSW vector store.

        Args:
            embedding_dim: Vector dimensionality
            max_elements: Maximum number of vectors (can be resized later)
            ef_construction: HNSW construction parameter (higher = better recall, slower build)
            M: HNSW M parameter (higher = better recall, more memory)
            init: Whether to initialize the index. Set to False when loading an existing index.
        """
        if hnswlib is None:
            raise RuntimeError("hnswlib is not installed")

        self.embedding_dim = embedding_dim
        self.max_elements = max_elements
        self.ef_construction = ef_construction
        self.M = M

        # Initialize HNSW index with inner product (for normalized vectors = cosine)
        self.index = hnswlib.Index(space="ip", dim=embedding_dim)
        
        if init:
            self.index.init_index(
                max_elements=max_elements,
                ef_construction=ef_construction,
                M=M,
            )

        # Track current element count
        self._current_count = 0

    def add_vector(self, label: int, vector: List[float]) -> None:
        """
        Add a single vector to the index.

        Args:
            label: Integer label for this vector
            vector: Vector to add (will be normalized for cosine similarity)
        """
        self._ensure_capacity(1)
        # Normalize vector for cosine similarity via inner product
        normalized = self._normalize_vector(vector)

        # Add to index
        self.index.add_items(np.array([normalized]), np.array([label]))
        self._current_count += 1

    def add_vectors(self, labels: List[int], vectors: List[List[float]]) -> None:
        """
        Add multiple vectors to the index.

        Args:
            labels: List of integer labels
            vectors: List of vectors (will be normalized)
        """
        if len(labels) != len(vectors):
            raise ValueError("labels and vectors must have same length")

        if not labels:
            return

        self._ensure_capacity(len(labels))
        # Normalize vectors
        normalized = self._normalize_vectors(vectors)

        # Add to index
        self.index.add_items(np.array(normalized), np.array(labels))
        self._current_count += len(labels)

    def knn_query(
        self, vector: List[float], k: int = 10, ef: Optional[int] = None
    ) -> List[Tuple[int, float]]:
        """
        Query for k nearest neighbors.

        Args:
            vector: Query vector (will be normalized)
            k: Number of neighbors to return
            ef: HNSW ef parameter for search (higher = better recall, slower)

        Returns:
            List of (label, distance) tuples sorted by distance
        """
        if self._current_count == 0:
            return []

        # Set ef for search if provided
        if ef is not None:
            self.index.set_ef(ef)

        # Normalize query vector
        normalized = self._normalize_vector(vector)

        # Query index (handle case where deleted items reduce available results)
        try:
            labels, distances = self.index.knn_query(np.array([normalized]), k=k)
        except RuntimeError:
            # If k is larger than available non-deleted items, reduce k
            # This can happen when many items are marked deleted
            actual_k = min(k, self._current_count)
            if actual_k == 0:
                return []
            labels, distances = self.index.knn_query(np.array([normalized]), k=actual_k)

        # Convert to list of tuples
        results = []
        for label, distance in zip(labels[0], distances[0]):
            results.append((int(label), float(distance)))

        return results

    def mark_deleted(self, label: int) -> None:
        """
        Mark a vector as deleted (tombstone).

        Args:
            label: Label to mark as deleted
        """
        self.index.mark_deleted(label)

    def mark_deleted_batch(self, labels: List[int]) -> None:
        """
        Mark multiple vectors as deleted.

        Args:
            labels: List of labels to mark as deleted
        """
        for label in labels:
            self.index.mark_deleted(label)

    def save(self, path: Path) -> None:
        """
        Save index to disk.

        Args:
            path: Path to save index file
        """
        path.parent.mkdir(parents=True, exist_ok=True)
        self.index.save_index(str(path))

    def load(self, path: Path, max_elements: Optional[int] = None) -> None:
        """
        Load index from disk.

        Args:
            path: Path to index file
            max_elements: Override max_elements (useful for resizing)
        """
        if not path.exists():
            raise FileNotFoundError(f"Index file not found: {path}")

        # Load index
        self.index.load_index(str(path), max_elements=max_elements or self.max_elements)

        # Update element count
        self._current_count = self.index.get_current_count()

    def resize(self, new_max_elements: int) -> None:
        """
        Resize the index to accommodate more elements.

        Args:
            new_max_elements: New maximum element count
        """
        self.index.resize_index(new_max_elements)
        self.max_elements = new_max_elements

    def get_vectors(self, labels: List[int]) -> List[List[float]]:
        """
        Retrieve vectors by their labels.

        Args:
            labels: List of labels to retrieve

        Returns:
            List of vectors (denormalized back to original scale)
        """
        if not labels:
            return []

        # Get items from HNSW (returns normalized vectors)
        normalized_vectors = self.index.get_items(labels)

        # Denormalize is not necessary for our use case since we'll re-add them
        # They're already normalized and that's what we want
        return normalized_vectors.tolist()

    def get_current_count(self) -> int:
        """
        Get current number of indexed vectors.

        Returns:
            Number of vectors in index
        """
        return self._current_count

    def _ensure_capacity(self, additional: int) -> None:
        """
        Ensure the index can accommodate additional vectors.

        Args:
            additional: Number of new vectors to add
        """
        required = self._current_count + additional
        if required <= self.max_elements:
            return

        new_max = max(self.max_elements * 2, required)
        self.resize(new_max)

    @staticmethod
    def _normalize_vector(vector: List[float]) -> List[float]:
        """
        Normalize a single vector to unit length.

        Args:
            vector: Vector to normalize

        Returns:
            Normalized vector
        """
        arr = np.array(vector, dtype=np.float32)
        norm = np.linalg.norm(arr)

        if norm == 0:
            return vector  # Avoid division by zero

        return (arr / norm).tolist()

    @staticmethod
    def _normalize_vectors(vectors: List[List[float]]) -> List[List[float]]:
        """
        Normalize multiple vectors to unit length.

        Args:
            vectors: List of vectors to normalize

        Returns:
            List of normalized vectors
        """
        if not vectors:
            return []

        arr = np.array(vectors, dtype=np.float32)
        norms = np.linalg.norm(arr, axis=1, keepdims=True)

        # Avoid division by zero
        norms = np.where(norms == 0, 1, norms)

        normalized = arr / norms
        return normalized.tolist()


def create_hnsw_store(
    embedding_dim: int,
    max_elements: int = 10000,
    ef_construction: int = 200,
    M: int = 16,
) -> HnswVectorStore:
    """
    Create a new HNSW vector store.

    Args:
        embedding_dim: Vector dimensionality
        max_elements: Maximum number of vectors
        ef_construction: HNSW construction parameter
        M: HNSW M parameter

    Returns:
        Initialized HnswVectorStore
    """
    return HnswVectorStore(
        embedding_dim=embedding_dim,
        max_elements=max_elements,
        ef_construction=ef_construction,
        M=M,
    )


def load_hnsw_store(
    path: Path,
    embedding_dim: int,
    max_elements: int = 10000,
) -> HnswVectorStore:
    """
    Load an HNSW vector store from disk.

    Args:
        path: Path to index file
        embedding_dim: Vector dimensionality
        max_elements: Maximum number of vectors

    Returns:
        Loaded HnswVectorStore
    """
    store = HnswVectorStore(
        embedding_dim=embedding_dim,
        max_elements=max_elements,
        init=False,
    )
    store.load(path, max_elements=max_elements)
    return store
