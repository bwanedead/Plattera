from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional

from corpus.interfaces import CorpusProvider

from ..lanes.semantic.manifest import (
    manifest_path,
    hnsw_index_path,
    metadata_db_path,
    read_manifest,
)
from ..lanes.semantic.persistent_store import PersistentVectorStore, load_persistent_store
from .diagnose import RuntimeIndexIdentity, SliceDiagnoser, SliceDiagnosis
from .inventory_provider import resolve_view_for_pool_identifier
from .reason_codes import DiagnosticReasonCode


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
    tombstoned_vectors: int
    tombstone_ratio: float
    compact_recommended: bool
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
        return PoolOpenResult(
            report=PoolOpenReport(
                status=PoolOpenStatus.UNAVAILABLE,
                reason_code=DiagnosticReasonCode.UNAVAILABLE_UNKNOWN,
                detail="manifest_unavailable",
                action_hint=ACTION_HINT_REBUILD_POOL,
            )
        )

    try:
        store = load_persistent_store(
            pool_identifier=pool_identifier,
            embedding_dim=manifest.embedding_dim,
            hnsw_path=hnsw_path,
            metadata_db_path=metadata_path,
        )
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


def build_pool_health_report(
    store: PersistentVectorStore, *, threshold: float
) -> PoolHealthReport:
    stats = store.get_stats()
    return PoolHealthReport(
        active_vectors=stats["active_chunks"],
        tombstoned_vectors=stats["tombstoned_vectors"],
        tombstone_ratio=stats["tombstone_ratio"],
        compact_recommended=store.should_compact(threshold=threshold),
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
