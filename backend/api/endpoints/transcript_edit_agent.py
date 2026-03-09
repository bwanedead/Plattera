"""Kernel-backed transcript-edit agent run endpoints."""

from __future__ import annotations

import logging
from threading import Thread
from time import time
import time as _time
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from agents.transcript_edit.controller import run_transcript_edit_controller_loop
from agents.transcript_edit.contracts import TranscriptEditAgentRunRequest, TranscriptEditAgentRunResult
from agents.transcript_edit.handoff_packet import build_handoff_packet, persist_handoff_packet
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
_PROGRESS_LOG_LIMIT = 40
_CRITICAL_EVENT_LIMIT = 200
_NONCRITICAL_PROGRESS_PERSIST_INTERVAL_SECONDS = 2.0


def _is_critical_progress_event(event: dict[str, Any]) -> bool:
    event_type = str(event.get("event_type") or "").strip().lower()
    phase = str(event.get("phase") or "").strip().lower()
    if event_type in {"human_feedback_needed", "human_feedback", "resolver_invalid"}:
        return True
    if phase in {
        "human_feedback_needed",
        "human_feedback_received",
        "human_feedback_consumed",
        "human_feedback_reused",
        "human_feedback_stale",
        "human_feedback_prompt_superseded",
        "resolver_invalid",
    }:
        return True
    return False


def _progress_material_signature(event: dict[str, Any]) -> tuple[Any, ...]:
    return (
        str(event.get("phase") or "").strip().lower(),
        str(event.get("event_type") or "").strip().lower(),
        event.get("iteration"),
        str(event.get("execution_state") or "").strip().lower(),
    )


def _safe_registry_update_run(*, run_id: str, patch: dict[str, Any], context: str) -> bool:
    try:
        _registry.update_run(run_id=run_id, patch=patch)
        return True
    except Exception as exc:
        logger.warning(
            "TX_REGISTRY_UPDATE_FAILED ► run_id=%s context=%s error_type=%s error=%s",
            run_id,
            context,
            type(exc).__name__,
            str(exc)[:220],
        )
        return False


class TranscriptEditAgentApiRequest(TranscriptEditAgentRunRequest):
    background: bool = True


class TranscriptEditAgentResumeRequest(BaseModel):
    background: bool = True
    trigger: str | None = "manual_resume"


def _should_wait_feedback(*, result: TranscriptEditAgentRunResult, summary: dict[str, Any]) -> bool:
    status = str(result.status or "").strip().lower()
    if status not in {"needs_review", "failed"}:
        return False
    if bool(summary.get("human_feedback_pending")):
        return True
    classification = str(summary.get("terminal_classification") or "").strip().lower()
    if classification in {
        "blocked_human_feedback_needed",
        "blocked_waiting_feedback",
        "blocked_waiting_feedback_timeout",
    }:
        return True
    # Timeout can race with waiting-feedback ownership; treat it as resumable only with strong HITL evidence.
    reason = str(getattr(result, "reason_code", "") or "").strip().lower()
    if status == "failed" and "budget_wall_time_exceeded" in reason:
        pending_ids = [str(v).strip() for v in list(summary.get("pending_feedback_prompt_ids") or []) if str(v).strip()]
        waiting_owner = summary.get("waiting_feedback_owner")
        return bool(pending_ids) or isinstance(waiting_owner, dict)
    return False


def _build_resume_request_payload(request: TranscriptEditAgentApiRequest) -> dict[str, Any]:
    payload = request.model_dump(mode="json")
    payload.pop("background", None)
    return payload


def _extract_resume_source_ref(*, run: dict[str, Any]) -> str | None:
    snapshot = run.get("snapshot") if isinstance(run.get("snapshot"), dict) else {}
    latest_refs = snapshot.get("latest_refs") if isinstance(snapshot.get("latest_refs"), dict) else {}
    for key in ("tx_edited_transcript_ref", "tx_source_transcript_ref"):
        row = latest_refs.get(key)
        if isinstance(row, dict):
            path = str(row.get("artifact_path") or "").strip()
            if path:
                return path
        if isinstance(row, str) and str(row).strip():
            return str(row).strip()
    return None


def _extract_resume_pending_feedback(run: dict[str, Any]) -> tuple[str | None, str | None, dict[str, Any] | None]:
    snapshot = run.get("snapshot") if isinstance(run.get("snapshot"), dict) else {}
    runtime_hitl = snapshot.get("runtime_hitl_state") if isinstance(snapshot.get("runtime_hitl_state"), dict) else {}
    summary = snapshot.get("terminal_summary") if isinstance(snapshot.get("terminal_summary"), dict) else {}
    blocker_registry = runtime_hitl.get("blocker_registry") if isinstance(runtime_hitl.get("blocker_registry"), dict) else {}
    blocker_rows = [row for row in list(blocker_registry.get("rows") or []) if isinstance(row, dict)]

    waiting_owner = next(
        (
            row
            for row in blocker_rows
            if str(row.get("state") or "").strip().lower() == "waiting_feedback"
        ),
        None,
    )

    prompt_id = str((waiting_owner or {}).get("linked_prompt_id") or "").strip() or None
    decision_key = str((waiting_owner or {}).get("decision_key") or "").strip().lower() or None

    if not prompt_id:
        prompt_id = str(runtime_hitl.get("pending_feedback_prompt_id") or "").strip() or None
    if not decision_key:
        decision_key = str(runtime_hitl.get("pending_feedback_decision_key") or "").strip().lower() or None

    if not prompt_id:
        pending_ids = [str(v).strip() for v in list(summary.get("pending_feedback_prompt_ids") or []) if str(v).strip()]
        if pending_ids:
            prompt_id = pending_ids[0]

    if not decision_key and prompt_id:
        body = str(prompt_id).strip().lower()
        if body.startswith("hitl_"):
            body = body[len("hitl_") :]
            parts = body.split("_")
            if parts:
                maybe = parts[0]
                if maybe in {"township", "range", "section", "tie", "closure", "acreage"}:
                    if maybe == "tie" and len(parts) > 1 and parts[1] in {"distance", "bearing"}:
                        decision_key = f"tie_{parts[1]}"
                    elif maybe == "closure" and len(parts) > 2 and parts[1] == "or" and parts[2] == "pob":
                        decision_key = "closure_or_pob"
                    elif maybe in {"township", "range", "section", "acreage"}:
                        decision_key = maybe

    prompt_context: dict[str, Any] | None = None
    if decision_key:
        prompt_context = {"decision_key": decision_key}
    return prompt_id, decision_key, prompt_context


def _build_resume_request_for_run(*, run: dict[str, Any], trigger: str | None, background: bool) -> TranscriptEditAgentApiRequest:
    request_meta = run.get("request") if isinstance(run.get("request"), dict) else {}
    payload = request_meta.get("resume_request") if isinstance(request_meta.get("resume_request"), dict) else {}
    snapshot = run.get("snapshot") if isinstance(run.get("snapshot"), dict) else {}
    summary = snapshot.get("terminal_summary") if isinstance(snapshot.get("terminal_summary"), dict) else {}
    base_payload = dict(payload)
    source_ref = _extract_resume_source_ref(run=run)
    if source_ref:
        base_payload["source_transcript_ref"] = source_ref
        base_payload["source_text"] = None
    if trigger:
        base_payload["trigger"] = trigger
    pending_prompt_id, pending_decision_key, prompt_context = _extract_resume_pending_feedback(run)
    runtime_hitl = snapshot.get("runtime_hitl_state") if isinstance(snapshot.get("runtime_hitl_state"), dict) else {}
    blocker_registry = (
        dict(runtime_hitl.get("blocker_registry"))
        if isinstance(runtime_hitl.get("blocker_registry"), dict)
        else (
            dict(summary.get("blocker_registry"))
            if isinstance(summary.get("blocker_registry"), dict)
            else None
        )
    )
    if pending_prompt_id:
        base_payload["resume_pending_feedback_prompt_id"] = pending_prompt_id
    if pending_decision_key:
        base_payload["resume_pending_feedback_decision_key"] = pending_decision_key
    if isinstance(prompt_context, dict):
        base_payload["resume_pending_feedback_prompt"] = prompt_context
    if isinstance(blocker_registry, dict):
        base_payload["resume_blocker_registry"] = blocker_registry
    base_payload["background"] = bool(background)
    return TranscriptEditAgentApiRequest.model_validate(base_payload)


def request_run_resume_if_waiting(*, run_id: str, trigger: str | None, background: bool = True) -> dict[str, Any]:
    run = _registry.get_run(run_id)
    if not isinstance(run, dict):
        return {"resumed": False, "reason": "run_not_found"}
    status = str(run.get("status") or "").strip().lower()
    if status == "running":
        return {"resumed": False, "reason": "already_running"}
    if status != "waiting_feedback":
        return {"resumed": False, "reason": f"not_waiting_feedback:{status or 'unknown'}"}
    request = _build_resume_request_for_run(run=run, trigger=trigger, background=background)
    updated = _safe_registry_update_run(
        run_id=run_id,
        patch={
            "status": "running",
            "snapshot": {
                **(run.get("snapshot") if isinstance(run.get("snapshot"), dict) else {}),
                "run_id": run_id,
                "status": "running",
                "resume_trigger": str(trigger or "").strip() or "resume",
                "live_status": {
                    "phase": "resume_starting",
                    "message": "Resuming transcript edit run.",
                    "execution_state": "running",
                    "timestamp_epoch_seconds": int(time()),
                },
            },
        },
        context="resume_mark_running",
    )
    if not updated:
        return {"resumed": False, "reason": "resume_registry_update_failed"}
    thread = Thread(target=_execute_run, args=(run_id, request), daemon=True)
    thread.start()
    return {"resumed": True, "run_id": run_id, "status": "running"}


def _execute_run(run_id: str, request: TranscriptEditAgentApiRequest) -> None:
    try:
        progress_log: list[dict[str, Any]] = []
        critical_events: list[dict[str, Any]] = []
        seq = 0
        loop_started_mono = _time.perf_counter()
        last_event_mono = loop_started_mono
        last_registry_persist_mono = loop_started_mono
        last_registry_material_signature: tuple[Any, ...] | None = None

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
            nonlocal last_event_mono, last_registry_persist_mono, last_registry_material_signature
            now_mono = _time.perf_counter()
            elapsed_ms = int((now_mono - loop_started_mono) * 1000)
            since_prev_ms = int((now_mono - last_event_mono) * 1000)
            last_event_mono = now_mono
            latest = {
                "timestamp_epoch_seconds": int(time()),
                "elapsed_ms": elapsed_ms,
                "since_prev_ms": since_prev_ms,
                **(event if isinstance(event, dict) else {}),
            }
            progress_log.append(latest)
            is_critical = _is_critical_progress_event(latest)
            if is_critical:
                critical_events.append(dict(latest))
                if len(critical_events) > _CRITICAL_EVENT_LIMIT:
                    del critical_events[:-_CRITICAL_EVENT_LIMIT]
            if len(progress_log) > _PROGRESS_LOG_LIMIT:
                del progress_log[:-_PROGRESS_LOG_LIMIT]
            current_signature = _progress_material_signature(latest)
            signature_changed = current_signature != last_registry_material_signature
            persist_due_to_time = (
                (now_mono - last_registry_persist_mono) >= _NONCRITICAL_PROGRESS_PERSIST_INTERVAL_SECONDS
            )
            should_persist = bool(
                is_critical
                or last_registry_material_signature is None
                or persist_due_to_time
                or signature_changed
            )
            if should_persist:
                persisted = _safe_registry_update_run(
                    run_id=run_id,
                    patch={
                        "status": "running",
                        "snapshot": {
                            "run_id": run_id,
                            "status": "running",
                            "live_status": latest,
                            "progress_log": list(progress_log),
                            "critical_events": list(critical_events),
                        },
                    },
                    context="progress_update",
                )
                if persisted:
                    last_registry_persist_mono = now_mono
                    last_registry_material_signature = current_signature
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
            startup_countdown_seconds=15,
        )
        run_terminal_message = terminal_message(result)
        run_terminal_summary = terminal_summary(
            progress_log,
            result,
            critical_events=critical_events,
            runtime_hitl_state=(
                result.runtime_hitl_state
                if isinstance(result.runtime_hitl_state, dict)
                else None
            ),
        )
        handoff_packet = build_handoff_packet(
            run_id=run_id,
            request=request,
            result=result,
            terminal_summary=run_terminal_summary,
            terminal_message=run_terminal_message,
            progress_log=progress_log,
        )
        handoff_packet_ref = persist_handoff_packet(
            run_id=run_id,
            dossier_id=request.dossier_id,
            packet=handoff_packet,
        )
        run_terminal_summary = {
            **run_terminal_summary,
            "handoff_packet_ref": handoff_packet_ref,
            "handoff_summary": handoff_packet.get("handoff_summary"),
        }
        waiting_feedback = _should_wait_feedback(result=result, summary=run_terminal_summary)
        final_status = "waiting_feedback" if waiting_feedback else result.status
        _safe_registry_update_run(
            run_id=run_id,
            patch={
                "status": final_status,
                "snapshot": {
                    "run_id": run_id,
                    "status": final_status,
                    "reason_code": result.reason_code,
                    "iterations": result.iterations,
                    "session_id": result.session_id,
                    "run_artifact_ref": result.run_artifact_ref,
                    "latest_refs": result.latest_refs,
                    "review_required": result.review_required,
                    "terminal_summary": run_terminal_summary,
                    "runtime_hitl_state": (
                        result.runtime_hitl_state if isinstance(result.runtime_hitl_state, dict) else None
                    ),
                    "live_status": progress_log[-1] if progress_log else None,
                    "progress_log": list(progress_log),
                    "critical_events": list(critical_events),
                    "waiting_feedback": bool(waiting_feedback),
                    "resumable": bool(waiting_feedback),
                },
            },
            context="finalize_run",
        )
        if waiting_feedback:
            _publish_viewer_event(
                "status",
                {
                    "phase": "waiting_feedback",
                    "message": "Paused waiting for human feedback. Run is resumable.",
                    "execution_state": "waiting",
                    "iteration": result.iterations,
                    "latest_refs": result.latest_refs,
                    "review_required": result.review_required,
                    "summary": run_terminal_summary,
                    "handoff_packet_ref": handoff_packet_ref,
                    "handoff_summary": handoff_packet.get("handoff_summary"),
                    "terminal": False,
                    "resumable": True,
                },
            )
        else:
            _publish_viewer_event(
                "done",
                {
                    "phase": result.status,
                    "message": run_terminal_message,
                    "execution_state": result.status,
                    "iteration": result.iterations,
                    "latest_refs": result.latest_refs,
                    "review_required": result.review_required,
                    "summary": run_terminal_summary,
                    "handoff_packet_ref": handoff_packet_ref,
                    "handoff_summary": handoff_packet.get("handoff_summary"),
                    "terminal": True,
                },
            )
        logger.info(
            "TX_LOOP_DONE ► run_id=%s status=%s iterations=%s elapsed_ms=%s reason=%s",
            run_id,
            final_status,
            result.iterations,
            int((_time.perf_counter() - loop_started_mono) * 1000),
            result.reason_code,
        )
    except Exception as exc:
        _safe_registry_update_run(
            run_id=run_id,
            patch={"status": "failed", "error": str(exc)},
            context="exception_path_mark_failed",
        )
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
            "validation_mode": request.validation_mode,
            "has_source_transcript_ref": bool(request.source_transcript_ref),
            "has_source_text": bool(request.source_text),
            "source_image_refs_count": len(request.source_image_refs or []),
            "has_edit_plan": isinstance(request.edit_plan, dict),
            "resume_request": _build_resume_request_payload(request),
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


@router.post("/run/{run_id}/resume")
async def resume_run(run_id: str, request: TranscriptEditAgentResumeRequest) -> dict[str, Any]:
    result = request_run_resume_if_waiting(
        run_id=run_id,
        trigger=request.trigger,
        background=request.background,
    )
    if not bool(result.get("resumed")):
        reason = str(result.get("reason") or "resume_not_allowed")
        if reason == "run_not_found":
            raise HTTPException(status_code=404, detail=reason)
        if reason == "already_running":
            raise HTTPException(status_code=409, detail=reason)
        raise HTTPException(status_code=409, detail=reason)
    return result
