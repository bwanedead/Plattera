"""
Tests for SQLite VectorMetadataStore.

Validates:
- Schema initialization
- CRUD operations (upsert, lookup by chunk_id, lookup by label)
- Slice queries for replace-slice support
- Tombstone marking
"""

import sqlite3
import tempfile
from pathlib import Path

import pytest

from .metadata_store import ChunkMetadata, IndexedEntryState, VectorMetadataStore


def test_schema_initialization():
    """VectorMetadataStore initializes schema in a new sqlite file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "metadata.db"

        # Schema should not exist yet
        assert not db_path.exists()

        # Initialize store (creates schema)
        store = VectorMetadataStore(db_path)

        # Database file should now exist
        assert db_path.exists()

        # Should be able to create another store instance (idempotent)
        store2 = VectorMetadataStore(db_path)
        assert store2.count_active_chunks() == 0


def test_upsert_and_lookup_by_chunk_id():
    """Store supports upsert and lookup by chunk_id."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "metadata.db"
        store = VectorMetadataStore(db_path)

        # Insert chunk metadata
        metadata = ChunkMetadata(
            chunk_id="chunk_abc123",
            label=42,
            dossier_id="dossier_1",
            pool_identifier="FINAL_SEGMENTS",
            entry_id="entry_xyz",
            selector_json='{"kind":"section","section_index":0}',
        )

        store.upsert_chunk(metadata)

        # Lookup by chunk_id
        retrieved = store.lookup_by_chunk_id("chunk_abc123")

        assert retrieved is not None
        assert retrieved.chunk_id == "chunk_abc123"
        assert retrieved.label == 42
        assert retrieved.dossier_id == "dossier_1"
        assert retrieved.pool_identifier == "FINAL_SEGMENTS"
        assert retrieved.entry_id == "entry_xyz"
        assert retrieved.selector_json == '{"kind":"section","section_index":0}'
        assert retrieved.is_deleted is False


def test_lookup_by_label():
    """Store supports lookup by internal label."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "metadata.db"
        store = VectorMetadataStore(db_path)

        metadata = ChunkMetadata(
            chunk_id="chunk_def456",
            label=99,
            dossier_id="dossier_2",
            pool_identifier="FINAL_SEGMENTS",
            entry_id="entry_abc",
            selector_json='{"kind":"paragraph","paragraph_index":1}',
        )

        store.upsert_chunk(metadata)

        # Lookup by label
        retrieved = store.lookup_by_label(99)

        assert retrieved is not None
        assert retrieved.chunk_id == "chunk_def456"
        assert retrieved.label == 99
        assert retrieved.dossier_id == "dossier_2"


def test_upsert_idempotent():
    """Upserting the same chunk_id twice updates the record."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "metadata.db"
        store = VectorMetadataStore(db_path)

        # First insert
        metadata1 = ChunkMetadata(
            chunk_id="chunk_stable",
            label=10,
            dossier_id="dossier_1",
            pool_identifier="FINAL_SEGMENTS",
            entry_id="entry_old",
            selector_json='{"kind":"section","section_index":0}',
        )
        store.upsert_chunk(metadata1)

        # Second insert with same chunk_id but different data
        metadata2 = ChunkMetadata(
            chunk_id="chunk_stable",
            label=20,
            dossier_id="dossier_2",
            pool_identifier="FINAL_SEGMENTS",
            entry_id="entry_new",
            selector_json='{"kind":"section","section_index":1}',
        )
        store.upsert_chunk(metadata2)

        # Should have only one record (updated)
        retrieved = store.lookup_by_chunk_id("chunk_stable")

        assert retrieved is not None
        assert retrieved.label == 20  # Updated
        assert retrieved.entry_id == "entry_new"  # Updated
        assert retrieved.dossier_id == "dossier_2"  # Updated

        # Old label should not exist
        assert store.lookup_by_label(10) is None


def test_list_labels_for_slice():
    """Store can list labels for (dossier_id, pool) slice."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "metadata.db"
        store = VectorMetadataStore(db_path)

        # Insert chunks for dossier_1
        for i in range(5):
            store.upsert_chunk(
                ChunkMetadata(
                    chunk_id=f"chunk_d1_{i}",
                    label=i,
                    dossier_id="dossier_1",
                    pool_identifier="FINAL_SEGMENTS",
                    entry_id=f"entry_{i}",
                    selector_json='{"kind":"section","section_index":0}',
                )
            )

        # Insert chunks for dossier_2
        for i in range(3):
            store.upsert_chunk(
                ChunkMetadata(
                    chunk_id=f"chunk_d2_{i}",
                    label=i + 100,
                    dossier_id="dossier_2",
                    pool_identifier="FINAL_SEGMENTS",
                    entry_id=f"entry_{i}",
                    selector_json='{"kind":"section","section_index":0}',
                )
            )

        # List labels for dossier_1, FINAL_SEGMENTS
        labels_d1 = store.list_labels_for_slice("dossier_1", "FINAL_SEGMENTS")

        assert len(labels_d1) == 5
        assert set(labels_d1) == {0, 1, 2, 3, 4}

        # List labels for dossier_2, FINAL_SEGMENTS
        labels_d2 = store.list_labels_for_slice("dossier_2", "FINAL_SEGMENTS")

        assert len(labels_d2) == 3
        assert set(labels_d2) == {100, 101, 102}

        # Non-existent dossier
        labels_none = store.list_labels_for_slice("nonexistent", "FINAL_SEGMENTS")
        assert labels_none == []


def test_list_labels_for_entry():
    """Store can list labels for a specific entry slice."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "metadata.db"
        store = VectorMetadataStore(db_path)

        for i in range(3):
            store.upsert_chunk(
                ChunkMetadata(
                    chunk_id=f"chunk_a_{i}",
                    label=i,
                    dossier_id="dossier_1",
                    pool_identifier="FINAL_SEGMENTS",
                    entry_id="entry_a",
                    selector_json='{"kind":"section","section_index":0}',
                )
            )

        for i in range(2):
            store.upsert_chunk(
                ChunkMetadata(
                    chunk_id=f"chunk_b_{i}",
                    label=i + 10,
                    dossier_id="dossier_1",
                    pool_identifier="FINAL_SEGMENTS",
                    entry_id="entry_b",
                    selector_json='{"kind":"section","section_index":0}',
                )
            )

        store.upsert_chunk(
            ChunkMetadata(
                chunk_id="chunk_other",
                label=99,
                dossier_id="dossier_2",
                pool_identifier="FINAL_SEGMENTS",
                entry_id="entry_a",
                selector_json='{"kind":"section","section_index":0}',
            )
        )

        labels_a = store.list_labels_for_entry("FINAL_SEGMENTS", "dossier_1", "entry_a")
        assert set(labels_a) == {0, 1, 2}

        labels_b = store.list_labels_for_entry("FINAL_SEGMENTS", "dossier_1", "entry_b")
        assert set(labels_b) == {10, 11}

        labels_none = store.list_labels_for_entry("FINAL_SEGMENTS", "dossier_1", "missing")
        assert labels_none == []


def test_mark_deleted():
    """Store can mark labels as deleted (tombstone)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "metadata.db"
        store = VectorMetadataStore(db_path)

        # Insert chunks
        for i in range(5):
            store.upsert_chunk(
                ChunkMetadata(
                    chunk_id=f"chunk_{i}",
                    label=i,
                    dossier_id="dossier_1",
                    pool_identifier="FINAL_SEGMENTS",
                    entry_id=f"entry_{i}",
                    selector_json='{"kind":"section","section_index":0}',
                )
            )

        # All should be active
        assert store.count_active_chunks() == 5

        # Mark labels 1 and 3 as deleted
        store.mark_deleted([1, 3])

        # Count active should decrease
        assert store.count_active_chunks() == 3

        # Verify deleted chunks have is_deleted=True
        chunk1 = store.lookup_by_label(1)
        assert chunk1 is not None
        assert chunk1.is_deleted is True

        chunk3 = store.lookup_by_label(3)
        assert chunk3 is not None
        assert chunk3.is_deleted is True

        # Non-deleted chunks should still be active
        chunk0 = store.lookup_by_label(0)
        assert chunk0 is not None
        assert chunk0.is_deleted is False


def test_get_next_label():
    """Store can provide next available label."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "metadata.db"
        store = VectorMetadataStore(db_path)

        # Empty store should return 0
        assert store.get_next_label() == 0

        # Insert some chunks
        store.upsert_chunk(
            ChunkMetadata(
                chunk_id="chunk_0",
                label=0,
                dossier_id="dossier_1",
                pool_identifier="FINAL_SEGMENTS",
                entry_id="entry_0",
                selector_json='{"kind":"section","section_index":0}',
            )
        )

        assert store.get_next_label() == 1

        store.upsert_chunk(
            ChunkMetadata(
                chunk_id="chunk_5",
                label=5,
                dossier_id="dossier_1",
                pool_identifier="FINAL_SEGMENTS",
                entry_id="entry_5",
                selector_json='{"kind":"section","section_index":0}',
            )
        )

        # Should return max + 1
        assert store.get_next_label() == 6


def test_lookup_missing_returns_none():
    """Lookup for non-existent chunk/label returns None."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "metadata.db"
        store = VectorMetadataStore(db_path)

        assert store.lookup_by_chunk_id("nonexistent") is None
        assert store.lookup_by_label(999) is None


def test_indexed_entry_state_upsert_and_get():
    """Store can upsert and read indexed_entry_state rows."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "metadata.db"
        store = VectorMetadataStore(db_path)

        missing = store.get_indexed_entry_state(
            pool_identifier="FINAL_SEGMENTS",
            dossier_id="dossier_1",
            entry_id="entry_1",
        )
        assert missing is None

        store.upsert_indexed_entry_state(
            pool_identifier="FINAL_SEGMENTS",
            dossier_id="dossier_1",
            entry_id="entry_1",
            indexed_signature="sig_v1",
            embedding_model_fingerprint="model_v1",
            chunking_policy_id="policy_v1",
        )

        retrieved = store.get_indexed_entry_state(
            pool_identifier="FINAL_SEGMENTS",
            dossier_id="dossier_1",
            entry_id="entry_1",
        )
        assert retrieved is not None
        assert isinstance(retrieved, IndexedEntryState)
        assert retrieved.indexed_signature == "sig_v1"
        assert retrieved.embedding_model_fingerprint == "model_v1"
        assert retrieved.chunking_policy_id == "policy_v1"

        store.upsert_indexed_entry_state(
            pool_identifier="FINAL_SEGMENTS",
            dossier_id="dossier_1",
            entry_id="entry_1",
            indexed_signature="sig_v2",
            embedding_model_fingerprint="model_v2",
            chunking_policy_id="policy_v2",
        )

        updated = store.get_indexed_entry_state(
            pool_identifier="FINAL_SEGMENTS",
            dossier_id="dossier_1",
            entry_id="entry_1",
        )
        assert updated is not None
        assert updated.indexed_signature == "sig_v2"
        assert updated.embedding_model_fingerprint == "model_v2"
        assert updated.chunking_policy_id == "policy_v2"


def test_schema_version_mismatch_detection():
    """Metadata store detects and fails on schema version mismatch."""
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"

        # Create DB with old schema version
        conn = sqlite3.connect(db_path)
        try:
            cursor = conn.cursor()
            # Create tables manually
            cursor.execute(
                """
                CREATE TABLE chunk_metadata (
                    chunk_id TEXT PRIMARY KEY,
                    label INTEGER NOT NULL UNIQUE,
                    dossier_id TEXT,
                    pool_identifier TEXT NOT NULL,
                    entry_id TEXT NOT NULL,
                    selector_json TEXT NOT NULL,
                    preview TEXT,
                    segment_id TEXT,
                    draft_id TEXT,
                    is_deleted INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE schema_version (
                    version INTEGER PRIMARY KEY
                )
                """
            )
            # Insert old version (current is 4, use 3)
            cursor.execute("INSERT INTO schema_version (version) VALUES (?)", (3,))
            conn.commit()
        finally:
            conn.close()

        # Attempt to open with current code should fail with clear error
        try:
            store = VectorMetadataStore(db_path)
            assert False, "Should have raised RuntimeError for schema mismatch"
        except RuntimeError as e:
            assert "schema version mismatch" in str(e).lower()
            assert "database has version 3" in str(e)
            assert "code expects version 4" in str(e)
            assert "rebuild" in str(e).lower()
