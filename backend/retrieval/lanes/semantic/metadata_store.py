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

METADATA_SCHEMA_VERSION = 1


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
        is_deleted: Tombstone flag (True = deleted, False = active)
    """

    chunk_id: str
    label: int
    dossier_id: Optional[str]
    pool_identifier: str
    entry_id: str
    selector_json: str
    is_deleted: bool = False


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

            # Schema version tracking
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_version (
                    version INTEGER PRIMARY KEY
                )
                """
            )

            # Insert schema version if not present
            cursor.execute("SELECT version FROM schema_version LIMIT 1")
            if cursor.fetchone() is None:
                cursor.execute("INSERT INTO schema_version (version) VALUES (?)", (METADATA_SCHEMA_VERSION,))

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
                (chunk_id, label, dossier_id, pool_identifier, entry_id, selector_json, is_deleted)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(chunk_id) DO UPDATE SET
                    label = excluded.label,
                    dossier_id = excluded.dossier_id,
                    pool_identifier = excluded.pool_identifier,
                    entry_id = excluded.entry_id,
                    selector_json = excluded.selector_json,
                    is_deleted = excluded.is_deleted
                """,
                (
                    metadata.chunk_id,
                    metadata.label,
                    metadata.dossier_id,
                    metadata.pool_identifier,
                    metadata.entry_id,
                    metadata.selector_json,
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
                SELECT chunk_id, label, dossier_id, pool_identifier, entry_id, selector_json, is_deleted
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
                is_deleted=bool(row[6]),
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
                SELECT chunk_id, label, dossier_id, pool_identifier, entry_id, selector_json, is_deleted
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
                is_deleted=bool(row[6]),
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
