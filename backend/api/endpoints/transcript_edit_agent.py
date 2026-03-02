"""Kernel-backed transcript-edit agent run endpoints."""

from __future__ import annotations

import logging
from threading import Thread
from time import time
import time as _time
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query

from agents.transcript_edit.controller import run_transcript_edit_controller_loop
from agents.transcript_edit.contracts import TranscriptEditAgentRunRequest
from agents.transcript_edit.terminalization import terminal_message, terminal_summary
from agent_kernel.actions import ActionExecutor, ActionExecutorDeps
from agent_kernel.session import KernelSessionManager
from agent_kernel.tooling import (
    TranscriptAuditTool,
    TranscriptImageVerificationTool,
    TranscriptEditPlanApplyTool,
    TranscriptMappingPromoterTool,
    TranscriptSpanSeedsSaverTool,
    TranscriptSpanOpenerTool,
)
from services.agent_kernel.run_artifact_persistence_service import RunArtifactPersistenceService
from services.agent_viewer.event_bus import event_bus as viewer_event_bus
from transcript_edit.run_registry import TranscriptionEditRunRegistry

router = APIRouter()

_registry = TranscriptionEditRunRegistry()
logger = logging.getLogger(__name__)

class TranscriptEditAgentApiRequest(TranscriptEditAgentRunRequest):
    background: bool = True


def _execute_run(run_id: str, request: TranscriptEditAgentApiRequest) -> None:
    try:
        progress_log: list[dict[str, Any]] = []
        seq = 0
        loop_started_mono = _time.perf_counter()
        last_event_mono = loop_started_mono

        def _to_artifact_ref_map(obj: Any) -> dict[str, dict[str, str]]:
            if not isinstance(obj, dict):
                return {}
            refs: dict[str, dict[str, str]] = {}
            for key, value in obj.items():
                if isinstance(value, str) and value.strip():
                    refs[str(key)] = {"artifact_path": value}
                elif isinstance(value, dict):
                    path = value.get("artifact_path")
                    if isinstance(path, str) and path.strip():
                        refs[str(key)] = {"artifact_path": path}
            return refs

        def _publish_viewer_event(event_type: str, event: dict[str, Any]) -> None:
            nonlocal seq
            payload = event if isinstance(event, dict) else {}
            viewer_event_bus.publish_sync(
                f"transcript_edit:{run_id}",
                {
                    "protocol": "agent_viewer_event_v1",
                    "run_id": run_id,
                    "loop_kind": "transcript_edit",
                    "seq": seq,
                    "iteration": payload.get("iteration"),
                    "timestamp_epoch_seconds": int(time()),
                    "event_type": event_type,
                    "status": {
                        "stage": payload.get("phase"),
                        "line1": payload.get("message") or "Transcript edit update",
                        "line2": payload.get("execution_state"),
                    },
                    "artifact_refs": _to_artifact_ref_map(payload.get("latest_refs")),
                    "payload": payload,
                },
            )
            seq += 1

        def _progress_update(event: dict[str, Any]) -> None:
            nonlocal last_event_mono
            now_mono = _time.perf_counter()
            elapsed_ms = int((now_mono - loop_started_mono) * 1000)
            since_prev_ms = int((now_mono - last_event_mono) * 1000)
            last_event_mono = now_mono
            progress_log.append(
                {
                    "timestamp_epoch_seconds": int(time()),
                    "elapsed_ms": elapsed_ms,
                    "since_prev_ms": since_prev_ms,
                    **(event if isinstance(event, dict) else {}),
                }
            )
            if len(progress_log) > 40:
                del progress_log[:-40]
            latest = progress_log[-1] if progress_log else None
            _registry.update_run(
                run_id=run_id,
                patch={
                    "status": "running",
                    "snapshot": {
                        "run_id": run_id,
                        "status": "running",
                        "live_status": latest,
                        "progress_log": list(progress_log),
                    },
                },
            )
            event_type = str(event.get("event_type") or "status")
            phase = str(event.get("phase") or "status")
            iter_value = event.get("iteration")
            message = str(event.get("message") or "").strip()
            logger.info(
                "TX_LOOP_EVENT ► run_id=%s iteration=%s phase=%s elapsed_ms=%s since_prev_ms=%s message=%s",
                run_id,
                iter_value if isinstance(iter_value, int) else "n/a",
                phase,
                elapsed_ms,
                since_prev_ms,
                message[:220] if message else "n/a",
            )
            _publish_viewer_event(event_type, event)

        persistence = RunArtifactPersistenceService()
        session_manager = KernelSessionManager(
            action_executor=ActionExecutor(
                deps=ActionExecutorDeps(
                    transcript_auditor=TranscriptAuditTool(),
                    transcript_span_opener=TranscriptSpanOpenerTool(),
                    transcript_image_verifier=TranscriptImageVerificationTool(),
                    transcript_plan_applier=TranscriptEditPlanApplyTool(),
                    transcript_span_seeds_saver=TranscriptSpanSeedsSaverTool(),
                    transcript_promoter=TranscriptMappingPromoterTool(),
                )
            ),
            persistence_service=persistence,
        )
        result = run_transcript_edit_controller_loop(
            session_manager=session_manager,
            request=TranscriptEditAgentRunRequest.model_validate(request.model_dump(mode="json")),
            request_id_prefix=f"tx-agent-{run_id}",
            progress_cb=_progress_update,
        )
        run_terminal_summary = terminal_summary(progress_log, result)
        _registry.update_run(
            run_id=run_id,
            patch={
                "status": result.status,
                "snapshot": {
                    "run_id": run_id,
                    "status": result.status,
                    "reason_code": result.reason_code,
                    "iterations": result.iterations,
                    "session_id": result.session_id,
                    "run_artifact_ref": result.run_artifact_ref,
                    "latest_refs": result.latest_refs,
                    "review_required": result.review_required,
                    "terminal_summary": run_terminal_summary,
                    "live_status": progress_log[-1] if progress_log else None,
                    "progress_log": list(progress_log),
                },
            },
        )
        _publish_viewer_event(
            "done",
            {
                "phase": result.status,
                "message": terminal_message(result),
                "execution_state": result.status,
                "iteration": result.iterations,
                "latest_refs": result.latest_refs,
                "review_required": result.review_required,
                "summary": run_terminal_summary,
                "terminal": True,
            },
        )
        logger.info(
            "TX_LOOP_DONE ► run_id=%s status=%s iterations=%s elapsed_ms=%s reason=%s",
            run_id,
            result.status,
            result.iterations,
            int((_time.perf_counter() - loop_started_mono) * 1000),
            result.reason_code,
        )
    except Exception as exc:
        _registry.update_run(run_id=run_id, patch={"status": "failed", "error": str(exc)})
        viewer_event_bus.publish_sync(
            f"transcript_edit:{run_id}",
            {
                "protocol": "agent_viewer_event_v1",
                "run_id": run_id,
                "loop_kind": "transcript_edit",
                "seq": seq if "seq" in dir() else 0,
                "iteration": None,
                "timestamp_epoch_seconds": int(time()),
                "event_type": "done",
                "status": {"stage": "failed", "line1": "Transcript edit run failed", "line2": str(exc)[:240]},
                "artifact_refs": {},
                "payload": {"error": str(exc), "terminal": True},
            },
        )


@router.post("/run")
async def start_run(request: TranscriptEditAgentApiRequest) -> dict[str, Any]:
    if not request.source_transcript_ref and not request.source_text:
        raise HTTPException(status_code=400, detail="source_transcript_ref_or_source_text_required")
    run_id = f"tx_agent_{int(time())}_{uuid4().hex[:8]}"
    _registry.create_run(
        run_id=run_id,
        request={
            "dossier_id": request.dossier_id,
            "transcription_id": request.transcription_id,
            "trigger": request.trigger,
            "model": request.model,
            "max_iterations": request.max_iterations,
            "auto_promote": request.auto_promote,
            "mode": request.mode,
            "has_source_transcript_ref": bool(request.source_transcript_ref),
            "has_source_text": bool(request.source_text),
            "source_image_refs_count": len(request.source_image_refs or []),
            "has_edit_plan": isinstance(request.edit_plan, dict),
        },
    )
    if request.background:
        thread = Thread(target=_execute_run, args=(run_id, request), daemon=True)
        thread.start()
        return {"run_id": run_id, "status": "running"}
    _execute_run(run_id, request)
    run = _registry.get_run(run_id)
    return run or {"run_id": run_id, "status": "unknown"}


@router.get("/run/{run_id}")
async def get_run(run_id: str) -> dict[str, Any]:
    run = _registry.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="run_not_found")
    return run


@router.get("/runs")
async def list_runs(limit: int = Query(default=20, ge=1, le=200)) -> dict[str, Any]:
    runs = _registry.list_runs(limit=limit)
    return {"runs": runs, "count": len(runs)}
