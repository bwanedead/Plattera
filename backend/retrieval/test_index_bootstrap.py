from __future__ import annotations

from pathlib import Path

from retrieval.engine.pool_maintenance import (
    BootstrapIdentity,
    PoolBootstrapStatus,
    bootstrap_pool_artifacts,
)
from retrieval.engine.reason_codes import DiagnosticReasonCode
from retrieval.lanes.semantic.manifest import (
    MANIFEST_SCHEMA_VERSION,
    SemanticIndexManifest,
    read_manifest,
    write_manifest,
)
from retrieval.lanes.semantic.metadata_store import VectorMetadataStore


class StubStore:
    def __init__(self, metadata_db_path: Path):
        self.metadata_store = VectorMetadataStore(metadata_db_path)

    def save(self, hnsw_path: Path, _metadata_path: Path) -> None:
        hnsw_path.write_text("stub", encoding="utf-8")


def _identity() -> BootstrapIdentity:
    return BootstrapIdentity(
        embedding_dim=4,
        embedding_model_id="embed-stub",
        embedding_model_fingerprint="embed-stub:fingerprint",
        chunking_policy_id="final_segments_v1",
    )


def test_bootstrap_creates_and_idempotent(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("retrieval.lanes.semantic.manifest.assets_root", lambda: tmp_path)
    monkeypatch.setattr(
        "retrieval.engine.pool_maintenance._resolve_bootstrap_identity",
        lambda **_kwargs: (_identity(), None),
    )
    monkeypatch.setattr(
        "retrieval.engine.pool_maintenance.create_persistent_store",
        lambda **kwargs: StubStore(kwargs["metadata_db_path"]),
    )

    report = bootstrap_pool_artifacts("FINAL_SEGMENTS")
    assert report.status == PoolBootstrapStatus.CREATED

    pool_root = tmp_path / "semantic_indexes" / "FINAL_SEGMENTS"
    assert (pool_root / "manifest.json").exists()
    assert (pool_root / "hnsw.bin").exists()
    assert (pool_root / "metadata.db").exists()

    report_again = bootstrap_pool_artifacts("FINAL_SEGMENTS")
    assert report_again.status == PoolBootstrapStatus.ALREADY_INITIALIZED


def test_bootstrap_missing_embeddings_no_mutation(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("retrieval.lanes.semantic.manifest.assets_root", lambda: tmp_path)
    monkeypatch.setattr(
        "retrieval.engine.pool_maintenance._resolve_bootstrap_identity",
        lambda **_kwargs: (None, "embedding_asset_missing"),
    )

    report = bootstrap_pool_artifacts("FINAL_SEGMENTS")
    assert report.status == PoolBootstrapStatus.EMBEDDINGS_MISSING
    assert report.reason_code == DiagnosticReasonCode.UNAVAILABLE_EMBEDDINGS_MISSING

    pool_root = tmp_path / "semantic_indexes" / "FINAL_SEGMENTS"
    assert not (pool_root / "manifest.json").exists()
    assert not (pool_root / "hnsw.bin").exists()
    assert not (pool_root / "metadata.db").exists()


def test_bootstrap_partial_missing_needs_force(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("retrieval.lanes.semantic.manifest.assets_root", lambda: tmp_path)
    monkeypatch.setattr(
        "retrieval.engine.pool_maintenance._resolve_bootstrap_identity",
        lambda **_kwargs: (_identity(), None),
    )
    monkeypatch.setattr(
        "retrieval.engine.pool_maintenance.create_persistent_store",
        lambda **kwargs: StubStore(kwargs["metadata_db_path"]),
    )

    write_manifest(
        "FINAL_SEGMENTS",
        SemanticIndexManifest(
            schema_version=MANIFEST_SCHEMA_VERSION,
            pool_identifier="FINAL_SEGMENTS",
            embedding_dim=4,
            embedding_model_id="embed-stub",
            embedding_model_fingerprint="embed-stub:fingerprint",
            chunking_policy_id="final_segments_v1",
        ),
    )

    report = bootstrap_pool_artifacts("FINAL_SEGMENTS")
    assert report.status == PoolBootstrapStatus.NEEDS_FORCE_REPAIR
    assert report.reason_code == DiagnosticReasonCode.UNAVAILABLE_NEEDS_FORCE_REPAIR

    pool_root = tmp_path / "semantic_indexes" / "FINAL_SEGMENTS"
    assert (pool_root / "manifest.json").exists()
    assert not (pool_root / "hnsw.bin").exists()
    assert not (pool_root / "metadata.db").exists()

    repaired = bootstrap_pool_artifacts("FINAL_SEGMENTS", force=True)
    assert repaired.status == PoolBootstrapStatus.REPAIRED
    assert (pool_root / "hnsw.bin").exists()
    assert (pool_root / "metadata.db").exists()


def test_bootstrap_identity_mismatch_needs_force(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("retrieval.lanes.semantic.manifest.assets_root", lambda: tmp_path)
    monkeypatch.setattr(
        "retrieval.engine.pool_maintenance._resolve_bootstrap_identity",
        lambda **_kwargs: (_identity(), None),
    )
    monkeypatch.setattr(
        "retrieval.engine.pool_maintenance.create_persistent_store",
        lambda **kwargs: StubStore(kwargs["metadata_db_path"]),
    )

    write_manifest(
        "FINAL_SEGMENTS",
        SemanticIndexManifest(
            schema_version=MANIFEST_SCHEMA_VERSION,
            pool_identifier="FINAL_SEGMENTS",
            embedding_dim=4,
            embedding_model_id="embed-stub",
            embedding_model_fingerprint="old-fingerprint",
            chunking_policy_id="final_segments_v1",
        ),
    )
    pool_root = tmp_path / "semantic_indexes" / "FINAL_SEGMENTS"
    (pool_root / "hnsw.bin").write_text("stub", encoding="utf-8")
    VectorMetadataStore(pool_root / "metadata.db")

    report = bootstrap_pool_artifacts("FINAL_SEGMENTS")
    assert report.status == PoolBootstrapStatus.NEEDS_FORCE_REPAIR

    current = read_manifest("FINAL_SEGMENTS")
    assert current is not None
    assert current.embedding_model_fingerprint == "old-fingerprint"

    repaired = bootstrap_pool_artifacts("FINAL_SEGMENTS", force=True)
    assert repaired.status == PoolBootstrapStatus.REPAIRED
    updated = read_manifest("FINAL_SEGMENTS")
    assert updated is not None
    assert updated.embedding_model_fingerprint == _identity().embedding_model_fingerprint
