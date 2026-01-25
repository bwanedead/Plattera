from __future__ import annotations

import logging
import time
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
    PoolBootstrapReport,
    PoolHealthReport,
    PoolMaintenanceController,
    PoolOpenReport,
    PoolOpenResult,
    PoolOpenStatus,
    bootstrap_pool_artifacts,
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
logger = logging.getLogger(__name__)

MAX_DIAGNOSE_SLICE_LIMIT = 1000
DEFAULT_DIAGNOSE_LIMIT = 200
MAX_EXECUTE_LIMIT = 100
DEFAULT_EXECUTE_LIMIT = 25


def _truncate(value: Optional[str], max_len: int = 200) -> Optional[str]:
    if value is None:
        return None
    if len(value) <= max_len:
        return value
    return value[: max_len - 3] + "..."


def _shorten(value: Optional[str], length: int = 8) -> Optional[str]:
    if not value:
        return value
    return value[:length]


def _log_event(name: str, **fields: object) -> None:
    emoji = ""
    if name == "index_bootstrap_result":
        emoji = "🔧"
    elif name == "index_execute_requested":
        emoji = "📥"
    elif name == "index_job_started":
        emoji = "▶️"
    elif name == "index_job_finished":
        status_value = fields.get("status")
        status_token = str(status_value).lower() if status_value is not None else ""
        emoji = "🏁✅" if status_token in ("succeeded", "ok", "success") else "🏁❌"
    elif name == "index_slice_executed":
        status_value = fields.get("status")
        emoji = "❌" if status_value and status_value != "healthy" else "✅"
    elif name == "index_job_progress":
        emoji = "⏳"
    elif name == "index_job_separator":
        emoji = "─"

    if name == "index_slice_executed":
        message = (
            f"{name} {emoji} dossier={fields.get('dossier_id')} entry={fields.get('entry_id')} "
            f"+{fields.get('chunks_added')} -{fields.get('deleted_count')} "
            f"status={fields.get('status')} pool={fields.get('pool_identifier')}"
        )
    elif name == "index_job_finished":
        message = (
            f"{name} {emoji} job={fields.get('job_id')} pool={fields.get('pool_identifier')} "
            f"status={fields.get('status')} ok={fields.get('ok')} failed={fields.get('failed')} "
            f"duration_ms={fields.get('duration_ms')}"
        )
    elif name == "index_job_started":
        message = (
            f"{name} {emoji} job={fields.get('job_id')} pool={fields.get('pool_identifier')} "
            f"total={fields.get('total_slices')} model_id={fields.get('model_id')} "
            f"model_fp={fields.get('model_fp')} chunking={fields.get('chunking_policy_id')}"
        )
    elif name == "index_execute_requested":
        message = (
            f"{name} {emoji} job={fields.get('job_id')} pool={fields.get('pool_identifier')} "
            f"mode={fields.get('mode')} selected={fields.get('selected_slices')} "
            f"limit={fields.get('limit')} dry_run={fields.get('dry_run')}"
        )
    elif name == "index_bootstrap_result":
        message = (
            f"{name} {emoji} pool={fields.get('pool_identifier')} "
            f"status={fields.get('status')} reason={fields.get('reason_code') or 'none'}"
        )
    elif name == "index_job_progress":
        message = (
            f"{name} {emoji} job={fields.get('job_id')} pool={fields.get('pool_identifier')} "
            f"done={fields.get('done')}/{fields.get('total')} ok={fields.get('ok')} "
            f"failed={fields.get('failed')}"
        )
    elif name == "index_job_separator":
        message = f"{name} {emoji * 24}"
    else:
        message = name
    logger.info(message, extra={"event": name, **fields})


class ExecuteRequest(BaseModel):
    pool_identifier: str
    mode: str
    limit: int = DEFAULT_EXECUTE_LIMIT
    dossier_id: Optional[str] = None
    dry_run: bool = False


class BootstrapRequest(BaseModel):
    pool_identifier: Optional[str] = None
    force: bool = False


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


def _serialize_bootstrap(report: PoolBootstrapReport) -> Dict:
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
    model_id: Optional[str],
    dry_run: bool,
) -> None:
    store = IndexMaintenanceJobStore()
    now = datetime.utcnow().isoformat()
    store.update_status(job_id, IndexMaintenanceJobStatus.RUNNING, started_at=now)
    start_time = time.monotonic()
    _log_event(
        "index_job_started",
        job_id=job_id,
        pool_identifier=pool_identifier,
        total_slices=len(selection),
        model_id=model_id,
        model_fp=_shorten(runtime_identity.embedding_model_fingerprint),
        chunking_policy_id=runtime_identity.chunking_policy_id,
    )
    _log_event(
        "index_job_separator",
        job_id=job_id,
        pool_identifier=pool_identifier,
    )

    open_result = safe_open_pool(pool_identifier)
    if open_result.report.status != PoolOpenStatus.OK or open_result.store is None:
        error = (
            open_result.report.reason_code.value
            if open_result.report.reason_code
            else "unavailable"
        )
        store.update_status(
            job_id,
            IndexMaintenanceJobStatus.FAILED,
            finished_at=datetime.utcnow().isoformat(),
            error=error,
        )
        _log_event(
            "index_job_finished",
            job_id=job_id,
            pool_identifier=pool_identifier,
            status=IndexMaintenanceJobStatus.FAILED.value,
            total=len(selection),
            done=0,
            ok=0,
            failed=len(selection),
            duration_ms=int((time.monotonic() - start_time) * 1000),
            error=_truncate(error),
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
    last_progress_time = time.monotonic()
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

        if not dry_run:
            deleted_count = getattr(exec_result, "deleted_count", 0)
            chunks_added = getattr(exec_result, "chunks_added", 0)
            did_write_state = getattr(exec_result, "did_write_state", False)
            status_value = exec_result.status.value
            reason = _truncate(exec_result.reason)
            if (
                deleted_count > 0
                or chunks_added > 0
                or did_write_state
                or exec_result.status != SliceStatus.HEALTHY
            ):
                _log_event(
                    "index_slice_executed",
                    job_id=job_id,
                    pool_identifier=pool_identifier,
                    dossier_id=exec_result.dossier_id,
                    entry_id=exec_result.entry_id,
                    status=status_value,
                    deleted_count=deleted_count,
                    chunks_added=chunks_added,
                    did_write_state=did_write_state,
                    reason=reason,
                )

        now_time = time.monotonic()
        if progress.done % 10 == 0 or (now_time - last_progress_time) >= 5:
            _log_event(
                "index_job_progress",
                job_id=job_id,
                pool_identifier=pool_identifier,
                done=progress.done,
                total=progress.total,
                ok=progress.ok,
                failed=progress.failed,
            )
            last_progress_time = now_time

    final_status = (
        IndexMaintenanceJobStatus.SUCCEEDED
        if progress.failed == 0
        else IndexMaintenanceJobStatus.FAILED
    )
    error = None
    if final_status == IndexMaintenanceJobStatus.FAILED:
        error = "slice_failures"
    store.update_status(
        job_id,
        final_status,
        finished_at=datetime.utcnow().isoformat(),
    )
    _log_event(
        "index_job_separator",
        job_id=job_id,
        pool_identifier=pool_identifier,
    )
    _log_event(
        "index_job_finished",
        job_id=job_id,
        pool_identifier=pool_identifier,
        status=final_status.value,
        total=progress.total,
        done=progress.done,
        ok=progress.ok,
        failed=progress.failed,
        duration_ms=int((time.monotonic() - start_time) * 1000),
        error=_truncate(error),
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


@router.post("/bootstrap")
async def bootstrap_index(payload: BootstrapRequest) -> Dict:
    pool_identifier = payload.pool_identifier
    pools = [pool_identifier] if pool_identifier else ["FINAL_SEGMENTS", "EVERYTHING"]
    for pool in pools:
        if pool not in ("FINAL_SEGMENTS", "EVERYTHING"):
            raise HTTPException(status_code=400, detail="Unsupported pool identifier")

    results = []
    for pool in pools:
        bootstrap_report = bootstrap_pool_artifacts(
            pool_identifier=pool,
            force=payload.force,
        )
        _log_event(
            "index_bootstrap_result",
            pool_identifier=pool,
            status=bootstrap_report.status.value,
            reason_code=bootstrap_report.reason_code.value if bootstrap_report.reason_code else None,
            detail=_truncate(bootstrap_report.detail),
        )
        open_result = safe_open_pool(pool)
        results.append(
            {
                "pool_identifier": pool,
                "bootstrap": _serialize_bootstrap(bootstrap_report),
                "pool_open": _serialize_pool_open(open_result.report),
            }
        )

    return {"results": results}


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
        bootstrap_report = bootstrap_pool_artifacts(
            pool_identifier=payload.pool_identifier,
            force=False,
        )
        open_result = safe_open_pool(payload.pool_identifier)
        if open_result.report.status != PoolOpenStatus.OK or open_result.store is None:
            error = (
                bootstrap_report.reason_code.value
                if bootstrap_report.reason_code
                else bootstrap_report.status.value
            )
            store.update_status(
                job.id,
                IndexMaintenanceJobStatus.FAILED,
                finished_at=datetime.utcnow().isoformat(),
                error=error,
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
    counts = _build_counts(diagnoses)
    model_id = None
    try:
        model_info = resolve_embedding_model(AssetsService())
        model_id = model_info.asset_id
    except Exception:
        model_id = None
    _log_event(
        "index_execute_requested",
        job_id=job.id,
        pool_identifier=payload.pool_identifier,
        mode=payload.mode,
        limit=request.limit,
        dossier_id=payload.dossier_id or "*",
        dry_run=payload.dry_run,
        selected_slices=len(selection),
        missing_count=counts["missing"],
        stale_count=counts["stale"],
        unavailable_count=counts["unavailable"],
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
        model_id=model_id,
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
