"""
Semantic Index Artifact Manifest and Path Helpers
==================================================

Manages manifest files for semantic vector indexes.

Key responsibilities:
- Define manifest schema for index state (pool, embedding config, chunking policy)
- Provide path helpers for index artifacts (scoped under assets root)
- Round-trip JSON serialization for manifest state
- Deterministic manifest validation
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from config.paths import assets_root


# -----------------------------------------------------------------------------
# Manifest Models
# -----------------------------------------------------------------------------


@dataclass(frozen=True)
class SemanticIndexManifest:
    """
    Manifest for a semantic vector index.

    Attributes:
        schema_version: Manifest schema version for compatibility tracking
        pool_identifier: Which corpus pool/view is indexed (e.g., "FINAL_SEGMENTS")
        embedding_dim: Vector dimensionality
        embedding_model_id: Model identifier for tracking model changes
        embedding_model_fingerprint: Model fingerprint for detecting model weight changes (optional)
        chunking_policy_id: Chunking policy identifier for tracking policy changes
        created_at: ISO timestamp of index creation
        updated_at: ISO timestamp of last index update
    """

    schema_version: str
    pool_identifier: str
    embedding_dim: int
    embedding_model_id: str
    chunking_policy_id: str
    embedding_model_fingerprint: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    def to_dict(self) -> dict:
        """Convert to JSON-serializable dict."""
        return {
            "schema_version": self.schema_version,
            "pool_identifier": self.pool_identifier,
            "embedding_dim": self.embedding_dim,
            "embedding_model_id": self.embedding_model_id,
            "embedding_model_fingerprint": self.embedding_model_fingerprint,
            "chunking_policy_id": self.chunking_policy_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> SemanticIndexManifest:
        """Create from dict (loaded from JSON)."""
        return cls(
            schema_version=data["schema_version"],
            pool_identifier=data["pool_identifier"],
            embedding_dim=data["embedding_dim"],
            embedding_model_id=data["embedding_model_id"],
            chunking_policy_id=data["chunking_policy_id"],
            embedding_model_fingerprint=data.get("embedding_model_fingerprint"),
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
        )


# Current schema version (increment when manifest structure changes)
MANIFEST_SCHEMA_VERSION = "v1"


# -----------------------------------------------------------------------------
# Path Helpers
# -----------------------------------------------------------------------------


def semantic_index_root() -> Path:
    """
    Root directory for all semantic index artifacts.

    Returns path under existing assets root (dev-safe and frozen-safe).
    """
    root = assets_root() / "semantic_indexes"
    root.mkdir(parents=True, exist_ok=True)
    return root


def semantic_index_pool_root(pool_identifier: str) -> Path:
    """
    Root directory for a specific pool's semantic index artifacts.

    Args:
        pool_identifier: Pool/view identifier (e.g., "FINAL_SEGMENTS")

    Returns:
        Path to pool-specific index directory
    """
    pool_root = semantic_index_root() / pool_identifier
    pool_root.mkdir(parents=True, exist_ok=True)
    return pool_root


def manifest_path(pool_identifier: str) -> Path:
    """
    Path to the manifest file for a pool's semantic index.

    Args:
        pool_identifier: Pool/view identifier

    Returns:
        Path to manifest.json
    """
    return semantic_index_pool_root(pool_identifier) / "manifest.json"


def hnsw_index_path(pool_identifier: str) -> Path:
    """
    Path to the HNSW index binary file for a pool.

    Args:
        pool_identifier: Pool/view identifier

    Returns:
        Path to hnsw.bin
    """
    return semantic_index_pool_root(pool_identifier) / "hnsw.bin"


def metadata_db_path(pool_identifier: str) -> Path:
    """
    Path to the SQLite metadata database for a pool.

    Args:
        pool_identifier: Pool/view identifier

    Returns:
        Path to metadata.db
    """
    return semantic_index_pool_root(pool_identifier) / "metadata.db"


# -----------------------------------------------------------------------------
# Manifest I/O
# -----------------------------------------------------------------------------


def write_manifest(pool_identifier: str, manifest: SemanticIndexManifest) -> None:
    """
    Write manifest to disk.

    Args:
        pool_identifier: Pool/view identifier
        manifest: Manifest object to write
    """
    path = manifest_path(pool_identifier)
    path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(manifest.to_dict(), f, indent=2, ensure_ascii=False)


def read_manifest(pool_identifier: str) -> Optional[SemanticIndexManifest]:
    """
    Read manifest from disk.

    Args:
        pool_identifier: Pool/view identifier

    Returns:
        Manifest object if exists and valid, None otherwise
    """
    path = manifest_path(pool_identifier)

    if not path.exists():
        return None

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return SemanticIndexManifest.from_dict(data)
    except (json.JSONDecodeError, KeyError, TypeError):
        # Corrupt or invalid manifest
        return None


def manifest_exists(pool_identifier: str) -> bool:
    """
    Check if manifest file exists for a pool.

    Args:
        pool_identifier: Pool/view identifier

    Returns:
        True if manifest.json exists
    """
    return manifest_path(pool_identifier).exists()
