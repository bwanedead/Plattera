"""
Tests for persistent vector store adapter.

Validates:
- Public API uses chunk_id (not labels)
- Upsert idempotency (same chunk_id doesn't create duplicates)
- Build → save → load → query round-trip
- Tombstone/deletion integration

All tests in this module require hnswlib and numpy dependencies.
Run HNSW integration tests: pytest -m hnsw
Run non-HNSW tests: pytest -m "not hnsw"
"""

import tempfile
from pathlib import Path

import pytest

from .persistent_store import create_persistent_store, load_persistent_store

# Mark all tests in this module as requiring HNSW
pytestmark = pytest.mark.hnsw


def test_create_and_upsert():
    """Persistent store can be created and chunks can be upserted."""
    with tempfile.TemporaryDirectory() as tmpdir:
        metadata_db = Path(tmpdir) / "metadata.db"

        store = create_persistent_store(
            pool_identifier="FINAL_SEGMENTS",
            embedding_dim=4,
            metadata_db_path=metadata_db,
        )

        # Upsert a chunk
        store.upsert(
            chunk_id="chunk_abc123",
            vector=[1.0, 0.0, 0.0, 0.0],
            dossier_id="dossier_1",
            entry_id="entry_xyz",
            selector_json='{"kind":"section","section_index":0}',
        )

        stats = store.get_stats()
        assert stats["total_vectors"] == 1
        assert stats["active_chunks"] == 1


def test_query_returns_chunk_ids():
    """Query returns chunk_id (not internal labels)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        metadata_db = Path(tmpdir) / "metadata.db"

        store = create_persistent_store(
            pool_identifier="FINAL_SEGMENTS",
            embedding_dim=4,
            metadata_db_path=metadata_db,
        )

        # Add chunks
        store.upsert(
            chunk_id="chunk_aaa",
            vector=[1.0, 0.0, 0.0, 0.0],
            dossier_id="dossier_1",
            entry_id="entry_1",
            selector_json='{"kind":"section","section_index":0}',
        )
        store.upsert(
            chunk_id="chunk_bbb",
            vector=[0.0, 1.0, 0.0, 0.0],
            dossier_id="dossier_1",
            entry_id="entry_2",
            selector_json='{"kind":"section","section_index":1}',
        )

        # Query
        results = store.query(vector=[1.0, 0.0, 0.0, 0.0], k=2)

        # Should return chunk_ids (not labels)
        assert len(results) == 2
        chunk_ids = [chunk_id for chunk_id, _ in results]
        assert "chunk_aaa" in chunk_ids
        assert "chunk_bbb" in chunk_ids

        # Top result should be chunk_aaa (closest to query)
        assert results[0][0] == "chunk_aaa"


def test_upsert_idempotent():
    """Upserting same chunk_id twice doesn't create duplicate retrievable IDs."""
    with tempfile.TemporaryDirectory() as tmpdir:
        metadata_db = Path(tmpdir) / "metadata.db"

        store = create_persistent_store(
            pool_identifier="FINAL_SEGMENTS",
            embedding_dim=4,
            metadata_db_path=metadata_db,
        )

        # Add several chunks to ensure graph connectivity
        for i in range(10):
            vec = [0.0] * 4
            vec[0] = 0.5 + (i * 0.05)
            store.upsert(
                chunk_id=f"chunk_filler_{i}",
                vector=vec,
                dossier_id="dossier_1",
                entry_id=f"entry_{i}",
                selector_json='{"kind":"section","section_index":0}',
            )

        # First upsert of target chunk
        store.upsert(
            chunk_id="chunk_stable",
            vector=[1.0, 0.0, 0.0, 0.0],
            dossier_id="dossier_1",
            entry_id="entry_1",
            selector_json='{"kind":"section","section_index":0}',
        )

        # Second upsert with same chunk_id but different vector
        store.upsert(
            chunk_id="chunk_stable",
            vector=[0.0, 1.0, 0.0, 0.0],
            dossier_id="dossier_1",
            entry_id="entry_1",
            selector_json='{"kind":"section","section_index":0}',
        )

        # Query in y direction (should match updated vector)
        results_y = store.query(vector=[0.0, 1.0, 0.0, 0.0], k=10)
        y_chunk_ids = [cid for cid, _ in results_y]

        # chunk_stable should appear exactly once
        assert y_chunk_ids.count("chunk_stable") == 1


def test_save_load_round_trip():
    """Index build → save → load → query returns chunk_id hits."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        metadata_db = tmpdir_path / "metadata.db"
        hnsw_file = tmpdir_path / "hnsw.bin"

        # Build index
        store1 = create_persistent_store(
            pool_identifier="FINAL_SEGMENTS",
            embedding_dim=3,
            metadata_db_path=metadata_db,
        )

        store1.upsert(
            chunk_id="chunk_red",
            vector=[1.0, 0.0, 0.0],
            dossier_id="dossier_1",
            entry_id="entry_1",
            selector_json='{"kind":"section","section_index":0}',
        )
        store1.upsert(
            chunk_id="chunk_green",
            vector=[0.0, 1.0, 0.0],
            dossier_id="dossier_1",
            entry_id="entry_2",
            selector_json='{"kind":"section","section_index":1}',
        )

        # Query before save
        results1 = store1.query(vector=[1.0, 0.0, 0.0], k=2)
        assert results1[0][0] == "chunk_red"

        # Save
        store1.save(hnsw_path=hnsw_file, metadata_path=metadata_db)

        # Load into new store
        store2 = load_persistent_store(
            pool_identifier="FINAL_SEGMENTS",
            embedding_dim=3,
            hnsw_path=hnsw_file,
            metadata_db_path=metadata_db,
        )

        # Query after load
        results2 = store2.query(vector=[1.0, 0.0, 0.0], k=2)

        # Should return same chunk_ids
        assert results2[0][0] == "chunk_red"
        assert len(results2) == 2


def test_delete_slice():
    """delete_slice tombstones all chunks for a dossier/pool."""
    with tempfile.TemporaryDirectory() as tmpdir:
        metadata_db = Path(tmpdir) / "metadata.db"

        store = create_persistent_store(
            pool_identifier="FINAL_SEGMENTS",
            embedding_dim=3,
            metadata_db_path=metadata_db,
        )

        # Add chunks for dossier_1
        for i in range(5):
            store.upsert(
                chunk_id=f"chunk_d1_{i}",
                vector=[1.0, 0.0, 0.0],
                dossier_id="dossier_1",
                entry_id=f"entry_{i}",
                selector_json='{"kind":"section","section_index":0}',
            )

        # Delete dossier_1 slice
        deleted_count = store.delete_slice(dossier_id="dossier_1")

        # Verify delete_slice returned correct count
        assert deleted_count == 5

        # Verify metadata store has them marked as deleted
        stats = store.get_stats()
        assert stats["active_chunks"] == 0  # All marked deleted


def test_query_skips_tombstoned_chunks():
    """Query automatically filters out tombstoned/deleted chunks."""
    with tempfile.TemporaryDirectory() as tmpdir:
        metadata_db = Path(tmpdir) / "metadata.db"

        store = create_persistent_store(
            pool_identifier="FINAL_SEGMENTS",
            embedding_dim=3,
            metadata_db_path=metadata_db,
            max_elements=100,
        )

        # Add chunks to dossier_1
        for i in range(10):
            vec = [0.0] * 3
            vec[0] = 1.0 - (i * 0.05)
            vec[1] = i * 0.05
            store.upsert(
                chunk_id=f"chunk_d1_{i}",
                vector=vec,
                dossier_id="dossier_1",
                entry_id=f"entry_{i}",
                selector_json='{"kind":"section","section_index":0}',
            )

        # Add many chunks to dossier_2 (won't be deleted - ensures graph connectivity)
        for i in range(30):
            vec = [0.0] * 3
            vec[1] = 1.0 - (i * 0.02)
            vec[2] = i * 0.02
            store.upsert(
                chunk_id=f"chunk_d2_{i}",
                vector=vec,
                dossier_id="dossier_2",
                entry_id=f"entry_{i}",
                selector_json='{"kind":"section","section_index":0}',
            )

        # Delete dossier_1 chunks (only 10 out of 40 total)
        deleted = store.delete_slice(dossier_id="dossier_1")
        assert deleted == 10

        # Query should not return dossier_1 chunks (tombstoned)
        results = store.query(vector=[1.0, 0.0, 0.0], k=20)
        chunk_ids = [cid for cid, _ in results]

        # No dossier_1 chunks should appear (they're tombstoned)
        d1_chunks = [cid for cid in chunk_ids if cid.startswith("chunk_d1_")]
        assert len(d1_chunks) == 0


def test_update_never_reuses_deleted_labels():
    """
    Updating same chunk_id multiple times allocates new labels (never reuses deleted).

    Verifies safe-by-design semantics:
    - Each update gets a fresh label
    - Old labels are tombstoned (never reused)
    - Chunk remains retrievable after N updates
    - No crashes during repeated update/query cycles
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        metadata_db = Path(tmpdir) / "metadata.db"

        store = create_persistent_store(
            pool_identifier="FINAL_SEGMENTS",
            embedding_dim=4,
            metadata_db_path=metadata_db,
            max_elements=1000,
        )

        # Add filler chunks to establish HNSW graph connectivity
        for i in range(20):
            vec = [0.0] * 4
            vec[0] = 0.3 + (i * 0.02)
            store.upsert(
                chunk_id=f"chunk_filler_{i}",
                vector=vec,
                dossier_id="dossier_filler",
                entry_id=f"entry_{i}",
                selector_json='{"kind":"section","section_index":0}',
            )

        # Track labels allocated for our target chunk
        allocated_labels = []

        # Initial insert
        store.upsert(
            chunk_id="chunk_target",
            vector=[1.0, 0.0, 0.0, 0.0],
            dossier_id="dossier_1",
            entry_id="entry_1",
            selector_json='{"kind":"section","section_index":0}',
        )

        # Get initial label
        meta_0 = store.metadata_store.lookup_by_chunk_id("chunk_target")
        assert meta_0 is not None
        allocated_labels.append(meta_0.label)

        # Update the same chunk 10 times with different vectors
        for i in range(10):
            angle = (i + 1) * 0.1
            vec = [1.0 - angle, angle, 0.0, 0.0]

            store.upsert(
                chunk_id="chunk_target",
                vector=vec,
                dossier_id="dossier_1",
                entry_id="entry_1",
                selector_json='{"kind":"section","section_index":0}',
            )

            # Get new label after update
            meta = store.metadata_store.lookup_by_chunk_id("chunk_target")
            assert meta is not None
            allocated_labels.append(meta.label)

            # Verify chunk remains retrievable
            results = store.query(vector=vec, k=5)
            chunk_ids = [cid for cid, _ in results]

            # Target chunk should be in results
            assert "chunk_target" in chunk_ids

            # Target chunk should appear exactly once (no duplicates)
            assert chunk_ids.count("chunk_target") == 1

        # Verify all labels are unique (never reused)
        assert len(allocated_labels) == 11  # Initial + 10 updates
        assert len(set(allocated_labels)) == 11  # All distinct

        # Verify labels are monotonically increasing (no reuse of deleted labels)
        for i in range(1, len(allocated_labels)):
            assert allocated_labels[i] > allocated_labels[i - 1], (
                f"Label {allocated_labels[i]} should be > {allocated_labels[i - 1]}"
            )

        # Final verification: chunk is still retrievable with latest vector
        final_vec = [1.0 - 1.0, 1.0, 0.0, 0.0]
        final_results = store.query(vector=final_vec, k=10)
        final_chunk_ids = [cid for cid, _ in final_results]

        assert "chunk_target" in final_chunk_ids
        assert final_chunk_ids.count("chunk_target") == 1

        # Verify stats: 21 vectors total (20 filler + 1 active target + 10 tombstoned old labels)
        stats = store.get_stats()
        assert stats["total_vectors"] == 31  # 20 filler + 11 target versions
        assert stats["active_chunks"] == 21  # 20 filler + 1 current target (10 old versions tombstoned)


@pytest.mark.hnsw
def test_get_stats():
    """get_stats() returns accurate tombstone statistics."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        store = create_persistent_store(
            pool_identifier="TEST_STATS_POOL",
            embedding_dim=4,
            hnsw_path=tmppath / "test.hnsw",
            metadata_path=tmppath / "test.db",
        )

        # Initial state: empty
        stats = store.get_stats()
        assert stats["active_chunks"] == 0
        assert stats["tombstoned_count"] == 0
        assert stats["tombstone_ratio"] == 0.0
        assert stats["pool_identifier"] == "TEST_STATS_POOL"
        assert stats["total_vectors"] == 0

        # Add 10 chunks
        for i in range(10):
            store.upsert(
                chunk_id=f"chunk_{i}",
                vector=[float(i), 0.0, 0.0, 0.0],
                dossier_id="dossier_1",
                entry_id=f"entry_{i}",
                selector_json='{"type": "whole"}',
            )

        stats = store.get_stats()
        assert stats["active_chunks"] == 10
        assert stats["tombstoned_count"] == 0
        assert stats["tombstone_ratio"] == 0.0
        assert stats["total_vectors"] == 10

        # Update 3 chunks (creates 3 tombstones)
        for i in range(3):
            store.upsert(
                chunk_id=f"chunk_{i}",
                vector=[float(i) + 1.0, 0.0, 0.0, 0.0],
                dossier_id="dossier_1",
                entry_id=f"entry_{i}",
                selector_json='{"type": "whole"}',
            )

        stats = store.get_stats()
        assert stats["active_chunks"] == 10  # Still 10 active chunks (updates don't increase count)
        assert stats["tombstoned_count"] == 3  # 3 old versions tombstoned
        assert stats["tombstone_ratio"] == 3 / 13  # 3 tombstoned out of 13 total
        assert stats["total_vectors"] == 13  # 10 original + 3 updates

        # Delete a slice (tombstone 10 chunks)
        deleted_count = store.delete_slice(dossier_id="dossier_1")
        assert deleted_count == 10

        stats = store.get_stats()
        assert stats["active_chunks"] == 0  # All chunks deleted
        assert stats["tombstoned_count"] == 13  # All 13 vectors tombstoned (10 active + 3 old)
        assert stats["tombstone_ratio"] == 1.0  # 100% tombstoned
        assert stats["total_vectors"] == 13
