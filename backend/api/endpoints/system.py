"""
System Management Endpoints
==========================

Endpoints for system health monitoring, cleanup, and maintenance.
"""

from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import Dict, Any, List
import logging
import hashlib
from pathlib import Path
import sys

import time
from utils.health_monitor import check_health as hm_check
import os
from services.agent_viewer.event_bus import event_bus as viewer_event_bus
from services.workflows.mapping.transcription_edit.run_registry import TranscriptionEditRunRegistry
logger = logging.getLogger(__name__)
router = APIRouter()


class HealthResponse(BaseModel):
    """Response model for health check endpoints"""
    status: str
    memory_usage_mb: float
    cpu_percent: float
    uptime_seconds: float
    overall_status: str
    recommendations: List[str] = []
    errors: List[str] = []
    # Readiness of heavy subsystems (alignment service) without triggering heavy work
    ready: bool = True


class CleanupResponse(BaseModel):
    """Response model for cleanup endpoints"""
    status: str
    actions_performed: List[str]
    memory_before_mb: float
    memory_after_mb: float
    memory_freed_mb: float
    errors: List[str] = []


def _mark_running_transcript_edit_runs_interrupted(*, reason_code: str) -> int:
    """Best-effort terminalization for in-flight transcript-edit runs before shutdown."""
    try:
        registry = TranscriptionEditRunRegistry()
        runs = registry.list_runs(limit=200)
    except Exception as exc:
        logger.warning("Failed to list transcript-edit runs before cleanup exit: %s", exc)
        return 0

    interrupted = 0
    now_epoch = int(time.time())
    for run in runs:
        if not isinstance(run, dict):
            continue
        if str(run.get("status") or "").lower() != "running":
            continue
        run_id = str(run.get("run_id") or "").strip()
        if not run_id:
            continue
        snapshot = run.get("snapshot") if isinstance(run.get("snapshot"), dict) else {}
        progress_log = snapshot.get("progress_log") if isinstance(snapshot.get("progress_log"), list) else []
        last_iteration = None
        if progress_log and isinstance(progress_log[-1], dict):
            last_iteration = progress_log[-1].get("iteration")
        summary = {
            "status": "failed",
            "reason_code": reason_code,
            "iterations": last_iteration,
            "review_required": True,
            "edits_applied_total": 0,
            "used_human_feedback": False,
            "mechanical_severity_clear": False,
            "mapping_ready": False,
            "promoted": False,
            "readiness_blocker": "service_shutdown",
            "closure_state": "blocked",
            "layer1_canonical_recovery": "unknown",
            "layer2_canonical_sanity": "unknown",
            "layer3_dependency_completeness": "blocked",
            "decision_ledger": {},
            "decision_ledger_summary": {},
            "unresolved_closure_requirements": [
                {
                    "decision_key": "system_shutdown",
                    "block_reason": "dependency",
                    "required_information": "Run interrupted by backend shutdown before completion.",
                    "self_retrievable": False,
                    "retrieval_attempted": False,
                    "minimal_user_action": "Re-run transcript edit loop after backend restart.",
                }
            ],
            "initial_findings": {},
            "final_findings": {},
        }
        registry.update_run(
            run_id=run_id,
            patch={
                "status": "failed",
                "error": reason_code,
                "snapshot": {
                    "run_id": run_id,
                    "status": "failed",
                    "reason_code": reason_code,
                    "terminal_summary": summary,
                    "live_status": {
                        "timestamp_epoch_seconds": now_epoch,
                        "phase": "interrupted",
                        "message": "Run interrupted by backend shutdown.",
                        "execution_state": "failed",
                        "iteration": last_iteration,
                    },
                    "progress_log": progress_log,
                },
            },
        )
        viewer_event_bus.publish_sync(
            f"transcript_edit:{run_id}",
            {
                "protocol": "agent_viewer_event_v1",
                "run_id": run_id,
                "loop_kind": "transcript_edit",
                "seq": now_epoch,
                "iteration": last_iteration,
                "timestamp_epoch_seconds": now_epoch,
                "event_type": "done",
                "status": {
                    "stage": "failed",
                    "line1": "Transcript edit run interrupted by shutdown",
                    "line2": reason_code,
                },
                "artifact_refs": {},
                "payload": {
                    "phase": "failed",
                    "message": "Run interrupted by backend shutdown before terminalization completed.",
                    "execution_state": "failed",
                    "summary": summary,
                    "terminal": True,
                },
            },
        )
        interrupted += 1
    return interrupted


def _file_identity(path: Path) -> Dict[str, Any]:
    out: Dict[str, Any] = {"path": str(path)}
    try:
        resolved = path.resolve()
        out["resolved_path"] = str(resolved)
    except Exception:
        resolved = path
    if not resolved.exists():
        out["exists"] = False
        return out
    out["exists"] = True
    try:
        raw = resolved.read_bytes()
        out["sha256"] = hashlib.sha256(raw).hexdigest()
        out["size_bytes"] = len(raw)
    except Exception as exc:
        out["read_error"] = str(exc)[:200]
    try:
        stat = resolved.stat()
        out["mtime_epoch_seconds"] = int(stat.st_mtime)
    except Exception:
        pass
    return out


@router.get("/runtime-identity")
async def runtime_identity() -> Dict[str, Any]:
    """
    Runtime identity probe for proving UI and CLI are using the same backend code.
    """
    try:
        from agent_kernel import tooling as tooling_module
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"runtime_identity_import_failed:{type(exc).__name__}:{exc}")

    root = Path(__file__).resolve().parents[2]
    files = {
        "system_endpoint": Path(__file__),
        "tooling_module": Path(tooling_module.__file__),
    }

    return {
        "status": "success",
        "process": {
            "pid": os.getpid(),
            "cwd": str(Path.cwd()),
            "python_executable": sys.executable,
            "platform": sys.platform,
        },
        "repo_root_guess": str(root),
        "files": {name: _file_identity(path) for name, path in files.items()},
    }


_LAST_HEALTH_LOG_TS: float = 0.0

@router.get("/health", response_model=HealthResponse)
async def check_system_health():
    """Cheap health using HealthMonitor only (no heavy service init)."""
    try:
        health_status = hm_check() or {}
        msg = (
            f"🏥 HEALTH ► mem={health_status.get('memory_usage_mb', 0)}MB "
            f"cpu={health_status.get('cpu_percent', 0)}% "
            f"status={health_status.get('overall_status', 'unknown')}"
        )
        global _LAST_HEALTH_LOG_TS
        now = time.time()
        overall_status = str(health_status.get("overall_status", "unknown"))
        should_log_info = overall_status not in ("healthy", "maintenance_needed")
        if now - _LAST_HEALTH_LOG_TS > 60 and should_log_info:
            logger.info(msg)
            _LAST_HEALTH_LOG_TS = now
        else:
            logger.debug(msg)

        # Import readiness lazily; this module is cheap
        try:
            from services.alignment_service_singleton import is_ready  # type: ignore
            ready_flag = bool(is_ready())
        except Exception:
            ready_flag = True  # default to true if readiness probe unavailable

        return HealthResponse(
            status="success",
            memory_usage_mb=float(health_status.get('memory_usage_mb', 0.0)),
            cpu_percent=float(health_status.get('cpu_percent', 0.0)),
            uptime_seconds=float(health_status.get('uptime_seconds', 0.0)),
            overall_status=str(health_status.get('overall_status', 'unknown')),
            recommendations=list(health_status.get('recommendations', [])),
            errors=list(health_status.get('errors', [])),
            ready=ready_flag,
        )
    except Exception as e:
        logger.warning(f"❌ /health failed: {e}")
        raise HTTPException(status_code=500, detail=f"Health check failed: {str(e)}")


@router.post("/cleanup", response_model=CleanupResponse)
async def perform_system_cleanup(background_tasks: BackgroundTasks):
    """
    Perform system cleanup including memory cleanup, garbage collection, and file system cleanup.
    Also schedules a delayed process exit when running as a sidecar.
    """
    logger.info("🧹 SYSTEM CLEANUP REQUEST")

    # 1) Mark in-flight transcript-edit runs as interrupted before shutdown.
    interrupted_runs = _mark_running_transcript_edit_runs_interrupted(
        reason_code="tx_agent_interrupted_shutdown",
    )

    # 2) Define and schedule the exit task FIRST, so shutdown is guaranteed.
    def delayed_exit():
        logger.info("🛑 Delayed exit requested via /api/cleanup – terminating process")
        time.sleep(0.5)
        os._exit(0)

    background_tasks.add_task(delayed_exit)

    # 3) Baseline cleanup result (so we always have something sane to return)
    cleanup_results: Dict[str, Any] = {
        "status": "success",
        "actions_performed": [f"marked_interrupted_transcript_edit_runs:{interrupted_runs}"],
        "memory_before_mb": 0.0,
        "memory_after_mb": 0.0,
        "errors": [],
    }

    # 4) Best-effort cleanup – never prevent shutdown
    try:
        # Lazy import to avoid heavy init for unrelated routes
        from services.alignment_service import AlignmentService  # type: ignore

        svc = AlignmentService()
        result = svc.force_cleanup() or {}

        # Merge any known keys from the service result into our baseline
        for key in ("status", "actions_performed", "memory_before_mb", "memory_after_mb", "errors"):
            if key in result:
                cleanup_results[key] = result[key]
    except Exception as e:
        logger.error(f"Cleanup logic failed, but shutdown is still scheduled: {e}")
        cleanup_results["status"] = "error"
        cleanup_results.setdefault("errors", []).append(str(e))

    # 5) Compute memory freed and return a normal response
    memory_freed = cleanup_results.get("memory_before_mb", 0.0) - cleanup_results.get("memory_after_mb", 0.0)

    response = CleanupResponse(
        status=str(cleanup_results.get("status", "unknown")),
        actions_performed=list(cleanup_results.get("actions_performed", [])),
        memory_before_mb=float(cleanup_results.get("memory_before_mb", 0.0)),
        memory_after_mb=float(cleanup_results.get("memory_after_mb", 0.0)),
        memory_freed_mb=round(memory_freed, 1),
        errors=list(cleanup_results.get("errors", [])),
    )

    logger.info(f"✅ CLEANUP COMPLETE ► Status: {response.status}, Memory freed: {response.memory_freed_mb}MB")
    return response


@router.get("/services")
async def get_services_status():
    """
    Get status of all backend services.
    """
    try:
        logger.info("🔍 SERVICES STATUS REQUEST")
        
        from services.alignment_service import AlignmentService  # type: ignore
        alignment_service = AlignmentService()
        
        # Check dependencies
        from alignment.alignment_utils import check_dependencies
        dependencies_available, missing_packages = check_dependencies()
        
        # Get engine info
        engine_info = alignment_service.alignment_engine.get_engine_info()
        
        # Get health status
        health_status = alignment_service.get_health_status()
        
        services_status = {
            'alignment_service': {
                'status': 'healthy' if health_status['overall_status'] == 'healthy' else 'warning',
                'health_status': health_status['overall_status'],
                'memory_usage_mb': health_status.get('memory_usage_mb', 0)
            },
            'dependencies': {
                'available': dependencies_available,
                'missing': missing_packages
            },
            'biopython_engine': {
                'status': 'available',
                'info': engine_info
            },
            'section_normalizer': {
                'status': 'available'
            }
        }
        
        logger.info("✅ SERVICES STATUS COMPLETE")
        return services_status
        
    except Exception as e:
        logger.error(f"❌ Services status check failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Services status check failed: {str(e)}"
        )


@router.get("/processing_types")
async def get_processing_types():
    """
    Get available processing types and their status.
    """
    try:
        logger.info("📋 PROCESSING TYPES REQUEST")
        
        processing_types = {
            "image-to-text": {
                "description": "Extract text from images using OCR and LLM processing",
                "models": ["gpt-4o", "gpt-4o-mini"],
                "extraction_modes": ["legal_document_json_relaxed", "generic_document_json"],
                "status": "available"
            },
            "text-to-schema": {
                "description": "Convert text to structured schema format",
                "models": ["gpt-4o"],
                "status": "available"
            },
            "alignment": {
                "description": "Align multiple legal document drafts for comparison",
                "consensus_strategies": ["highest_confidence", "majority", "sequential"],
                "status": "available"
            }
        }
        
        logger.info("✅ PROCESSING TYPES COMPLETE")
        return processing_types
        
    except Exception as e:
        logger.error(f"❌ Processing types check failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Processing types check failed: {str(e)}"
        ) 


