"""
SQLite Vector Metadata Store
=============================

Maps external chunk_id strings to internal HNSW integer labels and stores
chunk metadata for retrieval operations.

Key responsibilities:
- Bidirectional mapping: chunk_id ↔ label (int64)
- Chunk metadata storage (entry_ref, selector, dossier_id for slicing)
- Replace-slice support: list labels by (dossier_id, pool)
- Tombstone tracking for deleted vectors
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple


# -----------------------------------------------------------------------------
# Schema Version
# -----------------------------------------------------------------------------

METADATA_SCHEMA_VERSION = 4


# -----------------------------------------------------------------------------
# Metadata Models
# -----------------------------------------------------------------------------


@dataclass(frozen=True)
class ChunkMetadata:
    """
    Metadata for a single chunk in the vector index.

    Attributes:
        chunk_id: External stable identifier (hash-based)
        label: Internal HNSW integer label
        dossier_id: Dossier this chunk belongs to (for replace-slice)
        pool_identifier: Pool/view this chunk belongs to (e.g., "FINAL_SEGMENTS")
        entry_id: Corpus entry identifier
        selector_json: JSON-serialized ChunkSelector for reconstruction
        preview: Short deterministic excerpt for triage/debug (max ~200 chars)
        segment_id: Segment identifier (for FINAL_SEGMENTS CorpusEntryRef reconstruction)
        draft_id: Draft identifier (for FINAL_SEGMENTS CorpusEntryRef reconstruction)
        is_deleted: Tombstone flag (True = deleted, False = active)
    """

    chunk_id: str
    label: int
    dossier_id: Optional[str]
    pool_identifier: str
    entry_id: str
    selector_json: str
    preview: Optional[str] = None
    segment_id: Optional[str] = None
    draft_id: Optional[str] = None
    is_deleted: bool = False


@dataclass(frozen=True)
class IndexedEntryState:
    """
    Persistent indexed state for a single entry slice.

    Attributes:
        pool_identifier: Pool/view identifier (e.g., "FINAL_SEGMENTS")
        dossier_id: Dossier identifier
        entry_id: Corpus entry identifier
        indexed_signature: Content signature captured at index time
        embedding_model_fingerprint: Embedding model fingerprint used
        chunking_policy_id: Chunking policy identifier/hash used
    """

    pool_identifier: str
    dossier_id: str
    entry_id: str
    indexed_signature: str
    embedding_model_fingerprint: str
    chunking_policy_id: str


# -----------------------------------------------------------------------------
# VectorMetadataStore
# -----------------------------------------------------------------------------


class VectorMetadataStore:
    """
    SQLite-backed metadata store for vector index chunks.

    Manages bidirectional mapping between chunk_id (external) and label (internal),
    plus metadata needed for retrieval and replace-slice operations.
    """

    def __init__(self, db_path: Path):
        """
        Initialize metadata store.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        """Create schema if it doesn't exist."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()

            # Metadata table
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS chunk_metadata (
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

            # Index for fast label lookup
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_label
                ON chunk_metadata(label)
                """
            )

            # Index for replace-slice queries (dossier + pool)
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_dossier_pool
                ON chunk_metadata(dossier_id, pool_identifier)
                """
            )

            # Indexed entry state table
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS indexed_entry_state (
                    pool_identifier TEXT NOT NULL,
                    dossier_id TEXT NOT NULL,
                    entry_id TEXT NOT NULL,
                    indexed_signature TEXT NOT NULL,
                    embedding_model_fingerprint TEXT NOT NULL,
                    chunking_policy_id TEXT NOT NULL,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (pool_identifier, dossier_id, entry_id)
                )
                """
            )

            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_indexed_entry_state_identity
                ON indexed_entry_state(pool_identifier, dossier_id, entry_id)
                """
            )

            # Schema version tracking
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_version (
                    version INTEGER PRIMARY KEY
                )
                """
            )

            # Check schema version compatibility
            cursor.execute("SELECT version FROM schema_version LIMIT 1")
            row = cursor.fetchone()
            if row is None:
                # New DB: insert current schema version
                cursor.execute("INSERT INTO schema_version (version) VALUES (?)", (METADATA_SCHEMA_VERSION,))
            else:
                # Existing DB: verify schema version matches
                existing_version = row[0]
                if existing_version != METADATA_SCHEMA_VERSION:
                    raise RuntimeError(
                        f"Metadata store schema version mismatch: "
                        f"database has version {existing_version}, "
                        f"but code expects version {METADATA_SCHEMA_VERSION}. "
                        f"Rebuild the index or downgrade code to match DB version."
                    )

            conn.commit()
        finally:
            conn.close()

    def upsert_chunk(self, metadata: ChunkMetadata) -> None:
        """
        Insert or update chunk metadata.

        Args:
            metadata: ChunkMetadata to upsert
        """
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO chunk_metadata
                (chunk_id, label, dossier_id, pool_identifier, entry_id, selector_json, preview, segment_id, draft_id, is_deleted)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(chunk_id) DO UPDATE SET
                    label = excluded.label,
                    dossier_id = excluded.dossier_id,
                    pool_identifier = excluded.pool_identifier,
                    entry_id = excluded.entry_id,
                    selector_json = excluded.selector_json,
                    preview = excluded.preview,
                    segment_id = excluded.segment_id,
                    draft_id = excluded.draft_id,
                    is_deleted = excluded.is_deleted
                """,
                (
                    metadata.chunk_id,
                    metadata.label,
                    metadata.dossier_id,
                    metadata.pool_identifier,
                    metadata.entry_id,
                    metadata.selector_json,
                    metadata.preview,
                    metadata.segment_id,
                    metadata.draft_id,
                    1 if metadata.is_deleted else 0,
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def lookup_by_chunk_id(self, chunk_id: str) -> Optional[ChunkMetadata]:
        """
        Lookup metadata by chunk_id.

        Args:
            chunk_id: External chunk identifier

        Returns:
            ChunkMetadata if found, None otherwise
        """
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT chunk_id, label, dossier_id, pool_identifier, entry_id, selector_json, preview, segment_id, draft_id, is_deleted
                FROM chunk_metadata
                WHERE chunk_id = ?
                """,
                (chunk_id,),
            )
            row = cursor.fetchone()
            if row is None:
                return None

            return ChunkMetadata(
                chunk_id=row[0],
                label=row[1],
                dossier_id=row[2],
                pool_identifier=row[3],
                entry_id=row[4],
                selector_json=row[5],
                preview=row[6],
                segment_id=row[7],
                draft_id=row[8],
                is_deleted=bool(row[9]),
            )
        finally:
            conn.close()

    def lookup_by_label(self, label: int) -> Optional[ChunkMetadata]:
        """
        Lookup metadata by internal label.

        Args:
            label: Internal HNSW label

        Returns:
            ChunkMetadata if found, None otherwise
        """
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT chunk_id, label, dossier_id, pool_identifier, entry_id, selector_json, preview, segment_id, draft_id, is_deleted
                FROM chunk_metadata
                WHERE label = ?
                """,
                (label,),
            )
            row = cursor.fetchone()
            if row is None:
                return None

            return ChunkMetadata(
                chunk_id=row[0],
                label=row[1],
                dossier_id=row[2],
                pool_identifier=row[3],
                entry_id=row[4],
                selector_json=row[5],
                preview=row[6],
                segment_id=row[7],
                draft_id=row[8],
                is_deleted=bool(row[9]),
            )
        finally:
            conn.close()

    def list_labels_for_slice(self, dossier_id: str, pool_identifier: str) -> List[int]:
        """
        List all labels for a specific (dossier_id, pool) slice.

        Used for replace-slice operations to find all vectors to tombstone.

        Args:
            dossier_id: Dossier identifier
            pool_identifier: Pool/view identifier

        Returns:
            List of internal labels
        """
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT label
                FROM chunk_metadata
                WHERE dossier_id = ? AND pool_identifier = ?
                """,
                (dossier_id, pool_identifier),
            )
            return [row[0] for row in cursor.fetchall()]
        finally:
            conn.close()

    def list_labels_for_entry(
        self, pool_identifier: str, dossier_id: str, entry_id: str
    ) -> List[int]:
        """
        List all labels for a specific (pool, dossier, entry) slice.

        Args:
            pool_identifier: Pool/view identifier
            dossier_id: Dossier identifier
            entry_id: Corpus entry identifier

        Returns:
            List of internal labels
        """
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT label
                FROM chunk_metadata
                WHERE pool_identifier = ? AND dossier_id = ? AND entry_id = ?
                """,
                (pool_identifier, dossier_id, entry_id),
            )
            return [row[0] for row in cursor.fetchall()]
        finally:
            conn.close()

    def upsert_indexed_entry_state(
        self,
        *,
        pool_identifier: str,
        dossier_id: str,
        entry_id: str,
        indexed_signature: str,
        embedding_model_fingerprint: str,
        chunking_policy_id: str,
    ) -> None:
        """
        Upsert indexed state for a specific entry slice.
        """
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO indexed_entry_state (
                    pool_identifier,
                    dossier_id,
                    entry_id,
                    indexed_signature,
                    embedding_model_fingerprint,
                    chunking_policy_id,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(pool_identifier, dossier_id, entry_id) DO UPDATE SET
                    indexed_signature = excluded.indexed_signature,
                    embedding_model_fingerprint = excluded.embedding_model_fingerprint,
                    chunking_policy_id = excluded.chunking_policy_id,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    pool_identifier,
                    dossier_id,
                    entry_id,
                    indexed_signature,
                    embedding_model_fingerprint,
                    chunking_policy_id,
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def get_indexed_entry_state(
        self, *, pool_identifier: str, dossier_id: str, entry_id: str
    ) -> Optional[IndexedEntryState]:
        """
        Fetch indexed state for a specific entry slice.
        """
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT pool_identifier, dossier_id, entry_id,
                       indexed_signature, embedding_model_fingerprint, chunking_policy_id
                FROM indexed_entry_state
                WHERE pool_identifier = ? AND dossier_id = ? AND entry_id = ?
                """,
                (pool_identifier, dossier_id, entry_id),
            )
            row = cursor.fetchone()
            if row is None:
                return None

            return IndexedEntryState(
                pool_identifier=row[0],
                dossier_id=row[1],
                entry_id=row[2],
                indexed_signature=row[3],
                embedding_model_fingerprint=row[4],
                chunking_policy_id=row[5],
            )
        finally:
            conn.close()

    def list_indexed_entry_keys(
        self, *, pool_identifier: str, dossier_id: Optional[str] = None
    ) -> List[Tuple[str, str]]:
        """
        List indexed entry keys for a pool (optionally filtered by dossier).

        Returns:
            List of (dossier_id, entry_id) tuples.
        """
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            if dossier_id:
                cursor.execute(
                    """
                    SELECT dossier_id, entry_id
                    FROM indexed_entry_state
                    WHERE pool_identifier = ? AND dossier_id = ?
                    ORDER BY dossier_id, entry_id
                    """,
                    (pool_identifier, dossier_id),
                )
            else:
                cursor.execute(
                    """
                    SELECT dossier_id, entry_id
                    FROM indexed_entry_state
                    WHERE pool_identifier = ?
                    ORDER BY dossier_id, entry_id
                    """,
                    (pool_identifier,),
                )
            return [(row[0], row[1]) for row in cursor.fetchall()]
        finally:
            conn.close()

    def delete_indexed_entry_state(
        self, *, pool_identifier: str, dossier_id: str, entry_id: str
    ) -> None:
        """
        Delete indexed entry state for a specific entry slice.
        """
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                DELETE FROM indexed_entry_state
                WHERE pool_identifier = ? AND dossier_id = ? AND entry_id = ?
                """,
                (pool_identifier, dossier_id, entry_id),
            )
            conn.commit()
        finally:
            conn.close()

    def mark_deleted(self, labels: List[int]) -> None:
        """
        Mark labels as deleted (tombstone).

        Args:
            labels: List of internal labels to tombstone
        """
        if not labels:
            return

        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            # Use parameterized query with placeholders
            placeholders = ",".join("?" * len(labels))
            cursor.execute(
                f"""
                UPDATE chunk_metadata
                SET is_deleted = 1
                WHERE label IN ({placeholders})
                """,
                labels,
            )
            conn.commit()
        finally:
            conn.close()

    def count_active_chunks(self) -> int:
        """
        Count active (non-deleted) chunks.

        Returns:
            Number of active chunks
        """
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM chunk_metadata WHERE is_deleted = 0")
            return cursor.fetchone()[0]
        finally:
            conn.close()

    def count_deleted_chunks(self) -> int:
        """
        Count deleted chunk rows (is_deleted=1).

        Returns:
            Number of deleted chunk rows
        """
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM chunk_metadata WHERE is_deleted = 1")
            return cursor.fetchone()[0]
        finally:
            conn.close()

    def count_tombstoned_chunks(self) -> int:
        """
        Count deleted chunk rows (legacy name for count_deleted_chunks).

        Returns:
            Number of deleted chunk rows
        """
        return self.count_deleted_chunks()

    def delete_tombstones(self) -> int:
        """
        Permanently delete all tombstoned (is_deleted=1) entries from metadata.

        Returns:
            Number of tombstoned entries deleted
        """
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM chunk_metadata WHERE is_deleted = 1")
            deleted_count = cursor.rowcount
            conn.commit()
            return deleted_count
        finally:
            conn.close()

    def list_all_active_chunks(self) -> List[ChunkMetadata]:
        """
        List all active (non-deleted) chunks.

        Returns:
            List of ChunkMetadata for all active chunks
        """
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT chunk_id, label, dossier_id, pool_identifier, entry_id, selector_json, preview, segment_id, draft_id, is_deleted
                FROM chunk_metadata
                WHERE is_deleted = 0
                ORDER BY label ASC
                """
            )
            rows = cursor.fetchall()
            return [
                ChunkMetadata(
                    chunk_id=row[0],
                    label=row[1],
                    dossier_id=row[2],
                    pool_identifier=row[3],
                    entry_id=row[4],
                    selector_json=row[5],
                    preview=row[6],
                    segment_id=row[7],
                    draft_id=row[8],
                    is_deleted=bool(row[9]),
                )
                for row in rows
            ]
        finally:
            conn.close()

    def get_next_label(self) -> int:
        """
        Get the next available label value.

        Returns:
            Next label (max existing label + 1, or 0 if no labels exist)
        """
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT MAX(label) FROM chunk_metadata")
            max_label = cursor.fetchone()[0]
            return (max_label + 1) if max_label is not None else 0
        finally:
            conn.close()
