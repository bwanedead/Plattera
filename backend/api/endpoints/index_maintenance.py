from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

from corpus.virtual_provider import VirtualCorpusProvider
from retrieval.engine.diagnose import RuntimeIndexIdentity, SliceDiagnosis, SliceStatus
from retrieval.engine.execute import SliceExecutor
from retrieval.engine.inventory_provider import resolve_view_for_pool_identifier
from retrieval.engine.pool_maintenance import (
    PoolHealthReport,
    PoolMaintenanceController,
    PoolOpenReport,
    PoolOpenResult,
    PoolOpenStatus,
    safe_open_pool,
)
from retrieval.engine.reason_codes import DiagnosticReasonCode
from retrieval.lanes.semantic.chunking import FINAL_SEGMENTS_POLICY
from retrieval.lanes.semantic.embeddings import build_embedding_provider, compute_model_fingerprint
from retrieval.lanes.semantic.index_builder import SemanticIndexBuilder
from retrieval.lanes.semantic.provider import resolve_embedding_model
from services.assets.service import AssetsService
from services.index_maintenance import (
    IndexMaintenanceJob,
    IndexMaintenanceJobRequest,
    IndexMaintenanceJobStatus,
    IndexMaintenanceProgress,
    IndexMaintenanceRuntimeIdentity,
    IndexMaintenanceSliceResult,
    IndexMaintenanceJobStore,
)


router = APIRouter()

MAX_DIAGNOSE_SLICE_LIMIT = 1000
DEFAULT_DIAGNOSE_LIMIT = 200
MAX_EXECUTE_LIMIT = 100
DEFAULT_EXECUTE_LIMIT = 25


class ExecuteRequest(BaseModel):
    pool_identifier: str
    mode: str
    limit: int = DEFAULT_EXECUTE_LIMIT
    dossier_id: Optional[str] = None
    dry_run: bool = False


def _bounded_limit(requested: Optional[int], default: int, max_limit: int) -> int:
    if requested is None:
        return default
    return max(1, min(max_limit, int(requested)))


def _resolve_runtime_identity(
    pool_identifier: str,
) -> Tuple[Optional[RuntimeIndexIdentity], Optional[PoolOpenReport], Optional[IndexMaintenanceRuntimeIdentity]]:
    if pool_identifier not in ("FINAL_SEGMENTS", "EVERYTHING"):
        return (
            None,
            PoolOpenReport(
                status=PoolOpenStatus.UNAVAILABLE,
                reason_code=DiagnosticReasonCode.UNAVAILABLE_UNKNOWN,
                detail="unsupported_pool_identifier",
                action_hint=None,
            ),
            None,
        )
    try:
        model_info = resolve_embedding_model(AssetsService())
        fingerprint = compute_model_fingerprint(model_info)
        chunking_policy_id = FINAL_SEGMENTS_POLICY.policy_id
        identity = RuntimeIndexIdentity(
            embedding_model_fingerprint=fingerprint,
            chunking_policy_id=chunking_policy_id,
        )
        job_identity = IndexMaintenanceRuntimeIdentity(
            embedding_model_fingerprint=fingerprint,
            chunking_policy_id=chunking_policy_id,
        )
        return identity, None, job_identity
    except Exception as exc:
        return (
            None,
            PoolOpenReport(
                status=PoolOpenStatus.UNAVAILABLE,
                reason_code=DiagnosticReasonCode.UNAVAILABLE_UNKNOWN,
                detail=type(exc).__name__,
                action_hint=None,
            ),
            None,
        )


def _serialize_pool_open(report: PoolOpenReport) -> Dict:
    return {
        "status": report.status.value,
        "reason_code": report.reason_code.value if report.reason_code else None,
        "detail": report.detail,
        "action_hint": report.action_hint,
    }


def _serialize_pool_health(report: PoolHealthReport) -> Dict:
    return asdict(report)


def _serialize_slice(slice_diag: SliceDiagnosis) -> Dict:
    return {
        "pool_identifier": slice_diag.pool_identifier,
        "dossier_id": slice_diag.dossier_id,
        "entry_id": slice_diag.entry_id,
        "status": slice_diag.status.value,
        "desired_signature": slice_diag.desired_signature,
        "indexed_signature": slice_diag.indexed_signature,
        "reason": slice_diag.reason,
    }


def _build_counts(slices: List[SliceDiagnosis]) -> Dict[str, int]:
    counts = {"healthy": 0, "missing": 0, "stale": 0, "unavailable": 0}
    for s in slices:
        if s.status == SliceStatus.HEALTHY:
            counts["healthy"] += 1
        elif s.status == SliceStatus.MISSING:
            counts["missing"] += 1
        elif s.status in (SliceStatus.STALE_CONTENT, SliceStatus.STALE_IDENTITY):
            counts["stale"] += 1
        elif s.status == SliceStatus.UNAVAILABLE:
            counts["unavailable"] += 1
    return counts


def _fallback_unavailable(pool_identifier: str, exc: Exception) -> Dict:
    report = PoolOpenReport(
        status=PoolOpenStatus.UNAVAILABLE,
        reason_code=DiagnosticReasonCode.UNAVAILABLE_UNKNOWN,
        detail=type(exc).__name__,
        action_hint=None,
    )
    return {
        "pool_identifier": pool_identifier,
        "pool_open": _serialize_pool_open(report),
        "pool_health": None,
        "slice_diagnoses": None,
        "counts": {"healthy": 0, "missing": 0, "stale": 0, "unavailable": 0},
    }


def _collect_slice_diagnoses(
    *,
    pool_identifier: str,
    dossier_id: Optional[str],
    runtime_identity: RuntimeIndexIdentity,
    store_result: PoolOpenResult,
) -> List[SliceDiagnosis]:
    corpus_provider = VirtualCorpusProvider()
    from retrieval.engine.diagnose import SliceDiagnoser

    diagnoser = SliceDiagnoser(
        corpus_provider=corpus_provider,
        metadata_store=store_result.store.metadata_store,
        pool_identifier=pool_identifier,
        runtime_identity=runtime_identity,
        view=resolve_view_for_pool_identifier(pool_identifier),
    )
    return diagnoser.diagnose(dossier_id=dossier_id)


def _select_slices(
    diagnoses: List[SliceDiagnosis],
    mode: str,
    limit: int,
) -> List[SliceDiagnosis]:
    if mode == "missing_only":
        candidates = [d for d in diagnoses if d.status == SliceStatus.MISSING]
    elif mode == "missing_and_stale":
        candidates = [
            d
            for d in diagnoses
            if d.status in (SliceStatus.MISSING, SliceStatus.STALE_CONTENT, SliceStatus.STALE_IDENTITY)
        ]
    else:
        raise HTTPException(status_code=400, detail="Unsupported mode")

    candidates.sort(key=lambda d: (d.dossier_id, d.entry_id))
    return candidates[:limit]


def _as_reason_code(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    valid = {code.value for code in DiagnosticReasonCode}
    if value in valid:
        return value
    return None


def _run_job(
    *,
    job_id: str,
    pool_identifier: str,
    selection: List[SliceDiagnosis],
    runtime_identity: RuntimeIndexIdentity,
    dry_run: bool,
) -> None:
    store = IndexMaintenanceJobStore()
    now = datetime.utcnow().isoformat()
    store.update_status(job_id, IndexMaintenanceJobStatus.RUNNING, started_at=now)

    open_result = safe_open_pool(pool_identifier)
    if open_result.report.status != PoolOpenStatus.OK or open_result.store is None:
        store.update_status(
            job_id,
            IndexMaintenanceJobStatus.FAILED,
            finished_at=datetime.utcnow().isoformat(),
            error=open_result.report.reason_code.value if open_result.report.reason_code else "unavailable",
        )
        return

    corpus_provider = VirtualCorpusProvider()
    builder = SemanticIndexBuilder(
        corpus_provider=corpus_provider,
        embedding_provider=build_embedding_provider(assets_service=AssetsService()),
    )
    executor = SliceExecutor(
        corpus_provider=corpus_provider,
        vector_store=open_result.store,
        builder=builder,
        runtime_identity=runtime_identity,
        view=resolve_view_for_pool_identifier(pool_identifier),
    )

    progress = IndexMaintenanceProgress(total=len(selection), done=0, ok=0, failed=0)
    for diagnosis in selection:
        if dry_run:
            result = IndexMaintenanceSliceResult(
                dossier_id=diagnosis.dossier_id,
                entry_id=diagnosis.entry_id,
                status="dry_run",
                reason_code=None,
                detail=None,
            )
            progress.done += 1
            progress.ok += 1
        else:
            exec_result = executor.execute_entry(
                dossier_id=diagnosis.dossier_id,
                entry_id=diagnosis.entry_id,
            )
            reason_code = _as_reason_code(exec_result.reason)
            result = IndexMaintenanceSliceResult(
                dossier_id=exec_result.dossier_id,
                entry_id=exec_result.entry_id,
                status=exec_result.status.value,
                reason_code=reason_code,
                detail=None if reason_code else exec_result.reason,
            )
            progress.done += 1
            if exec_result.status == SliceStatus.HEALTHY:
                progress.ok += 1
            else:
                progress.failed += 1

        job_data = store.get(job_id) or {}
        results = job_data.get("results", [])
        results.append(result.__dict__)
        store.update_fields(
            job_id,
            progress=progress.__dict__,
            results=results,
        )

    final_status = (
        IndexMaintenanceJobStatus.SUCCEEDED
        if progress.failed == 0
        else IndexMaintenanceJobStatus.FAILED
    )
    store.update_status(
        job_id,
        final_status,
        finished_at=datetime.utcnow().isoformat(),
    )


@router.get("/diagnose")
async def diagnose_index(
    *,
    pool_identifier: str,
    include_slices: bool = False,
    limit_slices: int = DEFAULT_DIAGNOSE_LIMIT,
    dossier_id: Optional[str] = None,
) -> Dict:
    try:
        runtime_identity, identity_report, _job_identity = _resolve_runtime_identity(pool_identifier)
        if runtime_identity is None:
            return {
                "pool_identifier": pool_identifier,
                "pool_open": _serialize_pool_open(identity_report),
                "pool_health": None,
                "slice_diagnoses": None,
                "counts": {"healthy": 0, "missing": 0, "stale": 0, "unavailable": 0},
            }

        controller = PoolMaintenanceController(corpus_provider=VirtualCorpusProvider())
        report = controller.diagnose_pool(
            pool_identifier=pool_identifier,
            runtime_identity=runtime_identity,
            dossier_id=dossier_id,
            compaction_threshold=0.3,
        )
        slices = report.slice_diagnoses or []
        counts = _build_counts(slices)
        limit = _bounded_limit(limit_slices, DEFAULT_DIAGNOSE_LIMIT, MAX_DIAGNOSE_SLICE_LIMIT)

        response = {
            "pool_identifier": pool_identifier,
            "pool_open": _serialize_pool_open(report.pool_open),
            "pool_health": _serialize_pool_health(report.pool_health)
            if report.pool_health
            else None,
            "slice_diagnoses": None,
            "counts": counts,
        }
        if include_slices:
            response["slice_diagnoses"] = [
                _serialize_slice(s) for s in slices[:limit]
            ]
        return response
    except Exception as exc:
        return _fallback_unavailable(pool_identifier, exc)


@router.post("/execute")
async def execute_index(
    payload: ExecuteRequest, background_tasks: BackgroundTasks
) -> Dict:
    runtime_identity, identity_report, job_identity = _resolve_runtime_identity(
        payload.pool_identifier
    )
    request = IndexMaintenanceJobRequest(
        pool_identifier=payload.pool_identifier,
        mode=payload.mode,
        limit=_bounded_limit(payload.limit, DEFAULT_EXECUTE_LIMIT, MAX_EXECUTE_LIMIT),
        dossier_id=payload.dossier_id,
        dry_run=payload.dry_run,
    )
    store = IndexMaintenanceJobStore()
    job = IndexMaintenanceJob.new(request=request, identity=job_identity)
    store.create(job)

    if runtime_identity is None:
        store.update_status(
            job.id,
            IndexMaintenanceJobStatus.FAILED,
            finished_at=datetime.utcnow().isoformat(),
            error=identity_report.detail if identity_report else "identity_unavailable",
        )
        return {"job_id": job.id, "status": IndexMaintenanceJobStatus.FAILED.value}

    open_result = safe_open_pool(payload.pool_identifier)
    if open_result.report.status != PoolOpenStatus.OK or open_result.store is None:
        store.update_status(
            job.id,
            IndexMaintenanceJobStatus.FAILED,
            finished_at=datetime.utcnow().isoformat(),
            error=open_result.report.reason_code.value if open_result.report.reason_code else "unavailable",
        )
        return {"job_id": job.id, "status": IndexMaintenanceJobStatus.FAILED.value}

    diagnoses = _collect_slice_diagnoses(
        pool_identifier=payload.pool_identifier,
        dossier_id=payload.dossier_id,
        runtime_identity=runtime_identity,
        store_result=open_result,
    )

    selection = _select_slices(diagnoses, payload.mode, request.limit)
    store.update_fields(
        job.id,
        progress=IndexMaintenanceProgress(total=len(selection)).__dict__,
    )

    if not selection:
        store.update_status(
            job.id,
            IndexMaintenanceJobStatus.SUCCEEDED,
            finished_at=datetime.utcnow().isoformat(),
        )
        return {"job_id": job.id, "status": IndexMaintenanceJobStatus.SUCCEEDED.value}

    background_tasks.add_task(
        _run_job,
        job_id=job.id,
        pool_identifier=payload.pool_identifier,
        selection=selection,
        runtime_identity=runtime_identity,
        dry_run=payload.dry_run,
    )
    return {"job_id": job.id, "status": IndexMaintenanceJobStatus.QUEUED.value}


@router.get("/jobs/{job_id}")
async def get_index_job(job_id: str, limit_results: int = 200) -> Dict:
    store = IndexMaintenanceJobStore()
    job = store.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    cap = _bounded_limit(limit_results, 200, 1000)
    results = job.get("results", [])
    job["results"] = results[:cap]
    job["results_returned"] = len(job["results"])
    job["results_total"] = len(results)
    return job
