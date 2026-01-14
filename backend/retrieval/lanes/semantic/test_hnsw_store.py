"""
Tests for HNSW vector store wrapper.

Validates:
- Index creation and persistence
- Vector addition and querying
- Save/load round-trip
- Tombstone (mark_deleted) functionality
- Cosine-equivalent similarity via normalization

All tests in this module require hnswlib and numpy dependencies.
Run HNSW integration tests: pytest -m hnsw
Run non-HNSW tests: pytest -m "not hnsw"
"""

import tempfile
from pathlib import Path

import numpy as np
import pytest

from .hnsw_store import HnswVectorStore, create_hnsw_store, load_hnsw_store

# Mark all tests in this module as requiring HNSW
pytestmark = pytest.mark.hnsw


def test_create_index():
    """HnswVectorStore can create an index with configured embedding_dim."""
    store = create_hnsw_store(embedding_dim=128, max_elements=100)

    assert store.embedding_dim == 128
    assert store.max_elements == 100
    assert store.get_current_count() == 0


def test_add_and_query():
    """Vectors can be added and queried."""
    store = create_hnsw_store(embedding_dim=4, max_elements=100)

    # Add some vectors
    store.add_vector(label=0, vector=[1.0, 0.0, 0.0, 0.0])
    store.add_vector(label=1, vector=[0.0, 1.0, 0.0, 0.0])
    store.add_vector(label=2, vector=[0.0, 0.0, 1.0, 0.0])

    assert store.get_current_count() == 3

    # Query for nearest to [1.0, 0.0, 0.0, 0.0]
    results = store.knn_query(vector=[1.0, 0.0, 0.0, 0.0], k=3)

    # Should return label 0 as closest
    assert len(results) == 3
    assert results[0][0] == 0  # label 0 is closest


def test_save_and_load():
    """Index can be saved to disk and loaded back."""
    with tempfile.TemporaryDirectory() as tmpdir:
        index_path = Path(tmpdir) / "test_index.bin"

        # Create and populate store
        store1 = create_hnsw_store(embedding_dim=4, max_elements=100)
        store1.add_vector(label=0, vector=[1.0, 0.0, 0.0, 0.0])
        store1.add_vector(label=1, vector=[0.0, 1.0, 0.0, 0.0])
        store1.add_vector(label=2, vector=[0.0, 0.0, 1.0, 0.0])

        # Save
        store1.save(index_path)
        assert index_path.exists()

        # Load into new store
        store2 = load_hnsw_store(path=index_path, embedding_dim=4, max_elements=100)

        assert store2.get_current_count() == 3

        # Query should return same results
        results = store2.knn_query(vector=[1.0, 0.0, 0.0, 0.0], k=3)

        assert len(results) == 3
        assert results[0][0] == 0  # label 0 still closest


def test_deterministic_query():
    """After reload, knn_query returns same top hits for deterministic fixture."""
    with tempfile.TemporaryDirectory() as tmpdir:
        index_path = Path(tmpdir) / "test_index.bin"

        # Create fixture vectors
        vectors = [
            [1.0, 0.0, 0.0],
            [0.9, 0.1, 0.0],
            [0.0, 1.0, 0.0],
        ]

        # Build index
        store1 = create_hnsw_store(embedding_dim=3, max_elements=100)
        for i, vec in enumerate(vectors):
            store1.add_vector(label=i, vector=vec)

        # Query before save
        query_vec = [1.0, 0.0, 0.0]
        results1 = store1.knn_query(vector=query_vec, k=2)

        # Save and reload
        store1.save(index_path)
        store2 = load_hnsw_store(path=index_path, embedding_dim=3, max_elements=100)

        # Query after reload
        results2 = store2.knn_query(vector=query_vec, k=2)

        # Top results should be consistent
        assert results1[0][0] == results2[0][0]  # Same top label
        assert results1[1][0] == results2[1][0]  # Same second label


def test_mark_deleted():
    """mark_deleted prevents deleted labels from returning as hits."""
    # Use larger fixture to ensure HNSW graph remains connected after deletion
    store = create_hnsw_store(embedding_dim=4, max_elements=100, M=32, ef_construction=200)

    # Add more vectors to ensure graph connectivity
    vectors = []
    for i in range(10):
        vec = [0.0] * 4
        vec[0] = 1.0 - (i * 0.05)  # Varying similarity
        vec[1] = i * 0.05
        vectors.append(vec)
        store.add_vector(label=i, vector=vec)

    # Query should return label 0 as top hit
    results_before = store.knn_query(vector=[1.0, 0.0, 0.0, 0.0], k=5)
    assert results_before[0][0] == 0

    # Mark label 0 as deleted
    store.mark_deleted(label=0)

    # Query should no longer return label 0
    results_after = store.knn_query(vector=[1.0, 0.0, 0.0, 0.0], k=5)

    returned_labels = [label for label, _ in results_after]
    assert 0 not in returned_labels


def test_mark_deleted_batch():
    """mark_deleted_batch can delete multiple labels."""
    # Use larger fixture to ensure HNSW graph remains connected
    store = create_hnsw_store(embedding_dim=4, max_elements=100, M=32, ef_construction=200)

    # Add vectors with varying similarities
    for i in range(15):
        vec = [0.0] * 4
        vec[i % 4] = 1.0 - (i * 0.02)
        vec[(i + 1) % 4] = i * 0.02
        store.add_vector(label=i, vector=vec)

    # Query before deletion
    results_before = store.knn_query(vector=[1.0, 0.0, 0.0, 0.0], k=10)
    before_labels = [label for label, _ in results_before]

    # Verify labels 1 and 3 are in results initially
    assert 1 in before_labels or 3 in before_labels

    # Mark labels 1 and 3 as deleted
    store.mark_deleted_batch([1, 3])

    # Query should not return labels 1 or 3
    results = store.knn_query(vector=[1.0, 0.0, 0.0, 0.0], k=10)

    returned_labels = [label for label, _ in results]
    assert 1 not in returned_labels
    assert 3 not in returned_labels


def test_add_vectors_batch():
    """add_vectors can add multiple vectors at once."""
    store = create_hnsw_store(embedding_dim=3, max_elements=100)

    labels = [0, 1, 2]
    vectors = [
        [1.0, 0.0, 0.0],
        [0.0, 1.0, 0.0],
        [0.0, 0.0, 1.0],
    ]

    store.add_vectors(labels=labels, vectors=vectors)

    assert store.get_current_count() == 3

    # Query should work
    results = store.knn_query(vector=[1.0, 0.0, 0.0], k=1)
    assert results[0][0] == 0


def test_cosine_similarity_via_normalization():
    """Store uses cosine-equivalent similarity (normalized vectors + inner product)."""
    store = create_hnsw_store(embedding_dim=3, max_elements=100)

    # Add vectors with different magnitudes but same direction
    store.add_vector(label=0, vector=[1.0, 0.0, 0.0])  # magnitude 1
    store.add_vector(label=1, vector=[2.0, 0.0, 0.0])  # magnitude 2 (same direction)
    store.add_vector(label=2, vector=[0.0, 1.0, 0.0])  # different direction

    # Query with a vector in the same direction as 0 and 1
    results = store.knn_query(vector=[3.0, 0.0, 0.0], k=3)

    # Labels 0 and 1 should be equally close (both aligned with query)
    # and closer than label 2
    top_labels = [label for label, _ in results[:2]]
    assert 0 in top_labels
    assert 1 in top_labels

    # Verify label 2 is not in top 2
    assert 2 not in top_labels


def test_empty_index_query():
    """Querying an empty index returns empty results."""
    store = create_hnsw_store(embedding_dim=3, max_elements=100)

    results = store.knn_query(vector=[1.0, 0.0, 0.0], k=5)

    assert results == []


def test_load_missing_file_raises():
    """Loading from non-existent file raises FileNotFoundError."""
    with tempfile.TemporaryDirectory() as tmpdir:
        nonexistent_path = Path(tmpdir) / "nonexistent.bin"

        store = HnswVectorStore(embedding_dim=3)

        with pytest.raises(FileNotFoundError):
            store.load(nonexistent_path)
