"""
Tests for semantic index manifest and path helpers.

Validates:
- Manifest round-trip serialization
- Path resolution under assets root
- Deterministic behavior
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from .manifest import (
    MANIFEST_SCHEMA_VERSION,
    SemanticIndexManifest,
    hnsw_index_path,
    manifest_exists,
    manifest_path,
    metadata_db_path,
    read_manifest,
    semantic_index_pool_root,
    semantic_index_root,
    write_manifest,
)


def test_manifest_round_trip():
    """Manifest can be serialized to dict and back deterministically."""
    manifest = SemanticIndexManifest(
        schema_version=MANIFEST_SCHEMA_VERSION,
        pool_identifier="FINAL_SEGMENTS",
        embedding_dim=384,
        embedding_model_id="bge-small-en-v1.5",
        chunking_policy_id="final_segments_v1",
        created_at="2026-01-11T00:00:00Z",
        updated_at="2026-01-11T01:00:00Z",
    )

    # Round-trip via dict
    as_dict = manifest.to_dict()
    restored = SemanticIndexManifest.from_dict(as_dict)

    assert restored == manifest
    assert restored.schema_version == MANIFEST_SCHEMA_VERSION
    assert restored.pool_identifier == "FINAL_SEGMENTS"
    assert restored.embedding_dim == 384
    assert restored.embedding_model_id == "bge-small-en-v1.5"
    assert restored.chunking_policy_id == "final_segments_v1"
    assert restored.created_at == "2026-01-11T00:00:00Z"
    assert restored.updated_at == "2026-01-11T01:00:00Z"


def test_manifest_json_serializable():
    """Manifest dict is JSON-serializable."""
    manifest = SemanticIndexManifest(
        schema_version=MANIFEST_SCHEMA_VERSION,
        pool_identifier="FINAL_SEGMENTS",
        embedding_dim=384,
        embedding_model_id="bge-small-en-v1.5",
        chunking_policy_id="final_segments_v1",
    )

    as_dict = manifest.to_dict()
    json_str = json.dumps(as_dict)
    restored_dict = json.loads(json_str)

    assert restored_dict["schema_version"] == MANIFEST_SCHEMA_VERSION
    assert restored_dict["pool_identifier"] == "FINAL_SEGMENTS"
    assert restored_dict["embedding_dim"] == 384


def test_paths_resolve_under_assets_root():
    """Path helpers resolve under the existing assets root."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)

        # Mock assets_root to use temp directory
        with patch("retrieval.lanes.semantic.manifest.assets_root", return_value=tmp_path):
            # Verify root path is created under assets
            root = semantic_index_root()
            assert root == tmp_path / "semantic_indexes"
            assert root.exists()

            # Verify pool-specific root
            pool_root = semantic_index_pool_root("FINAL_SEGMENTS")
            assert pool_root == tmp_path / "semantic_indexes" / "FINAL_SEGMENTS"
            assert pool_root.exists()

            # Verify artifact paths
            manifest_file = manifest_path("FINAL_SEGMENTS")
            hnsw_file = hnsw_index_path("FINAL_SEGMENTS")
            metadata_file = metadata_db_path("FINAL_SEGMENTS")

            assert manifest_file == pool_root / "manifest.json"
            assert hnsw_file == pool_root / "hnsw.bin"
            assert metadata_file == pool_root / "metadata.db"


def test_write_and_read_manifest():
    """Manifest can be written and read back from disk."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)

        with patch("retrieval.lanes.semantic.manifest.assets_root", return_value=tmp_path):
            pool_id = "FINAL_SEGMENTS"

            # Write manifest
            manifest = SemanticIndexManifest(
                schema_version=MANIFEST_SCHEMA_VERSION,
                pool_identifier=pool_id,
                embedding_dim=384,
                embedding_model_id="bge-small-en-v1.5",
                chunking_policy_id="final_segments_v1",
                created_at="2026-01-11T00:00:00Z",
            )

            write_manifest(pool_id, manifest)

            # Verify file exists
            assert manifest_exists(pool_id)

            # Read back
            restored = read_manifest(pool_id)

            assert restored is not None
            assert restored.schema_version == MANIFEST_SCHEMA_VERSION
            assert restored.pool_identifier == pool_id
            assert restored.embedding_dim == 384
            assert restored.embedding_model_id == "bge-small-en-v1.5"
            assert restored.chunking_policy_id == "final_segments_v1"
            assert restored.created_at == "2026-01-11T00:00:00Z"


def test_read_manifest_missing():
    """Reading non-existent manifest returns None."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)

        with patch("retrieval.lanes.semantic.manifest.assets_root", return_value=tmp_path):
            pool_id = "NONEXISTENT"

            assert not manifest_exists(pool_id)
            assert read_manifest(pool_id) is None


def test_read_manifest_corrupt():
    """Reading corrupt manifest returns None."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)

        with patch("retrieval.lanes.semantic.manifest.assets_root", return_value=tmp_path):
            pool_id = "FINAL_SEGMENTS"

            # Write corrupt JSON
            path = manifest_path(pool_id)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("{invalid json", encoding="utf-8")

            # Should return None for corrupt manifest
            assert read_manifest(pool_id) is None


def test_manifest_deterministic():
    """Multiple writes of same manifest produce identical files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)

        with patch("retrieval.lanes.semantic.manifest.assets_root", return_value=tmp_path):
            pool_id = "FINAL_SEGMENTS"

            manifest = SemanticIndexManifest(
                schema_version=MANIFEST_SCHEMA_VERSION,
                pool_identifier=pool_id,
                embedding_dim=384,
                embedding_model_id="bge-small-en-v1.5",
                chunking_policy_id="final_segments_v1",
            )

            # Write twice
            write_manifest(pool_id, manifest)
            content1 = manifest_path(pool_id).read_text(encoding="utf-8")

            write_manifest(pool_id, manifest)
            content2 = manifest_path(pool_id).read_text(encoding="utf-8")

            # Should be identical
            assert content1 == content2


def test_manifest_includes_fingerprint():
    """Manifest preserves embedding_model_fingerprint field in round-trip."""
    with tempfile.TemporaryDirectory() as tmpdir:
        with mock_semantic_index_root(tmpdir):
            pool_id = "TEST_FINGERPRINT_POOL"

            # Create manifest with fingerprint
            manifest = SemanticIndexManifest(
                schema_version=MANIFEST_SCHEMA_VERSION,
                pool_identifier=pool_id,
                embedding_dim=384,
                embedding_model_id="all-MiniLM-L6-v2",
                embedding_model_fingerprint="all-MiniLM-L6-v2:abc123def456",
                chunking_policy_id="final_segments_v1",
                created_at="2026-01-14T00:00:00Z",
                updated_at="2026-01-14T00:00:00Z",
            )

            # Write and read back
            write_manifest(pool_id, manifest)
            restored = read_manifest(pool_id)

            assert restored is not None
            assert restored.embedding_model_fingerprint == "all-MiniLM-L6-v2:abc123def456"
            assert restored.embedding_model_id == "all-MiniLM-L6-v2"


def test_manifest_without_fingerprint_backward_compat():
    """Manifest without fingerprint field (old format) loads correctly."""
    with tempfile.TemporaryDirectory() as tmpdir:
        with mock_semantic_index_root(tmpdir):
            pool_id = "TEST_BACKWARD_COMPAT"
            path = manifest_path(pool_id)
            path.parent.mkdir(parents=True, exist_ok=True)

            # Write old-format manifest (no fingerprint field)
            old_manifest = {
                "schema_version": "v1",
                "pool_identifier": pool_id,
                "embedding_dim": 384,
                "embedding_model_id": "all-MiniLM-L6-v2",
                "chunking_policy_id": "final_segments_v1",
                "created_at": "2026-01-14T00:00:00Z",
                "updated_at": "2026-01-14T00:00:00Z",
            }

            with open(path, "w", encoding="utf-8") as f:
                json.dump(old_manifest, f)

            # Read should succeed with fingerprint=None
            restored = read_manifest(pool_id)
            assert restored is not None
            assert restored.embedding_model_fingerprint is None
            assert restored.embedding_model_id == "all-MiniLM-L6-v2"
