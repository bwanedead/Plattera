"""Backend API endpoints for controller-driven agent-loop runs."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from threading import Thread
from time import time
from typing import Any, AsyncGenerator, Optional
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from agent_kernel.models import KernelBudgets, KernelGoal, KernelSessionStartRequest
from agent_kernel.session import KernelSessionManager
from agent_kernel.tooling import CorpusArtifactOpener
from agents.controller.controller import (
    restore_transcript_event_hook,
    run_controller_loop,
    set_transcript_event_hook,
)
from agents.controller.openai_client import OpenAINextStepClient
from agents.controller.bootstrap import (
    hydrate_and_persist_finalized_dossier_text,
    persist_deed_text_artifact,
)
from services.agent_kernel.run_artifact_persistence_service import RunArtifactPersistenceService
from services.agent_loop.event_bus import event_bus
from services.agent_loop.run_registry_service import AgentLoopRunRegistryService
from services.dossier.management_service import DossierManagementService
from services.dossier.finalized_snapshot_service import FinalizedSnapshotService
from config.paths import agent_kernel_artifacts_root, dossiers_feature_graphs_artifacts_root

router = APIRouter()
logger = logging.getLogger(__name__)

_run_registry = AgentLoopRunRegistryService()
_artifact_opener = CorpusArtifactOpener()
_dossier_manager = DossierManagementService()
_finalized_snapshot_service = FinalizedSnapshotService()
_MAX_ARTIFACT_JSON_BYTES = 262144
_MAX_LOG_ERROR_CHARS = 1000


class AgentLoopRunRequest(BaseModel):
    dossier_id: Optional[str] = None
    text: Optional[str] = None
    initial_ir_ref: Optional[str] = None
    model: str = "gpt-5.2"
    max_iterations: int = Field(default=12, ge=1, le=100)
    requires_global_placement: bool = False
    render_required: bool = False
    background: bool = True


def _build_start_request(run_id: str, request: AgentLoopRunRequest) -> KernelSessionStartRequest:
    request_id = f"agent-loop-{run_id}"
    initial_graph_json = None
    bootstrap_metadata: dict[str, Any] = {
        "source": "agent_loop_api_bootstrap",
        "dossier_id": request.dossier_id,
    }
    if request.text and request.text.strip():
        deed_artifact = persist_deed_text_artifact(
            request_id=request_id,
            deed_text=request.text.strip(),
            dossier_id=request.dossier_id,
        )
        bootstrap_metadata["source"] = "agent_loop_api_text_bootstrap"
        bootstrap_metadata["deed_text_excerpt"] = deed_artifact.excerpt
        bootstrap_metadata["deed_text_artifact_ref"] = deed_artifact.artifact_path
    elif request.dossier_id:
        deed_artifact = hydrate_and_persist_finalized_dossier_text(
            request_id=request_id,
            dossier_id=request.dossier_id,
        )
        if deed_artifact is not None:
            bootstrap_metadata["source"] = "agent_loop_api_dossier_bootstrap"
            bootstrap_metadata["deed_text_excerpt"] = deed_artifact.excerpt
            bootstrap_metadata["deed_text_artifact_ref"] = deed_artifact.artifact_path
        else:
            bootstrap_metadata["bootstrap_note"] = (
                "dossier_deed_text_hydration_failed; suggested_first_move=hydrate_deed"
            )

    if bootstrap_metadata:
        initial_graph_json = {
            "graph_id": f"graph_{request_id}",
            "nodes": [],
            "edges": [],
            "metadata": bootstrap_metadata,
        }
    return KernelSessionStartRequest(
        request_id=request_id,
        goal=KernelGoal(
            requires_global_placement=request.requires_global_placement,
            render_required=request.render_required,
            objective="agent_loop_api_run",
        ),
        budgets=KernelBudgets(
            max_steps=30,
            max_wall_time_seconds=600,
            max_retrieval_calls=12,
            max_semantic_calls=8,
            max_patch_calls=8,
        ),
        dossier_id=request.dossier_id,
        source_entry_ref=(f"final:{request.dossier_id}" if request.dossier_id else None),
        initial_ir_ref=request.initial_ir_ref,
        initial_graph_json=initial_graph_json,
    )


def _ensure_text_run_has_real_dossier(request: AgentLoopRunRequest) -> AgentLoopRunRequest:
    if request.dossier_id or not (request.text and request.text.strip()):
        return request
    text = request.text.strip()
    title_seed = " ".join(text.split())[:72]
    title = title_seed or "Direct Text Agent Loop Run"
    dossier = _dossier_manager.create_dossier(title=title)
    _finalized_snapshot_service.write_finalized_snapshot(
        dossier_id=str(dossier.id),
        stitched_text=text,
        dossier_title=dossier.title,
        metadata={"source": "agent_loop_direct_text_bootstrap"},
    )
    return request.model_copy(update={"dossier_id": str(dossier.id)})


def _execute_run(run_id: str, request: AgentLoopRunRequest) -> None:
    try:
        persistence = RunArtifactPersistenceService()
        session_manager = KernelSessionManager(persistence_service=persistence)
        llm_client = OpenAINextStepClient()
        start_request = _build_start_request(run_id, request)
        seq_state = {"seq": 0}

        def _on_controller_event(event: dict[str, object]) -> None:
            tape_event = _agent_tape_event_from_transcript_event(run_id=run_id, event=event, seq=seq_state["seq"])
            seq_state["seq"] += 1
            if tape_event is None:
                return
            event_bus.publish_sync(run_id, tape_event)
            _run_registry.update_run(
                run_id=run_id,
                patch={"live_status": tape_event.get("status"), "last_agent_tape_event": tape_event},
            )

        previous_hook = set_transcript_event_hook(_on_controller_event)
        try:
            result = run_controller_loop(
                session_manager=session_manager,
                llm_client=llm_client,
                start_request=start_request,
                model=request.model,
                max_iterations=request.max_iterations,
            )
        finally:
            restore_transcript_event_hook(previous_hook)
        patch = {
            "status": "completed",
            "session_id": result.session_id,
            "run_artifact_ref": result.run_artifact_ref,
            "transcript_artifact_ref": result.transcript_artifact_ref,
            "terminal": result.terminal.model_dump(mode="json"),
            "dashboard": result.last_dashboard,
        }
        updated = _run_registry.update_run(run_id=run_id, patch=patch)
        logger.info(
            "agent_loop_run_completed %s",
            json.dumps(
                {
                    "run_id": run_id,
                    "status": "completed",
                    "model": request.model,
                    "max_iterations": request.max_iterations,
                    "session_id": result.session_id,
                    "run_artifact_ref": result.run_artifact_ref,
                    "transcript_artifact_ref": result.transcript_artifact_ref,
                    "terminal": result.terminal.model_dump(mode="json"),
                },
                ensure_ascii=True,
            ),
        )
        if updated is not None:
            event_bus.publish_sync(run_id, {"event_type": "run_completed", "run": updated})
    except Exception as exc:
        logger.exception("agent_loop_run_failed")
        snapshot = _run_registry.get_run(run_id) or {}
        logger.error(
            "agent_loop_run_failed_summary %s",
            json.dumps(
                {
                    "run_id": run_id,
                    "status": "failed",
                    "model": request.model,
                    "max_iterations": request.max_iterations,
                    "error_type": type(exc).__name__,
                    "error_message": str(exc)[:_MAX_LOG_ERROR_CHARS],
                    "run_artifact_ref": snapshot.get("run_artifact_ref"),
                    "transcript_artifact_ref": snapshot.get("transcript_artifact_ref"),
                },
                ensure_ascii=True,
            ),
        )
        patch = {"status": "failed", "error": str(exc)}
        updated = _run_registry.update_run(run_id=run_id, patch=patch)
        if updated is not None:
            event_bus.publish_sync(run_id, {"event_type": "run_failed", "run": updated})


@router.post("/run")
async def start_agent_loop_run(request: AgentLoopRunRequest) -> dict[str, Any]:
    if not request.initial_ir_ref and not request.text and not request.dossier_id:
        raise HTTPException(status_code=400, detail="one_of_dossier_id_or_text_or_initial_ir_ref_required")
    request = _ensure_text_run_has_real_dossier(request)
    run_id = f"run_{int(time())}_{uuid4().hex[:8]}"
    entry = _run_registry.create_run(
        run_id=run_id,
        request={
            "request_id": f"agent-loop-{run_id}",
            "dossier_id": request.dossier_id,
            "model": request.model,
        },
    )
    logger.info(
        "agent_loop_run_created %s",
        json.dumps(
            {
                "run_id": run_id,
                "request_id": f"agent-loop-{run_id}",
                "dossier_id": request.dossier_id,
                "has_text_input": bool(request.text and request.text.strip()),
                "initial_ir_ref": request.initial_ir_ref,
                "model": request.model,
                "max_iterations": request.max_iterations,
                "background": request.background,
            },
            ensure_ascii=True,
        ),
    )
    await event_bus.publish(run_id, {"event_type": "run_started", "run": entry})

    if request.background:
        thread = Thread(target=_execute_run, args=(run_id, request), daemon=True)
        thread.start()
        return {"run_id": run_id, "status": "running", "dossier_id": request.dossier_id}

    _execute_run(run_id, request)
    run = _run_registry.get_run(run_id)
    return run or {"run_id": run_id, "status": "unknown"}


@router.get("/run/{run_id}")
async def get_agent_loop_run(run_id: str) -> dict[str, Any]:
    run = _run_registry.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="run_not_found")
    return run


@router.get("/runs")
async def list_agent_loop_runs(limit: int = Query(default=20, ge=1, le=200)) -> dict[str, Any]:
    runs = _run_registry.list_runs(limit=limit)
    return {"runs": runs, "count": len(runs)}


@router.get("/artifact/open")
async def open_agent_loop_artifact(artifact_ref: str = Query(..., min_length=1)) -> dict[str, Any]:
    payload = _artifact_opener.open_artifact({"artifact_ref": artifact_ref})
    return {
        "reason_codes": payload.get("reason_codes", []),
        "summary": payload.get("summary", ""),
        "artifact_ref": (
            payload.get("artifact_ref").model_dump(mode="json")
            if hasattr(payload.get("artifact_ref"), "model_dump")
            else payload.get("artifact_ref")
        ),
    }


@router.get("/artifact/json")
async def get_agent_loop_artifact_json(artifact_ref: str = Query(..., min_length=1)) -> dict[str, Any]:
    safe_path = _resolve_agent_loop_artifact_path(artifact_ref)
    if safe_path is None:
        raise HTTPException(status_code=400, detail="artifact_ref_outside_allowed_roots")
    if not safe_path.exists():
        raise HTTPException(status_code=404, detail="artifact_not_found")
    try:
        raw = safe_path.read_bytes()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"artifact_read_failed:{type(exc).__name__}") from exc
    if len(raw) > _MAX_ARTIFACT_JSON_BYTES:
        raise HTTPException(status_code=413, detail="artifact_json_too_large")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"artifact_json_invalid:{type(exc).__name__}") from exc
    if not isinstance(payload, (dict, list)):
        raise HTTPException(status_code=400, detail="artifact_json_not_object_or_array")
    return {"artifact_path": str(safe_path), "json": payload}


async def _sse_stream(run_id: str, q: asyncio.Queue) -> AsyncGenerator[str, None]:
    try:
        while True:
            try:
                data = await asyncio.wait_for(q.get(), timeout=10.0)
                yield f"data: {data}\n\n"
            except asyncio.TimeoutError:
                yield "event: ping\ndata: {}\n\n"
    except asyncio.CancelledError:
        return
    finally:
        await event_bus.unsubscribe(run_id, q)


@router.get("/events/{run_id}", include_in_schema=False)
async def stream_agent_loop_events(run_id: str):
    q = await event_bus.subscribe(run_id)
    return StreamingResponse(_sse_stream(run_id, q), media_type="text/event-stream")


def _resolve_agent_loop_artifact_path(artifact_ref: str) -> Path | None:
    try:
        path = Path(artifact_ref).resolve()
    except Exception:
        return None
    roots: list[Path] = []
    try:
        roots.append(agent_kernel_artifacts_root().resolve())
    except Exception:
        pass
    try:
        roots.append(dossiers_feature_graphs_artifacts_root().resolve())
    except Exception:
        pass
    for root in roots:
        if path == root or root in path.parents:
            return path
    return None


def _agent_tape_event_from_transcript_event(*, run_id: str, event: dict[str, object], seq: int) -> dict[str, Any] | None:
    event_type = str(event.get("event_type") or "")
    payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
    ts = event.get("timestamp_epoch_seconds")
    iteration = payload.get("iteration")

    def _status_obj(
        *,
        stage: str,
        action_type: str | None = None,
        outcome: str | None = None,
        line1: str,
        line2: str | None = None,
        reason_code: str | None = None,
        artifact_refs: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        display_delta = payload.get("display_delta")
        return {
            "event_type": "agent_tape_update",
            "run_id": run_id,
            "seq": seq,
            "timestamp_epoch_seconds": ts,
            "source_event_type": event_type,
            "status": {
                "iteration": iteration if isinstance(iteration, int) else None,
                "stage": stage,
                "phase": _agent_tape_phase(
                    stage=stage,
                    action_type=action_type,
                    outcome=outcome,
                    reason_code=reason_code,
                ),
                "action_type": action_type,
                "outcome": outcome,
                "reason_code": reason_code,
                "status_chip": _agent_tape_status_chip(
                    stage=stage,
                    action_type=action_type,
                    outcome=outcome,
                    reason_code=reason_code,
                ),
                "display_delta": (
                    str(display_delta)[:220]
                    if isinstance(display_delta, str) and display_delta.strip()
                    else None
                ),
                "artifact_refs": artifact_refs or None,
                "line1": line1[:200],
                "line2": (line2[:240] if isinstance(line2, str) else None),
            },
        }

    if event_type == "agent_proposed_step":
        action_type = str(payload.get("action_type") or "")
        why = str(payload.get("why") or "")
        summary_excerpt = payload.get("iteration_summary_excerpt")
        line2 = str(summary_excerpt) if isinstance(summary_excerpt, str) and summary_excerpt else why
        return _status_obj(
            stage="proposed",
            action_type=action_type or None,
            outcome="proposed",
            line1=f"Proposed {action_type or 'step'}",
            line2=line2,
        )
    if event_type == "controller_autofill":
        action_type = str(payload.get("action_type") or "")
        filled = payload.get("filled")
        filled_text = ", ".join(str(v) for v in filled[:5]) if isinstance(filled, list) else ""
        return _status_obj(
            stage="validating",
            action_type=action_type or None,
            outcome="autofill",
            line1=f"Controller autofilled {action_type or 'step'}",
            line2=filled_text or None,
        )
    if event_type == "controller_refusal":
        action_type = str(payload.get("action_type") or "")
        refusal = payload.get("refusal") if isinstance(payload.get("refusal"), dict) else {}
        reason_code = str((refusal or {}).get("reason_code") or event.get("detail") or "")
        how_to = payload.get("how_to") if isinstance(payload.get("how_to"), dict) else {}
        line2 = None
        if isinstance(how_to.get("minimal_working_example"), dict):
            line2 = "Use tool_cheatsheet minimal_working_example (see transcript)"
        return _status_obj(
            stage="refused",
            action_type=action_type or None,
            outcome="controller_refusal",
            reason_code=reason_code or None,
            line1=f"Controller refused {action_type or 'step'}: {reason_code or 'invalid request'}",
            line2=line2,
        )
    if event_type == "controller_parse_failed":
        parse_error = str(payload.get("parse_error") or "")
        attempt = str(payload.get("attempt") or "")
        return _status_obj(
            stage="parse_failed",
            outcome="parse_failed",
            reason_code=parse_error or None,
            line1=f"Proposal parse failed ({attempt or 'attempt'})",
            line2=parse_error or str(payload.get('error') or '')[:200] or None,
        )
    if event_type == "controller_parse_fail_resync":
        action_type = str(payload.get("action_type") or "")
        return _status_obj(
            stage="resync",
            action_type=action_type or None,
            outcome="controller_resync",
            line1=f"Controller resync: {action_type or 'open_artifact'}",
            line2=str(payload.get("why") or "") or None,
        )
    if event_type == "kernel_step_result":
        action_type = str(payload.get("action_type") or "")
        execution_state = str(payload.get("execution_state") or event.get("detail") or "")
        refusal = payload.get("refusal") if isinstance(payload.get("refusal"), dict) else {}
        terminal = payload.get("terminal") if isinstance(payload.get("terminal"), dict) else {}
        dash_fc = payload.get("dashboard_failure_classification") if isinstance(payload.get("dashboard_failure_classification"), dict) else {}
        latest_refs = payload.get("latest_refs") if isinstance(payload.get("latest_refs"), dict) else {}
        reason_code = str(
            (refusal or {}).get("reason_code")
            or (terminal or {}).get("reason_code")
            or (dash_fc or {}).get("reason_code")
            or ""
        )
        ref_keys = [k for k, v in latest_refs.items() if isinstance(v, str) and v][:4]
        line2 = f"Updated refs: {', '.join(ref_keys)}" if ref_keys else None
        artifact_refs = {k: v for k, v in latest_refs.items() if isinstance(v, str) and v}
        return _status_obj(
            stage="executing",
            action_type=action_type or None,
            outcome=execution_state or None,
            reason_code=reason_code or None,
            line1=f"{action_type or 'step'} -> {execution_state or 'completed'}",
            line2=line2,
            artifact_refs=artifact_refs or None,
        )
    if event_type == "controller_no_progress_stop":
        return _status_obj(
            stage="stopped",
            outcome="no_progress",
            reason_code=str(payload.get("reason_code") or event.get("detail") or "") or None,
            line1="Controller stopped: no-progress safety brake",
            line2=str(payload.get("reason_code") or "") or None,
        )
    return None


def _agent_tape_phase(
    *,
    stage: str,
    action_type: str | None,
    outcome: str | None,
    reason_code: str | None,
) -> str:
    stage_l = (stage or "").lower()
    action_l = (action_type or "").lower()
    outcome_l = (outcome or "").lower()
    reason_l = (reason_code or "").lower()

    if stage_l in {"stopped"} or "no_progress" in reason_l:
        return "stopped"
    if stage_l in {"parse_failed", "resync"}:
        return "recovering"
    if stage_l in {"refused"} or "refusal" in outcome_l:
        return "repairing"
    if action_l in {"draft_ir", "propose_patch", "set_graph_requirements"}:
        return "drafting"
    if action_l in {"compile", "judge", "bundle", "validate", "georeference", "declare_done"}:
        return "verifying"
    if action_l in {"open_artifact", "open_text_spans", "hydrate_deed", "retrieve_evidence", "upsert_deed_span_index"}:
        return "diagnosing"
    if stage_l in {"proposed", "validating", "executing"}:
        return "working"
    return "working"


def _agent_tape_status_chip(
    *,
    stage: str,
    action_type: str | None,
    outcome: str | None,
    reason_code: str | None,
) -> str:
    stage_l = (stage or "").lower()
    action_l = (action_type or "").lower()
    outcome_l = (outcome or "").lower()
    reason_l = (reason_code or "").lower()

    if "declare_done" in action_l and outcome_l in {"executed", "completed"}:
        return "Done"
    if stage_l == "stopped" or "no_progress" in reason_l:
        return "Stopped"
    if stage_l in {"parse_failed", "resync"}:
        return "Recovering"
    if stage_l == "refused":
        return "Needs input"
    if action_l in {"hydrate_deed", "open_artifact", "open_text_spans"}:
        return "Reading deed"
    if action_l == "retrieve_evidence":
        return "Researching"
    if action_l in {"draft_ir", "propose_patch", "set_graph_requirements"}:
        return "Drafting"
    if action_l in {"compile", "judge"}:
        return "Checking"
    if action_l == "bundle":
        return "Packaging"
    if action_l == "georeference":
        return "Mapping"
    if action_l == "validate":
        return "Validating"
    if action_l == "declare_done":
        return "Final review"
    if stage_l in {"proposed", "validating", "executing"}:
        return "Working"
    return "Working"
