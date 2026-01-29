from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Tuple

from corpus.interfaces import CorpusProvider

from ..lanes.semantic.chunking import FINAL_SEGMENTS_POLICY
from ..lanes.semantic.manifest import (
    MANIFEST_SCHEMA_VERSION,
    SemanticIndexManifest,
    manifest_path,
    hnsw_index_path,
    metadata_db_path,
    read_manifest,
    write_manifest,
)
from ..lanes.semantic.persistent_store import (
    PersistentVectorStore,
    create_persistent_store,
    load_persistent_store,
)
from ..lanes.semantic.embeddings import compute_model_fingerprint, SentenceTransformersEmbeddingProvider
from ..lanes.semantic.provider import EmbeddingAssetMissingError, resolve_embedding_model
from .diagnose import RuntimeIndexIdentity, SliceDiagnoser, SliceDiagnosis
from .inventory_provider import resolve_view_for_pool_identifier
from .reason_codes import DiagnosticReasonCode
from services.assets.service import AssetsService


class PoolOpenStatus(str, Enum):
    OK = "ok"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class PoolOpenReport:
    status: PoolOpenStatus
    reason_code: Optional[DiagnosticReasonCode]
    detail: Optional[str] = None
    action_hint: Optional[str] = None


@dataclass(frozen=True)
class PoolHealthReport:
    active_vectors: int
    active_chunks: int
    total_vectors: int
    tombstoned_vectors: int
    tombstone_ratio: float
    compact_recommended: bool
    vector_consistency_ok: bool
    consistency_reason: Optional[str] = None
    compact_threshold: Optional[float] = None


@dataclass(frozen=True)
class PoolMaintenanceReport:
    pool_identifier: str
    pool_open: PoolOpenReport
    pool_health: Optional[PoolHealthReport] = None
    slice_diagnoses: Optional[List[SliceDiagnosis]] = None


@dataclass(frozen=True)
class PoolOpenResult:
    report: PoolOpenReport
    store: Optional[PersistentVectorStore] = None


ACTION_HINT_REBUILD_POOL = "REBUILD_POOL"
ACTION_HINT_FORCE_REPAIR = "FORCE_REPAIR"


class PoolBootstrapStatus(str, Enum):
    CREATED = "created"
    REPAIRED = "repaired"
    ALREADY_INITIALIZED = "already_initialized"
    NEEDS_FORCE_REPAIR = "needs_force_repair"
    EMBEDDINGS_MISSING = "embeddings_missing"
    FAILED = "failed"


@dataclass(frozen=True)
class PoolBootstrapReport:
    pool_identifier: str
    status: PoolBootstrapStatus
    reason_code: Optional[DiagnosticReasonCode]
    detail: Optional[str] = None
    action_hint: Optional[str] = None


@dataclass(frozen=True)
class BootstrapIdentity:
    embedding_dim: int
    embedding_model_id: str
    embedding_model_fingerprint: str
    chunking_policy_id: str


_POOL_CACHE: Dict[str, Tuple[PersistentVectorStore, str]] = {}


def _compute_manifest_fingerprint(manifest: SemanticIndexManifest) -> str:
    """Compute a fingerprint for manifest state to invalidate cache."""
    return f"{manifest.schema_version}|{manifest.embedding_dim}|{manifest.embedding_model_fingerprint}|{manifest.chunking_policy_id}"


def safe_open_pool(pool_identifier: str) -> PoolOpenResult:
    """
    Safe pool-open boundary that never throws.

    Returns PoolOpenReport with stable reason codes for common failure modes.
    """
    manifest_file = manifest_path(pool_identifier)
    hnsw_path = hnsw_index_path(pool_identifier)
    metadata_path = metadata_db_path(pool_identifier)

    missing_files = [
        name
        for name, path in (
            ("manifest.json", manifest_file),
            ("hnsw.bin", hnsw_path),
            ("metadata.db", metadata_path),
        )
        if not path.exists()
    ]
    if missing_files:
        # Invalidate cache if files are missing
        if pool_identifier in _POOL_CACHE:
            del _POOL_CACHE[pool_identifier]
        return PoolOpenResult(
            report=PoolOpenReport(
                status=PoolOpenStatus.UNAVAILABLE,
                reason_code=DiagnosticReasonCode.UNAVAILABLE_UNKNOWN,
                detail=f"missing_files:{', '.join(missing_files)}",
                action_hint=ACTION_HINT_REBUILD_POOL,
            )
        )

    manifest = read_manifest(pool_identifier)
    if manifest is None:
        # Invalidate cache if manifest is missing
        if pool_identifier in _POOL_CACHE:
            del _POOL_CACHE[pool_identifier]
        return PoolOpenResult(
            report=PoolOpenReport(
                status=PoolOpenStatus.UNAVAILABLE,
                reason_code=DiagnosticReasonCode.UNAVAILABLE_UNKNOWN,
                detail="manifest_unavailable",
                action_hint=ACTION_HINT_REBUILD_POOL,
            )
        )

    fingerprint = _compute_manifest_fingerprint(manifest)
    if pool_identifier in _POOL_CACHE:
        cached_store, cached_fp = _POOL_CACHE[pool_identifier]
        if cached_fp == fingerprint:
            return PoolOpenResult(
                report=PoolOpenReport(
                    status=PoolOpenStatus.OK,
                    reason_code=None,
                    detail=None,
                    action_hint=None,
                ),
                store=cached_store,
            )

    try:
        store = load_persistent_store(
            pool_identifier=pool_identifier,
            embedding_dim=manifest.embedding_dim,
            hnsw_path=hnsw_path,
            metadata_db_path=metadata_path,
        )
        # Update cache
        _POOL_CACHE[pool_identifier] = (store, fingerprint)
        return PoolOpenResult(
            report=PoolOpenReport(
                status=PoolOpenStatus.OK,
                reason_code=None,
                detail=None,
                action_hint=None,
            ),
            store=store,
        )
    except Exception as exc:
        message = str(exc).lower()
        if "schema version mismatch" in message:
            return PoolOpenResult(
                report=PoolOpenReport(
                    status=PoolOpenStatus.UNAVAILABLE,
                    reason_code=DiagnosticReasonCode.UNAVAILABLE_SCHEMA_VERSION_MISMATCH,
                    detail="metadata_schema_version_mismatch",
                    action_hint=ACTION_HINT_REBUILD_POOL,
                )
            )
        return PoolOpenResult(
            report=PoolOpenReport(
                status=PoolOpenStatus.UNAVAILABLE,
                reason_code=DiagnosticReasonCode.UNAVAILABLE_UNKNOWN,
                detail=f"{type(exc).__name__}",
                action_hint=None,
            )
        )


def bootstrap_pool_artifacts(
    pool_identifier: str,
    *,
    force: bool = False,
    assets_service: Optional[AssetsService] = None,
) -> PoolBootstrapReport:
    """
    Ensure empty semantic index artifacts exist for a pool.

    Creates manifest.json, hnsw.bin, and metadata.db when all are missing.
    Returns stable status without mutating unless force=True for partial/mismatched artifacts.
    """
    identity, identity_detail = _resolve_bootstrap_identity(
        assets_service=assets_service or AssetsService()
    )
    if identity is None:
        return PoolBootstrapReport(
            pool_identifier=pool_identifier,
            status=PoolBootstrapStatus.EMBEDDINGS_MISSING,
            reason_code=DiagnosticReasonCode.UNAVAILABLE_EMBEDDINGS_MISSING,
            detail=identity_detail,
            action_hint=None,
        )

    manifest_file = manifest_path(pool_identifier)
    hnsw_path = hnsw_index_path(pool_identifier)
    metadata_path = metadata_db_path(pool_identifier)

    missing_files = [
        name
        for name, path in (
            ("manifest.json", manifest_file),
            ("hnsw.bin", hnsw_path),
            ("metadata.db", metadata_path),
        )
        if not path.exists()
    ]

    if missing_files:
        if len(missing_files) < 3 and not force:
            return PoolBootstrapReport(
                pool_identifier=pool_identifier,
                status=PoolBootstrapStatus.NEEDS_FORCE_REPAIR,
                reason_code=DiagnosticReasonCode.UNAVAILABLE_NEEDS_FORCE_REPAIR,
                detail=f"missing_files:{', '.join(missing_files)}",
                action_hint=ACTION_HINT_FORCE_REPAIR,
            )
        try:
            if force and len(missing_files) < 3:
                _clear_pool_artifacts(manifest_file, hnsw_path, metadata_path)
            _write_empty_pool_artifacts(
                pool_identifier=pool_identifier,
                identity=identity,
            )
        except Exception as exc:
            return PoolBootstrapReport(
                pool_identifier=pool_identifier,
                status=PoolBootstrapStatus.FAILED,
                reason_code=DiagnosticReasonCode.UNAVAILABLE_UNKNOWN,
                detail=f"bootstrap_failed:{type(exc).__name__}",
                action_hint=None,
            )
        status = (
            PoolBootstrapStatus.REPAIRED
            if force and len(missing_files) < 3
            else PoolBootstrapStatus.CREATED
        )
        return PoolBootstrapReport(
            pool_identifier=pool_identifier,
            status=status,
            reason_code=None,
            detail=None,
            action_hint=None,
        )

    manifest = read_manifest(pool_identifier)
    if manifest is None:
        return _handle_manifest_repair(
            pool_identifier=pool_identifier,
            manifest_file=manifest_file,
            hnsw_path=hnsw_path,
            metadata_path=metadata_path,
            identity=identity,
            force=force,
            detail="manifest_unavailable",
        )

    mismatch = _check_identity_mismatch(manifest, identity)
    if mismatch:
        return _handle_manifest_repair(
            pool_identifier=pool_identifier,
            manifest_file=manifest_file,
            hnsw_path=hnsw_path,
            metadata_path=metadata_path,
            identity=identity,
            force=force,
            detail=f"identity_mismatch:{mismatch}",
        )

    return PoolBootstrapReport(
        pool_identifier=pool_identifier,
        status=PoolBootstrapStatus.ALREADY_INITIALIZED,
        reason_code=None,
        detail=None,
        action_hint=None,
    )


def build_pool_health_report(
    store: PersistentVectorStore, *, threshold: float
) -> PoolHealthReport:
    stats = store.get_stats()
    active_chunks = stats["active_chunks"]
    total_vectors = stats["total_vectors"]
    if active_chunks == 0:
        vector_consistency_ok = True
        consistency_reason = None
    elif total_vectors == 0:
        vector_consistency_ok = False
        consistency_reason = DiagnosticReasonCode.UNAVAILABLE_VECTOR_INDEX_EMPTY.value
    elif total_vectors < active_chunks:
        vector_consistency_ok = False
        consistency_reason = (
            DiagnosticReasonCode.UNAVAILABLE_VECTOR_METADATA_MISMATCH.value
        )
    else:
        vector_consistency_ok = True
        consistency_reason = None
    return PoolHealthReport(
        active_vectors=active_chunks,
        active_chunks=active_chunks,
        total_vectors=total_vectors,
        tombstoned_vectors=stats["tombstoned_vectors"],
        tombstone_ratio=stats["tombstone_ratio"],
        compact_recommended=store.should_compact(threshold=threshold),
        vector_consistency_ok=vector_consistency_ok,
        consistency_reason=consistency_reason,
        compact_threshold=threshold,
    )


class PoolMaintenanceController:
    """
    UI/agent-facing maintenance surface for per-pool diagnostics.
    """

    def __init__(self, *, corpus_provider: CorpusProvider):
        self.corpus_provider = corpus_provider

    def diagnose_pool(
        self,
        *,
        pool_identifier: str,
        runtime_identity: Optional[RuntimeIndexIdentity],
        dossier_id: Optional[str] = None,
        compaction_threshold: float = 0.3,
    ) -> PoolMaintenanceReport:
        open_result = safe_open_pool(pool_identifier)
        if open_result.report.status != PoolOpenStatus.OK or open_result.store is None:
            return PoolMaintenanceReport(
                pool_identifier=pool_identifier,
                pool_open=open_result.report,
                pool_health=None,
                slice_diagnoses=None,
            )

        view = resolve_view_for_pool_identifier(pool_identifier)
        diagnoser = SliceDiagnoser(
            corpus_provider=self.corpus_provider,
            metadata_store=open_result.store.metadata_store,
            pool_identifier=pool_identifier,
            runtime_identity=runtime_identity,
            view=view,
        )
        diagnoses = diagnoser.diagnose(dossier_id=dossier_id)
        health = build_pool_health_report(
            open_result.store, threshold=compaction_threshold
        )

        return PoolMaintenanceReport(
            pool_identifier=pool_identifier,
            pool_open=open_result.report,
            pool_health=health,
            slice_diagnoses=diagnoses,
        )


def _resolve_bootstrap_identity(
    *, assets_service: AssetsService
) -> tuple[Optional[BootstrapIdentity], Optional[str]]:
    try:
        model_info = resolve_embedding_model(assets_service)
    except EmbeddingAssetMissingError:
        return None, "embedding_asset_missing"
    except Exception as exc:
        return None, f"embedding_resolve_failed:{type(exc).__name__}"

    embedding_dim = _embedding_dim_from_manifest(model_info.manifest)
    if embedding_dim is None:
        try:
            provider = SentenceTransformersEmbeddingProvider(
                model_info=model_info,
                batch_size=1,
            )
            vectors = provider.embed(["bootstrap"])
            embedding_dim = len(vectors[0]) if vectors and vectors[0] else None
        except Exception as exc:
            return None, f"embedding_unloadable:{type(exc).__name__}"

    if not embedding_dim:
        return None, "embedding_dim_unavailable"

    fingerprint = compute_model_fingerprint(model_info)
    return (
        BootstrapIdentity(
            embedding_dim=int(embedding_dim),
            embedding_model_id=model_info.asset_id,
            embedding_model_fingerprint=fingerprint,
            chunking_policy_id=FINAL_SEGMENTS_POLICY.policy_id,
        ),
        None,
    )


def _embedding_dim_from_manifest(manifest: Optional[dict]) -> Optional[int]:
    if not manifest:
        return None
    value = manifest.get("embedding_dim")
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _check_identity_mismatch(
    manifest: SemanticIndexManifest, identity: BootstrapIdentity
) -> Optional[str]:
    if manifest.embedding_dim != identity.embedding_dim:
        return "embedding_dim"
    if manifest.embedding_model_fingerprint:
        if manifest.embedding_model_fingerprint != identity.embedding_model_fingerprint:
            return "embedding_model_fingerprint"
    elif manifest.embedding_model_id != identity.embedding_model_id:
        return "embedding_model_id"
    if manifest.chunking_policy_id != identity.chunking_policy_id:
        return "chunking_policy_id"
    return None


def _handle_manifest_repair(
    *,
    pool_identifier: str,
    manifest_file,
    hnsw_path,
    metadata_path,
    identity: BootstrapIdentity,
    force: bool,
    detail: str,
) -> PoolBootstrapReport:
    if not force:
        return PoolBootstrapReport(
            pool_identifier=pool_identifier,
            status=PoolBootstrapStatus.NEEDS_FORCE_REPAIR,
            reason_code=DiagnosticReasonCode.UNAVAILABLE_NEEDS_FORCE_REPAIR,
            detail=detail,
            action_hint=ACTION_HINT_FORCE_REPAIR,
        )
    try:
        _clear_pool_artifacts(manifest_file, hnsw_path, metadata_path)
        _write_empty_pool_artifacts(pool_identifier=pool_identifier, identity=identity)
    except Exception as exc:
        return PoolBootstrapReport(
            pool_identifier=pool_identifier,
            status=PoolBootstrapStatus.FAILED,
            reason_code=DiagnosticReasonCode.UNAVAILABLE_UNKNOWN,
            detail=f"bootstrap_failed:{type(exc).__name__}",
            action_hint=None,
        )
    return PoolBootstrapReport(
        pool_identifier=pool_identifier,
        status=PoolBootstrapStatus.REPAIRED,
        reason_code=None,
        detail=None,
        action_hint=None,
    )


def _clear_pool_artifacts(manifest_file, hnsw_path, metadata_path) -> None:
    for path in (manifest_file, hnsw_path, metadata_path):
        if path.exists():
            path.unlink()
    for suffix in ("-wal", "-shm"):
        sidecar = metadata_path.with_name(metadata_path.name + suffix)
        if sidecar.exists():
            sidecar.unlink()


def _write_empty_pool_artifacts(
    *,
    pool_identifier: str,
    identity: BootstrapIdentity,
) -> None:
    store = create_persistent_store(
        pool_identifier=pool_identifier,
        embedding_dim=identity.embedding_dim,
        metadata_db_path=metadata_db_path(pool_identifier),
    )
    store.save(hnsw_index_path(pool_identifier), metadata_db_path(pool_identifier))
    now = datetime.utcnow().isoformat() + "Z"
    manifest = SemanticIndexManifest(
        schema_version=MANIFEST_SCHEMA_VERSION,
        pool_identifier=pool_identifier,
        embedding_dim=identity.embedding_dim,
        embedding_model_id=identity.embedding_model_id,
        embedding_model_fingerprint=identity.embedding_model_fingerprint,
        chunking_policy_id=identity.chunking_policy_id,
        created_at=now,
        updated_at=now,
    )
    write_manifest(pool_identifier, manifest)
